"""
The "SMC" button: a mechanical Smart Money Concepts read (no discretion, no lookahead) that looks for a CONFIRMED setup:
every rule of a strategy met on closed candles, the order still valid now.

Rules (each one coded exactly, causal: a candle only knows the candles before it)
  swings     the valid pullback: the leg's extreme ("mother") candle becomes a swing only when a later candle trades
             beyond its opposite end (an inside bar is a pause, not a pullback)
  BOS        a candle BODY close beyond the last confirmed swing, with the trend; CHoCH the same against the trend
  sweep      a WICK beyond a swing (or a session / previous-day level) that closes back inside: liquidity taken; the
             level moves to the wick tip and only a body close beyond that tip breaks structure
  FVG        3 candles: candle 1's high below candle 3's low (bullish, candle 2 bullish), or the mirror
  OB         the last opposite candle before the impulse that broke structure, with an FVG after it, fresh (untouched),
             and inducement (IDM: the first internal pullback after the break) swept before price comes back to it
  premium / discount   above / below 50 % of the dealing range (swing low → swing high)

Strategies (HTF H1, LTF M5)
  A  trend continuation      H1 break → IDM swept → price in discount taps the fresh H1 OB → M5 sweep + CHoCH + FVG
                             → limit at the M5 FVG, SL beyond the M5 low, TP the H1 external high (≥ 2R)
  B  external sweep reversal a wick through the previous day's high / low that closes back → M5 CHoCH + FVG in premium
                             (discount) → limit at the FVG, SL beyond the sweep, TP the previous day's equilibrium (≥ 1.5R)
  C  supply → demand flip    an H1 supply OB tapped, then broken by a body close with an FVG → the push's origin is demand
                             → M5 inducement swept → limit at the zone, SL below it, TP the push high (≥ 2R)
  D  session sweep           the Asian range (00–06 UTC) swept in the London (07–10) or New York (12–15) killzone into
                             premium (discount) of the H1 range → M5 CHoCH + FVG → limit at the FVG, TP the other side
                             of the Asian range (≥ 1.5R)
  E  single candle OB        one H1 candle sweeps an H1 swing with its wick and closes with a strong body the other way
                             (a whole LTF CHoCH in one candle) → limit at its 50 % where an M5 FVG sits, SL beyond the
                             wick, TP the H1 liquidity on the other side (≥ 1.5R)

The master checklist (the 7 questions; one "no" and there is no trade), checked on every setup:
  1 H1 bias by a body-close break in the trade's direction   2 IDM or external liquidity swept
  3 entry in discount (buys) / premium (sells) of the H1 range   4 a fresh FVG / OB at the entry
  5 LTF change of character with displacement   6 London / New York hours (07–16 UTC, not Friday evening or Monday
  morning), no high-impact news within 15 minutes   7 reward ≥ 3R
A setup is CONFIRMED only when its strategy's rules AND the 7 questions pass.

Every order: a limit valid 1 hour (4 for C), the stop first when both levels sit in one candle, closed at market after
4 hours. No partials and no break-even in the test (the rules' management is left to the trader).
"""

from typing import Optional

H1S, M5S, DAY = 3600, 300, 86400
EXPIRY = {"A": 12, "B": 12, "C": 48, "D": 12, "E": 12}  # M5 candles a limit stays valid
HOLD = 48  # M5 candles: closed at market after 4 hours
MIN_RR = {"A": 2.0, "B": 1.5, "C": 2.0, "D": 1.5, "E": 1.5}  # to be a candidate; the checklist asks 3R
NAMES = {"A": "Trend continuation (H1 OB + IDM + M5 CHoCH)", "B": "External liquidity sweep reversal (PDH / PDL)",
         "C": "Supply → demand flip (S2D / D2S)", "D": "Session sweep (Asian range + London / NY killzone)",
         "E": "Single candle OB (H1 wick sweep, M5 entry at its 50 %)"}
CHECK_RR = 3.0
# The approximate range: price does not have to reach the exact level. The limit sits at the near edge of an entry zone
# of ± TOL["entry"] × the stop distance (at least the spread) around the ideal entry, and a zone (OB / flip) counts as
# tapped when price comes within TOL["zone"] × its height.
TOL = {"entry": 0.10, "zone": 0.10}


# ---------------------------------------------------------------- primitives
def swings(c, w: int = 2):
    n = len(c)
    sh: list[Optional[float]] = [None] * n
    sl: list[Optional[float]] = [None] * n
    for i in range(w, n - w):
        h, lo = c[i].high, c[i].low
        if all(c[i - k].high < h and c[i + k].high < h for k in range(1, w + 1)):
            sh[i] = h
        if all(c[i - k].low > lo and c[i + k].low > lo for k in range(1, w + 1)):
            sl[i] = lo
    return sh, sl


def pullback_swings(c):
    """The valid-pullback rule: in an up leg the candle with the highest high is the "mother" candle; the high becomes a
    swing high only when a later candle trades below that mother candle's LOW (wick or body). An inside bar (inside the
    mother candle) is only a pause, never a pullback. The mirror for a down leg. Returns the swings and, for each candle,
    the swings it confirms."""
    n = len(c)
    sh: list[Optional[float]] = [None] * n
    sl: list[Optional[float]] = [None] * n
    at: dict[int, list[tuple[str, int]]] = {}
    if n < 2:
        return sh, sl, at
    d, m = (1 if c[1].close >= c[0].close else -1), 0
    for i in range(1, n):
        x = c[i]
        if d > 0:
            if x.high > c[m].high:
                m = i
            elif x.low < c[m].low:
                sh[m] = c[m].high
                at.setdefault(i, []).append(("H", m))
                d, m = -1, min(range(m, i + 1), key=lambda k: c[k].low)
        else:
            if x.low < c[m].low:
                m = i
            elif x.high > c[m].high:
                sl[m] = c[m].low
                at.setdefault(i, []).append(("L", m))
                d, m = 1, max(range(m, i + 1), key=lambda k: c[k].high)
    return sh, sl, at


class Structure:
    """The structure walk: swings confirmed by a valid pullback (or a 5-candle fractal), BOS / CHoCH on a body close,
    wick sweeps. After a sweep the level moves to the new wick tip: only a body close beyond THAT breaks structure."""

    def __init__(self, c, w: int = 2, mode: str = "pullback"):
        self.c = c
        n = len(c)
        if mode == "pullback":
            self.sh, self.sl, at = pullback_swings(c)
        else:
            self.sh, self.sl = swings(c, w)
            at = {}
            for j in range(n):
                if self.sh[j] is not None:
                    at.setdefault(j + w, []).append(("H", j))
                if self.sl[j] is not None:
                    at.setdefault(j + w, []).append(("L", j))
        self.ev: list[list[tuple]] = [[] for _ in range(n)]  # (kind, dir, level, swing index)
        self.trend = [0] * n
        self.last_sh: list[Optional[tuple]] = [None] * n  # most recent confirmed swing high (level, index), kept after a break
        self.last_sl: list[Optional[tuple]] = [None] * n
        self.swing_lows_after: list[int] = []  # indices of confirmed swing lows, in order of confirmation
        self.swing_highs_after: list[int] = []
        self.confirmed_at: dict[int, int] = {}  # swing index → the candle that confirmed it
        trend, lh, ll, ksh, ksl = 0, None, None, None, None
        for i in range(n):
            for kind, j in at.get(i, ()):
                self.confirmed_at[j] = i
                if kind == "H":
                    lh = ksh = (self.sh[j], j)
                    self.swing_highs_after.append(j)
                else:
                    ll = ksl = (self.sl[j], j)
                    self.swing_lows_after.append(j)
            x = c[i]
            if lh:
                if x.close > lh[0]:
                    self.ev[i].append(("BOS" if trend == 1 else "CHOCH", 1, lh[0], lh[1]))
                    trend, lh = 1, None
                elif x.high > lh[0]:
                    self.ev[i].append(("SWEEP", 1, lh[0], lh[1]))
                    lh = (x.high, lh[1])  # the line moves to the new wick tip
            if ll:
                if x.close < ll[0]:
                    self.ev[i].append(("BOS" if trend == -1 else "CHOCH", -1, ll[0], ll[1]))
                    trend, ll = -1, None
                elif x.low < ll[0]:
                    self.ev[i].append(("SWEEP", -1, ll[0], ll[1]))
                    ll = (x.low, ll[1])
            self.trend[i], self.last_sh[i], self.last_sl[i] = trend, ksh, ksl

    def breaks(self, i: int, d: int) -> Optional[tuple]:
        return next((e for e in self.ev[i] if e[0] in ("BOS", "CHOCH") and e[1] == d), None)

    def swept(self, i: int, d: int) -> bool:
        """A wick took a swing on the `d` side (+1 highs / −1 lows) and closed back."""
        return any(e[0] == "SWEEP" and e[1] == d for e in self.ev[i])


def fvgs(c) -> list[Optional[tuple]]:
    """(dir, bottom, top) of the FVG whose 3rd candle is i."""
    out: list[Optional[tuple]] = [None] * len(c)
    for i in range(2, len(c)):
        a, m, b = c[i - 2], c[i - 1], c[i]
        if b.low > a.high and m.close > m.open:
            out[i] = (1, a.high, b.low)
        elif b.high < a.low and m.close < m.open:
            out[i] = (-1, b.high, a.low)
    return out


def ltf_confirm(st: Structure, fv, s: int, d: int, window: int) -> Optional[tuple[int, tuple]]:
    """After a sweep at s: a structure break in direction d within `window` candles, with an FVG of the same direction
    formed in that displacement. Returns (the candle it is all known at, the FVG)."""
    n = len(st.c)
    for k in range(s + 1, min(n, s + 1 + window)):
        if st.breaks(k, d):
            for j in range(min(n - 1, k + 2), s, -1):
                if fv[j] and fv[j][0] == d:
                    return max(k, j), fv[j]
            return None
        # the sweep is undone when price closes beyond its extreme
        ext = max(x.high for x in st.c[s:k + 1]) if d < 0 else min(x.low for x in st.c[s:k + 1])
        if (d < 0 and st.c[k].close > ext) or (d > 0 and st.c[k].close < ext):
            return None
    return None


def simulate(c, k0: int, d: int, entry: float, sl: float, tp: float, expiry: int, cost: float) -> dict:
    """A limit placed at the close of k0: PENDING → FILLED → WIN / LOSS / TIME, or EXPIRED / MISSED (TP first)."""
    n = len(c)
    fill = None
    end = min(n, k0 + 1 + expiry)
    for i in range(k0 + 1, end):
        x = c[i]
        if (d > 0 and x.low <= entry) or (d < 0 and x.high >= entry):
            fill = i
            break
        if (d > 0 and x.high >= tp) or (d < 0 and x.low <= tp):
            return {"state": "MISSED", "at": i}
    if fill is None:
        return {"state": "PENDING" if end == n and n - 1 - k0 < expiry else "EXPIRED"}
    risk = abs(entry - sl)
    stop_end = min(n, fill + HOLD)
    for j in range(fill, stop_end):
        x = c[j]
        if (d > 0 and x.low <= sl) or (d < 0 and x.high >= sl):  # the stop first, from the fill candle on
            return {"state": "LOSS", "fill": fill, "at": j, "r": -1.0 - cost / risk}
        if j > fill and ((d > 0 and x.high >= tp) or (d < 0 and x.low <= tp)):
            return {"state": "WIN", "fill": fill, "at": j, "r": abs(tp - entry) / risk - cost / risk}
    if stop_end == n and n - fill < HOLD:
        return {"state": "ACTIVE", "fill": fill, "rNow": (c[-1].close - entry) / risk * d}
    return {"state": "TIME", "fill": fill, "at": stop_end - 1, "r": (c[stop_end - 1].close - entry) / risk * d - cost / risk}


# ---------------------------------------------------------------- the H1 context seen from an M5 candle
class H1View:
    def __init__(self, h1):
        self.c = h1
        self.st = Structure(h1)
        self.fv = fvgs(h1)
        self.times = [x.time for x in h1]

    def closed_at(self, t_close: int) -> int:
        """Index of the last H1 candle closed at time t_close (−1 if none)."""
        lo, hi = 0, len(self.times)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.times[mid] + H1S <= t_close:
                lo = mid + 1
            else:
                hi = mid
        return lo - 1

    def range_mid(self, i: int) -> Optional[tuple[float, float, float]]:
        """The dealing range of the last confirmed H1 swing high and low: (low, mid, high)."""
        if i < 0 or not self.st.last_sh[i] or not self.st.last_sl[i]:
            return None
        hi, lo = self.st.last_sh[i][0], self.st.last_sl[i][0]
        if hi <= lo:
            return None
        return lo, (hi + lo) / 2, hi


def _ob_before(c, lo_i: int, hi_i: int, d: int) -> Optional[int]:
    """The last opposite candle before the impulse: bearish for a bullish leg (d = +1), from the leg's origin back."""
    for k in range(hi_i, max(lo_i, hi_i - 6) - 1, -1):
        x = c[k]
        if (d > 0 and x.close < x.open) or (d < 0 and x.close > x.open):
            return k
    return None


# ---------------------------------------------------------------- the four strategies
def _setup(sid, d, k0, m5, ideal, sl, tp, steps, cost, extra=None) -> Optional[dict]:
    if abs(ideal - sl) <= 0:
        return None
    tol = max(cost, TOL["entry"] * abs(ideal - sl))
    entry = ideal + d * tol  # the near edge of the entry zone: filled when price comes close, not only at the exact level
    risk = abs(entry - sl)
    if risk <= 0 or (d > 0 and not (sl < entry < tp)) or (d < 0 and not (tp < entry < sl)):
        return None
    rr = abs(tp - entry) / risk
    if rr < MIN_RR[sid]:
        return None
    out = {"strategy": sid, "dir": d, "index": k0, "time": m5[k0].time + M5S, "entry": entry, "ideal": ideal,
           "zone": (ideal - tol, ideal + tol), "sl": sl, "tp": tp, "rr": rr, "steps": steps, **(extra or {})}
    out["result"] = simulate(m5, k0, d, entry, sl, tp, EXPIRY[sid], cost)
    return out


def strategy_d(m5, st5, fv5, h1v: H1View, cost: float, fmt) -> tuple[list, list]:
    setups, watch = [], []
    days: dict[int, list[int]] = {}
    for i, x in enumerate(m5):
        days.setdefault(x.time // DAY, []).append(i)
    for day, idx in days.items():
        asia = [i for i in idx if (m5[i].time % DAY) < 6 * H1S]
        if len(asia) < 48:
            continue
        ah, al = max(m5[i].high for i in asia), min(m5[i].low for i in asia)
        taken = {1: False, -1: False}
        for i in idx:
            tod = m5[i].time % DAY
            zone = "London" if 7 * H1S <= tod < 10 * H1S else "New York" if 12 * H1S <= tod < 15 * H1S else None
            if not zone:
                continue
            for side, level in ((1, ah), (-1, al)):
                x = m5[i]
                if taken[side] or not ((side > 0 and x.high > level) or (side < 0 and x.low < level)):
                    continue
                taken[side] = True
                d = -side  # a sweep of the Asian high sells, of the low buys
                hv = h1v.closed_at(x.time + M5S)
                rng = h1v.range_mid(hv)
                ext = x.high if side > 0 else x.low
                poi = bool(rng and ((d < 0 and ext > rng[1]) or (d > 0 and ext < rng[1])))
                steps = [("Asian range marked (00:00–06:00 UTC)", True, f"high {fmt(ah)} · low {fmt(al)}"),
                         (f"{zone} killzone sweep of the Asian {'high' if side > 0 else 'low'}", True, f"wick to {fmt(ext)} at {_hm(x.time)} UTC"),
                         ("Into an HTF POI: H1 " + ("premium" if d < 0 else "discount"), poi,
                          f"H1 range {fmt(rng[0])} – {fmt(rng[2])}, 50 % at {fmt(rng[1])}" if rng else "no H1 range yet")]
                if not poi:
                    watch.append({"time": x.time, "steps": steps + [("M5 CHoCH + FVG", False, "—")], "dir": d})
                    continue
                conf = ltf_confirm(st5, fv5, i, d, 12)
                if not conf:
                    watch.append({"time": x.time, "steps": steps + [("M5 CHoCH + FVG within 1 hour", False, "waiting for the M5 break with a gap"
                                                                     if len(m5) - 1 - i < 12 else "no break with a gap: no trade")], "dir": d})
                    continue
                k0, g = conf
                entry = g[2] if d > 0 else g[1]  # the gap's near edge
                swing = (min(m5[j].low for j in range(i, k0 + 1)) if d > 0 else max(m5[j].high for j in range(i, k0 + 1)))
                sl = swing - cost if d > 0 else swing + cost
                tp = ah if d > 0 else al
                s = _setup("D", d, k0, m5, entry, sl, tp, steps + [("M5 CHoCH with an FVG", True, f"gap {fmt(g[1])} – {fmt(g[2])}")], cost,
                           {"geo": {"box": (ah, al, m5[asia[0]].time, m5[asia[-1]].time + M5S), "sweep": (level, x.time), "gap": (g[1], g[2], m5[i].time)}})
                if s:
                    setups.append(s)
                else:
                    watch.append({"time": x.time, "steps": steps + [("M5 CHoCH with an FVG", True, f"gap {fmt(g[1])} – {fmt(g[2])}"),
                                                                    (f"Reward ≥ {MIN_RR['D']}R to the other side", False, "too close: no trade")], "dir": d})
    return setups, watch


def strategy_b(m5, st5, fv5, cost: float, fmt) -> tuple[list, list]:
    setups, watch = [], []
    days: dict[int, list[int]] = {}
    for i, x in enumerate(m5):
        days.setdefault(x.time // DAY, []).append(i)
    keys = sorted(days)
    for a, b in zip(keys, keys[1:]):
        prev, idx = days[a], days[b]
        pdh, pdl = max(m5[i].high for i in prev), min(m5[i].low for i in prev)
        eq = (pdh + pdl) / 2
        taken = {1: False, -1: False}
        for i in idx:
            tod = m5[i].time % DAY
            if not (6 * H1S <= tod < 20 * H1S):
                continue
            x = m5[i]
            for side, level in ((1, pdh), (-1, pdl)):
                if taken[side] or not ((side > 0 and x.high > level) or (side < 0 and x.low < level)):
                    continue
                taken[side] = True
                d = -side
                steps = [("Previous day high / low marked", True, f"PDH {fmt(pdh)} · PDL {fmt(pdl)} · EQ {fmt(eq)}"),
                         (f"Wick sweep of the {'PDH' if side > 0 else 'PDL'}", True, f"to {fmt(x.high if side > 0 else x.low)} at {_hm(x.time)} UTC")]
                conf = ltf_confirm(st5, fv5, i, d, 12)
                if not conf:
                    watch.append({"time": x.time, "dir": d, "steps": steps + [("M5 CHoCH + FVG within 1 hour", False, "waiting for the M5 break with a gap"
                                                                                if len(m5) - 1 - i < 12 else "no break with a gap: no trade")]})
                    continue
                k0, g = conf
                entry = g[2] if d > 0 else g[1]
                inzone = (d < 0 and entry > eq) or (d > 0 and entry < eq)
                swing = (min(m5[j].low for j in range(i, k0 + 1)) if d > 0 else max(m5[j].high for j in range(i, k0 + 1)))
                sl = swing - cost if d > 0 else swing + cost
                steps2 = steps + [("M5 CHoCH with an FVG", True, f"gap {fmt(g[1])} – {fmt(g[2])}"),
                                  ("Entry in " + ("premium" if d < 0 else "discount") + " of the previous day", inzone, f"entry {fmt(entry)} vs EQ {fmt(eq)}")]
                s = _setup("B", d, k0, m5, entry, sl, eq, steps2, cost,
                           {"geo": {"pd": (pdh, pdl, m5[prev[0]].time), "sweep": (level, x.time), "gap": (g[1], g[2], m5[i].time)}}) if inzone else None
                if s:
                    setups.append(s)
                else:
                    watch.append({"time": x.time, "dir": d, "steps": steps2 + ([(f"Reward ≥ {MIN_RR['B']}R to the EQ", False, "too close: no trade")] if inzone else [])})
    return setups, watch


def _h1_pois(h1v: H1View, kind: str) -> list[dict]:
    """H1 zones. kind "A": the OB of each break (with FVG after it, IDM in front). kind "C": supply / demand flips."""
    c, st, fv = h1v.c, h1v.st, h1v.fv
    n, out = len(c), []
    for b in range(n):
        for e in st.ev[b]:
            if e[0] not in ("BOS", "CHOCH"):
                continue
            d, swing_i = e[1], e[3]
            # the impulse origin: the extreme between the broken swing and the break
            seg = range(swing_i, b + 1)
            o = min(seg, key=lambda k: c[k].low) if d > 0 else max(seg, key=lambda k: c[k].high)
            ob = _ob_before(c, swing_i, o, d)
            if ob is None:
                continue
            gap = next((fv[k] for k in range(ob + 1, b + 1) if fv[k] and fv[k][0] == d), None)
            if not gap:
                continue  # rule 1: the OB must leave an FVG
            zone = (c[ob].low, c[ob].high)
            if kind == "A":
                # IDM: the first internal swing (a low for a bullish leg) confirmed after the break, in front of the OB
                swl = st.swing_lows_after if d > 0 else st.swing_highs_after
                idm = next((k for k in swl if k > b and (d > 0 and c[k].low > zone[1] or d < 0 and c[k].high < zone[0])), None)
                if idm is None or idm > b + 60:
                    continue
                ext = max(c[k].high for k in range(b, idm + 1)) if d > 0 else min(c[k].low for k in range(b, idm + 1))
                origin = c[o].low if d > 0 else c[o].high
                out.append({"dir": d, "break": b, "kind": e[0], "ob": ob, "zone": zone, "gap": gap, "idm": idm,
                            "idmLevel": c[idm].low if d > 0 else c[idm].high, "ext": ext, "mid": (ext + origin) / 2, "from": st.confirmed_at.get(idm, idm + 2)})  # known at that close
            else:
                # C: this zone is supply (d = −1) / demand (d = +1); look for its tap, a reaction, then a body close through it
                for t1 in range(b + 1, min(n, b + 120)):
                    x = c[t1]
                    if (d < 0 and x.high >= zone[0]) or (d > 0 and x.low <= zone[1]):
                        break
                else:
                    continue
                for t2 in range(t1 + 2, min(n, t1 + 48)):
                    x = c[t2]
                    if (d < 0 and x.close < zone[0] - (zone[1] - zone[0]) * 2) or (d > 0 and x.close > zone[1] + (zone[1] - zone[0]) * 2):
                        break  # the zone held: it was a real reaction, no flip
                    if (d < 0 and x.close > zone[1]) or (d > 0 and x.close < zone[0]):
                        push = range(t1, t2 + 1)
                        r = min(push, key=lambda k: c[k].low) if d < 0 else max(push, key=lambda k: c[k].high)
                        org = _ob_before(c, t1, r, -d)
                        g2 = next((fv[k] for k in range(r + 1, t2 + 1) if fv[k] and fv[k][0] == -d), None)
                        if org is not None and g2:
                            ext = max(c[k].high for k in push) if d < 0 else min(c[k].low for k in push)
                            out.append({"dir": -d, "break": t2, "kind": "FLIP", "ob": org, "zone": (c[org].low, c[org].high), "gap": g2,
                                        "supply": zone, "tap": t1, "ext": ext, "from": t2})
                        break
    return out


def strategy_ac(sid: str, m5, st5, fv5, h1v: H1View, cost: float, fmt) -> tuple[list, list]:
    setups, watch = [], []
    pois = _h1_pois(h1v, sid)
    t5 = [x.time for x in m5]
    import bisect
    for p in pois:
        d, zone, c1 = p["dir"], p["zone"], h1v.c
        t_from = c1[p["from"]].time + H1S if p["from"] < len(c1) else None  # the H1 close that makes the zone known
        if t_from is None or t_from < t5[0] - H1S:
            continue
        i0 = bisect.bisect_left(t5, t_from)
        life = min(len(m5), i0 + 12 * 120)  # 5 days
        if sid == "A":
            steps = [(f"H1 {p['kind']} {'bullish' if d > 0 else 'bearish'}", True, f"broke {fmt(h1v.c[p['break']].close)} on a body close"),
                     ("H1 OB with an FVG after it", True, f"OB {fmt(zone[0])} – {fmt(zone[1])}")]
            # IDM swept, then a tap of the fresh OB in discount (premium)
            swept = tap = None
            for i in range(i0, life):
                x = m5[i]
                if (d > 0 and x.close < zone[0]) or (d < 0 and x.close > zone[1]):
                    break  # the OB failed
                if swept is None:
                    if (d > 0 and x.low < p["idmLevel"]) or (d < 0 and x.high > p["idmLevel"]):
                        swept = i
                    if (d > 0 and x.high > p["ext"]) or (d < 0 and x.low < p["ext"]):
                        break  # the high was taken first: the leg goes on without a pullback
                zt = TOL["zone"] * (zone[1] - zone[0])  # near enough to the OB counts as a tap
                if swept is not None and ((d > 0 and x.low <= zone[1] + zt) or (d < 0 and x.high >= zone[0] - zt)):
                    tap = i
                    break
            disc = ("discount" if d > 0 else "premium")
            st_idm = ("IDM swept (first H1 pullback after the break)", swept is not None, f"IDM {fmt(p['idmLevel'])}")
            if tap is None:
                if swept is not None or life == len(m5):
                    watch.append({"time": m5[min(len(m5) - 1, swept or i0)].time, "dir": d,
                                  "steps": steps + [st_idm, (f"Price taps the fresh OB in {disc}", False, f"OB {fmt(zone[0])} – {fmt(zone[1])} · 50 % {fmt(p['mid'])}")],
                                  "alive": life == len(m5) or (swept is not None and i >= len(m5) - 1)})
                continue
            in_zone = (d > 0 and zone[1] < p["mid"]) or (d < 0 and zone[0] > p["mid"])
            steps2 = steps + [st_idm, (f"Price taps the fresh OB in {disc}", in_zone, f"tap at {_hm(m5[tap].time)} UTC · 50 % {fmt(p['mid'])}")]
            if not in_zone:
                continue
            # M5: a sweep inside the POI, then CHoCH + FVG (within 2 hours of the tap)
            sw = next((i for i in range(tap, min(len(m5), tap + 24)) if st5.swept(i, -d)), None)
            if sw is None:
                watch.append({"time": m5[tap].time, "dir": d, "alive": len(m5) - tap < 24,
                              "steps": steps2 + [("M5 liquidity sweep inside the OB", False, "waiting" if len(m5) - tap < 24 else "none: no trade")]})
                continue
            conf = ltf_confirm(st5, fv5, sw, d, 24)
            st_sw = ("M5 liquidity sweep inside the OB", True, f"at {_hm(m5[sw].time)} UTC")
            if not conf:
                watch.append({"time": m5[sw].time, "dir": d, "alive": len(m5) - sw < 24,
                              "steps": steps2 + [st_sw, ("M5 CHoCH + FVG", False, "waiting" if len(m5) - sw < 24 else "none: no trade")]})
                continue
            k0, g = conf
            entry = g[2] if d > 0 else g[1]
            swing = min(m5[j].low for j in range(tap, k0 + 1)) if d > 0 else max(m5[j].high for j in range(tap, k0 + 1))
            sl = swing - cost if d > 0 else swing + cost
            s = _setup("A", d, k0, m5, entry, sl, p["ext"], steps2 + [st_sw, ("M5 CHoCH with an FVG", True, f"gap {fmt(g[1])} – {fmt(g[2])}")], cost,
                       {"geo": {"ob": (zone[1], zone[0], h1v.c[p["ob"]].time), "sweep": (m5[sw].low if d > 0 else m5[sw].high, m5[sw].time),
                                "gap": (g[1], g[2], m5[tap].time)}})
            if s:
                setups.append(s)
        else:
            steps = [("H1 supply / demand OB tapped", True, f"zone {fmt(p['supply'][0])} – {fmt(p['supply'][1])}"),
                     ("Broken through by a body close, with an FVG", True, f"flip zone {fmt(zone[0])} – {fmt(zone[1])}")]
            # M5 inducement: a swing (low for a buy) formed after the flip and swept while price is still away from the zone
            idm = None
            for i in range(i0, life):
                x = m5[i]
                zt = TOL["zone"] * (zone[1] - zone[0])
                if (d > 0 and x.low <= zone[1] + zt) or (d < 0 and x.high >= zone[0] - zt):
                    break  # reached the zone before any inducement was taken: the zone itself was the inducement
                if (d > 0 and x.high > p["ext"] + (p["ext"] - zone[1])) or (d < 0 and x.low < p["ext"] - (zone[0] - p["ext"])):
                    break  # gone without a pullback
                if st5.swept(i, -d):
                    idm = i
                    break
            if idm is None:
                if life == len(m5):
                    watch.append({"time": h1v.c[p["break"]].time, "dir": d, "alive": True,
                                  "steps": steps + [("M5 inducement swept before the zone", False, "waiting for the pullback")]})
                continue
            entry = zone[1] if d > 0 else zone[0]
            sl = zone[0] - cost if d > 0 else zone[1] + cost
            s = _setup("C", d, idm, m5, entry, sl, p["ext"], steps + [("M5 inducement swept", True, f"at {_hm(m5[idm].time)} UTC")], cost,
                       {"geo": {"ob": (zone[1], zone[0], h1v.c[p["ob"]].time), "sweep": (m5[idm].low if d > 0 else m5[idm].high, m5[idm].time)}})
            if s:
                setups.append(s)
    return setups, watch


def strategy_e(m5, fv5, h1v: H1View, cost: float, fmt) -> tuple[list, list]:
    import bisect
    setups, watch = [], []
    c, st = h1v.c, h1v.st
    t5 = [x.time for x in m5]
    for h in range(1, len(c)):
        x = c[h]
        if x.time < t5[0]:
            continue
        rng = x.high - x.low
        a, b = bisect.bisect_left(t5, x.time), bisect.bisect_left(t5, x.time + H1S)
        if rng <= 0 or b - a < 10 or b >= len(m5) + 1:
            continue
        for side, lv in ((1, st.last_sh[h - 1]), (-1, st.last_sl[h - 1])):
            if not lv:
                continue
            level, d = lv[0], -side
            body = abs(x.close - x.open)
            if side > 0:
                ok = x.high > level and x.close < level and x.close < x.open and x.close < x.low + rng / 2 and body >= 0.5 * rng
            else:
                ok = x.low < level and x.close > level and x.close > x.open and x.close > x.low + rng / 2 and body >= 0.5 * rng
            if not ok:
                continue
            mid = (x.high + x.low) / 2
            steps = [(f"H1 wick sweep of the swing {'high' if side > 0 else 'low'} {fmt(level)}", True, f"wick {fmt(x.high if side > 0 else x.low)}, close {fmt(x.close)}"),
                     ("Strong body close the other way (a whole LTF CHoCH)", True, f"body {body / rng * 100:.0f} % of the candle")]
            g = next((fv5[i] for i in range(b - 1, a - 1, -1) if fv5[i] and fv5[i][0] == d and fv5[i][1] - 0.1 * rng <= mid <= fv5[i][2] + 0.1 * rng), None)
            if not g:
                watch.append({"time": x.time + H1S, "dir": d, "steps": steps + [("M5 FVG at the candle's 50 %", False, "none: no trade")]})
                continue
            tgt = st.last_sl[h] if d < 0 else st.last_sh[h]
            k0 = b - 1
            steps2 = steps + [("M5 FVG at the candle's 50 %", True, f"50 % {fmt(mid)} · gap {fmt(g[1])} – {fmt(g[2])}")]
            if not tgt:
                continue
            sl = x.high + cost if d < 0 else x.low - cost
            sres = _setup("E", d, k0, m5, mid, sl, tgt[0], steps2, cost,
                          {"geo": {"candle": (x.high, x.low, x.time), "sweep": (level, x.time), "gap": (g[1], g[2], x.time)}})
            if sres:
                setups.append(sres)
            else:
                watch.append({"time": x.time + H1S, "dir": d, "steps": steps2 + [(f"Reward ≥ {MIN_RR['E']}R to the H1 liquidity", False, "too close: no trade")]})
    return setups, watch


def weekday(t: int) -> int:
    return (t // DAY + 3) % 7  # Monday 0


def master_checklist(s: dict, h1v: H1View, fmt) -> list[tuple[str, bool, str]]:
    """The 7 questions (news is answered live only: the test has no news history)."""
    d, t, entry = s["dir"], s["time"], s["entry"]
    hv = h1v.closed_at(t)
    tr = h1v.st.trend[hv] if hv >= 0 else 0
    rng = h1v.range_mid(hv)
    swept = [a for a, ok, _ in s["steps"] if ok and ("sweep" in a.lower() or "swept" in a.lower())]
    tod, wd = t % DAY, weekday(t)
    hours_ok = 7 * H1S <= tod < 16 * H1S and not (wd == 4 and tod >= 15 * H1S) and not (wd == 0 and tod < 7 * H1S)
    ltf = {"C": "H1 flip with an FVG (the push through supply / demand)", "E": "one H1 candle = an LTF CHoCH, M5 FVG"}.get(s["strategy"], "M5 CHoCH with an FVG")
    side = "discount" if d > 0 else "premium"
    return [
        ("1 · H1 bias by a body-close break in the trade's direction", tr == d,
         f"H1 structure {'bullish' if tr > 0 else 'bearish' if tr < 0 else 'undefined'}"),
        ("2 · IDM or external liquidity swept", bool(swept), swept[0] if swept else "no sweep"),
        (f"3 · Entry in {side} of the H1 range", bool(rng) and ((d > 0 and entry < rng[1]) or (d < 0 and entry > rng[1])),
         f"entry {fmt(entry)} vs 50 % {fmt(rng[1])}" if rng else "no H1 range"),
        ("4 · Fresh FVG / OB at the entry", True, "the limit sits at an untouched gap / zone"),
        ("5 · LTF change of character with displacement", True, ltf),
        ("6 · London / New York hours, no Friday evening or Monday morning", hours_ok, f"{_hm(t)} UTC"),
        (f"7 · Reward ≥ {CHECK_RR:g}R", s["rr"] >= CHECK_RR, f"1:{s['rr']:.2f}"),
    ]


def _hm(t: int) -> str:
    return f"{(t % DAY) // 3600:02d}:{(t % 3600) // 60:02d}"


def scan_all(m5, h1, cost: float, decimals: int) -> dict:
    """Every strategy on the candles: its setups (with their simulated result) and what is forming now."""
    fmt = lambda v: f"{v:.{decimals}f}"  # noqa: E731
    st5, fv5, h1v = Structure(m5), fvgs(m5), H1View(h1)
    out = {}
    for sid, fn in (("A", lambda: strategy_ac("A", m5, st5, fv5, h1v, cost, fmt)), ("B", lambda: strategy_b(m5, st5, fv5, cost, fmt)),
                    ("C", lambda: strategy_ac("C", m5, st5, fv5, h1v, cost, fmt)), ("D", lambda: strategy_d(m5, st5, fv5, h1v, cost, fmt)),
                    ("E", lambda: strategy_e(m5, fv5, h1v, cost, fmt))):
        s, w = fn()
        s.sort(key=lambda x: x["time"])
        for x in s:
            x["checklist"] = master_checklist(x, h1v, fmt)
            x["pass"] = all(ok for _, ok, _ in x["checklist"])
        out[sid] = {"setups": s, "watch": sorted(w, key=lambda x: x["time"])}
    out["_st5"], out["_h1v"] = st5, h1v
    return out


def stats(setups: list[dict]) -> dict:
    done = [s["result"] for s in setups if "r" in s["result"]]
    rs = [r["r"] for r in done]
    return {"setups": len(setups), "trades": len(rs), "winRate": round(100 * sum(r > 0 for r in rs) / len(rs), 1) if rs else 0,
            "totalR": round(sum(rs), 1), "avgR": round(sum(rs) / len(rs), 2) if rs else 0}


# ---------------------------------------------------------------- the button: what each strategy shows now
def _ago_ok(t: int, last_t: int, hours: float) -> bool:
    return last_t - t <= hours * H1S


def smc_now(m5, h1, cost: float, spec: dict, price: float, lot_fn, news=None) -> dict:
    """Each strategy now: CONFIRMED (every rule met, its limit still valid), RUNNING (filled, open), FORMING (the first
    rules met, waiting for the next), WAITING (what it watches), plus its result on the M5 history the feed gives."""
    dec, pip = spec["decimals"], spec["pipSize"]
    fmt = lambda v: f"{v:.{dec}f}"  # noqa: E731
    res = scan_all(m5, h1, cost, dec)
    h1v = res["_h1v"]
    last_t = m5[-1].time + M5S
    days = round((m5[-1].time - m5[0].time) / DAY)
    gaps = sum(1 for g in fvgs(m5) if g)
    noisy = gaps < len(m5) / 40  # the feed's wicks overlap: gaps (and so SMC entries) almost never form
    # the H1 read
    hi = h1v.closed_at(last_t)
    tr = h1v.st.trend[hi] if hi >= 0 else 0
    lastev = next(((h1v.c[k].time, e) for k in range(hi, max(-1, hi - 300), -1) for e in h1v.st.ev[k] if e[0] in ("BOS", "CHOCH")), None)
    rng = h1v.range_mid(hi)
    where = None
    if rng:
        pos = (price - rng[0]) / (rng[2] - rng[0])
        where = ("above the H1 range (premium)" if pos > 1 else "below the H1 range (discount)" if pos < 0
                 else ("premium" if pos > 0.5 else "discount") + f" ({pos * 100:.0f} % of the H1 range)")
    bsl = h1v.st.last_sh[hi][0] if hi >= 0 and h1v.st.last_sh[hi] else None
    ssl = h1v.st.last_sl[hi][0] if hi >= 0 and h1v.st.last_sl[hi] else None
    day_now = m5[-1].time // DAY
    today = [x for x in m5 if x.time // DAY == day_now]
    before = [x for x in m5 if x.time // DAY < day_now]
    prev = [x for x in before if x.time // DAY == before[-1].time // DAY] if before else []
    asia = [x for x in today if x.time % DAY < 6 * H1S]
    rows = []
    for sid in "ABCDE":
        s_all, w_all = res[sid]["setups"], res[sid]["watch"]
        row = {"id": sid, "name": NAMES[sid], "test": {**stats(s_all), "days": days, "checklist": stats([x for x in s_all if x["pass"]])},
               "status": "WAITING", "steps": [], "checklist": [], "reason": ""}
        live = next((s for s in reversed(s_all) if s["result"]["state"] in ("PENDING", "ACTIVE")), None)
        if live:
            r, d = live["result"], live["dir"]
            chk = list(live["checklist"])
            if news is not None:
                hit = news(live["time"]) or (news(last_t) if r["state"] == "PENDING" else None)
                chk[5] = (chk[5][0], chk[5][1] and not hit, chk[5][2] + (f" · news: {hit}" if hit else " · no high-impact news within 15 min"))
            passed = all(ok for _, ok, _ in chk)
            row["checklist"] = [{"label": a, "ok": b, "detail": c} for a, b, c in chk]
            row["status"] = ("CONFIRMED" if r["state"] == "PENDING" else "RUNNING") if passed else "BLOCKED"
            row["steps"] = [{"label": a, "ok": b, "detail": c} for a, b, c in live["steps"]]
            row["setup"] = {"direction": "BUY" if d > 0 else "SELL", "entryType": "LIMIT", "entry": round(live["entry"], dec), "sl": round(live["sl"], dec),
                            "tp": round(live["tp"], dec), "rr": round(live["rr"], 2), "since": live["time"],
                            "entryZone": [round(live["zone"][0], dec), round(live["zone"][1], dec)], "ideal": round(live["ideal"], dec),
                            "validUntil": live["time"] + EXPIRY[sid] * M5S, "slPips": round(abs(live["entry"] - live["sl"]) / pip, 1),
                            "lots": lot_fn(live["entry"], live["sl"]), "rNow": round(r.get("rNow", 0), 2), "filled": r["state"] == "ACTIVE",
                            "geo": {**live.get("geo", {}), "eq": (lambda rg: rg[1] if rg else None)(h1v.range_mid(h1v.closed_at(live["time"])))}}
            fails = [a.split(" · ", 1)[-1] for a, ok, _ in chk if not ok]
            row["reason"] = (f"Every rule and the 7 questions met at {_hm(live['time'])} UTC: limit {fmt(live['entry'])} valid until {_hm(live['time'] + EXPIRY[sid] * M5S)} UTC"
                             if r["state"] == "PENDING" and passed else
                             f"The strategy's rules are met, but the checklist says no: {'; '.join(fails)}. No trade" if r["state"] == "PENDING" else
                             f"The strategy's limit filled ({r.get('rNow', 0):+.2f}R now), but the checklist said no: {'; '.join(fails)}. Not a trade to follow" if not passed else
                             f"Filled, running: {r.get('rNow', 0):+.2f}R now, closed at market 4 hours after the fill at the latest")
        else:
            w = next((w for w in reversed(w_all) if (w.get("alive") or "waiting" in w["steps"][-1][2]) and _ago_ok(w["time"], last_t, 4)), None)
            if w:
                row["status"] = "FORMING"
                row["steps"] = [{"label": a, "ok": b, "detail": c} for a, b, c in w["steps"]]
                nxt = next((a for a, b, _ in w["steps"] if not b), "")
                row["reason"] = f"{sum(1 for _, b, _ in w['steps'] if b)} of {len(w['steps'])} rules met · next: {nxt}"
            elif sid == "D":
                if last_t % DAY >= 15 * H1S:
                    row["reason"] = "Today's killzones are over (London 07–10, New York 12–15 UTC): the next setup forms from tomorrow's Asian range"
                elif len(asia) >= 48:
                    ah, al = max(x.high for x in asia), min(x.low for x in asia)
                    row["reason"] = (f"Asian range {fmt(al)} – {fmt(ah)}: waiting for the London (07–10 UTC) or New York (12–15 UTC) killzone "
                                     "to sweep the high (then sell) or the low (then buy), into H1 premium / discount")
                else:
                    row["reason"] = "Waiting for today's Asian range (00:00–06:00 UTC) to form"
            elif sid == "B":
                if last_t % DAY >= 20 * H1S:
                    row["reason"] = "Past 20:00 UTC: the next sweep is watched from 06:00 UTC against today's high / low"
                elif prev:
                    pdh, pdl = max(x.high for x in prev), min(x.low for x in prev)
                    row["reason"] = f"Waiting for a wick through the previous day's high {fmt(pdh)} (sell) or low {fmt(pdl)} (buy), then an M5 CHoCH + FVG"
                else:
                    row["reason"] = "Not enough history"
            elif sid == "A":
                row["reason"] = "Waiting for an H1 break with a fresh OB (FVG after it), its inducement swept and price back in the OB in discount / premium"
            elif sid == "C":
                row["reason"] = "Waiting for an H1 supply (demand) zone tapped then broken by a body close with an FVG: the flip"
            else:
                row["reason"] = "Waiting for one H1 candle to sweep an H1 swing with its wick and close strongly the other way"
            last = s_all[-1] if s_all else None
            if last and "r" in last["result"]:
                row["last"] = {"direction": "BUY" if last["dir"] > 0 else "SELL", "at": last["time"], "result": last["result"]["state"],
                               "r": round(last["result"]["r"], 2)}
        rows.append(row)
    order = {"CONFIRMED": 0, "RUNNING": 1, "BLOCKED": 2, "FORMING": 3, "WAITING": 4}
    rows.sort(key=lambda r: (order[r["status"]], r["id"]))
    conf = [r for r in rows if r["status"] == "CONFIRMED"]
    every = [s for sid in "ABCDE" for s in res[sid]["setups"]]
    alltest = {**stats(every), "checklist": stats([s for s in every if s["pass"]])}
    return {
        "read": {"trend": "bullish" if tr > 0 else "bearish" if tr < 0 else "undefined",
                 "lastBreak": ({"kind": lastev[1][0], "dir": "bullish" if lastev[1][1] > 0 else "bearish", "level": round(lastev[1][2], dec), "at": lastev[0] + H1S}
                               if lastev else None),
                 "zone": where, "bsl": round(bsl, dec) if bsl else None, "ssl": round(ssl, dec) if ssl else None},
        "verdict": (f"{len(conf)} confirmed SMC setup(s): every rule met" if conf else
                    "No confirmed SMC setup now" + (": one is forming" if any(r["status"] == "FORMING" for r in rows) else "")),
        "strategies": rows, "test": {**alltest, "days": days}, "triggers": smc_triggers(m5, res, cost, spec, price),
        "dataNote": ("This pair's M5 feed has overlapping wicks: fair value gaps (and so SMC entries) almost never form on it" if noisy else None),
    }


# ---------------------------------------------------------------- what would make each SMC strategy BUY / SELL from here
def smc_triggers(m5, res: dict, cost: float, spec: dict, price: float) -> list[dict]:
    """Each SMC strategy's trigger on each side, from the levels it watches now. The entry / stop are estimates (the
    exact ones come from the M5 candles when the rules confirm): entry at the level, stop 2 M5 ATR beyond it."""
    from ..core.quant_primitives import atr

    pip, dec = spec["pipSize"], spec["decimals"]
    h1v = res["_h1v"]
    a5 = next((v for v in reversed(atr(m5[-400:])) if v), None) or 10 * pip
    hi1 = h1v.closed_at(m5[-1].time + M5S)
    rngs = [h1v.c[k].high - h1v.c[k].low for k in range(max(0, hi1 - 13), hi1 + 1)]
    a1 = (sum(rngs) / len(rngs)) if rngs else 5 * a5
    last_t = m5[-1].time + M5S
    tod = last_t % DAY
    day_now = m5[-1].time // DAY
    today = [x for x in m5 if x.time // DAY == day_now]
    before = [x for x in m5 if x.time // DAY < day_now]
    prev = [x for x in before if x.time // DAY == before[-1].time // DAY] if before else []
    asia = [x for x in today if x.time % DAY < 6 * H1S]
    test = {sid: {"kind": "last ~2 months of M5", **stats(res[sid]["setups"])} for sid in "ABCDE"}
    out = []

    def add(sid, d, trigger, level, entry, sl, tp, blockers, note):
        risk = abs(entry - sl)
        if risk <= 0 or (d > 0 and not (sl < entry < tp)) or (d < 0 and not (tp < entry < sl)):
            return
        out.append({"family": "smc", "id": sid, "name": NAMES[sid], "dir": "BUY" if d > 0 else "SELL", "trigger": trigger,
                    "order": "LIMIT after the M5 CHoCH + FVG", "level": level, "entry": entry, "sl": sl, "tp": tp,
                    "rr": abs(tp - entry) / risk, "distPips": abs(price - level) / pip, "blockers": blockers, "ready": not blockers,
                    "note": note, "maxHours": 4, "test": test[sid]})

    # D: the Asian range swept in a killzone
    if len(asia) >= 48 and tod < 15 * H1S:
        ah, al = max(x.high for x in asia), min(x.low for x in asia)
        kz = 7 * H1S <= tod < 10 * H1S or 12 * H1S <= tod < 15 * H1S
        bl = [] if kz else ["waits for the London (07-10) or New York (12-15 UTC) killzone"]
        add("D", -1, f"sweep of the Asian high {ah:.{dec}f}, then M5 CHoCH + FVG", ah, ah, ah + 2 * a5 + cost, al, bl, "TP: the Asian low")
        add("D", 1, f"sweep of the Asian low {al:.{dec}f}, then M5 CHoCH + FVG", al, al, al - 2 * a5 - cost, ah, bl, "TP: the Asian high")
    # B: the previous day's high / low swept
    if prev and 6 * H1S <= tod < 20 * H1S:
        pdh, pdl = max(x.high for x in prev), min(x.low for x in prev)
        eq = (pdh + pdl) / 2
        add("B", -1, f"wick through the PDH {pdh:.{dec}f}, then M5 CHoCH + FVG", pdh, pdh, pdh + 2 * a5 + cost, eq, [], "TP: the previous day 50 %")
        add("B", 1, f"wick through the PDL {pdl:.{dec}f}, then M5 CHoCH + FVG", pdl, pdl, pdl - 2 * a5 - cost, eq, [], "TP: the previous day 50 %")
    # A: the latest fresh H1 OB of each side, not failed, its external high / low not taken yet
    pois = _h1_pois(h1v, "A")
    for d in (1, -1):
        p = next((p for p in reversed(pois) if p["dir"] == d and p["break"] >= hi1 - 120), None)
        if not p:
            continue
        z = p["zone"]
        seg = h1v.c[p["break"]:hi1 + 1]
        failed = any((d > 0 and x.close < z[0]) or (d < 0 and x.close > z[1]) for x in seg)
        done = (d > 0 and price > p["ext"]) or (d < 0 and price < p["ext"])
        if failed or done:
            continue
        lvl = z[1] if d > 0 else z[0]
        idm_taken = any((d > 0 and x.low < p["idmLevel"]) or (d < 0 and x.high > p["idmLevel"]) for x in h1v.c[p["idm"]:hi1 + 1])
        bl = [] if idm_taken else [f"IDM {p['idmLevel']:.{dec}f} not swept yet"]
        add("A", d, f"price back in the fresh H1 OB {z[0]:.{dec}f} - {z[1]:.{dec}f}, then M5 sweep + CHoCH + FVG", lvl, lvl,
            (z[0] - cost) if d > 0 else (z[1] + cost), p["ext"], bl, "TP: the H1 external " + ("high" if d > 0 else "low"))
    # E: one H1 candle sweeping the last H1 swing and closing back
    sh = h1v.st.last_sh[hi1] if hi1 >= 0 else None
    sw = h1v.st.last_sl[hi1] if hi1 >= 0 else None
    if sh and sw:
        add("E", -1, f"an H1 candle wicks above the swing high {sh[0]:.{dec}f} and closes back below", sh[0], sh[0] - 0.25 * a1, sh[0] + 0.5 * a1 + cost,
            sw[0], [], "entry at that candle 50 % - TP: the H1 swing low")
        add("E", 1, f"an H1 candle wicks below the swing low {sw[0]:.{dec}f} and closes back above", sw[0], sw[0] + 0.25 * a1, sw[0] - 0.5 * a1 - cost,
            sh[0], [], "entry at that candle 50 % - TP: the H1 swing high")
    return out
