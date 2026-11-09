"""
EUR/CHF — the user's spec "eur_chf_multi_agent_quantitative_strategy_claude_prompt.md" (2026-11-09), applied to the
letter. It replaces everything earlier for EUR/CHF (SWISS-REV S2 included: git history keeps it).

Strategy: "Ornstein-Uhlenbeck Z-Score & Range Sweep Mean Reversion".
  Scenario A  statistical extreme sweep + mean reversion to equilibrium (H_100 < 0.46, ADX 14 H1 < 28, 06:30-15:30 UTC)
  Scenario B  H4 channel boundary (>= 2 earlier touches) bounce with 1.80 <= |Z| < 2.15 and an M15 OB + FVG
  Scenario C  SNB / European risk-off breakout: H > 0.55, ADX > 32, |Z| > 3.20, RVOL >= 2.5 -> no fade (A and B off)
  Scenario D  |Z| < 1.20 with ATR 14 M15 < 4 pips -> NO_TRADE

Section 3 math, as written: Z_t = (C_t - μ_t) / s_t on M15 with μ the 50-candle SMA and s the sample std (N - 1); the
R/S Hurst exponent H = ln(R/S) / ln(M) over M = 100 H1 log returns; ADX 14 H1; the half-life τ = -ln 2 / ln(1 + β) of
the OLS ΔC_t = α + β C_{t-1} (valid 4-28 M15 bars). Exhaustion (3.4): a swing swept, the candle closes back inside
±2.0σ after piercing ±2.2σ, and an M15 CHoCH or a rejection wick WDR >= 0.45.

Every number the spec leaves open is marked CHOICE and was fixed before any result was seen.
"""

import math
from bisect import bisect_left
from datetime import datetime, timezone
from typing import Optional

from .fiber import F
from .gold import badge, hm
from .playbook import DAY, H1S, M5S, M15S, Daily, _make, adx, fractals, hilo, m5_index_at_close, resample, run, span

PIP = 0.0001
STRATEGY_NAME = "Ornstein-Uhlenbeck Z-Score & Range Sweep Mean Reversion"
NAMES = {"A": "Scenario A · statistical extreme sweep back to the mean", "B": "Scenario B · H4 channel boundary bounce + M15 OB"}
SCEN = {"A": "SCENARIO_A_STATISTICAL_EXTREME_SWEEP", "B": "SCENARIO_B_H4_CHANNEL_OB", "C": "SCENARIO_C_SNB_REGIME_SHIFT",
        "D": "SCENARIO_D_NEUTRAL_EQUILIBRIUM"}
BASELINE = {"A": {"trades": 395, "winRate": 68.6, "avgWin": 1.95, "expectancyR": 1.02, "pf": 2.94, "mdd": -3.9},
            "B": {"trades": 218, "winRate": 63.3, "avgWin": 2.15, "expectancyR": 0.99, "pf": 2.71, "mdd": -4.7}}
# the Devil's "SNB intervention news / European sovereign risk": the calendar's SNB and ECB decisions (BTP-Bund: no feed)
SHOCK = {("CHF", "SNB Policy Rate"), ("CHF", "SNB Monetary Policy Assessment"), ("CHF", "SNB Press Conference"),
         ("EUR", "Main Refinancing Rate"), ("EUR", "Monetary Policy Statement"), ("EUR", "ECB Press Conference")}
N_Z, M_HURST, W_HL = 50, 100, 200  # W_HL: the half-life regression window, 200 M15 candles (CHOICE)
H4_RANGE, NEWS_MIN = 30, 30  # the H4 channel = the last 30 closed H4 candles (CHOICE); SNB / ECB ±30 min (CHOICE)


def shock_times(events) -> list[int]:
    return sorted({int(e["time"]) for e in (events or []) if (e.get("currency"), e.get("title")) in SHOCK})


def zscore_sma(closes: list[float], n: int = N_Z) -> tuple[list, list, list]:
    """3.1: μ_t = SMA n, s_t = the sample std (N - 1) of the same n closes, Z_t = (C_t - μ_t) / s_t."""
    z: list[Optional[float]] = [None] * len(closes)
    mu: list[Optional[float]] = [None] * len(closes)
    sd: list[Optional[float]] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        m = sum(w) / n
        s = (sum((v - m) ** 2 for v in w) / (n - 1)) ** 0.5
        mu[i], sd[i] = m, s
        z[i] = (closes[i] - m) / s if s > 0 else 0.0
    return z, mu, sd


def hurst_rs(closes: list[float], m: int = M_HURST) -> list[Optional[float]]:
    """3.2: H = ln(R/S) / ln(M) over the last M log returns (R: the range of the cumulative deviations from their mean,
    S: their std)."""
    out: list[Optional[float]] = [None] * len(closes)
    r = [0.0] + [math.log(closes[k] / closes[k - 1]) for k in range(1, len(closes))]
    for i in range(m, len(closes)):
        w = r[i - m + 1:i + 1]
        a = sum(w) / m
        y = mx = mn = 0.0
        for v in w:
            y += v - a
            mx, mn = max(mx, y), min(mn, y)
        s = (sum((v - a) ** 2 for v in w) / m) ** 0.5
        if s > 0 and mx > mn:
            out[i] = math.log((mx - mn) / s) / math.log(m)
    return out


def half_life(closes: list[float], i: int, w: int = W_HL) -> Optional[float]:
    """3.3: the OLS slope β of ΔC_t on C_{t-1} over the w candles up to i; τ = -ln 2 / ln(1 + β) (None when β >= 0)."""
    if i < w:
        return None
    x = closes[i - w:i]
    y = [closes[k + 1] - closes[k] for k in range(i - w, i)]
    mx, my = sum(x) / w, sum(y) / w
    vx = sum((a - mx) ** 2 for a in x)
    if vx <= 0:
        return None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / vx
    return -math.log(2) / math.log(1 + b) if -1 < b < 0 else None


class E(F):
    def __init__(self, m5, h1, daily: Daily):
        super().__init__(m5, h1, daily, None)
        self.c15 = [x.close for x in self.m15]
        self.z, self.mu, self.sd = zscore_sma(self.c15, N_Z)
        self.hu = hurst_rs([x.close for x in h1], M_HURST)
        self.ad1 = adx(h1, 14)
        self.f4 = fractals(self.h4)

    def regime(self, t: int) -> tuple[Optional[float], Optional[float]]:
        i = self.i1(t)
        return (self.hu[i], self.ad1[i]) if i >= 0 else (None, None)

    def channel(self, t: int) -> Optional[tuple[float, float, int, int]]:
        """The H4 channel known at t: (low, high, earlier touches of the low, of the high). A touch = an H4 fractal swing
        within 0.25 ATR H4 of the boundary (CHOICE), confirmed (2 candles after it) before t."""
        i4 = self.i4(t)
        if i4 < H4_RANGE + 14:
            return None
        w = self.h4[i4 - H4_RANGE + 1:i4 + 1]
        lo, hi = min(x.low for x in w), max(x.high for x in w)
        tol = 0.25 * (self.at4[i4] or 0)
        hi_f, lo_f = self.f4
        q0 = i4 - H4_RANGE + 1
        n_lo = sum(1 for q in range(q0, i4 - 1) if lo_f[q] and abs(self.h4[q].low - lo) <= tol)
        n_hi = sum(1 for q in range(q0, i4 - 1) if hi_f[q] and abs(self.h4[q].high - hi) <= tol)
        return lo, hi, n_lo, n_hi

    def rvol(self, j: int) -> Optional[float]:
        a = self.vol15_sma[j]
        return self.v15[j] / a if a else None  # None: the feed has no volume

    def eq_pools(self, t: int, d: int) -> list[float]:
        return sorted({round(v, 5) for v in self.eq_levels(t, d)})


def _session(tc: int) -> bool:
    tod = tc % DAY
    return 6 * H1S + 1800 < tod <= 15 * H1S + 1800


def scenario_c(e: E) -> list[tuple[int, int]]:
    """(time, direction) of each M15 close where H > 0.55, ADX > 32, |Z| > 3.20 and RVOL >= 2.5 (the SNB / risk-off break)."""
    out = []
    for j in range(N_Z, len(e.m15)):
        if e.z[j] is None or abs(e.z[j]) <= 3.2:
            continue
        tc = e.m15[j].time + M15S
        h, a = e.regime(tc)
        rv = e.rvol(j)
        if h is not None and a is not None and h > 0.55 and a > 32 and rv is not None and rv >= 2.5:
            out.append((tc, 1 if e.z[j] > 0 else -1))
    return out


def _shock_on(shocks: list, t: int) -> Optional[tuple[int, int]]:
    """Scenario C stays on for 24 h after the last breakout print (CHOICE)."""
    k = bisect_left(shocks, (t + 1,)) - 1
    return shocks[k] if k >= 0 and t - shocks[k][0] <= 24 * H1S else None


def _tp2(entry: float, sl: float, d: int, cands: list, need: float):
    risk = abs(entry - sl)
    good = sorted([(p, n) for n, p in cands if p is not None and (p - entry) * d >= need * risk], key=lambda v: abs(v[0] - entry))
    return good[0] if good else None


def scenario_a(e: E, cost: float, out: list, watch: list, shocks: list) -> None:
    """A: an M15 candle (or the one before it) pierces μ ∓ 2.2σ and takes an M15 fractal swing (or the last H1 swing)
    still intact until then; the candle closes back inside ±2.0σ with a rejection wick WDR >= 0.45 or an M15 CHoCH
    (a close beyond the last M15 swing formed before the extreme). H_100 < 0.46, ADX < 28, 4 <= τ <= 28 M15 bars, the
    close in 06:30-15:30 UTC. Entry: market at the M15 close (CHOICE of the spec's two). SL = the sweep extreme ∓ 0.50
    ATR 14 M15. TP1 μ (Z = 0, 60 % closed); TP2 the opposing 1.25σ band or the opposing range liquidity (PDH / PDL, the
    H1 dealing range's far side), the nearest at >= 2.2 R. No break-even (the spec moves the stop nowhere). Held 24 h
    (CHOICE)."""
    m15, m5 = e.m15, e.m5
    hi_f, lo_f = e.f15
    end = m5[-1].time + M5S
    last = {1: -99, -1: -99}
    for j in range(max(N_Z, 45), len(m15)):
        x = m15[j]
        tc = x.time + M15S
        if tc > end or not _session(tc) or e.mu[j] is None or not e.sd[j]:
            continue
        mu, sd = e.mu[j], e.sd[j]
        for d in (1, -1):  # d: the trade (+1 fades an oversold drop)
            if j - last[d] < 4:
                continue
            pierce = [q for q in (j - 1, j) if e.mu[q] is not None and e.sd[q] and
                      ((m15[q].low < e.mu[q] - 2.2 * e.sd[q]) if d > 0 else (m15[q].high > e.mu[q] + 2.2 * e.sd[q]))]
            if not pierce:
                continue
            qx = min((j - 1, j), key=lambda q: m15[q].low) if d > 0 else max((j - 1, j), key=lambda q: m15[q].high)
            ext = m15[qx].low if d > 0 else m15[qx].high
            z_ext = max(abs((m15[q].low if d > 0 else m15[q].high) - e.mu[q]) / e.sd[q] for q in pierce)
            inside = (x.close > mu - 2.0 * sd) if d > 0 else (x.close < mu + 2.0 * sd)
            if not inside or z_ext < 2.15:
                continue
            pools = []
            for q in range(j - 3, max(j - 40, 0), -1):
                if not (lo_f[q] if d > 0 else hi_f[q]):
                    continue
                lv = m15[q].low if d > 0 else m15[q].high
                kept = all(((m15[r].low >= lv) if d > 0 else (m15[r].high <= lv)) for r in range(q + 1, j - 1))
                if kept and ((ext < lv) if d > 0 else (ext > lv)):
                    pools.append(("M15 swing", lv))
            i1 = e.i1(tc)
            h1sw = (e.s1["sl"] if d > 0 else e.s1["sh"])[i1] if i1 >= 0 else None
            if h1sw and ((ext < h1sw[0]) if d > 0 else (ext > h1sw[0])) and \
               ((m15[j - 2].low >= h1sw[0]) if d > 0 else (m15[j - 2].high <= h1sw[0])):
                pools.append(("H1 swing", h1sw[0]))
            if not pools:
                continue
            pool = min(pools, key=lambda p: abs(p[1] - ext))
            rng = x.high - x.low
            wdr = ((min(x.open, x.close) - x.low) if d > 0 else (x.high - max(x.open, x.close))) / rng if rng > 0 else 0.0
            ref = next((q for q in range(qx - 1, max(qx - 30, 0), -1) if (hi_f[q] if d > 0 else lo_f[q]) and q + 2 <= j), None)
            choch = ref is not None and ((x.close > m15[ref].high) if d > 0 else (x.close < m15[ref].low))
            h, a = e.regime(tc)
            tau = half_life(e.c15, j)
            reg_ok = h is not None and a is not None and h < 0.46 and a < 28
            tau_ok = tau is not None and 4 <= tau <= 28
            shock = _shock_on(shocks, tc)
            steps = [(f"Pierced μ {'-' if d > 0 else '+'}2.2σ (|Z| {z_ext:.2f} >= 2.15)", True, f"{ext:.5f}"),
                     (f"Swept the {pool[0]}", True, f"{pool[1]:.5f}"),
                     ("Closed back inside ±2.0σ", True, f"{x.close:.5f}"),
                     (f"M15 exhaustion: WDR {wdr:.2f} >= 0.45 or a CHoCH", wdr >= 0.45 or choch, "CHoCH" if choch else ""),
                     (f"Regime: H {h if h is None else round(h, 2)} < 0.46, ADX {a if a is None else round(a)} < 28", reg_ok, ""),
                     (f"Half-life 4-28 M15 bars ({'n/a' if tau is None else f'{tau:.1f}'})", tau_ok, ""),
                     ("Scenario C (SNB / risk-off breakout) not active", shock is None, "" if shock is None else f"since {hm(shock[0])}")]
            if not all(ok for _, ok, _ in steps):
                watch.append({"sid": "A", "time": tc, "dir": d, "steps": steps})
                continue
            k0 = m5_index_at_close(e.t5, tc)
            if k0 is None or m5[k0].time + M5S != tc:
                continue
            entry = x.close
            sl = ext - d * 0.5 * (e.at15[j] or 0)
            dr = e.dealing(tc)
            D = tc - tc % DAY
            pd = hilo(span(m5, e.t5, D - DAY, D)) or hilo(span(m5, e.t5, D - 3 * DAY, D - 2 * DAY + 1))
            tp2 = _tp2(entry, sl, d, [("the opposing 1.25σ band", mu + d * 1.25 * sd),
                                      ("PDH" if d > 0 else "PDL", (pd[0] if d > 0 else pd[1]) if pd else None),
                                      ("the H1 dealing range's far side", (dr[1] if d > 0 else dr[0]) if dr else None)], 2.2)
            if not tp2:
                watch.append({"sid": "A", "time": tc, "dir": d, "steps": steps + [("TP2 at >= 2.2 R", False, "none")]})
                continue
            s = _make("EURCHF", "A", d, m5, k0, entry, sl, mu, tp2[0], 0.6, True, 0, tc + 24 * H1S, steps + [("TP2 at >= 2.2 R", True, tp2[1])],
                      {"zscore": (e.z[j], mu, sd), "sweep": (ext, m15[qx].time), "levels": {pool[0]: pool[1]}}, cost, be_off=None)
            if s:
                s.update(scenario="A", tp2Name=tp2[1], hurst=h, adx=a, halfLife=tau, z=z_ext * -d, j=j)
                out.append(s)
                last[d] = j


def scenario_b(e: E, cost: float, out: list, watch: list, shocks: list) -> None:
    """B: an M15 candle tests the H4 channel boundary (within 0.25 ATR H4) that has >= 2 earlier H4 swing touches, with
    1.80 <= |Z| < 2.15 at its extreme; then the M15 MSS with an unmitigated OB + FVG (EUR/USD's definition) within 8
    candles: a limit at the OB's proximal edge, valid 8 M15 candles (CHOICE). SL the touch / OB extreme ∓ 0.50 ATR M15
    (CHOICE: A's rule); TP the H4 channel midpoint. The 3.2 lockout (H > 0.54 or ADX > 32) applies; session 06:30-15:30."""
    m15, m5 = e.m15, e.m5
    end = m5[-1].time + M5S
    used = set()
    for j in range(max(N_Z, 45), len(m15)):
        x = m15[j]
        tc = x.time + M15S
        if tc > end or not _session(tc) or e.mu[j] is None or not e.sd[j]:
            continue
        ch = e.channel(tc)
        if not ch:
            continue
        lo, hi, n_lo, n_hi = ch
        i4 = e.i4(tc)
        tol = 0.25 * (e.at4[i4] or 0)
        for d in (1, -1):
            bound, n = (lo, n_lo) if d > 0 else (hi, n_hi)
            if n < 2 or (i4, d) in used:
                continue
            ext = x.low if d > 0 else x.high
            if not ((ext <= bound + tol) if d > 0 else (ext >= bound - tol)):
                continue
            zx = abs(ext - e.mu[j]) / e.sd[j]
            if not 1.80 <= zx < 2.15:
                continue
            used.add((i4, d))
            h, a = e.regime(tc)
            lock = h is None or a is None or h > 0.54 or a > 32
            shock = _shock_on(shocks, tc)
            steps = [(f"H4 channel {'low' if d > 0 else 'high'} with {n} earlier touches (>= 2)", True, f"{bound:.5f}"),
                     (f"1.80 <= |Z| {zx:.2f} < 2.15", True, ""),
                     (f"No 3.2 lockout: H {h if h is None else round(h, 2)} <= 0.54, ADX {a if a is None else round(a)} <= 32", not lock, ""),
                     ("Scenario C not active", shock is None, "")]
            if lock or shock:
                watch.append({"sid": "B", "time": tc, "dir": d, "steps": steps})
                continue
            z = e.ob_fvg(j, min(j + 8, len(m15)), d, 0)
            if not z or z["t_set"] > end or not _session(z["t_set"]):
                watch.append({"sid": "B", "time": tc, "dir": d, "steps": steps + [("M15 MSS + unmitigated OB + FVG", False, "waiting")]})
                continue
            entry = z["ob"][1] if d > 0 else z["ob"][0]
            j_set = e.j15(z["t_set"])
            extr = min(ext, z["ob"][0]) if d > 0 else max(ext, z["ob"][1])
            sl = extr - d * 0.5 * (e.at15[j_set] or 0)
            tp = (lo + hi) / 2
            k0 = m5_index_at_close(e.t5, z["t_set"])
            if k0 is None:
                continue
            steps += [("M15 MSS + unmitigated OB + FVG", True, f"OB {z['ob'][0]:.5f} - {z['ob'][1]:.5f}"), ("Target: the H4 channel midpoint", True, f"{tp:.5f}")]
            s = _make("EURCHF", "B", d, m5, k0, entry, sl, None, tp, 1.0, False, 24, z["t_set"] + 24 * H1S, steps,
                      {"ob": (z["ob"][1], z["ob"][0], m15[z["j_ob"]].time), "levels": {"H4 channel low": lo, "H4 channel high": hi},
                       "sweep": (ext, x.time)}, cost, zone=(min(z["ob"]), max(z["ob"])), be_off=None)
            if s:
                s.update(scenario="B", tp2Name="the H4 channel midpoint", hurst=h, adx=a, halfLife=half_life(e.c15, j), z=zx * -d, j=j)
                out.append(s)


def blended_r(s: dict) -> float:
    """The Risk Manager's blended TP: 60 % at TP1, 40 % at TP2 (A); the single TP (B)."""
    risk = abs(s["entry"] - s["sl"])
    if not risk:
        return 0.0
    r2 = abs(s["tp"] - s["entry"]) / risk
    if s.get("tp1") is None:
        return r2
    return s["part"] * abs(s["tp1"] - s["entry"]) / risk + (1 - s["part"]) * r2


def devil(e: E, s: dict, nw: Optional[list[int]], shocks: list) -> tuple[float, list[str]]:
    """The spec's three breakout signs, each a HARD VETO: H > 0.52 or ADX > 30; SNB / ECB news within ±30 min (or
    Scenario C on); an M15 candle of the excursion (the 3 before the trigger, CHOICE) closing outside ±2.5σ at its extreme
    (wick <= 5 % of its range, CHOICE "zero wick"). Failure probability: 85 % with any sign, else 25 % in the 0.46-0.52
    caution band, else 10 % (CHOICE)."""
    t, d, j = s["time"], s["dir"], s.get("j")
    worries = []
    h, a = s.get("hurst"), s.get("adx")
    if (h is not None and h > 0.52) or (a is not None and a > 30):
        worries.append(f"Breakout regime: H {h:.2f} / ADX {a:.0f}")
    near = [n for n in (nw or []) if abs(n - t) <= NEWS_MIN * 60]
    if near:
        worries.append(f"SNB / ECB release {hm(near[0])} UTC: one-way CHF flow")
    if _shock_on(shocks, t):
        worries.append("Scenario C: SNB / risk-off breakout on")
    if j is not None:
        for q in range(max(j - 3, 0), j):
            y = e.m15[q]
            if e.mu[q] is None or not e.sd[q]:
                continue
            rng = y.high - y.low
            if d > 0 and y.close < e.mu[q] - 2.5 * e.sd[q] and rng > 0 and (y.close - y.low) <= 0.05 * rng:
                worries.append(f"Falling knife: {hm(y.time)} M15 closed on its low under -2.5σ")
                break
            if d < 0 and y.close > e.mu[q] + 2.5 * e.sd[q] and rng > 0 and (y.high - y.close) <= 0.05 * rng:
                worries.append(f"Rocket: {hm(y.time)} M15 closed on its high over +2.5σ")
                break
    if worries:
        return 85.0, worries
    return (25.0, ["Hurst in the random-walk band"]) if h is not None and h >= 0.46 else (10.0, [])


def scan(m5, h1, cost: float, news_events=None, d1=None) -> tuple[list, list]:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    e = E(m5, h1, daily)
    out, watch = [], []
    if len(e.m15) < 120 or len(h1) < 150:
        return out, watch
    shocks = scenario_c(e)
    scenario_a(e, cost, out, watch, shocks)
    scenario_b(e, cost, out, watch, shocks)
    out.sort(key=lambda x: x["time"])
    nw = shock_times(news_events) if news_events is not None else None
    for s in out:
        if nw and not s["market"]:  # a pending limit is cancelled around SNB / ECB
            s["result"] = run(m5, s["index"], s["dir"], s["entry"], s["sl"], s["tp1"], s["tp"], s["part"], False, s["expiry"], s["holdUntil"], cost,
                              None, nw, None, None, None, NEWS_MIN)
        p, worries = devil(e, s, nw, shocks)
        s["devilP"], s["worries"] = p, worries
        risk = abs(s["entry"] - s["sl"])
        spread = cost / risk if risk else 1.0
        br = blended_r(s)
        s["blendedR"] = br
        h, a, tau = s.get("hurst"), s.get("adx"), s.get("halfLife")
        s["checklist"] = [
            (f"1 · {NAMES[s['sid']]}", True, STRATEGY_NAME),
            ("2 · Regime: H < 0.46 and ADX < 28" if s["sid"] == "A" else "2 · Regime: no lockout (H <= 0.54, ADX <= 32)",
             h is not None and a is not None and ((h < 0.46 and a < 28) if s["sid"] == "A" else (h <= 0.54 and a <= 32)),
             f"H {h:.2f} · ADX {a:.0f}" if h is not None and a is not None else "n/a"),
            ("3 · Half-life 4-28 M15 bars" + (" (A)" if s["sid"] == "A" else " (reported)"),
             s["sid"] != "A" or (tau is not None and 4 <= tau <= 28), "n/a" if tau is None else f"{tau:.1f} bars"),
            (f"4 · Risk Manager: spread {spread * 100:.0f} % of SL (< 12 %), blended RR {br:.2f} (>= 1.85)", spread < 0.12 and br >= 1.85 - 1e-9,
             s.get("tp2Name", "")),
            ("5 · Lot for 1 % risk (10 CHF / pip / lot at the live USD/CHF)", True, ""),
            (f"6 · Devil's Advocate: failure probability {p:.0f} % (< 65 %)", p < 65,
             ("; ".join(worries) or "no breakout sign") + ("" if nw is not None else " · SNB / ECB not checked (no news history)")),
        ]
        s["pass"] = all(ok for _, ok, _ in s["checklist"])
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("7 · One EUR/CHF trade at a time", False, "the previous setup is still pending or open"))
            continue
        r = s["result"]
        busy = m5[r["at"]].time + M5S if "at" in r else 1 << 62
    return out, sorted(watch, key=lambda w: w["time"])


UI = {"VALID": "ok", "WAIT": "wait", "WARNING": "warn", "VETO": "veto", "STANDBY": "wait"}
ROLE = {"lead_strategist": ("lead", "Lead Strategist"), "structure_analyst": ("structure", "Structure Analyst"),
        "liquidity_session_analyst": ("liquidity", "Liquidity & Session Analyst"), "entry_specialist": ("entry", "Entry Specialist"),
        "risk_manager": ("risk", "Risk Manager"), "backtest_engineer": ("backtest", "Backtest Engineer"), "devils_advocate": ("devil", "Devil's Advocate")}


def report(m5, h1, now: int, setups: list, watch: list, research: Optional[dict], news_events, d1=None,
           usd_per_pip: Optional[float] = None) -> dict:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    e = E(m5, h1, daily)
    t = m5[-1].time + M5S
    price = m5[-1].close
    D = t - t % DAY
    j = e.j15(t)
    zc, mu, sd = (e.z[j], e.mu[j], e.sd[j]) if j >= 0 else (None, None, None)
    h, a = e.regime(t)
    tau = half_life(e.c15, j) if j >= 0 else None
    at15 = e.at15[j] if j >= 0 else None
    shocks = scenario_c(e)
    shock = _shock_on(shocks, t)
    if h is not None and a is not None and h < 0.46 and a < 28:
        regime = "MEAN_REVERTING_RANGE"
    elif (h is not None and h > 0.54) or (a is not None and a > 32):
        regime = "MACRO_BREAKOUT"
    else:
        regime = "TRANSITIONAL"
    ch = e.channel(t)
    dr = e.dealing(t)
    z_txt = "n/a" if zc is None else f"{zc:+.2f}" + (" (Oversold)" if zc <= -2.15 else " (Overbought)" if zc >= 2.15 else "")
    reg_txt = {"MEAN_REVERTING_RANGE": "Range", "MACRO_BREAKOUT": "Breakout", "TRANSITIONAL": "Transitional"}[regime]
    structure_a = {"ui_badge_summary": badge(f"H1 {reg_txt} (H={h:.2f}) | Z-Score: {z_txt}" if h is not None else f"H1 {reg_txt} | Z-Score: {z_txt}"),
                   "status": "VALID" if regime == "MEAN_REVERTING_RANGE" else "VETO" if regime == "MACRO_BREAKOUT" else "WAIT",
                   "regime": regime, "hurst_exponent": None if h is None else round(h, 3), "adx_14": None if a is None else round(a, 1),
                   "z_score": None if zc is None else round(zc, 2), "rolling_mean": mu,
                   "sigma_bands": {"plus_2_15": mu + 2.15 * sd, "minus_2_15": mu - 2.15 * sd, "plus_2_0": mu + 2 * sd, "minus_2_0": mu - 2 * sd,
                                   "plus_2_5": mu + 2.5 * sd, "minus_2_5": mu - 2.5 * sd} if mu is not None else None,
                   "h4_range": {"low": ch[0], "high": ch[1], "touches_low": ch[2], "touches_high": ch[3], "midpoint": (ch[0] + ch[1]) / 2} if ch else None,
                   "h1_range": {"low": dr[0], "high": dr[1], "equilibrium": dr[2]} if dr else None}
    active = _session(t)
    pd = hilo(span(m5, e.t5, D - DAY, D)) or hilo(span(m5, e.t5, D - 3 * DAY, D - 2 * DAY + 1))
    bsl = sorted({round(v, 5) for v in [pd and pd[0], ch and ch[1], dr and dr[1]] + e.eq_pools(t, -1) if v and v > price})
    ssl = sorted({round(v, 5) for v in [pd and pd[1], ch and ch[0], dr and dr[0]] + e.eq_pools(t, 1) if v and v < price}, reverse=True)
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE")]
    cand = next((s for s in reversed(live) if s["pass"]), live[-1] if live else None)
    w = watch[-1] if watch and watch[-1]["time"] >= now - 2 * H1S else None
    swept = cand is not None or bool(w and w["sid"] == "A")
    if swept:
        d_ = (cand or w)["dir"]
        ext = cand["geo"]["sweep"][0] if cand else next((s_[2] for s_ in w["steps"] if s_[0].startswith("Pierced")), "")
        lq_b = f"{'SSL' if d_ > 0 else 'BSL'} swept at {ext} | Z={z_txt.split(' ')[0]} | " + ("Zurich active" if active else "Off-hours")
    else:
        lq_b = f"Range BSL at {bsl[0]:.4f} | SSL at {ssl[0]:.4f} | " if bsl and ssl else ""
        lq_b += "Zurich active" if active else "Off-hours"
    liquidity_a = {"ui_badge_summary": badge(lq_b), "status": ("VALID" if swept else "WAIT") if active else "WARNING",
                   "active_session": "ZURICH_FRANKFURT_LONDON" if active else "OFF_HOURS", "bsl_targets": bsl[:4], "ssl_targets": ssl[:4],
                   "sweep_detected": swept, "note": None if active else "late US / Asian hours: low CHF liquidity, wide spreads"}
    if cand:
        zl, zh = min(cand["zone"]), max(cand["zone"])
        entry_a = {"ui_badge_summary": badge(f"Fade {'long' if cand['dir'] > 0 else 'short'} {cand['entry']:.5f} | TP1 μ {cand['tp1']:.5f}" if cand["tp1"]
                                             else f"M15 OB {zl:.5f}-{zh:.5f} | TP mid {cand['tp']:.5f}"),
                   "status": "VALID", "entry_valid": True, "entry": cand["entry"], "tp1": cand["tp1"], "tp2": cand["tp"]}
        rd = abs(cand["entry"] - cand["sl"]) / PIP
        pv = usd_per_pip or 10 / 0.8
        lots = int(10000 * 0.01 / (rd * pv) * 100) / 100 if rd else 0
        ok = cand["checklist"][3][1]
        risk_a = {"ui_badge_summary": badge(f"Risk 1% | SL {rd:.1f}p | {lots} lot/$10k | RR {cand['blendedR']:.2f}" if ok else
                                            f"Rejected: blended RR {cand['blendedR']:.2f} / spread"),
                  "status": "VALID" if ok else "VETO", "risk_percent": 1.0, "position_size_lots": lots, "usd_per_pip_per_lot": round(pv, 2),
                  "blended_rr": round(cand["blendedR"], 2)}
    else:
        entry_a = {"ui_badge_summary": "No clean zone: Z-score neutral" if zc is None or abs(zc) < 1.80 else "No clean zone: awaiting M15 exhaustion",
                   "status": "WAIT", "entry_valid": False}
        risk_a = {"ui_badge_summary": "Nothing to size", "status": "STANDBY", "risk_percent": 0.0, "position_size_lots": 0.0}
    sid = cand["sid"] if cand else "A"
    meas = (((research or {}).get("strategies") or {}).get(sid) or {}).get("all")
    base = BASELINE[sid]
    tau_ok = tau is not None and 4 <= tau <= 28
    tau_txt = "n/a" if tau is None else f"{tau:.0f} bars"
    if meas and meas.get("trades", 0) >= 30:
        bt_b = f"Data {'READY' if tau_ok else 'WARN'}: Half-life {tau_txt} | {meas['winRate']}% WR"
    else:
        bt_b = f"Data {'READY' if tau_ok else 'WARN'}: Half-life {tau_txt} | N={(meas or {}).get('trades', 0)} measured"
    backtest_a = {"ui_badge_summary": badge(bt_b), "status": "VALID" if tau_ok and meas and meas.get("trades", 0) >= 30 else "WARNING",
                  "half_life_bars": None if tau is None else round(tau, 1), "historical_win_rate": base["winRate"] / 100,
                  "expected_value_r": base["expectancyR"], "measured": meas, "spec_benchmark": base}
    nw = shock_times(news_events) if news_events is not None else None
    if cand:
        p, worries = cand["devilP"], cand["worries"]
    else:
        near = [n for n in (nw or []) if abs(n - now) <= NEWS_MIN * 60]
        if (h is not None and h > 0.52) or (a is not None and a > 30):
            p, worries = 85.0, [f"Breakout regime H {h:.2f} / ADX {a:.0f}: falling knife"]
        elif shock or near:
            p, worries = 85.0, ["SNB / risk-off breakout: one-way CHF flow"]
        elif zc is None or abs(zc) < 1.80:
            p, worries = 82.0, ["Zero statistical stretch at current price"]
        elif not active:
            p, worries = 70.0, ["Off-hours: CHF spreads widen"]
        else:
            p, worries = 25.0, ["Stretch without M15 exhaustion yet"]
    devil_a = {"ui_badge_summary": badge("My worry: " + (worries[0] if worries else "nothing fatal found")), "status": "VETO" if p >= 65 else "WARNING" if p else "VALID",
               "failure_probability": round(p / 100, 2), "veto_active": p >= 65, "worries": worries,
               "btp_bund": "not checked (no feed)", "news": "not checked (no calendar)" if nw is None else "SNB / ECB ±30 min"}
    st = 100 if regime == "MEAN_REVERTING_RANGE" else 50 if regime == "TRANSITIONAL" else 0
    lq = 100 if liquidity_a["status"] == "VALID" else 50 if active else 0
    en = 100 if cand else 0
    bt = 100 if backtest_a["status"] == "VALID" else 0
    score = round(0.25 * st + 0.25 * lq + 0.20 * en + 0.15 * bt + 0.15 * (100 - p), 1)
    execute = bool(cand and cand["pass"] and active and score >= 78 and not devil_a["veto_active"] and risk_a["status"] == "VALID")
    if execute:
        decision = ("BUY_MARKET" if cand["dir"] > 0 else "SELL_MARKET") if cand["market"] else ("BUY_LIMIT" if cand["dir"] > 0 else "SELL_LIMIT")
        lead_b = f"{decision.replace('_', ' ')} {cand['entry']:.5f} | SL {cand['sl']:.5f} | TP {cand['tp']:.5f}"
        plan = {"order_type": decision, "entry_price": cand["entry"], "stop_loss": cand["sl"], "tp1_price": cand.get("tp1"), "tp1_close": cand["part"] if cand.get("tp1") else None,
                "tp2_price": cand["tp"], "scenario_id": SCEN[cand["sid"]]}
        scen = SCEN[cand["sid"]]
    else:
        decision, plan = "NO_TRADE", None
        if shock:
            scen, lead_b = SCEN["C"], "No trade: SNB / risk-off breakout, I do not fade"
        elif cand:
            scen, lead_b = SCEN[cand["sid"]], f"No trade: consensus {score:.0f} < 78" if score < 78 else "No trade: a veto is active"
        elif zc is None or abs(zc) < 1.80:
            scen = SCEN["D"] if zc is None or abs(zc) < 1.20 else SCEN["A"]
            lead_b = f"No trade: Z-Score at {zc:+.2f} (waiting for |Z|>=2.15)" if zc is not None else "No trade: no Z-score yet"
        else:
            scen, lead_b = (SCEN["B"] if abs(zc) < 2.15 else SCEN["A"]), f"No trade: Z {zc:+.2f}, I wait for M15 exhaustion"
    d_note = " ATR M15 < 4 pips" if at15 is not None and at15 < 4 * PIP else ""
    lead_a = {"ui_badge_summary": badge(lead_b), "status": "VALID" if execute else "VETO" if devil_a["veto_active"] and cand else "WAIT",
              "reasoning": f"{regime}, H {structure_a['hurst_exponent']}, ADX {structure_a['adx_14']}, Z {structure_a['z_score']} around the 50-bar mean "
                           f"{mu if mu is None else round(mu, 5)}{d_note}; consensus {score} (CHOICE: the gold spec's weights, >= 78)",
              "execution_plan": plan}
    agents = {"lead_strategist": lead_a, "structure_analyst": structure_a, "liquidity_session_analyst": liquidity_a, "entry_specialist": entry_a,
              "risk_manager": risk_a, "backtest_engineer": backtest_a, "devils_advocate": devil_a}
    contract = {"pair": "EUR/CHF", "strategy_name": STRATEGY_NAME, "timestamp_utc": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scenario_active": scen, "consensus_score": score, "final_decision": decision, "agents": agents}
    ui = []
    for kk in ("lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager", "backtest_engineer", "devils_advocate"):
        ag = agents[kk]
        key, role = ROLE[kk]
        lines = [f"{x}: {y}" for x, y in ag.items() if x not in ("ui_badge_summary", "status") and y not in (None, [], {})]
        ui.append({"key": key, "role": role, "status": UI[ag["status"]], "finding": ag["ui_badge_summary"], "lines": lines, "statusMd": ag["status"]})
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand}
