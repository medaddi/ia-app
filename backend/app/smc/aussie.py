"""
AUD/CHF — the user's spec "aud_chf_multi_agent_quantitative_strategy_claude_prompt.md" (2026-11-09), applied to the
letter. It replaces everything earlier for AUD/CHF (the analysis-only team: git history keeps it).

Strategy: "Risk-Regime Trend Efficiency & Cross-Session Inducement Pullback".
  Scenario A  H1 trend inducement sweep + EMA ribbon order block continuation (23:00-05:00 or 06:30-10:30 UTC)
  Scenario B  Asian squeeze (BWR < 0.85 for >= 6 M15) -> Zurich open sweep + expansion -> first FVG retest
  Scenario C  risk-off shock: H1 bearish CHoCH by a displacement > 2.0 ATR H1 closing under EMA 200 -> short the
              50-61.8 % retracement into the new H1 bearish order block
  Scenario D  ER 20 H1 < 0.22, or the 20:45-22:30 UTC rollover -> NO_TRADE

Section 3 math as written: Kaufman ER 20 on H1; the H1 ribbon EMA 21 / 55 / 200; the confirmed trend = the ribbon
stacked, ER >= 0.32 and the last H1 structural break a BOS that way (gold.structure, 0.10 ATR); the pullback into
50-78.6 % of the H1 impulse leg touching [EMA 21, EMA 55]; the IDM / L_Asia sweep; the RSI 14 M15 hook (<= 38 then
> 45 on the displacement MSS + FVG, the mirror 62 / 55 for shorts, CHOICE); BWR = (BB 20, 2σ width) / (KC 20, 1.5 ATR
width) on M15.

Every number the spec leaves open is marked CHOICE and was fixed before any result was seen.
"""

from bisect import bisect_left
from datetime import datetime, timezone
from typing import Optional

from .engines import efficiency
from .fiber import F
from .gold import badge, hm
from .playbook import DAY, H1S, M5S, M15S, Daily, _make, atr, body, ema, hilo, m5_index_at_close, resample, rsi, run, span

PIP = 0.0001
STRATEGY_NAME = "Risk-Regime Trend Efficiency & Cross-Session Inducement Pullback"
NAMES = {"A": "Scenario A · H1 trend IDM sweep + EMA ribbon OB", "B": "Scenario B · Asian squeeze → Zurich expansion FVG retest",
         "C": "Scenario C · risk-off shock: short the H1 bearish OB"}
SCEN = {"A": "SCENARIO_A_TREND_PULLBACK", "B": "SCENARIO_B_ZURICH_SQUEEZE", "C": "SCENARIO_C_RISK_OFF_SHOCK", "D": "SCENARIO_D_CHOP_OR_ROLLOVER"}
BASELINE = {"A": {"trades": 312, "winRate": 57.7, "avgWin": 2.95, "expectancyR": 1.28, "pf": 3.03, "mdd": -4.9},
            "B": {"trades": 196, "winRate": 54.6, "avgWin": 2.70, "expectancyR": 1.02, "pf": 2.56, "mdd": -5.8},
            "C": {"trades": 0, "winRate": None, "avgWin": None, "expectancyR": None, "pf": None, "mdd": None}}  # the spec gives none
NEWS_MIN = 15  # the user's rule (no trade at the news): AUD / CHF high-impact releases ±15 min (CHOICE, the guide's pause)


def rollover(t: int) -> bool:
    tod = t % DAY
    return 20 * H1S + 2700 <= tod < 22 * H1S + 1800


def news_times(events) -> list[int]:
    return sorted({int(e["time"]) for e in (events or []) if e.get("currency") in ("AUD", "CHF")})


def bwr(c, n: int = 20) -> list[Optional[float]]:
    """3.3: (BB upper - BB lower) / (KC upper - KC lower) = 4 σ_20 / (3 ATR_20); σ the population std (Bollinger),
    the Keltner ATR over 20 (CHOICE: the channel's own length)."""
    a = atr(c, n)
    out: list[Optional[float]] = [None] * len(c)
    for i in range(n - 1, len(c)):
        w = [x.close for x in c[i - n + 1:i + 1]]
        m = sum(w) / n
        sd = (sum((v - m) ** 2 for v in w) / n) ** 0.5
        if a[i]:
            out[i] = 4 * sd / (3 * a[i])
    return out


class A(F):
    def __init__(self, m5, h1, daily: Daily):
        super().__init__(m5, h1, daily, None)
        c1 = [x.close for x in h1]
        self.er = efficiency(c1, 20)
        self.e21, self.e55, self.e200 = ema(c1, 21), ema(c1, 55), ema(c1, 200)
        self.rsi15 = rsi([x.close for x in self.m15], 14)
        self.bw = bwr(self.m15, 20)

    def trend(self, i: int) -> int:
        """3.1: +1 / -1 when C > EMA21 > EMA55 > EMA200 (mirror), ER 20 >= 0.32 and the last H1 break a BOS that way."""
        if i < 0 or None in (self.e21[i], self.e55[i], self.e200[i], self.er[i]) or self.er[i] < 0.32:
            return 0
        c, ev = self.h1[i].close, self.s1["event"][i]
        if c > self.e21[i] > self.e55[i] > self.e200[i] and ev == ("BOS", 1):
            return 1
        if c < self.e21[i] < self.e55[i] < self.e200[i] and ev == ("BOS", -1):
            return -1
        return 0

    def impulse(self, i: int, d: int) -> Optional[tuple[float, float, int, int]]:
        """The last H1 impulse leg in the trend: (SL_imp, SH_imp, index of the low, of the high), the low before the high
        for d = +1 (the mirror for d = -1)."""
        sl, sh = self.s1["sl"][i], self.s1["sh"][i]
        if not sl or not sh or sh[0] <= sl[0]:
            return None
        if (d > 0 and sl[1] < sh[1]) or (d < 0 and sh[1] < sl[1]):
            return sl[0], sh[0], sl[1], sh[1]
        return None

    def regime(self, t: int) -> str:
        i = self.i1(t)
        j = self.j15(t)
        tr = self.trend(i)
        if tr:
            return "RISK_ON_UPTREND" if tr > 0 else "RISK_OFF_DOWNTREND"
        if j >= 5 and all(self.bw[q] is not None and self.bw[q] < 0.85 for q in range(j - 5, j + 1)):
            return "SQUEEZE_COMPRESSION"
        if i >= 0 and self.er[i] is not None and self.er[i] < 0.22:
            return "NOISY_CHOP"
        return "TRANSITIONAL"


def _in_a(tc: int) -> bool:
    tod = tc % DAY
    return tod > 23 * H1S or tod <= 5 * H1S or 6 * H1S + 1800 < tod <= 10 * H1S + 1800


def _shock(other, t: int, d: int, inverse: bool) -> Optional[str]:
    """The Devil's cross-currency shock (CHOICE): the twin's last closed H1 candle has a body > 1.5 ATR 14 H1 against
    the trade: for a long, AUD/CAD falling (AUD weak) or EUR/CHF falling (CHF strong); the mirror for a short. `inverse`
    is kept for a twin quoted the other way (none here)."""
    if not other:
        return None
    h, at, tt, name = other
    k = bisect_left(tt, t - H1S + 1) - 1
    if k < 15 or not at[k]:
        return None
    x = h[k]
    mv = x.close - x.open
    against = ((mv < 0) if d > 0 else (mv > 0)) != inverse
    if abs(mv) > 1.5 * at[k] and against:
        return f"{name} {'drops' if mv < 0 else 'jumps'} {abs(mv) / at[k]:.1f} ATR at {hm(x.time)}"
    return None


def scenario_a(a: A, cost: float, out: list, watch: list) -> None:
    """A: H1 trend d (3.1) with the H4 structure trend the same; an M15 candle closing in 23:00-05:00 or 06:30-10:30 UTC
    whose extreme is inside 50-78.6 % of the impulse leg and touches the ribbon [EMA21, EMA55], sweeping an internal M15
    IDM (a counter-trend fractal formed after the impulse extreme, intact until then) or L_Asia / H_Asia (after 06:00);
    RSI 14 M15 <= 38 on the pullback (>= 62 short); within 8 M15 candles the displacement MSS with an unmitigated OB + FVG
    (EUR/USD's definition), RSI back > 45 (< 55) on the MSS candle, the OB touching the ribbon (± 0.25 ATR H1, CHOICE).
    Limit at the OB proximal edge / the 50 % FVG inside it (CHOICE, the FVG / OB zone), valid 8 M15 (CHOICE). SL = the
    sweep extreme ∓ 0.35 ATR M15. TP1 the external H1 swing (100 % of the leg, 50 % closed); TP2 the -0.272 else
    -0.618 extension at >= 3.0 R. Held 72 h (CHOICE: the carry hold). Shorts 0.5 % risk (counter-carry overnight)."""
    m15, m5 = a.m15, a.m5
    hi_f, lo_f = a.f15
    end = m5[-1].time + M5S
    used = set()
    for j in range(60, len(m15)):
        x = m15[j]
        tc = x.time + M15S
        if tc > end or not _in_a(tc) or rollover(tc):
            continue
        i1 = a.i1(tc)
        d = a.trend(i1)
        if not d or (a.i4(tc) < 0 or a.s4["trend"][a.i4(tc)] != d):
            continue
        imp = a.impulse(i1, d)
        if not imp or (imp, d) in used:
            continue
        lo, hi, ilo, ihi = imp
        leg = hi - lo
        z50, z786 = (hi - 0.5 * leg, hi - 0.786 * leg) if d > 0 else (lo + 0.5 * leg, lo + 0.786 * leg)
        ext = x.low if d > 0 else x.high
        in_fib = (z786 <= ext <= z50) if d > 0 else (z50 <= ext <= z786)
        r_lo, r_hi = min(a.e21[i1], a.e55[i1]), max(a.e21[i1], a.e55[i1])
        rib = x.low <= r_hi and x.high >= r_lo
        if not (in_fib and rib):
            continue
        t_imp = a.h1[ihi if d > 0 else ilo].time
        D = tc - tc % DAY
        pools = []
        for q in range(j - 3, max(j - 60, 0), -1):
            if m15[q].time < t_imp:
                break
            if not (lo_f[q] if d > 0 else hi_f[q]):
                continue
            lv = m15[q].low if d > 0 else m15[q].high
            if all(((m15[r].low >= lv) if d > 0 else (m15[r].high <= lv)) for r in range(q + 1, j)) and ((ext < lv) if d > 0 else (ext > lv)):
                pools.append(("IDM", lv))
                break
        if tc % DAY >= 6 * H1S:
            asia = hilo(span(m5, a.t5, D, D + 6 * H1S))
            if asia:
                lv = asia[1] if d > 0 else asia[0]
                if ((ext < lv) if d > 0 else (ext > lv)) and ((m15[j - 1].low >= lv) if d > 0 else (m15[j - 1].high <= lv)):
                    pools.append(("L_Asia" if d > 0 else "H_Asia", lv))
        steps = [(f"H1 {'Risk-On uptrend' if d > 0 else 'Risk-Off downtrend'} (ER {a.er[i1]:.2f} >= 0.32, ribbon stacked, BOS) + H4", True, ""),
                 ("Pullback in 50-78.6 % of the H1 leg, touching EMA21-EMA55", True, f"{min(z50, z786):.5f}-{max(z50, z786):.5f}"),
                 ("Swept IDM / session liquidity", bool(pools), f"{pools[0][0]} {pools[0][1]:.5f}" if pools else "none")]
        if not pools:
            watch.append({"sid": "A", "time": tc, "dir": d, "steps": steps})
            continue
        rs = [a.rsi15[q] for q in range(max(j - 8, 0), j + 1) if a.rsi15[q] is not None]
        dip = bool(rs) and ((min(rs) <= 38) if d > 0 else (max(rs) >= 62))
        steps.append((f"RSI 14 M15 {'<= 38' if d > 0 else '>= 62'} on the pullback", dip, f"{(min(rs) if d > 0 else max(rs)):.0f}" if rs else ""))
        if not dip:
            watch.append({"sid": "A", "time": tc, "dir": d, "steps": steps})
            continue
        used.add((imp, d))
        z = a.ob_fvg(j, min(j + 8, len(m15)), d, 0)
        if not z or z["t_set"] > end:
            watch.append({"sid": "A", "time": tc, "dir": d, "steps": steps + [("M15 displacement MSS + unmitigated OB + FVG", False, "waiting")]})
            continue
        jm = z["j_mss"]
        hook = a.rsi15[jm] is not None and ((a.rsi15[jm] > 45) if d > 0 else (a.rsi15[jm] < 55))
        tol = 0.25 * (a.at1[i1] or 0)
        ob_rib = z["ob"][0] <= r_hi + tol and z["ob"][1] >= r_lo - tol
        hl = (min(m15[q].low for q in range(j, jm + 1)) > lo) if d > 0 else (max(m15[q].high for q in range(j, jm + 1)) < hi)
        steps += [("M15 displacement MSS + unmitigated OB + FVG", True, f"OB {z['ob'][0]:.5f}-{z['ob'][1]:.5f}"),
                  (f"RSI hook back {'> 45' if d > 0 else '< 55'} on the MSS candle", hook, "" if a.rsi15[jm] is None else f"{a.rsi15[jm]:.0f}"),
                  ("OB inside the EMA21-EMA55 value zone", ob_rib, ""),
                  ("Higher low above SL_imp" if d > 0 else "Lower high under SH_imp", hl, "")]
        if not (hook and ob_rib and hl):
            watch.append({"sid": "A", "time": z["t_set"], "dir": d, "steps": steps})
            continue
        sw_ext = min(m15[q].low for q in range(j, jm + 1)) if d > 0 else max(m15[q].high for q in range(j, jm + 1))
        ce = (z["fvg"][0] + z["fvg"][1]) / 2
        entry = ce if z["ob"][0] <= ce <= z["ob"][1] else z["ob"][1] if d > 0 else z["ob"][0]
        j_set = a.j15(z["t_set"])
        sl = sw_ext - d * 0.35 * (a.at15[j_set] or 0)
        tp1 = hi if d > 0 else lo
        risk = abs(entry - sl)
        ext_272, ext_618 = (hi + 0.272 * leg, hi + 0.618 * leg) if d > 0 else (lo - 0.272 * leg, lo - 0.618 * leg)
        tp2 = next(((p, n) for p, n in ((ext_272, "-0.272 extension"), (ext_618, "-0.618 extension")) if risk and (p - entry) * d >= 3.0 * risk), None)
        if not tp2:
            watch.append({"sid": "A", "time": z["t_set"], "dir": d, "steps": steps + [("TP2 extension at >= 3.0 R", False, "none")]})
            continue
        k0 = m5_index_at_close(a.t5, z["t_set"])
        if k0 is None:
            continue
        s = _make("AUDCHF", "A", d, m5, k0, entry, sl, tp1, tp2[0], 0.5, False, 24, z["t_set"] + 72 * H1S, steps + [("TP2 at >= 3.0 R", True, tp2[1])],
                  {"ob": (z["ob"][1], z["ob"][0], m15[z["j_ob"]].time), "fvg": (z["fvg"][0], z["fvg"][1], m15[z["j_ob"]].time),
                   "sweep": (sw_ext, x.time), "levels": {pools[0][0]: pools[0][1], "SL_imp": lo, "SH_imp": hi}}, cost,
                  zone=(min(z["ob"]), max(z["ob"])), be_off=None)
        if s:
            s.update(scenario="A", tp2Name=tp2[1], er=a.er[i1], riskPct=0.5 if d < 0 else 1.0, impulse=(lo, hi), idm=pools[0][1])
            out.append(s)


def scenario_b(a: A, cost: float, out: list, watch: list) -> None:
    """B: a run of >= 6 M15 candles with BWR < 0.85 inside 00:00-06:00 UTC; the Asian box = that session's high / low.
    06:30-08:30 UTC: a candle trades beyond one side of the box, then (that candle or a later one in the window) an M15
    candle in the H4 trend direction with a body >= 1.5 ATR 14 M15 and RVOL >= 1.7 closes beyond the box on the trend
    side. Its FVG (the first 3-candle gap with the expansion candle in the middle, CHOICE): a limit at the FVG's
    proximal edge (the first retest), valid until 09:30 UTC. SL the expansion candle's start ∓ 0.35 ATR M15 (CHOICE);
    TP = the broken box edge + 2.5 × the box height. Closed at 20:45 (the rollover)."""
    m15, m5 = a.m15, a.m5
    end = m5[-1].time + M5S
    for D in sorted({x.time - x.time % DAY for x in m5}):
        js = [q for q in range(a.j15(D + M15S) + 1, a.j15(D + 6 * H1S) + 1) if 0 <= q < len(m15)]
        run_, sq = 0, False
        for q in js:
            run_ = run_ + 1 if a.bw[q] is not None and a.bw[q] < 0.85 else 0
            sq = sq or run_ >= 6
        if not sq:
            continue
        box = hilo(span(m5, a.t5, D, D + 6 * H1S))
        if not box:
            continue
        bh, bl = box
        H = bh - bl
        i4 = a.i4(D + 6 * H1S + 1800)
        d = a.s4["trend"][i4] if i4 >= 0 else 0
        if not d or H <= 0:
            continue
        swept = False
        for q in range(a.j15(D + 6 * H1S + 1800) + 1, a.j15(D + 8 * H1S + 1800) + 1):
            if q >= len(m15) or m15[q].time + M15S > end:
                break
            x = m15[q]
            swept = swept or x.high > bh or x.low < bl
            if not swept:
                continue
            at = a.at15[q] or 0
            v = a.vol15_sma[q]
            rv = a.v15[q] / v if v else None
            exp_ = ((x.close > x.open) if d > 0 else (x.close < x.open)) and body(x) >= 1.5 * at and ((x.close > bh) if d > 0 else (x.close < bl))
            if not exp_:
                continue
            steps = [("Asian squeeze: BWR < 0.85 for >= 6 M15", True, f"box {bl:.5f}-{bh:.5f}"),
                     ("Zurich open sweep of a box side", True, ""),
                     (f"Expansion with H4: body {body(x) / at:.1f} ATR (>= 1.5)", True, hm(x.time)),
                     (f"RVOL >= 1.7 ({'n/a' if rv is None else f'{rv:.1f}'})", rv is not None and rv >= 1.7, "")]
            if not steps[-1][1] or q + 1 >= len(m15):
                watch.append({"sid": "B", "time": x.time + M15S, "dir": d, "steps": steps})
                break
            p, n_ = m15[q - 1], m15[q + 1]
            gap = (n_.low - p.high) if d > 0 else (p.low - n_.high)
            if gap <= 0 or n_.time + M15S > end:
                watch.append({"sid": "B", "time": x.time + M15S, "dir": d, "steps": steps + [("M15 FVG of the expansion", False, "none")]})
                break
            entry = n_.low if d > 0 else n_.high
            sl = (x.open - d * 0.35 * at)
            tp = (bh + 2.5 * H) if d > 0 else (bl - 2.5 * H)
            t_set = n_.time + M15S
            k0 = m5_index_at_close(a.t5, t_set)
            if k0 is None or t_set >= D + 9 * H1S + 1800:
                break
            steps.append(("Limit at the first FVG retest", True, f"{entry:.5f}"))
            s = _make("AUDCHF", "B", d, m5, k0, entry, sl, None, tp, 1.0, False, max(1, (D + 9 * H1S + 1800 - t_set) // M5S), D + 20 * H1S + 2700,
                      steps, {"fvg": (min(entry, p.high if d > 0 else p.low), max(entry, p.high if d > 0 else p.low), p.time),
                              "levels": {"Asia box high": bh, "Asia box low": bl}}, cost,
                      zone=(min(entry, p.high if d > 0 else p.low), max(entry, p.high if d > 0 else p.low)), be_off=None)
            if s:
                s.update(scenario="B", tp2Name="2.5 × the Asian box", riskPct=0.5 if d < 0 else 1.0)
                out.append(s)
            break


def scenario_c(a: A, cost: float, out: list, watch: list) -> None:
    """C: an H1 candle turns the H1 structure to a bearish CHoCH, its body > 2.0 ATR 14 H1, closing under EMA 200. The leg
    = from the last H1 swing high before it to that candle's low; the H1 bearish OB = the last bullish H1 candle before
    it. A short limit at the 50 % retracement when it lies in the OB (else the OB's low, when the OB is inside 50-61.8 %,
    CHOICE), valid 24 h (CHOICE); SL the OB high + 0.35 ATR 14 H1 (CHOICE: A's buffer on H1); TP1 the displacement low
    (50 %), TP2 the -0.272 extension of the leg at >= 2.6 R (the Risk Manager)."""
    h1, m5 = a.h1, a.m5
    for i in range(201, len(h1) - 1):
        ev, pv = a.s1["event"][i], a.s1["event"][i - 1]
        x = h1[i]
        if ev != ("CHOCH", -1) or pv == ev or not a.at1[i] or a.e200[i] is None:
            continue
        if not (x.open - x.close > 2.0 * a.at1[i] and x.close < a.e200[i]):
            continue
        sh = a.s1["sh"][i]
        if not sh:
            continue
        top, low = sh[0], x.low
        leg = top - low
        ob = next((h1[q] for q in range(i - 1, max(i - 8, 0), -1) if h1[q].close > h1[q].open), None)
        if not ob or leg <= 0:
            continue
        r50, r618 = low + 0.5 * leg, low + 0.618 * leg
        if ob.low <= r50 <= ob.high:
            entry = r50
        elif r50 <= ob.low <= r618:
            entry = ob.low
        else:
            watch.append({"sid": "C", "time": x.time + H1S, "dir": -1, "steps": [("Risk-off CHoCH > 2 ATR under EMA 200", True, ""), ("OB in the 50-61.8 % zone", False, "")]})
            continue
        sl = ob.high + 0.35 * a.at1[i]
        risk = sl - entry
        tp2 = low - 0.272 * leg
        if risk <= 0 or (entry - tp2) < 2.6 * risk:
            watch.append({"sid": "C", "time": x.time + H1S, "dir": -1, "steps": [("Risk-off CHoCH > 2 ATR under EMA 200", True, ""), ("TP2 -0.272 at >= 2.6 R", False, "")]})
            continue
        t_set = x.time + H1S
        k0 = m5_index_at_close(a.t5, t_set)
        if k0 is None:
            continue
        steps = [(f"H1 bearish CHoCH, displacement {(x.open - x.close) / a.at1[i]:.1f} ATR (> 2.0), close under EMA 200", True, hm(x.time)),
                 ("Short limit at the 50-61.8 % retrace into the H1 bearish OB", True, f"{entry:.5f}")]
        s = _make("AUDCHF", "C", -1, m5, k0, entry, sl, low, tp2, 0.5, False, 24 * 12, t_set + 72 * H1S, steps,
                  {"ob": (ob.high, ob.low, ob.time), "levels": {"displacement low": low, "swing high": top}}, cost, zone=(entry, entry), be_off=None)
        if s:
            s.update(scenario="C", tp2Name="-0.272 extension", riskPct=0.5)
            out.append(s)


def devil(a: A, s: dict, twins) -> tuple[float, list[str]]:
    """Failure probability (CHOICE: the weights): ER 20 < 0.25 +40 · the pullback CLOSED beyond the H1 major swing (A:
    an M15 close under SL_imp / over SH_imp before the entry) +70 · an AUD/CAD or EUR/CHF shock against the trade +35.
    Hard veto >= 65 %."""
    t, d = s["time"], s["dir"]
    i1 = a.i1(t)
    p, w = 0.0, []
    er = a.er[i1] if i1 >= 0 else None
    if er is not None and er < 0.25:
        p += 40
        w.append(f"ER {er:.2f} < 0.25: the ribbon whipsaws")
    if s["sid"] == "A" and s.get("impulse"):
        lo, hi = s["impulse"]
        j = a.j15(t)
        js = [q for q in range(max(j - 16, 0), j + 1)]
        if any(((a.m15[q].close < lo) if d > 0 else (a.m15[q].close > hi)) for q in js):
            p += 70
            w.append("the pullback closed beyond the H1 major swing")
    for tw, inv in ((twins or (None, None))[0], False), ((twins or (None, None))[1], False):
        msg = _shock(tw, t, d, inv)
        if msg:
            p += 35
            w.append(msg)
    return min(p, 100.0), w


def _twins(pair_m5) -> Optional[tuple]:
    """(AUD/CAD, EUR/CHF) M5 -> H1 candles, ATR and times for the Devil."""
    if not pair_m5:
        return None
    out = []
    for m, name in zip(pair_m5, ("AUD/CAD", "EUR/CHF")):
        if not m:
            out.append(None)
            continue
        h = resample(m, H1S)
        out.append((h, atr(h, 14), [x.time for x in h], name))
    return tuple(out)


def scan(m5, h1, cost: float, news_events=None, d1=None, twins_m5=None) -> tuple[list, list]:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    a = A(m5, h1, daily)
    out, watch = [], []
    if len(h1) < 260 or len(a.m15) < 120:
        return out, watch
    scenario_a(a, cost, out, watch)
    scenario_b(a, cost, out, watch)
    scenario_c(a, cost, out, watch)
    out.sort(key=lambda x: x["time"])
    tw = _twins(twins_m5)
    nw = news_times(news_events) if news_events is not None else None
    for s in out:
        t = s["time"]
        if nw and not s["market"]:
            s["result"] = run(m5, s["index"], s["dir"], s["entry"], s["sl"], s["tp1"], s["tp"], s["part"], False, s["expiry"], s["holdUntil"], cost,
                              None, nw, None, None, None, NEWS_MIN)
        p, worries = devil(a, s, tw)
        s["devilP"], s["worries"] = p, worries
        i1 = a.i1(t)
        er = a.er[i1] if i1 >= 0 else None
        near = [n for n in (nw or []) if abs(n - t) <= NEWS_MIN * 60]
        need = 3.0 if s["sid"] == "A" else 2.6
        s["checklist"] = [
            (f"1 · {NAMES[s['sid']]}", True, STRATEGY_NAME),
            ("2 · Scenario D: ER 20 >= 0.22 and not in the 20:45-22:30 rollover", (er is None or er >= 0.22) and not rollover(t), "" if er is None else f"ER {er:.2f}"),
            (f"3 · Risk Manager: RR to TP2 {s['rr']:.2f} (>= {need:g})", s["rr"] >= need - 1e-9, s.get("tp2Name", "")),
            (f"4 · Lot for {s.get('riskPct', 1.0):g} % risk (10 CHF / pip / lot at the live USD/CHF)", True, "shorts 0.5 %: counter-carry overnight"),
            (f"5 · No AUD / CHF high-impact release ±{NEWS_MIN} min (the user's news rule)", not near,
             "not checked (no news history)" if nw is None else (", ".join(hm(n) for n in near) + " UTC" if near else "clear")),
            (f"6 · Devil's Advocate: failure probability {p:.0f} % (< 65 %)", p < 65, "; ".join(worries) or "no trap found"),
        ]
        s["pass"] = all(ok for _, ok, _ in s["checklist"])
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("7 · One AUD/CHF trade at a time", False, "the previous setup is still pending or open"))
            continue
        r = s["result"]
        busy = m5[r["at"]].time + M5S if "at" in r else 1 << 62
    return out, sorted(watch, key=lambda w: w["time"])


UI = {"VALID": "ok", "WAIT": "wait", "WARNING": "warn", "VETO": "veto", "STANDBY": "wait"}
ROLE = {"lead_strategist": ("lead", "Lead Strategist"), "structure_analyst": ("structure", "Structure Analyst"),
        "liquidity_session_analyst": ("liquidity", "Liquidity & Session Analyst"), "entry_specialist": ("entry", "Entry Specialist"),
        "risk_manager": ("risk", "Risk Manager"), "backtest_engineer": ("backtest", "Backtest Engineer"), "devils_advocate": ("devil", "Devil's Advocate")}


def _session_name(t: int) -> str:
    tod = t % DAY
    if rollover(t):
        return "ROLLOVER_LOCKOUT"
    if tod >= 23 * H1S or tod < 6 * H1S:
        return "SYDNEY_TOKYO"
    if 6 * H1S + 1800 <= tod < 15 * H1S:
        return "ZURICH_LONDON"
    if 22 * H1S + 1800 <= tod < 23 * H1S:
        return "PRE_SYDNEY"
    return "NEW_YORK" if tod < 20 * H1S + 2700 else "PRE_SYDNEY"


def report(m5, h1, now: int, setups: list, watch: list, research: Optional[dict], news_events, d1=None,
           usd_per_pip: Optional[float] = None, twins_m5=None, macro: Optional[dict] = None) -> dict:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    a = A(m5, h1, daily)
    t = m5[-1].time + M5S
    price = m5[-1].close
    D = t - t % DAY
    i1, i4 = a.i1(t), a.i4(t)
    tr = a.trend(i1)
    h1t, h4t = a.s1["trend"][i1], (a.s4["trend"][i4] if i4 >= 0 else 0)
    er = a.er[i1] if i1 >= 0 else None
    regime = a.regime(t)
    d_ = tr or h1t or 1
    imp = a.impulse(i1, d_) if i1 >= 0 else None
    fib = None
    if imp:
        lo, hi = imp[0], imp[1]
        leg = hi - lo
        fib = sorted([hi - 0.5 * leg, hi - 0.786 * leg]) if d_ > 0 else sorted([lo + 0.5 * leg, lo + 0.786 * leg])
        pos = ((hi - price) / leg) if d_ > 0 else ((price - lo) / leg)
    dr = a.dealing(t)
    rib = (a.e21[i1], a.e55[i1], a.e200[i1]) if i1 >= 0 else (None, None, None)
    reg_txt = {"RISK_ON_UPTREND": "Risk-On Uptrend", "RISK_OFF_DOWNTREND": "Risk-Off Downtrend", "SQUEEZE_COMPRESSION": "Squeeze",
               "NOISY_CHOP": "Noisy Chop", "TRANSITIONAL": "Transitional"}[regime]
    sb = f"H1 {reg_txt} (ER={er:.2f})" if er is not None else f"H1 {reg_txt}"
    if imp and tr:
        sb += f" | Pullback at {pos * 100:.1f}%"
    structure_a = {"ui_badge_summary": badge(sb), "status": "VALID" if tr and tr == h4t else "VETO" if regime == "NOISY_CHOP" else "WAIT",
                   "regime": regime, "efficiency_ratio_20": None if er is None else round(er, 2),
                   "h4_bias": {1: "BULLISH", -1: "BEARISH"}.get(h4t, "NEUTRAL"), "h1_bias": {1: "BULLISH", -1: "BEARISH"}.get(h1t, "NEUTRAL"),
                   "ema_ribbon": {"ema_21": rib[0], "ema_55": rib[1], "ema_200": rib[2]},
                   "impulse_leg": {"low": imp[0], "high": imp[1]} if imp else None, "fib_50_786": fib,
                   "bwr_m15": None if a.j15(t) < 0 or a.bw[a.j15(t)] is None else round(a.bw[a.j15(t)], 2),
                   "dealing_range": {"low": dr[0], "high": dr[1], "equilibrium": dr[2]} if dr else None}
    sess = _session_name(t)
    asia = hilo(span(m5, a.t5, D, min(t, D + 6 * H1S)))
    pd = hilo(span(m5, a.t5, D - DAY, D)) or hilo(span(m5, a.t5, D - 3 * DAY, D - 2 * DAY + 1))
    j = a.j15(t)
    hi_f, lo_f = a.f15
    idm = None
    if imp and j > 3:
        t_imp = a.h1[imp[3] if d_ > 0 else imp[2]].time
        for q in range(j - 2, max(j - 60, 0), -1):
            if a.m15[q].time < t_imp:
                break
            if lo_f[q] if d_ > 0 else hi_f[q]:
                idm = a.m15[q].low if d_ > 0 else a.m15[q].high
                break
    bsl = sorted({round(v, 5) for v in [pd and pd[0], asia and asia[0], dr and dr[1], imp and imp[1]] + a.eq_levels(t, -1) if v and v > price})
    ssl = sorted({round(v, 5) for v in [pd and pd[1], asia and asia[1], dr and dr[0], imp and imp[0], idm] + a.eq_levels(t, 1) if v and v < price}, reverse=True)
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE")]
    cand = next((s for s in reversed(live) if s["pass"]), live[-1] if live else None)
    w = watch[-1] if watch and watch[-1]["time"] >= now - 3 * H1S else None
    swept = bool(cand and cand["sid"] == "A") or bool(w and w["sid"] == "A" and any(s_[0].startswith("Swept") and s_[1] for s_ in w["steps"]))
    sname = {"SYDNEY_TOKYO": "Sydney/Tokyo", "ZURICH_LONDON": "Zurich Open", "ROLLOVER_LOCKOUT": "Rollover lockout", "PRE_SYDNEY": "Pre-Sydney", "NEW_YORK": "New York"}[sess]
    if swept:
        lv = cand.get("idm") if cand else next((s_[2] for s_ in w["steps"] if s_[0].startswith("Swept")), "")
        lq_b = f"Internal IDM swept at {lv if isinstance(lv, str) else f'{lv:.4f}'} | {sname}"
    elif idm is not None:
        lq_b = f"Internal IDM resting at {idm:.4f} | " + (f"BSL target {bsl[0]:.4f}" if d_ > 0 and bsl else f"SSL target {ssl[0]:.4f}" if ssl else sname)
    else:
        lq_b = f"No IDM yet | {sname}"
    liquidity_a = {"ui_badge_summary": badge(lq_b), "status": "VETO" if sess == "ROLLOVER_LOCKOUT" else "VALID" if swept else "WAIT",
                   "active_session": sess, "idm_level": idm, "asia_range": {"high": asia[0], "low": asia[1]} if asia else None,
                   "bsl_targets": bsl[:4], "ssl_targets": ssl[:4], "sweep_detected": swept}
    if cand:
        zl, zh = min(cand["zone"]), max(cand["zone"])
        entry_a = {"ui_badge_summary": badge(f"{'Buy' if cand['dir'] > 0 else 'Sell'} limit {cand['entry']:.5f} | TP1 {cand['tp1'] or cand['tp']:.5f}"),
                   "status": "VALID", "entry_valid": True, "ote_zone": [zl, zh], "tp1": cand.get("tp1"), "tp2": cand["tp"]}
        rk = cand.get("riskPct", 1.0)
        rd = abs(cand["entry"] - cand["sl"]) / PIP
        pv = usd_per_pip or 10 / 0.8
        lots = int(10000 * rk / 100 / (rd * pv) * 100) / 100 if rd else 0
        ok = cand["checklist"][2][1]
        risk_a = {"ui_badge_summary": badge(f"Risk {rk:g}% | SL {rd:.1f}p | {lots} lot/$10k | RR {cand['rr']:.1f}" if ok else f"Rejected: RR {cand['rr']:.1f} < {2.6 if cand['sid'] != 'A' else 3.0:g}"),
                  "status": "VALID" if ok else "VETO", "risk_percent": rk, "position_size_lots": lots, "usd_per_pip_per_lot": round(pv, 2)}
    else:
        tgt = idm if idm is not None else (fib[1] if fib and d_ > 0 else fib[0] if fib else None)
        entry_a = {"ui_badge_summary": badge(f"No clean zone: awaiting {tgt:.4f} sweep & M15 FVG" if tgt else "No clean zone: awaiting M15 trend MSS+FVG"),
                   "status": "WAIT", "entry_valid": False, "ote_zone": fib}
        risk_a = {"ui_badge_summary": "Nothing to size", "status": "STANDBY", "risk_percent": 0.0, "position_size_lots": 0.0}
    sid = cand["sid"] if cand else "A"
    meas = (((research or {}).get("strategies") or {}).get(sid) or {}).get("all")
    base = BASELINE[sid]
    # the rolling check: the last 20 confirmed-trend H1 candles touching the ribbon (12 h apart, CHOICE): did price reach
    # the impulse's external swing before closing beyond the leg's start?
    tests = hits = 0
    q = i1 - 1
    while q > 220 and tests < 20:
        dq = a.trend(q)
        if dq and a.h1[q].low <= max(a.e21[q], a.e55[q]) and a.h1[q].high >= min(a.e21[q], a.e55[q]):
            im = a.impulse(q, dq)
            if im:
                tests += 1
                for r in range(q + 1, min(q + 120, i1)):
                    if (a.h1[r].high >= im[1]) if dq > 0 else (a.h1[r].low <= im[0]):
                        hits += 1
                        break
                    if (a.h1[r].close < im[0]) if dq > 0 else (a.h1[r].close > im[1]):
                        break
                q -= 12
                continue
        q -= 1
    if meas and meas.get("trades", 0) >= 30:
        bt_b, bt_s = f"Data READY: Setup {sid} {meas['winRate']}% WR ({meas['expectancyR']:+.2f}R EV)", "VALID"
    else:
        bt_b, bt_s = f"Data LIMITED: N={(meas or {}).get('trades', 0)} · {hits}/{tests} pullbacks hit TP1", "WARNING"
    backtest_a = {"ui_badge_summary": badge(bt_b), "status": bt_s, "historical_win_rate": None if base["winRate"] is None else base["winRate"] / 100,
                  "expected_value_r": base["expectancyR"], "measured": meas, "spec_benchmark": base, "rolling_er_pullbacks": f"{hits}/{tests}"}
    tw = _twins(twins_m5)
    if cand:
        p, worries = cand["devilP"], cand["worries"]
    else:
        p, worries = 0.0, []
        if sess == "ROLLOVER_LOCKOUT":
            p, worries = 90.0, ["Rollover 20:45-22:30: spreads blow out"]
        elif er is not None and er < 0.25:
            p, worries = 70.0, [f"ER {er:.2f} < 0.25: the EMA ribbon whipsaws"]
        elif tr and idm is not None:
            p, worries = 68.0, [f"Front-running {idm:.4f} IDM risks early stop-out"]
        elif not tr:
            p, worries = 66.0, ["No confirmed H1 risk regime: no trend to join"]
        for twn, inv in ((tw or (None, None))[0], False), ((tw or (None, None))[1], False):
            msg = _shock(twn, t, d_, inv)
            if msg:
                p = min(100.0, p + 35)
                worries.append(msg)
    devil_a = {"ui_badge_summary": badge("My worry: " + (worries[0] if worries else "nothing fatal found")), "status": "VETO" if p >= 65 else "WARNING" if p else "VALID",
               "failure_probability": round(p / 100, 2), "veto_active": p >= 65, "worries": worries,
               "cross_check": "AUD/CAD + EUR/CHF" if tw else "not checked (no AUD/CAD / EUR/CHF candles)",
               "vix": (macro or {}).get("vix")}
    st = 100 if structure_a["status"] == "VALID" else 50 if tr else 0
    lq = 100 if liquidity_a["status"] == "VALID" else 0 if sess == "ROLLOVER_LOCKOUT" else 50
    en = 100 if cand else 0
    bt = 100 if bt_s == "VALID" else 0
    score = round(0.25 * st + 0.25 * lq + 0.20 * en + 0.15 * bt + 0.15 * (100 - p), 1)
    execute = bool(cand and cand["pass"] and score >= 78 and not devil_a["veto_active"] and risk_a["status"] == "VALID" and sess != "ROLLOVER_LOCKOUT")
    if execute:
        decision = "BUY_LIMIT" if cand["dir"] > 0 else "SELL_LIMIT"
        lead_b = f"{decision.replace('_', ' ')} {cand['entry']:.5f} | SL {cand['sl']:.5f} | TP {cand['tp']:.5f}"
        plan = {"order_type": decision, "entry_price": cand["entry"], "stop_loss": cand["sl"], "tp1_price": cand.get("tp1"),
                "tp1_close": cand["part"] if cand.get("tp1") else None, "tp2_price": cand["tp"], "scenario_id": SCEN[cand["sid"]], "risk_percent": cand.get("riskPct", 1.0)}
        scen = SCEN[cand["sid"]]
    else:
        decision, plan = "NO_TRADE", None
        if sess == "ROLLOVER_LOCKOUT" or regime == "NOISY_CHOP":
            scen, lead_b = SCEN["D"], "No trade: rollover lockout" if sess == "ROLLOVER_LOCKOUT" else f"No trade: chop (ER {er:.2f} < 0.22)"
        elif cand:
            scen, lead_b = SCEN[cand["sid"]], f"No trade: consensus {score:.0f} < 78" if score < 78 else "No trade: a veto is active"
        elif regime == "SQUEEZE_COMPRESSION":
            scen, lead_b = SCEN["B"], "No trade: squeeze, I wait for the Zurich expansion"
        elif tr:
            scen = SCEN["A"]
            lead_b = f"No trade: I wait for M15 MSS after {idm:.4f} IDM sweep" if idm is not None else "No trade: I wait for a pullback into the ribbon"
        else:
            scen, lead_b = SCEN["A"], "No trade: no confirmed H1 risk regime yet"
    lead_a = {"ui_badge_summary": badge(lead_b), "status": "VALID" if execute else "VETO" if devil_a["veto_active"] and cand else "WAIT",
              "reasoning": f"{regime}, ER {structure_a['efficiency_ratio_20']}, H1 {structure_a['h1_bias']}, H4 {structure_a['h4_bias']}, {sess}; "
                           f"consensus {score} (CHOICE: the gold spec's weights, >= 78)",
              "execution_plan": plan}
    agents = {"lead_strategist": lead_a, "structure_analyst": structure_a, "liquidity_session_analyst": liquidity_a, "entry_specialist": entry_a,
              "risk_manager": risk_a, "backtest_engineer": backtest_a, "devils_advocate": devil_a}
    contract = {"pair": "AUD/CHF", "strategy_name": STRATEGY_NAME, "timestamp_utc": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scenario_active": scen, "consensus_score": score, "final_decision": decision, "agents": agents}
    ui = []
    for kk in ("lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager", "backtest_engineer", "devils_advocate"):
        ag = agents[kk]
        key, role = ROLE[kk]
        lines = [f"{x}: {y}" for x, y in ag.items() if x not in ("ui_badge_summary", "status") and y not in (None, [], {})]
        ui.append({"key": key, "role": role, "status": UI[ag["status"]], "finding": ag["ui_badge_summary"], "lines": lines, "statusMd": ag["status"]})
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand}
