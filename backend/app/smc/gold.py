"""
XAU/USD (Gold) — the user's spec "xau_usd_gold_multi_agent_quantitative_strategy_claude_prompt.md" (2026-11-09),
applied to the letter. It replaces everything earlier for gold.

Strategy: "London-NY Fix Liquidity Sweep & ATR Displacement (ICT/Quant)", the 3-phase liquidity-to-expansion cycle:
  Scenario A  H1 trend continuation + London / NY killzone sweep (the primary A+ setup)
  Scenario B  NY open "Judas swing" counter-trend reversal at an HTF liquidity extreme (risk 0.5 %)
  Scenario C  Tier-1 USD news protocol (CPI, NFP, FOMC, the Fed chair): lockout, pending limits pulled, post-news filter
  Scenario D  chop / Asian consolidation / overextended range: NO_TRADE with the wake-up BSL / SSL coordinates

The math (section 3): Wilder ATR 14; 3-bar fractal swings (H_i > H_{i-1}, H_{i-2} and >= H_{i+1}, H_{i+2}); BOS when the close
passes the last swing by 0.10 ATR in the trend, a CHoCH against it; MSS = a close beyond the internal swing right after a
sweep; liquidity pools (Asia 00:00-06:00, London 07:00-11:30, PDH / PDL, EQH / EQL within 0.15 ATR M15); a sweep on M15 =
penetration 0.10-1.25 ATR, a rejection close back inside (or on the next candle), wick dominance >= 0.45; displacement =
body >= 1.35 x the 20-candle average body and body / range >= 0.68; FVG >= 0.25 ATR M15; CE the FVG midpoint; the H1
dealing range, its 50 % equilibrium and the OTE 61.8-78.6 %.

The 7 agents (section 6) run as the DAG of section 1 and return the JSON contract of section 7; the Lead executes only
when the consensus score >= 78, the Risk Manager approves and the Devil gives no hard veto (failure probability >= 65 %).
Where the spec leaves a number open the code says "CHOICE".
"""

from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from typing import Optional

from .playbook import DAY, H1S, H4S, M5S, M15S, Daily, _make, atr, body, ema, fractals, hilo, m5_index_at_close, resample, run, span

STRATEGY_NAME = "London-NY Fix Liquidity Sweep & ATR Displacement (ICT/Quant)"
NAMES = {"A": "Scenario A · H1 trend continuation + killzone sweep", "B": "Scenario B · NY open Judas reversal at HTF liquidity"}
SCEN = {"A": "SCENARIO_A_HTF_CONTINUATION", "B": "SCENARIO_B_NY_JUDAS_REVERSAL"}
BASELINE = {  # the spec's table (section 5): its claims, shown as HYPOTHESIS next to what this app measures
    "A": {"trades": 418, "winRate": 58.4, "avgWin": 2.75, "expectancyR": 1.19, "pf": 2.86, "mdd": -5.4, "sharpe": 2.94},
    "B": {"trades": 164, "winRate": 49.4, "avgWin": 2.90, "expectancyR": 0.93, "pf": 2.38, "mdd": -6.8, "sharpe": 2.12},
}
TIER1 = ("CPI m/m", "CPI y/y", "Core CPI m/m", "Core CPI y/y", "Non-Farm Employment Change", "Federal Funds Rate", "FOMC Statement",
         "FOMC Press Conference", "FOMC Economic Projections", "FOMC Member Powell Speaks", "Fed Chair Powell Speaks",
         "Fed Chairman Warsh Speaks", "Fed Chairman Warsh Testifies")  # "Powell speech": the Fed chair (Warsh from 2026, CHOICE)


def hm(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M")


def tier1(events) -> list[int]:
    return sorted({int(e["time"]) for e in (events or []) if e.get("currency") == "USD" and e.get("title") in TIER1})


def badge(s: str) -> str:
    """The UI badge: at most 55 characters (section 1.4)."""
    return s if len(s) <= 55 else s[:54] + "…"


# ---------------------------------------------------------------- 3.2 the structure state machine
def structure(c, at, hi_f, lo_f) -> dict:
    """Per candle: trend (+1 / -1 / 0), the last structural break (kind, dir), the last confirmed swing high / low
    (price, index). A swing at j is known at j + 2. BOS: close > SH_last + 0.10 ATR while the trend is +1 (CHoCH when it
    is not), the mirror for lows; a broken swing is consumed."""
    n = len(c)
    trend, last_ev = [0] * n, [None] * n
    sh_c, sl_c = [None] * n, [None] * n
    tr, ev, sh, sl, csh, csl = 0, None, None, None, None, None
    for i in range(n):
        j = i - 2
        if j >= 0 and hi_f[j]:
            sh = csh = (c[j].high, j)
        if j >= 0 and lo_f[j]:
            sl = csl = (c[j].low, j)
        a = at[i] or 0
        if sh and c[i].close > sh[0] + 0.10 * a:
            ev = ("BOS" if tr == 1 else "CHOCH", 1)
            tr, sh = 1, None
        elif sl and c[i].close < sl[0] - 0.10 * a:
            ev = ("BOS" if tr == -1 else "CHOCH", -1)
            tr, sl = -1, None
        trend[i], last_ev[i], sh_c[i], sl_c[i] = tr, ev, csh, csl
    return {"trend": trend, "event": last_ev, "sh": sh_c, "sl": sl_c}


def avg_body(c, t: int) -> Optional[float]:
    """(1/20) Σ_{k=2..21} |C_{t-k} - O_{t-k}| (section 3.4)."""
    if t < 21:
        return None
    return sum(body(c[t - k]) for k in range(2, 22)) / 20


class G:
    def __init__(self, m5, h1, daily: Daily):
        self.m5, self.h1, self.daily = m5, h1, daily
        self.t5 = [x.time for x in m5]
        self.m15 = resample(m5, M15S)
        self.t15 = [x.time for x in self.m15]
        self.at5, self.at15, self.at1 = atr(m5, 14), atr(self.m15, 14), atr(h1, 14)
        self.f5, self.f15, self.f1 = fractals(m5), fractals(self.m15), fractals(h1)
        self.h4 = resample(h1, H4S)
        self.t4, self.t1 = [x.time for x in self.h4], [x.time for x in h1]
        self.at4 = atr(self.h4, 14)
        self.s1 = structure(h1, self.at1, *self.f1)
        self.s4 = structure(self.h4, self.at4, *fractals(self.h4))
        self.s15 = structure(self.m15, self.at15, *self.f15)
        self.e50 = ema([x.close for x in h1], 50)
        self.atr15_sma = [None] * len(self.m15)
        for j in range(33, len(self.m15)):
            w = self.at15[j - 19:j + 1]
            if all(w):
                self.atr15_sma[j] = sum(w) / 20
        # M15 volume = the sum of its three M5 volumes (the resampled candles carry no volume)
        self.v15 = [0.0] * len(self.m15)
        for x in m5:
            q = bisect_right(self.t15, x.time) - 1
            if q >= 0:
                self.v15[q] += getattr(x, "volume", 0) or 0
        self.vol15_sma = [None] * len(self.m15)
        for j in range(20, len(self.m15)):
            self.vol15_sma[j] = sum(self.v15[j - 20:j]) / 20
        from .engines import vwap
        self.vw, _ = vwap(m5)

    def i1(self, t: int) -> int:
        return bisect_right(self.t1, t - H1S) - 1

    def i4(self, t: int) -> int:
        return bisect_right(self.t4, t - H4S) - 1

    def j15(self, t: int) -> int:
        return bisect_right(self.t15, t - M15S) - 1

    def dealing(self, t: int) -> Optional[tuple[float, float, float]]:
        """[SL_anchor, SH_anchor] (the last confirmed H1 swings) and E_eq."""
        i = self.i1(t)
        if i < 0 or not self.s1["sh"][i] or not self.s1["sl"][i]:
            return None
        lo, hi = self.s1["sl"][i][0], self.s1["sh"][i][0]
        if hi <= lo:
            return None
        return lo, hi, 0.5 * (hi + lo)

    def levels(self, D: int, t: int) -> dict:
        """The liquidity pools known at time t of UTC day D."""
        m5, t5 = self.m5, self.t5
        asia = hilo(span(m5, t5, D, min(t, D + 6 * H1S)))
        lon = hilo(span(m5, t5, D + 7 * H1S, min(t, D + 11 * H1S + 1800))) if t > D + 7 * H1S else None
        pd = hilo(span(m5, t5, D - DAY, D)) or hilo(span(m5, t5, D - 3 * DAY, D - 2 * DAY + 1))
        return {"asia": asia, "london": lon, "pd": pd}

    def eq_levels(self, t: int, d: int) -> list[float]:
        """EQH (d=-1) / EQL (d=+1): two M15 swing points within 0.15 ATR M15 (the last 48 M15 candles, CHOICE)."""
        j = self.j15(t)
        hi_f, lo_f = self.f15
        pts = [(q, self.m15[q].low if d > 0 else self.m15[q].high) for q in range(max(0, j - 48), j - 1) if (lo_f[q] if d > 0 else hi_f[q])]
        out = []
        tol = 0.15 * (self.at15[j] or 0)
        for a in range(len(pts)):
            for b in range(a + 1, len(pts)):
                if abs(pts[a][1] - pts[b][1]) <= tol:
                    out.append((pts[a][1] + pts[b][1]) / 2)
        return sorted(set(round(v, 2 if v > 100 else 5) for v in out))  # gold to the cent, FX to 5 decimals


def sweep(g: G, j: int, pool: float, d: int) -> Optional[int]:
    """Section 3.3 on M15 candle j (d=+1: a sell-side sweep under `pool`): penetration 0.10-1.25 ATR 14, rejection close
    back inside (on j, or on j+1 for a 2-bar sweep), WDR >= 0.45. Returns the index of the confirming close."""
    m = g.m15
    x, a = m[j], g.at15[j]
    if not a or x.high <= x.low:
        return None
    pen = (pool - x.low) if d > 0 else (x.high - pool)
    if not (0.10 * a <= pen <= 1.25 * a):
        return None
    wdr = ((min(x.open, x.close) - x.low) if d > 0 else (x.high - max(x.open, x.close))) / (x.high - x.low)
    if wdr < 0.45:
        return None
    if (x.close > pool) if d > 0 else (x.close < pool):
        return j
    if j + 1 < len(m) and ((m[j + 1].close > pool) if d > 0 else (m[j + 1].close < pool)):
        return j + 1
    return None


def displacement_fvg(c, t: int, d: int, at15: Optional[float], internal: Optional[float]):
    """Section 3.4 on candles (t-2, t-1, t) of a TF: candle t-1 is the displacement (body >= 1.35 x the 20-candle average,
    body / range >= 0.68, in direction d) and closes beyond the internal swing (the MSS); the FVG between t-2 and t is at
    least 0.25 ATR M15. Returns (bottom, top, CE) or None."""
    if t < 22 or not at15:
        return None
    x = c[t - 1]
    ab = avg_body(c, t)
    rng = x.high - x.low
    if not ab or rng <= 0 or body(x) < 1.35 * ab or body(x) / rng < 0.68 or (x.close - x.open) * d <= 0:
        return None
    if internal is not None and not ((x.close > internal) if d > 0 else (x.close < internal)):
        return None
    if d > 0 and c[t].low > c[t - 2].high and c[t].low - c[t - 2].high >= 0.25 * at15:
        return c[t - 2].high, c[t].low, (c[t].low + c[t - 2].high) / 2
    if d < 0 and c[t].high < c[t - 2].low and c[t - 2].low - c[t].high >= 0.25 * at15:
        return c[t].high, c[t - 2].low, (c[t].high + c[t - 2].low) / 2
    return None


def order_block(c, t: int, d: int) -> Optional[tuple[float, float, int]]:
    """The originating order block: the last opposite candle before the displacement (within 5 candles, CHOICE)."""
    for q in range(t - 2, max(t - 7, 0), -1):
        if (c[q].close < c[q].open) if d > 0 else (c[q].close > c[q].open):
            return c[q].low, c[q].high, q
    return None


def _mss_entry(g: G, k_conf_time: int, d: int, ext: float, until: int):
    """After a sweep confirmed at k_conf_time: the first displacement MSS + FVG + OB, on M15 then M5 (CHOICE: within 4
    M15 / 12 M5 candles). Returns dict(tf, fvg, ob, t_set, k_disp_time) or None."""
    for tf, c, times, step, n_max, fr in (("M15", g.m15, g.t15, M15S, 4, g.f15), ("M5", g.m5, g.t5, M5S, 12, g.f5)):
        k0 = bisect_left(times, k_conf_time)
        hi_f, lo_f = fr
        ext_k = min(range(max(0, k0 - 4), min(k0 + 1, len(c))), key=lambda q: c[q].low if d > 0 else -c[q].high)
        ref = next((q for q in range(ext_k - 1, max(ext_k - 60, 0), -1) if (hi_f[q] if d > 0 else lo_f[q])), None)
        internal = None if ref is None else (c[ref].high if d > 0 else c[ref].low)
        if internal is None:
            continue
        for t in range(max(k0, ref + 4), min(k0 + n_max + 1, len(c))):
            if c[t].time + step > until:
                break
            j15 = g.j15(c[t].time + step)
            f = displacement_fvg(c, t, d, g.at15[j15] if j15 >= 0 else None, internal)
            if f:
                ob = order_block(c, t, d)
                if ob:
                    return {"tf": tf, "fvg": f, "ob": ob, "t_set": c[t].time + step, "t_disp": c[t - 1].time, "mss": internal}
    return None


def _tp1(g: G, t: int, d: int, entry: float, risk: float) -> tuple[float, str]:
    """TP1: the internal opposing liquidity (the nearest confirmed M15 swing beyond the entry) if at least 1.8 R, else 1.8 R."""
    j = g.j15(t)
    hi_f, lo_f = g.f15
    cand = [g.m15[q].high if d > 0 else g.m15[q].low for q in range(max(0, j - 60), j - 1) if (hi_f[q] if d > 0 else lo_f[q])]
    cand = sorted([p for p in cand if (p - entry) * d >= 1.8 * risk], key=lambda p: abs(p - entry))
    return (cand[0], "internal opposing liquidity") if cand else (entry + d * 1.8 * risk, "1.8 R")


def _ny_bars(g: G, t: int) -> int:
    return t


# ---------------------------------------------------------------- the scenarios
def scenario_a(g: G, cost: float, out: list, watch: list) -> None:
    """Scenario A. H4 and H1 aligned: the H1 close beyond EMA 50, the last H1 structural break a BOS that way, H4 the same
    trend. London 07:00-09:30 or NY 12:30-15:00 UTC: an M15 sweep (3.3) of L_Asia or an internal M15 EQL whose low sits in
    the H1 discount (<= E_eq); then the displacement MSS + FVG + OB on M15 or M5. Entry: a limit at the CE when it lies in
    the OTE, else the FVG's proximal edge; longs only at or under E_eq. SL = the sweep low - 0.35 ATR M15. TP1 the internal
    opposing liquidity / 1.8 R (half, SL to breakeven + 0.1 R); TP2 the nearest external pool (H_Asia, H_London, PDH) at
    RR >= 3.0. Risk 1 % (0.5 % when ATR M15 > 1.5 x its 20-candle mean). The limit lives until the window ends (CHOICE),
    the trade is closed at 20:00 UTC (CHOICE). The mirror for shorts."""
    m15 = g.m15
    for D in sorted({x.time - x.time % DAY for x in g.m5 if datetime.fromtimestamp(x.time, timezone.utc).weekday() < 5}):
        for w0, w1, kz in ((D + 7 * H1S, D + 9 * H1S + 1800, "London"), (D + 12 * H1S + 1800, D + 15 * H1S, "NY")):
            i1, i4 = g.i1(w0), g.i4(w0)
            if i1 < 50 or i4 < 5 or g.e50[i1] is None:
                continue
            ev = g.s1["event"][i1]
            for d in (1, -1):
                aligned = g.s4["trend"][i4] == d and ev == ("BOS", d) and (g.h1[i1].close - g.e50[i1]) * d > 0
                if not aligned:
                    continue
                dr = g.dealing(w0)
                if not dr:
                    continue
                j0, j1 = g.j15(w0) + 1, g.j15(w1) + 1
                for j in range(max(j0, 2), min(j1, len(m15))):
                    t = m15[j].time
                    lv = g.levels(D, t)
                    pools = ([("Asia low", lv["asia"][1])] if d > 0 and lv["asia"] else [("Asia high", lv["asia"][0])] if lv["asia"] else []) + \
                            [("M15 EQ" + ("L" if d > 0 else "H"), v) for v in g.eq_levels(t, d)]
                    hit = next(((n, p, k) for n, p in pools for k in [sweep(g, j, p, d)] if k is not None), None)
                    if not hit:
                        continue
                    name, pool, kc = hit
                    ext = m15[j].low if d > 0 else m15[j].high
                    in_zone = (ext <= dr[2]) if d > 0 else (ext >= dr[2])
                    steps = [("H4 and H1 aligned (EMA 50, last H1 break a BOS)", True, ""), (f"{kz} killzone", True, ""),
                             (f"M15 sweep of {name} (depth 0.10-1.25 ATR, WDR >= 0.45, close back inside)", True, f"{pool:.2f}"),
                             (f"Sweep in the H1 {'discount' if d > 0 else 'premium'} (E_eq {dr[2]:.2f})", in_zone, f"{ext:.2f}")]
                    if not in_zone:
                        continue
                    e = _mss_entry(g, m15[kc].time + M15S, d, ext, w1)
                    if not e:
                        watch.append({"sid": "A", "time": m15[kc].time + M15S, "dir": d, "steps": steps + [("Displacement MSS + FVG + OB (M15 / M5)", False, "waiting")]})
                        break
                    bot, top, ce = e["fvg"]
                    lo, hi = dr[0], dr[1]
                    ote = (hi - 0.786 * (hi - lo), hi - 0.618 * (hi - lo)) if d > 0 else (lo + 0.618 * (hi - lo), lo + 0.786 * (hi - lo))
                    entry = ce if ote[0] <= ce <= ote[1] else (top if d > 0 else bot)
                    if (entry > dr[2]) if d > 0 else (entry < dr[2]):
                        watch.append({"sid": "A", "time": e["t_set"], "dir": d, "steps": steps + [("Entry in the discount / premium", False, f"{entry:.2f} vs E_eq {dr[2]:.2f}")]})
                        break
                    j_set = g.j15(e["t_set"])
                    a15 = g.at15[j_set] or 0
                    sl = ext - d * 0.35 * a15
                    risk = abs(entry - sl)
                    tp1, tp1n = _tp1(g, e["t_set"], d, entry, risk)
                    lv = g.levels(D, e["t_set"])
                    ext_pools = [("H_Asia" if d > 0 else "L_Asia", (lv["asia"][0] if d > 0 else lv["asia"][1]) if lv["asia"] else None),
                                 ("H_London" if d > 0 else "L_London", (lv["london"][0] if d > 0 else lv["london"][1]) if lv["london"] else None),
                                 ("PDH" if d > 0 else "PDL", (lv["pd"][0] if d > 0 else lv["pd"][1]) if lv["pd"] else None)]
                    good = sorted([(n, p) for n, p in ext_pools if p is not None and (p - entry) * d >= 3.0 * risk], key=lambda t_: abs(t_[1] - entry))
                    steps += [(f"Displacement MSS on {e['tf']} (body >= 1.35 x avg, >= 68 % of range) + FVG >= 0.25 ATR + OB", True, f"{bot:.2f} - {top:.2f}"),
                              ("Entry: CE in the OTE" if entry == ce else "Entry: the FVG's proximal edge", True, f"{entry:.2f}")]
                    if not good:
                        watch.append({"sid": "A", "time": e["t_set"], "dir": d, "steps": steps + [("TP2: an external pool at RR >= 3.0", False, "none")]})
                        break
                    tp2n, tp2 = good[0]
                    hi_atr = g.atr15_sma[j_set] and a15 > 1.5 * g.atr15_sma[j_set]
                    k0 = m5_index_at_close(g.t5, e["t_set"])
                    if k0 is None:
                        break
                    s = _make("XAUUSD", "A", d, g.m5, k0, entry, sl, tp1, tp2, 0.5, False, max(1, (w1 - e["t_set"]) // M5S), D + 20 * H1S,
                              steps, {"levels": _geo_levels(lv), "fvg": (bot, top, e["t_disp"]), "ob": (e["ob"][1], e["ob"][0], g.m15[0].time if False else e["t_disp"]),
                                      "sweep": (ext, m15[j].time), "mss": (e["mss"], e["t_disp"]), "ote": ote, "dealing": dr, "window": (w0, w1)},
                              cost, zone=(bot, top), be_off=0.1 * risk)
                    if s:
                        s.update(riskPct=0.5 if hi_atr else 1.0, tp1Name=tp1n, tp2Name=tp2n, sweepDepthAtr=(abs(pool - ext) / (g.at15[j] or 1)),
                                 scenario="A", entryTf=e["tf"], ote=ote, dealing=dr, fvgCe=ce, sweepTime=m15[j].time)
                        out.append(s)
                    break


def scenario_b(g: G, cost: float, out: list, watch: list) -> None:
    """Scenario B. By 12:30 UTC the day already spans >= 85 % of ADR 14 in one direction (CHOICE: the 12:30 close against
    the 00:00 open gives the direction); between 12:30 and 14:15 UTC an M15 candle sweeps PDH (after an up-move) / PDL with
    RVOL M15 >= 1.8 (its volume over the 20-candle mean); then an M15 engulfing rejection and a CHoCH (an M15 close beyond
    the internal swing); entry on the M5 FVG retest (a limit at its proximal edge), target the session VWAP (anchored at
    00:00 UTC, CHOICE). SL the sweep extreme +/- 0.35 ATR M15; risk 0.5 %; RR >= 2.5 (the Risk Manager)."""
    m15 = g.m15
    for D in sorted({x.time - x.time % DAY for x in g.m5 if datetime.fromtimestamp(x.time, timezone.utc).weekday() < 5}):
        adr = g.daily.adr(D, 14)
        k_open = bisect_left(g.t5, D)
        k_1230 = m5_index_at_close(g.t5, D + 12 * H1S + 1800)
        if not adr or k_open >= len(g.m5) or k_1230 is None or k_1230 <= k_open:
            continue
        day_so_far = hilo(g.m5[k_open:k_1230 + 1])
        if not day_so_far or (day_so_far[0] - day_so_far[1]) < 0.85 * adr:
            continue
        move = 1 if g.m5[k_1230].close > g.m5[k_open].open else -1
        d = -move  # the reversal trade
        lv = g.levels(D, D + 12 * H1S + 1800)
        if not lv["pd"]:
            continue
        pool = lv["pd"][0] if d < 0 else lv["pd"][1]
        j0, j1 = g.j15(D + 12 * H1S + 1800) + 1, g.j15(D + 14 * H1S + 900) + 1
        for j in range(max(j0, 21), min(j1, len(m15) - 1)):
            x = m15[j]
            took = (x.high > pool) if d < 0 else (x.low < pool)
            if not took:
                continue
            rvol = g.v15[j] / g.vol15_sma[j] if g.vol15_sma[j] else 0
            y = m15[j + 1]
            engulf = (y.close < y.open and y.close < x.open and y.open >= x.close) if d < 0 else (y.close > y.open and y.close > x.open and y.open <= x.close)
            hi_f, lo_f = g.f15
            ref = next((q for q in range(j - 1, max(j - 40, 0), -1) if (lo_f[q] if d < 0 else hi_f[q])), None)
            choch = ref is not None and ((y.close < m15[ref].low) if d < 0 else (y.close > m15[ref].high))
            steps = [(f"Day already {100 * (day_so_far[0] - day_so_far[1]) / adr:.0f} % of ADR 14 (>= 85 %)", True, ""),
                     (f"Sweep of {'PDH' if d < 0 else 'PDL'} 12:30-14:15 UTC", True, f"{pool:.2f}"), (f"RVOL M15 {rvol:.1f} (>= 1.8)", rvol >= 1.8, ""),
                     ("M15 engulfing rejection + CHoCH", engulf and choch, "")]
            if not (rvol >= 1.8 and engulf and choch):
                watch.append({"sid": "B", "time": x.time + M15S, "dir": d, "steps": steps})
                break
            ext = max(x.high, y.high) if d < 0 else min(x.low, y.low)
            t_conf = y.time + M15S
            k5 = bisect_left(g.t5, y.time)
            fvg = None
            for t in range(k5, min(k5 + 12, len(g.m5))):
                c = g.m5
                if t < 2:
                    continue
                a15 = g.at15[g.j15(c[t].time + M5S)] or 0
                if d < 0 and c[t].high < c[t - 2].low and c[t - 2].low - c[t].high >= 0.25 * a15:
                    fvg = (c[t].high, c[t - 2].low, t)
                    break
                if d > 0 and c[t].low > c[t - 2].high and c[t].low - c[t - 2].high >= 0.25 * a15:
                    fvg = (c[t - 2].high, c[t].low, t)
                    break
            if not fvg:
                watch.append({"sid": "B", "time": t_conf, "dir": d, "steps": steps + [("M5 FVG for the retest", False, "none")]})
                break
            bot, top, kf = fvg
            entry = bot if d < 0 else top  # the proximal edge (where the retest arrives first)
            k0 = max(kf, m5_index_at_close(g.t5, t_conf) or kf)
            a15 = g.at15[g.j15(g.m5[k0].time + M5S)] or 0
            sl = ext - d * 0.35 * a15
            vw = g.vw[k0]
            risk = abs(entry - sl)
            steps += [("M5 FVG retest (limit at the proximal edge)", True, f"{bot:.2f} - {top:.2f}"), ("Target: the session VWAP", vw is not None, f"{vw:.2f}" if vw else "")]
            if not vw or risk <= 0 or (vw - entry) * d < 2.5 * risk:
                watch.append({"sid": "B", "time": g.m5[k0].time + M5S, "dir": d, "steps": steps + [("Risk Manager: RR >= 2.5 to the VWAP", False, "")]})
                break
            s = _make("XAUUSD", "B", d, g.m5, k0, entry, sl, None, vw, 1.0, False, max(1, (D + 15 * H1S - g.m5[k0].time) // M5S), D + 20 * H1S, steps,
                      {"levels": _geo_levels(lv), "fvg": (bot, top, g.m5[kf - 2].time), "sweep": (ext, x.time), "window": (D + 12 * H1S + 1800, D + 14 * H1S + 900)},
                      cost, zone=(bot, top))
            if s:
                s.update(riskPct=0.5, tp2Name="the session VWAP", scenario="B", rvol=rvol, sweepDepthAtr=abs(ext - pool) / (g.at15[j] or 1), sweepTime=x.time)
                out.append(s)
            break


def _geo_levels(lv: dict) -> dict:
    out = {}
    if lv.get("asia"):
        out.update({"Asia high": lv["asia"][0], "Asia low": lv["asia"][1]})
    if lv.get("london"):
        out.update({"London high": lv["london"][0], "London low": lv["london"][1]})
    if lv.get("pd"):
        out.update({"PDH": lv["pd"][0], "PDL": lv["pd"][1]})
    return out


# ---------------------------------------------------------------- the agents' numbers (section 6)
def devil(g: G, s: dict, news: list[int], macro: Optional[dict]) -> tuple[float, list[str]]:
    """The Devil's Advocate's failure probability (0-100 %) from the section 6 audit (CHOICE: the weights): ADR > 85 % in
    the trade direction +35 · an unmitigated opposing H4 order block between the entry and TP1 +30 · a sweep deeper than
    1.25 ATR +40 · a Tier-1 USD release within 45 min +40 · DXY moving against gold (the last daily change) +15 · US10Y
    against +10. A hard veto at >= 65 %."""
    t, d = s["time"], s["dir"]
    D = t - t % DAY
    worries, p = [], 0.0
    adr = g.daily.adr(D, 14)
    today = hilo(span(g.m5, g.t5, D, t))
    if adr and today:
        open_ = g.m5[bisect_left(g.t5, D)].open
        dir_move = (today[0] - open_) if d > 0 else (open_ - today[1])
        if dir_move >= 0.85 * adr:
            p += 35
            worries.append(f"Gold already {100 * dir_move / adr:.0f}% of ADR this way")
    tp1 = s.get("tp1") or s["tp"]
    i4 = g.i4(t)
    for q in range(max(1, i4 - 30), i4 + 1):  # opposing H4 order blocks: the last candle before an opposite H4 break
        ev = g.s4["event"][q]
        if ev and ev[1] == -d and (g.s4["event"][q - 1] != ev):
            ob = next((g.h4[r] for r in range(q - 1, max(q - 6, 0), -1) if ((g.h4[r].close > g.h4[r].open) if d > 0 else (g.h4[r].close < g.h4[r].open))), None)
            if ob is None:
                continue
            lo, hi = ob.low, ob.high
            between = (s["entry"] < lo < tp1) if d > 0 else (tp1 < hi < s["entry"])
            mitigated = any(((x.high >= lo) if d > 0 else (x.low <= hi)) for x in g.h4[q + 1:i4 + 1])
            if between and not mitigated:
                p += 30
                worries.append(f"H4 {'supply' if d > 0 else 'demand'} at {lo if d > 0 else hi:.2f} caps the move before TP1")
                break
    if (s.get("sweepDepthAtr") or 0) > 1.25:
        p += 40
        worries.append("sweep too deep (> 1.25 ATR): a breakout against us")
    near = [n for n in news if 0 <= n - t <= 45 * 60]
    if near:
        p += 40
        worries.append(f"Tier-1 USD news at {hm(near[0])} UTC (within 45 min)")
    for name, w in (("dxy", 15), ("us10y", 10)):
        v = (macro or {}).get(name)
        if not v:
            continue
        k = bisect_left([a for a, _ in v], D) - 1
        if k >= 1:
            ch = v[k][1] - v[k - 1][1]
            if (ch > 0 and d > 0) or (ch < 0 and d < 0):
                p += w
                worries.append(f"{name.upper()} {'up' if ch > 0 else 'down'} against the gold {'long' if d > 0 else 'short'}")
    return min(p, 100.0), worries


def scores(s: Optional[dict], ctx: dict, bt_ok: bool, devil_p: float) -> dict:
    """The Lead's consensus: Score = 0.25 S_struct + 0.25 S_liq + 0.20 S_entry + 0.15 S_backtest + 0.15 (100 - S_devil).
    CHOICE (the sub-scores): Structure 100 aligned with the zone right (B, counter-trend: 70), 50 aligned only, 0;
    Liquidity 100 a valid sweep in a killzone, 50 a killzone without one, 0; Entry 100 FVG + OB in the OTE, 80 outside it,
    0 none; Backtest 100 when N >= 30 and E[R] >= +0.45R, else 0 (rejected)."""
    if not s:
        st = 50 if ctx.get("aligned") else 0
        lq = 50 if ctx.get("killzone") else 0
        en, bt = 0, 100 if bt_ok else 0
    else:
        st = 70 if s["sid"] == "B" else 100
        lq = 100
        en = 100 if (s.get("ote") and s.get("fvgCe") is not None and s["ote"][0] <= s["entry"] <= s["ote"][1]) or s["sid"] == "B" else 80
        bt = 100 if bt_ok else 0
    total = 0.25 * st + 0.25 * lq + 0.20 * en + 0.15 * bt + 0.15 * (100 - devil_p)
    return {"S_struct": st, "S_liq": lq, "S_entry": en, "S_backtest": bt, "S_devil": devil_p, "score": round(total, 1)}


def backtest_ok(stats: Optional[dict]) -> tuple[bool, str]:
    """Section 5: a setup is REJECTED when its conditional subset has N < 30 or E[R] < +0.45R."""
    if not stats or not stats.get("trades"):
        return False, "no measured trade"
    n, e = stats["trades"], stats.get("expectancyR") or 0
    if n < 30 or e < 0.45:
        return False, f"REJECTED: N={n}, E[R] {e:+.2f}R (needs N >= 30, >= +0.45R)"
    return True, f"N={n}, E[R] {e:+.2f}R"


# ---------------------------------------------------------------- the pipeline (backtest and live)
def scan(m5, h1, cost: float, news_events=None, d1=None, macro: Optional[dict] = None, research: Optional[dict] = None) -> tuple[list, list]:
    """Scenarios A and B, then Scenario C (news) and D (chop) and the 7-agent gates on every setup."""
    daily = Daily(d1 if d1 else resample(h1, DAY))
    g = G(m5, h1, daily)
    out, watch = [], []
    scenario_a(g, cost, out, watch)
    scenario_b(g, cost, out, watch)
    out.sort(key=lambda x: x["time"])
    seen = set()
    out = [x for x in out if not ((x["sid"], x["time"], x["dir"]) in seen or seen.add((x["sid"], x["time"], x["dir"])))]
    nw = tier1(news_events) if news_events is not None else []
    for s in out:
        t = s["time"]
        # Scenario C: lockout 30 min before to 15 min after; pending limits pulled 15 min before (run's news window)
        lock = [n for n in nw if n - 30 * 60 <= t <= n + 15 * 60]
        post = [n for n in nw if n + 15 * 60 < t <= n + 30 * 60]
        post_ok = True
        for n in post:  # the FVG must lie outside the news candle's 50 % equilibrium
            kn = bisect_left(g.t5, n)
            if kn < len(m5):
                mid = (m5[kn].high + m5[kn].low) / 2
                post_ok = post_ok and not (min(s["zone"]) <= mid <= max(s["zone"]))
        if nw and not s["market"]:
            s["result"] = run(m5, s["index"], s["dir"], s["entry"], s["sl"], s["tp1"], s["tp"], s["part"], False, s["expiry"], s["holdUntil"], cost,
                              None, nw, None, s.get("beOff", 0.0), None)
        # Scenario D: ATR M15 compression
        j = g.j15(t)
        comp = bool(g.atr15_sma[j] and g.at15[j] and g.at15[j] < 0.60 * g.atr15_sma[j])
        p, worries = devil(g, s, nw, macro)
        stats = (((research or {}).get("strategies") or {}).get(s["sid"]) or {}).get("all")
        bt, bt_why = backtest_ok(stats)
        sc = scores(s, {}, bt, p)
        rr_ok = s["rr"] >= 2.5
        s["devilP"], s["worries"], s["consensus"] = p, worries, sc
        s["checklist"] = [
            (f"1 · {NAMES[s['sid']]}", True, STRATEGY_NAME),
            ("2 · Scenario C: no Tier-1 USD release from 30 min before to 15 min after", not lock,
             "not checked (no news history)" if news_events is None else ("news at " + ", ".join(hm(n) for n in lock) + " UTC" if lock else "clear")),
            ("2b · Post-news: the FVG outside the news candle's 50 %", post_ok, ""),
            (f"3 · Risk Manager: RR to the primary target >= 2.5 (A: TP2 >= 3.0)", rr_ok, f"1:{s['rr']:.2f}"),
            (f"4 · Lot for {s.get('riskPct', 1.0):g} % risk (equity × risk / (|entry - SL| × 100 oz))", True, ""),
            ("5 · Scenario D: ATR M15 not under 0.60 × its 20-candle mean", not comp, ""),
            (f"6 · Devil's Advocate: failure probability {p:.0f} % (< 65 %)", p < 65, "; ".join(worries) or "no fatal flaw"),
            (f"7 · Lead consensus score {sc['score']:.1f} (>= 78)", sc["score"] >= 78, f"Backtest: {bt_why}"),
        ]
        s["pass"] = all(ok for _, ok, _ in s["checklist"])
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("8 · One gold trade at a time", False, "the previous gold setup is still pending or open"))
            continue
        r = s["result"]
        busy = m5[r["at"]].time + M5S if "at" in r else 1 << 62
    for w in watch:
        w.setdefault("sid", "A")
    return out, sorted(watch, key=lambda w: w["time"])


# ---------------------------------------------------------------- the 7 agents and the JSON contract (sections 6 and 7)
UI = {"VALID": "ok", "WAIT": "wait", "WARNING": "warn", "VETO": "veto", "STANDBY": "wait"}
ROLE = {"lead_strategist": ("lead", "Lead Strategist"), "structure_analyst": ("structure", "Structure Analyst"),
        "liquidity_session_analyst": ("liquidity", "Liquidity & Session Analyst"), "entry_specialist": ("entry", "Entry Specialist"),
        "risk_manager": ("risk", "Risk Manager"), "backtest_engineer": ("backtest", "Backtest Engineer"), "devils_advocate": ("devil", "Devil's Advocate")}


def report(m5, h1, now: int, setups: list, watch: list, research: Optional[dict], news_events, macro: Optional[dict] = None, d1=None) -> dict:
    """The orchestrator's output for the UI (section 7), from closed candles: the DAG Structure + Liquidity + Backtest
    → Entry + Risk → Devil (veto) → Lead (consensus)."""
    daily = Daily(d1 if d1 else resample(h1, DAY))
    g = G(m5, h1, daily)
    t = m5[-1].time + M5S
    price = m5[-1].close
    D = t - t % DAY
    i1, i4, j = g.i1(t), g.i4(t), g.j15(t)
    dr = g.dealing(t)
    h1t, h4t, m15t = g.s1["trend"][i1], g.s4["trend"][i4] if i4 >= 0 else 0, g.s15["trend"][j]
    ev = g.s1["event"][i1]
    lv = g.levels(D, t)
    tod = t % DAY
    kz = "LONDON_KILLZONE" if 7 * H1S <= tod < 10 * H1S else "NY_COMEX_KILLZONE" if 12 * H1S + 1800 <= tod < 15 * H1S + 1800 else \
         "ASIA" if tod < 6 * H1S else "LONDON_NY_TRANSITION" if 10 * H1S <= tod < 12 * H1S + 1800 else "OFF_HOURS"
    killzone = kz in ("LONDON_KILLZONE", "NY_COMEX_KILLZONE")
    nw = tier1(news_events) if news_events is not None else None
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE")]
    cand = next((s for s in reversed(live) if s["pass"]), live[-1] if live else None)
    w = watch[-1] if watch and watch[-1]["time"] >= now - 3 * H1S else None

    def st_name(tr, other=None):
        if tr == 0:
            return "COMPRESSION_CHOP"
        if other is not None and other != 0 and other != tr:
            return "COUNTER_TREND_PULLBACK"
        return "BULLISH_TREND" if tr > 0 else "BEARISH_TREND"

    pct = None if not dr else 100 * (price - dr[0]) / (dr[1] - dr[0])
    zone = None if pct is None else ("Discount" if pct < 50 else "Premium")
    bos_px = None
    if ev:
        bos_px = g.s1["sh"][i1][0] if ev[1] > 0 and g.s1["sh"][i1] else g.s1["sl"][i1][0] if g.s1["sl"][i1] else None
    structure_a = {
        "ui_badge_summary": badge(f"H1 {'bullish' if h1t > 0 else 'bearish' if h1t < 0 else 'chop'} | " + (f"{ev[0]} {'up' if ev[1] > 0 else 'down'}" if ev else "no break")
                                  + (f" | {zone} {pct:.1f}%" if pct is not None else "")),
        "status": "VALID" if h1t and h1t == h4t else "WAIT",
        "h4_bias": {1: "BULLISH", -1: "BEARISH"}.get(h4t, "NEUTRAL"), "h1_bias": {1: "BULLISH", -1: "BEARISH"}.get(h1t, "NEUTRAL"),
        "h1_state": st_name(h1t, h4t), "m15_state": st_name(m15t, h1t),
        "dealing_range": {"low": dr[0], "high": dr[1], "equilibrium": dr[2]} if dr else None, "position_pct": pct, "zone": zone,
    }
    bsl = sorted({round(v, 2) for v in [lv["pd"] and lv["pd"][0], lv["asia"] and lv["asia"][0], lv["london"] and lv["london"][0]] + g.eq_levels(t, -1) if v and v > price})
    ssl = sorted({round(v, 2) for v in [lv["pd"] and lv["pd"][1], lv["asia"] and lv["asia"][1], lv["london"] and lv["london"][1]] + g.eq_levels(t, 1) if v and v < price}, reverse=True)
    swept = cand is not None or (w is not None and any("sweep" in s_[0].lower() and s_[1] for s_ in w["steps"]))
    nxt = next((n for n in (nw or []) if n >= now - 15 * 60), None)
    lock = nxt is not None and nxt - 30 * 60 <= now <= nxt + 15 * 60
    if nw is None:
        lq_s, lq_b = "WARNING", "News feed down: Tier-1 USD not checked"
    elif lock:
        lq_s, lq_b = "VETO", f"Tier-1 USD news {hm(nxt)} UTC: lockout"
    elif swept and killzone:
        lq_s, lq_b = "VALID", f"{'SSL' if (cand or w)['dir'] > 0 else 'BSL'} swept | {kz.replace('_', ' ').title()} active"
    else:
        lq_s = "WAIT"
        lq_b = (f"SSL resting at {ssl[0]:.2f} | " if ssl else "") + kz.replace("_", " ").title()
    liquidity_a = {"ui_badge_summary": badge(lq_b), "status": lq_s, "active_session": kz, "bsl_targets": bsl[:4], "ssl_targets": ssl[:4], "sweep_detected": bool(swept),
                   "next_tier1_usd": hm(nxt) if nxt else None}
    # the Backtest Engineer (in parallel with the two above)
    st_res = ((research or {}).get("strategies") or {})
    sid = cand["sid"] if cand else (w["sid"] if w else "A")
    meas = (st_res.get(sid) or {}).get("all")
    bt_ok, bt_why = backtest_ok(meas)
    base = BASELINE[sid]
    if len(m5) < 100:
        bt_badge = f"Data LIMITED: using baseline priors (WR {base['winRate']}%, EV +{base['expectancyR']}R)"
    elif bt_ok:
        bt_badge = f"Data READY: Setup {sid} {meas['winRate']}% WR ({meas['expectancyR']:+.2f}R EV)"
    else:
        bt_badge = f"Setup {sid} REJECTED: N={(meas or {}).get('trades', 0)}, EV {(meas or {}).get('expectancyR') or 0:+.2f}R"
    backtest_a = {"ui_badge_summary": badge(bt_badge), "status": "VALID" if bt_ok else "WARNING",
                  "historical_win_rate": (meas or {}).get("winRate") and meas["winRate"] / 100, "expected_value_r": (meas or {}).get("expectancyR"),
                  "sample_size": (meas or {}).get("trades", 0), "spec_baseline": base, "verdict": bt_why}
    # the Entry Specialist and the Risk Manager
    if cand:
        bot, top = min(cand["zone"]), max(cand["zone"])
        entry_a = {"ui_badge_summary": badge(f"{'Bull' if cand['dir'] > 0 else 'Bear'} FVG {bot:.2f}-{top:.2f} | limit {cand['entry']:.2f}"), "status": "VALID",
                   "entry_valid": True, "fvg_bounds": [bot, top], "ote_zone": list(cand["ote"]) if cand.get("ote") else None,
                   "limit_entry": cand["entry"], "invalidation": cand["sl"]}
        risk_pct = cand.get("riskPct", 1.0)
        rd = abs(cand["entry"] - cand["sl"])
        lots = int(10000 * risk_pct / 100 / (rd * 100) * 100) / 100 if rd else 0
        rr_ok = cand["rr"] >= 2.5
        risk_a = {"ui_badge_summary": badge(f"Risk {risk_pct:g}% | {lots} lot/$10k | RR 1:{cand['rr']:.1f}" if rr_ok else f"Rejected: RR 1:{cand['rr']:.1f} < 2.5"),
                  "status": "VALID" if rr_ok else "VETO", "risk_percent": risk_pct, "position_size_lots": lots, "projected_rr": round(cand["rr"], 2)}
    else:
        ote = None
        if dr:
            lo, hi = dr[0], dr[1]
            ote = [hi - 0.786 * (hi - lo), hi - 0.618 * (hi - lo)] if h1t >= 0 else [lo + 0.618 * (hi - lo), lo + 0.786 * (hi - lo)]
        wait_for = next((s_[0] for s_ in w["steps"] if not s_[1]), None) if w else None
        entry_a = {"ui_badge_summary": badge("No clean zone: " + (wait_for.split(" (")[0].lower() if wait_for else f"awaiting M15 FVG after {'SSL' if h1t >= 0 else 'BSL'} sweep")),
                   "status": "WAIT", "entry_valid": False, "fvg_bounds": None, "ote_zone": ote}
        risk_a = {"ui_badge_summary": "Nothing to size", "status": "STANDBY", "risk_percent": 0.0, "position_size_lots": 0.0, "projected_rr": None}
    # the Devil's Advocate (veto)
    if cand:
        p, worries = cand["devilP"], cand["worries"]
    else:
        p, worries = 0.0, []
        if pct is not None and 40 <= pct <= 60 and not swept:
            p, worries = 72.0, [f"Mid-range entry before {ssl[0]:.2f} sweep gets stopped" if ssl and h1t >= 0 else "Mid-range: no sweep yet"]
        if lock:
            p, worries = max(p, 70.0), [f"Tier-1 USD news at {hm(nxt)} UTC"] + worries
    devil_a = {"ui_badge_summary": badge("My worry: " + (worries[0] if worries else "nothing fatal found")), "status": "VETO" if p >= 65 else "WARNING" if p > 0 else "VALID",
               "failure_probability": round(p / 100, 2), "veto_active": p >= 65, "primary_risk_factor": worries[0] if worries else None, "worries": worries}
    # the Lead Strategist
    ctx = {"aligned": bool(h1t and h1t == h4t), "killzone": killzone}
    sc = cand["consensus"] if cand else scores(None, ctx, bt_ok, p)
    execute = bool(cand and cand["pass"] and risk_a["status"] == "VALID" and not devil_a["veto_active"] and sc["score"] >= 78)
    if execute:
        decision = ("BUY_LIMIT" if cand["dir"] > 0 else "SELL_LIMIT") if not cand["market"] else ("BUY_MARKET" if cand["dir"] > 0 else "SELL_MARKET")
        lead_b = f"{decision.replace('_', ' ')} {cand['entry']:.2f} | SL {cand['sl']:.2f} | TP2 {cand['tp']:.2f}"
        plan = {"order_type": decision, "entry_price": cand["entry"], "stop_loss": cand["sl"], "tp1_price": cand.get("tp1"), "tp2_price": cand["tp"],
                "invalidation_trigger": f"price through {cand['sl']:.2f} before the fill", "scenario_id": SCEN[cand["sid"]]}
        scen = SCEN[cand["sid"]]
    else:
        decision = "NO_TRADE"
        if lock:
            lead_b, scen = f"No trade: Tier-1 USD news lockout ({hm(nxt)} UTC)", "SCENARIO_C_NEWS_LOCKOUT"
        elif cand and devil_a["veto_active"]:
            lead_b, scen = "No trade: Devil's Advocate hard veto", SCEN[cand["sid"]]
        elif cand:
            lead_b, scen = f"No trade: consensus {sc['score']:.0f} < 78", SCEN[cand["sid"]]
        else:
            scen = "SCENARIO_D_NO_TRADE"
            wake = f"{'SSL' if h1t >= 0 else 'BSL'} {(ssl[0] if h1t >= 0 and ssl else bsl[0] if bsl else price):.2f}"
            lead_b = f"No trade: I wait for {'NY' if tod >= 10 * H1S else 'London'} sweep of {wake}"
        plan = {"order_type": "NONE", "entry_price": None, "stop_loss": None, "tp1_price": None, "tp2_price": None,
                "invalidation_trigger": f"H1 close beyond {dr[0]:.2f}" if dr and h1t >= 0 else (f"H1 close beyond {dr[1]:.2f}" if dr else None),
                "wake_up": {"bsl": bsl[:2], "ssl": ssl[:2]}}
    lead_a = {"ui_badge_summary": badge(lead_b), "status": "VALID" if execute else "VETO" if (lock or devil_a["veto_active"]) else "WAIT",
              "reasoning": f"H1 {structure_a['h1_state']}, H4 {structure_a['h4_bias']}, {kz}; consensus {sc['score']:.1f} "
                           f"(struct {sc['S_struct']}, liq {sc['S_liq']}, entry {sc['S_entry']}, backtest {sc['S_backtest']}, devil {sc['S_devil']:.0f} %)",
              "execution_plan": plan}
    agents = {"lead_strategist": lead_a, "structure_analyst": structure_a, "liquidity_session_analyst": liquidity_a, "entry_specialist": entry_a,
              "risk_manager": risk_a, "backtest_engineer": backtest_a, "devils_advocate": devil_a}
    contract = {"pair": "XAU/USD", "strategy_name": STRATEGY_NAME, "timestamp_utc": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scenario_active": scen, "consensus_score": sc["score"], "final_decision": decision, "agents": agents}
    ui = []
    for k in ("lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager", "backtest_engineer", "devils_advocate"):
        a = agents[k]
        key, role = ROLE[k]
        lines = [f"{kk}: {vv}" for kk, vv in a.items() if kk not in ("ui_badge_summary", "status") and vv not in (None, [], {})]
        ui.append({"key": key, "role": role, "status": UI[a["status"]], "finding": a["ui_badge_summary"], "lines": lines, "statusMd": a["status"]})
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand}
