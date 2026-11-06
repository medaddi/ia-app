"""
The shared SMC engine: one engine for every pair, only the config and the data differ (app/smc/configs/<PAIR>.json,
the same as the research configs smc/pairs/<PAIR>/config.json).
Taken from the app's SMC engine (git c262bdc, backend/app/analysis/smc_setups.py) and made configurable.

Every rule is causal: a candle only knows the candles before it, a swing exists only from the candle that confirms it,
and a setup is dated at the close of the last candle it needs (tests/test_engine.py shifts future data to prove it).

  primitives   valid-pullback swings · body-close BOS / CHoCH · wick SWEEP · 3-candle FVG · H1 OB with FVG + IDM
  strategies   S1 HTF trend continuation (internal id A) · S2 PDH / PDL sweep reversal (B) · S3 Asian range sweep +
               killzone, Power of 3 (D) · S4 single-candle OB + wick mitigation (E)
  gate         the 7-question master checklist (every question must pass)

See smc/DEFINITIONS.md for each term's operational definition and smc/RULEBOOK.md for the BUY and SELL rules.
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
# Sessions in UTC hours [start, end): the script's values; each pair's config may change them (smc/pairs/<PAIR>/config.json)
SESSIONS = {"asia": (0, 6), "london": (7, 10), "newyork": (12, 15), "trade": (7, 16)}
NEWS_MIN = 15  # minutes around a high-impact release with no entry (checklist question 6)
NEWS: list[int] = []  # release times (unix s) from smc/news/high_impact.csv, empty = not tested
MIN_ASIA_ATR = 0.0  # S3: the Asian range must be at least this many H1 ATR(14) (0 = no filter)


def configure(cfg: dict, news: list[int]) -> None:
    """Applies a pair's config: sessions, news window, minimum Asian range."""
    global NEWS_MIN, MIN_ASIA_ATR
    for k, v in (cfg.get("sessions_utc") or {}).items():
        SESSIONS[k] = tuple(v)
    NEWS_MIN = cfg.get("news_window_min", NEWS_MIN)
    MIN_ASIA_ATR = cfg.get("s3_min_asia_range_atr", 0.0)
    NEWS[:] = sorted(news)


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

    def atr(self, i: int, n: int = 14) -> Optional[float]:
        """ATR(n) of the H1 candles closed up to i (true range, simple mean)."""
        if i < n:
            return None
        c = self.c
        trs = [max(c[k].high, c[k - 1].close) - min(c[k].low, c[k - 1].close) for k in range(i - n + 1, i + 1)]
        return sum(trs) / n

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
        a0, a1 = SESSIONS["asia"]
        asia = [i for i in idx if a0 * H1S <= (m5[i].time % DAY) < a1 * H1S]
        if len(asia) < 0.8 * (a1 - a0) * 12:  # at least 80 % of the Asian M5 candles
            continue
        ah, al = max(m5[i].high for i in asia), min(m5[i].low for i in asia)
        if MIN_ASIA_ATR > 0:
            hv0 = h1v.closed_at(m5[asia[-1]].time + M5S)
            atr = h1v.atr(hv0)
            if not atr or ah - al < MIN_ASIA_ATR * atr:
                continue  # the Asian range is too narrow to trade after the spread
        taken = {1: False, -1: False}
        for i in idx:
            tod = m5[i].time % DAY
            lo_, ln_ = SESSIONS["london"], SESSIONS["newyork"]
            zone = "London" if lo_[0] * H1S <= tod < lo_[1] * H1S else "New York" if ln_[0] * H1S <= tod < ln_[1] * H1S else None
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
    """The 7 questions (news only when a calendar is loaded: smc/news/high_impact.csv)."""
    d, t, entry = s["dir"], s["time"], s["entry"]
    hv = h1v.closed_at(t)
    tr = h1v.st.trend[hv] if hv >= 0 else 0
    rng = h1v.range_mid(hv)
    swept = [a for a, ok, _ in s["steps"] if ok and ("sweep" in a.lower() or "swept" in a.lower())]
    tod, wd = t % DAY, weekday(t)
    t0, t1 = SESSIONS["trade"]
    hours_ok = t0 * H1S <= tod < t1 * H1S and not (wd == 4 and tod >= 15 * H1S) and not (wd == 0 and tod < 7 * H1S)
    import bisect
    k = bisect.bisect_left(NEWS, t - NEWS_MIN * 60)
    news_hit = k < len(NEWS) and NEWS[k] <= t + NEWS_MIN * 60
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
        ("6 · London / New York hours, no Friday evening or Monday morning, no high-impact news within the window",
         hours_ok and not news_hit, f"{_hm(t)} UTC" + (" · news" if news_hit else "" if NEWS else " · news not tested (no calendar)")),
        (f"7 · Reward ≥ {CHECK_RR:g}R", s["rr"] >= CHECK_RR, f"1:{s['rr']:.2f}"),
    ]


def _hm(t: int) -> str:
    return f"{(t % DAY) // 3600:02d}:{(t % 3600) // 60:02d}"


STRATEGY_OF = {"S1": "A", "S2": "B", "S3": "D", "S4": "E"}
STRATEGY_NAMES = {"S1": "HTF trend continuation", "S2": "PDH / PDL & external liquidity sweep reversal",
                  "S3": "Asian range sweep + killzone (Power of 3 / Judas swing)", "S4": "Single-candle OB & wick mitigation"}


def scan_all(m5, h1, cost: float, decimals: int) -> dict:
    """S1–S4 on the candles: each setup (with its simulated result and its checklist) and what was forming."""
    fmt = lambda v: f"{v:.{decimals}f}"  # noqa: E731
    st5, fv5, h1v = Structure(m5), fvgs(m5), H1View(h1)
    run = {"S1": lambda: strategy_ac("A", m5, st5, fv5, h1v, cost, fmt), "S2": lambda: strategy_b(m5, st5, fv5, cost, fmt),
           "S3": lambda: strategy_d(m5, st5, fv5, h1v, cost, fmt), "S4": lambda: strategy_e(m5, fv5, h1v, cost, fmt)}
    out = {}
    for sid, fn in run.items():
        s, w = fn()
        s.sort(key=lambda x: x["time"])
        for x in s:
            x["sid"] = sid
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


