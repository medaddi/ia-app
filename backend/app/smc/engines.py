"""
The pair-specific quantitative engines of the master spec "Pair-Specific Quantitative Trading Teams" (the user's
quantitative_trading_teams_claude_master_prompt.md, 2026-11-08), coded rule by rule:

  XAU/USD  GOLD-QUANT S1–S4   session liquidity sweep + M5 volatility displacement + true FVG
  EUR/USD  INST-AMD S1–S4     Asia accumulation → London / NY Judas manipulation → distribution, with the daily VWAP
  GBP/USD  CABLE-RAID S1–S4   deep stop-hunt with an M15 close reclaim + M5 breaker, London squeeze, NY OB pullback
  EUR/CHF  SWISS-REV S1–S3    Z-score (EMA 50) mean reversion at range extremes, VWAP ±2.5σ exhaustion
  AUD/CHF  RISK-REGIME S1–S4  ADX + Kaufman efficiency ratio regime switch: trend OTE pullback or range fade

Kept from the earlier guide because they passed the user's rule (win rate >= 55 % and profitable in both halves of the
year test): EUR/USD SnapBack 3σ (id SB) and AUD/CAD range reversion (id P), in playbook.py.

Data hygiene (the spec's part 3): an FVG counts only when its 3 candles are consecutive (no missing bar) and none opens
more than 0.35 ATR away from the previous close (true_fvg); a sweep inside the daily rollover (21:50-22:15 UTC) or made
by one abnormal candle (range > 3 ATR) is ignored (true_sweep). Every swing is known 2 candles after it; a setup is
dated at the close of the last candle it needs; trades are followed on M5 by playbook.run. Where the spec leaves a
choice, the code says "CHOICE".
"""

from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from typing import Optional

from .playbook import (DAY, H1S, H4S, M5S, M15S, Daily, _h1_bias, _make, adx, atr, body, ema, fractals, hilo,
                       m5_index_at_close, resample, rsi, span)

ROLL0, ROLL1 = 21 * H1S + 50 * 60, 22 * H1S + 15 * 60


# ---------------------------------------------------------------- the spec's indicators
def zscore(closes: list[float], n: int = 50) -> tuple[list, list, list]:
    """Z_t = (C_t - EMA_n) / sigma_t, sigma_t = sqrt(mean over the last n of (C - EMA_n,t)^2). Returns (z, mu, sigma)."""
    mu = ema(closes, n)
    z: list[Optional[float]] = [None] * len(closes)
    sg: list[Optional[float]] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        if mu[i] is None:
            continue
        s = (sum((closes[i - k] - mu[i]) ** 2 for k in range(n)) / n) ** 0.5
        sg[i] = s
        z[i] = (closes[i] - mu[i]) / s if s > 0 else 0.0
    return z, mu, sg


def efficiency(closes: list[float], n: int = 30) -> list[Optional[float]]:
    """Kaufman efficiency ratio ER_n = |C_t - C_{t-n}| / sum |C_{t-i} - C_{t-i-1}|."""
    out: list[Optional[float]] = [None] * len(closes)
    for i in range(n, len(closes)):
        path = sum(abs(closes[i - k] - closes[i - k - 1]) for k in range(n))
        out[i] = abs(closes[i] - closes[i - n]) / path if path > 0 else 0.0
    return out


def vwap(m5) -> tuple[list, list]:
    """The daily VWAP anchored at 00:00 UTC on typical price (H+L+C)/3, and its standard deviation. Weights are the
    volumes; a feed without volume (Yahoo forex) weighs every candle the same (CHOICE: a TWAP, stated)."""
    vw: list[Optional[float]] = [None] * len(m5)
    sd: list[Optional[float]] = [None] * len(m5)
    day, sw, swp, swp2 = None, 0.0, 0.0, 0.0
    for i, x in enumerate(m5):
        d = x.time - x.time % DAY
        if d != day:
            day, sw, swp, swp2 = d, 0.0, 0.0, 0.0
        w = x.volume if getattr(x, "volume", 0) and x.volume > 0 else 1.0
        tp = (x.high + x.low + x.close) / 3
        sw, swp, swp2 = sw + w, swp + w * tp, swp2 + w * tp * tp
        m = swp / sw
        vw[i], sd[i] = m, max(swp2 / sw - m * m, 0.0) ** 0.5
    return vw, sd


def range_pos(c, i: int, n: int) -> Optional[tuple[float, float, float]]:
    """The dealing range of the last n candles up to i: (low, high, position of the close in %)."""
    if i < n - 1:
        return None
    lo, hi = min(x.low for x in c[i - n + 1:i + 1]), max(x.high for x in c[i - n + 1:i + 1])
    return (lo, hi, 100 * (c[i].close - lo) / (hi - lo)) if hi > lo else None


def true_fvg(c, j: int, step: int, at: Optional[float]) -> Optional[tuple[int, float, float]]:
    """(dir, bottom, top) of the 3-candle FVG ending at j, ONLY when the 3 candles are consecutive (no missing bar) and
    neither later candle opens more than 0.35 ATR from the previous close: a feed gap is not a fair value gap."""
    if j < 2 or at is None:
        return None
    a, m, b = c[j - 2], c[j - 1], c[j]
    if b.time - m.time != step or m.time - a.time != step:
        return None
    if abs(m.open - a.close) > 0.35 * at or abs(b.open - m.close) > 0.35 * at:
        return None
    if b.low > a.high:
        return (1, a.high, b.low)
    if b.high < a.low:
        return (-1, b.high, a.low)
    return None


def true_sweep(x, at: Optional[float]) -> bool:
    """A candle that can take liquidity for real: not in the daily rollover (21:50-22:15 UTC), not a bad tick (its range
    over 3 ATR, CHOICE)."""
    t = x.time % DAY
    return not (ROLL0 <= t < ROLL1) and (at is None or x.high - x.low <= 3 * at)


def displacement(x, at: Optional[float]) -> bool:
    """|C - O| >= 1.5 ATR(14) and body / range >= 0.65."""
    rng = x.high - x.low
    return at is not None and rng > 0 and body(x) >= 1.5 * at and body(x) / rng >= 0.65


def feed_check(m5, at5, n: int = 300) -> dict:
    """The live feed's health on the last n M5 candles (weekends and the daily close excepted): missing bars, abnormal
    open jumps (> 0.35 ATR). Zones with a defect are FEED_GAP_IGNORED (true_fvg skips them)."""
    if len(m5) < 3:
        return {"bars": 0, "gaps": 0, "jumps": 0, "share": 1.0, "recentGap": True}
    k0 = max(1, len(m5) - n)
    gaps = jumps = 0
    recent = False
    for k in range(k0, len(m5)):
        dt = m5[k].time - m5[k - 1].time
        wd = datetime.fromtimestamp(m5[k - 1].time, timezone.utc).weekday()
        closed = (wd >= 4 and dt <= 3 * DAY) or (ROLL0 - 3600 <= m5[k - 1].time % DAY < ROLL1 + 3600 and dt <= 2 * H1S)
        bad = dt != M5S and not closed
        jump = at5[k] is not None and abs(m5[k].open - m5[k - 1].close) > 0.35 * at5[k] and not closed
        gaps += bad
        jumps += jump
        if (bad or jump) and k >= len(m5) - 20:
            recent = True
    tot = len(m5) - k0
    return {"bars": tot, "gaps": gaps, "jumps": jumps, "share": (gaps + jumps) / tot if tot else 1.0, "recentGap": recent}


class Ctx:
    """Everything an engine reads, computed once per scan (each value at index i uses candles up to i only)."""

    def __init__(self, m5, h1, daily: Daily):
        self.m5, self.h1, self.daily = m5, h1, daily
        self.t5 = [x.time for x in m5]
        self.at5 = atr(m5, 14)
        self.hi5, self.lo5 = fractals(m5)
        self.m15 = resample(m5, M15S)
        self.t15 = [x.time for x in self.m15]
        self.at15 = atr(self.m15, 14)
        self.hi15, self.lo15 = fractals(self.m15)
        self.t1 = [x.time for x in h1]
        self.at1 = atr(h1, 14)
        self.ad1 = adx(h1, 14)
        self.hhi, self.hlo = fractals(h1)
        self.c1 = [x.close for x in h1]
        self.vw, self.vsd = vwap(m5)

    def h1_at(self, t: int) -> int:
        """Index of the last H1 candle CLOSED at time t."""
        return bisect_right(self.t1, t - H1S) - 1

    def m15_at(self, t: int) -> int:
        return bisect_right(self.t15, t - M15S) - 1

    def bias(self, t: int) -> int:
        return _h1_bias(self.h1, self.t1, self.hhi, self.hlo, t)

    def day_hilo(self, a: int, b: int):
        return hilo(span(self.m5, self.t5, a, b))


def _mss_fvg(cx: Ctx, k: int, d: int, ext_k: int, fvg_t0: int = 0, fvg_t1: int = 1 << 62):
    """Candle k closes beyond the last M5 swing before the sweep extreme (the MSS / CHoCH) as a displacement candle; then
    the last TRUE FVG of the move (its 3rd candle opening in [fvg_t0, fvg_t1), up to 2 candles after k).
    Returns (level, fvg (bottom, top), k_fvg) or None."""
    m5 = cx.m5
    ref = next((j for j in range(ext_k - 1, max(ext_k - 80, 0), -1) if (cx.hi5[j] if d > 0 else cx.lo5[j])), None)
    if ref is None or k < ref + 2:
        return None
    lvl = m5[ref].high if d > 0 else m5[ref].low
    x = m5[k]
    if not ((d > 0 and x.close > lvl) or (d < 0 and x.close < lvl)) or not displacement(x, cx.at5[k]):
        return None
    fvg, kf = None, None
    for j in range(ext_k + 2, min(k + 3, len(m5))):
        g = true_fvg(m5, j, M5S, cx.at5[j])
        if g and g[0] == d and fvg_t0 <= m5[j].time < fvg_t1:
            fvg, kf = (g[1], g[2]), j
    return (lvl, fvg, kf) if fvg else (lvl, None, None)


def _raid(cx: Ctx, key: str, sid: str, d: int, w0: int, w1: int, levels: dict, max_depth: Optional[float], sl_of, tgt_of,
          need: float, pre: list, cost: float, expiry_until: int, hold_until: int, geo: dict, out: list, watch: list,
          fvg_t0: int = 0, fvg_t1: int = 1 << 62, ote: bool = False) -> None:
    """The shared raid: in [w0, w1) a TRUE sweep of one of `levels` (sell-side lows for a buy d=+1, buy-side highs for a
    sell), no deeper than max_depth; then the M5 MSS with displacement and a true FVG; a limit at the FVG's start (or at
    the 70 % OTE of the displacement leg when ote=True, CHOICE: the middle of 62-79 %); stop sl_of(extreme, entry);
    target tgt_of(entry) as (name, price) with at least `need` R, else the nearest (question 3 then says no)."""
    m5 = cx.m5
    ks, ke = bisect_left(cx.t5, w0), bisect_left(cx.t5, w1)
    if ke - ks < 3 or not levels:
        return
    k_sw = name = None
    for k in range(ks, ke):
        x = m5[k]
        if not true_sweep(x, cx.at5[k]):
            continue
        hit = [n for n, v in levels.items() if (x.low < v if d > 0 else x.high > v)]
        if hit:
            k_sw, name = k, hit[0]
            break
    if k_sw is None:
        return
    lv = levels[name]
    steps = pre + [(f"True sweep of the {name}", True, f"{lv:.5f}" if lv < 100 else f"{lv:.2f}")]
    ext_k, found = k_sw, None
    for k in range(k_sw, ke):
        if (d > 0 and m5[k].low < m5[ext_k].low) or (d < 0 and m5[k].high > m5[ext_k].high):
            ext_k = k
        depth = (lv - m5[ext_k].low) if d > 0 else (m5[ext_k].high - lv)
        if max_depth is not None and depth > max_depth:
            watch.append({"sid": sid, "time": m5[k].time + M5S, "dir": d, "steps": steps + [("Sweep depth inside the limit", False, "too deep: a breakdown, not a raid")]})
            return
        r = _mss_fvg(cx, k, d, ext_k, fvg_t0, fvg_t1)
        if r:
            found = (k, r)
            break
    if not found:
        watch.append({"sid": sid, "time": m5[k_sw].time + M5S, "dir": d, "steps": steps + [("M5 MSS with displacement (1.5 ATR, body 65 %)", False, "waiting")]})
        return
    k_m, (mss, fvg, kf) = found
    steps.append(("M5 MSS with a displacement candle (>= 1.5 ATR, body >= 65 %)", True, f"{mss:.5f}" if mss < 100 else f"{mss:.2f}"))
    if fvg is None:
        watch.append({"sid": sid, "time": m5[k_m].time + M5S, "dir": d, "steps": steps + [("True FVG in the move (no feed gap)", False, "none")]})
        return
    k0 = max(k_m, kf)
    t_set = m5[k0].time + M5S
    if t_set >= expiry_until:
        return
    sx = m5[ext_k].low if d > 0 else m5[ext_k].high
    if ote:
        top = max(m5[q].high for q in range(ext_k, k0 + 1)) if d > 0 else min(m5[q].low for q in range(ext_k, k0 + 1))
        entry = top - d * 0.705 * abs(top - sx)
    else:
        entry = fvg[1] if d > 0 else fvg[0]
    sl = sl_of(sx, entry, k0)
    tg = tgt_of(entry)
    if not tg:
        return
    risk = abs(entry - sl)
    if risk <= 0:
        return
    finals = sorted([t for t in tg if not t[0].startswith("TP1") and (t[1] - entry) * d > 0], key=lambda t: abs(t[1] - entry))
    good = [t for t in finals if abs(t[1] - entry) >= need * risk]
    if not finals:
        return
    tn, tp = (good or finals)[0]
    tp1 = next((t[1] for t in tg if t[0].startswith("TP1") and (t[1] - entry) * d > 0 and abs(t[1] - entry) < abs(tp - entry)), None)
    steps += [("True FVG left by the move", True, f"{fvg[0]:.5f} - {fvg[1]:.5f}" if fvg[0] < 100 else f"{fvg[0]:.2f} - {fvg[1]:.2f}"),
              (f"Target: {tn}", True, f"{tp:.5f}" if tp < 100 else f"{tp:.2f}")]
    s = _make(key, sid, d, m5, k0, entry, sl, tp1, tp, 0.5, False, max(1, (expiry_until - t_set) // M5S), hold_until, steps,
              {**geo, "fvg": (fvg[0], fvg[1], m5[kf - 2].time), "sweep": (sx, m5[ext_k].time), "mss": (mss, m5[k_m].time)}, cost, zone=fvg)
    if s:
        out.append(s)


def _days(m5) -> list[int]:
    return sorted({x.time - x.time % DAY for x in m5 if datetime.fromtimestamp(x.time, timezone.utc).weekday() < 5})


# ---------------------------------------------------------------- XAU/USD · GOLD-QUANT S1–S4
def gold(cx: Ctx, pip: float, cost: float) -> tuple[list, list]:
    """Levels: Asian range 00:00-06:00 UTC, London range 07:00-10:30 UTC (CHOICE: the London killzone), PDH / PDL (the
    previous UTC day). Asian compression: its range <= 0.85 ATR daily (14) (CHOICE: the 14-day average range).
    Killzones: London 07:00-10:30, NY / COMEX 12:30-16:00 UTC.
    S1 buy: H1 bullish or price in discount (<= 35 % of the 48-candle H1 range, CHOICE) → a true sweep of the Asian low /
       London low / PDL no deeper than 0.6 ATR H1 → M5 CHoCH with a displacement candle → limit at the true FVG's start;
       stop 0.25 ATR M5 under the sweep; TP1 the swept range's 50 % (half, break-even), TP2 the opposite side (Asian
       high / London high / PDH), at least 1:2.2.
    S2 sell: the mirror in premium (>= 65 %) or H1 bearish, sweep of the Asian high / London high / PDH.
    S3 NY continuation: London (07:00-12:30) closed an H1 candle beyond the Asian high (low) with ADX H1 > 28; in NY
       12:30-15:00 an M15 swing low (high) is swept inside the H1 order block (the last opposite H1 candle before the
       breakout, CHOICE) and an M15 candle closes back above (below) it: entry at that close; stop 0.25 ATR M5 beyond the
       sweep; target the London high (low) if 1:2.2, else 2.2 R (CHOICE).
    S4 PDH / PDL rejection: in a killzone a true sweep of PDH (PDL), an M15 close back inside, then the M15 MSS (close
       beyond the last M15 swing): entry at that close; stop 0.25 ATR M5 beyond the sweep; TP1 the previous day's 50 %,
       TP2 its other side.
    Vetoes (question 6 / the devil): ATR H1 over 2.5x its 20-candle mean (parabolic), today's range over 120 % of ADR 14,
    ADX H1 over 48. Closed at 20:00 UTC (CHOICE)."""
    out, watch = [], []
    m5, h1 = cx.m5, cx.h1
    if len(m5) < 300 or len(h1) < 60:
        return out, watch
    for D in _days(m5):
        asia = cx.day_hilo(D, D + 6 * H1S)
        lon = cx.day_hilo(D + 7 * H1S, D + 10 * H1S + 1800)
        pd = cx.day_hilo(D - DAY, D) or cx.day_hilo(D - 3 * DAY, D - 2 * DAY + 1)
        adr = cx.daily.adr(D, 14)
        if not asia or not adr:
            continue
        comp = (asia[0] - asia[1]) <= 0.85 * adr
        for w0, w1, kz in ((D + 7 * H1S, D + 10 * H1S + 1800, "London"), (D + 12 * H1S + 1800, D + 16 * H1S, "NY / COMEX")):
            i1 = cx.h1_at(w0)
            if i1 < 50:
                continue
            at1 = cx.at1[i1]
            rp = range_pos(h1, i1, 48)
            bias = cx.bias(w0)
            mean20 = sum(v for v in cx.at1[i1 - 19:i1 + 1] if v) / 20 if all(cx.at1[i1 - 19:i1 + 1]) else None
            parab = bool(mean20 and at1 and at1 > 2.5 * mean20)
            hi_adx = bool(cx.ad1[i1] and cx.ad1[i1] > 48)
            if not at1 or not rp or parab or hi_adx:
                continue
            for d in (1, -1):
                ok_ctx = (bias == 1 or rp[2] <= 35) if d > 0 else (bias == -1 or rp[2] >= 65)
                if not ok_ctx:
                    continue
                lv = {"Asian low": asia[1], "London low": lon[1] if lon and kz != "London" else None, "PDL": pd[1] if pd else None} if d > 0 else \
                     {"Asian high": asia[0], "London high": lon[0] if lon and kz != "London" else None, "PDH": pd[0] if pd else None}
                lv = {k: v for k, v in lv.items() if v is not None}
                pre = [(f"{kz} killzone", True, ""), (f"Asian range compressed (<= 0.85 ATR daily: {(asia[0] - asia[1]):.2f} / {0.85 * adr:.2f})", comp, ""),
                       (f"H1 {'bullish or discount' if d > 0 else 'bearish or premium'} ({rp[2]:.0f} % of the range)", True, "")]
                if not comp:
                    continue

                def tgt(entry, d=d):
                    side = [("TP1 Asian 50 %", (asia[0] + asia[1]) / 2), ("the Asian " + ("high" if d > 0 else "low"), asia[0] if d > 0 else asia[1])]
                    if pd:
                        side.append(("the PD" + ("H" if d > 0 else "L"), pd[0] if d > 0 else pd[1]))
                    return side
                _raid(cx, "XAUUSD", "S1" if d > 0 else "S2", d, w0, w1, lv, 0.6 * at1,
                      lambda sx, e, k, d=d: sx - d * 0.25 * (cx.at5[k] or 0), tgt, 2.2, pre, cost, w1, D + 20 * H1S,
                      {"levels": {**{"Asian high": asia[0], "Asian low": asia[1]}, **({"PDH": pd[0], "PDL": pd[1]} if pd else {})}, "window": (w0, w1)}, out, watch)
            # S3 · NY COMEX continuation
            if kz == "NY / COMEX":
                _gold_s3(cx, D, asia, lon, cost, out, watch)
        # S4 · PDH / PDL rejection + M15 MSS (both killzones)
        if pd:
            _gold_s4(cx, D, pd, cost, out, watch)
    return out, watch


def _gold_s3(cx: Ctx, D: int, asia, lon, cost, out, watch) -> None:
    m5, h1 = cx.m5, cx.h1
    i_lo, i_hi = cx.h1_at(D + 8 * H1S), cx.h1_at(D + 12 * H1S + 1800)
    for d in (1, -1):
        lvl = asia[0] if d > 0 else asia[1]
        brk = next((i for i in range(max(i_lo, 1), i_hi + 1) if (h1[i].close > lvl if d > 0 else h1[i].close < lvl) and cx.ad1[i] and cx.ad1[i] > 28), None)
        if brk is None:
            continue
        ob = next((j for j in range(brk, max(brk - 6, 0), -1) if (h1[j].close < h1[j].open if d > 0 else h1[j].close > h1[j].open)), None)
        if ob is None:
            continue
        ob_lo, ob_hi = h1[ob].low, h1[ob].high
        j0, j1 = cx.m15_at(D + 12 * H1S + 1800) + 1, cx.m15_at(D + 15 * H1S) + 1
        for j in range(max(j0, 3), min(j1, len(cx.m15))):
            y = cx.m15[j]
            sw = next((q for q in range(j - 3, max(j - 40, 0), -1) if (cx.lo15[q] if d > 0 else cx.hi15[q])), None)
            if sw is None:
                continue
            sl_lvl = cx.m15[sw].low if d > 0 else cx.m15[sw].high
            took = (y.low < sl_lvl and ob_lo <= y.low <= ob_hi) if d > 0 else (y.high > sl_lvl and ob_lo <= y.high <= ob_hi)
            back = (y.close > sl_lvl) if d > 0 else (y.close < sl_lvl)
            if not (took and back and true_sweep(y, cx.at15[j])):
                continue
            t_set = y.time + M15S
            k0 = m5_index_at_close(cx.t5, t_set)
            if k0 is None or m5[k0].time + M5S != t_set:
                break
            entry = m5[k0].close
            ext = y.low if d > 0 else y.high
            sl = ext - d * 0.25 * (cx.at5[k0] or 0)
            risk = abs(entry - sl)
            tgt = lon[0] if (lon and d > 0) else (lon[1] if lon else None)
            tp = tgt if tgt and (tgt - entry) * d >= 2.2 * risk else entry + d * 2.2 * risk
            steps = [(f"London closed an H1 candle {'above the Asian high' if d > 0 else 'under the Asian low'} with ADX > 28", True, f"ADX {cx.ad1[brk]:.0f}"),
                     ("NY 12:30-15:00: M15 inducement swept inside the H1 order block", True, f"{ob_lo:.2f} - {ob_hi:.2f}"),
                     ("M15 close back beyond the swept swing", True, "")]
            s = _make("XAUUSD", "S3", d, m5, k0, entry, sl, None, tp, 1.0, True, 0, D + 20 * H1S, steps,
                      {"ob": (ob_hi, ob_lo, h1[ob].time), "sweep": (ext, y.time)}, cost)
            if s:
                out.append(s)
            break


def _gold_s4(cx: Ctx, D: int, pd, cost, out, watch) -> None:
    m5 = cx.m5
    for w0, w1 in ((D + 7 * H1S, D + 10 * H1S + 1800), (D + 12 * H1S + 1800, D + 16 * H1S)):
        j0, j1 = cx.m15_at(w0) + 1, cx.m15_at(w1) + 1
        for d in (1, -1):  # +1: PDL taken → buy
            lvl = pd[1] if d > 0 else pd[0]
            js = next((j for j in range(max(j0, 3), min(j1, len(cx.m15))) if (cx.m15[j].low < lvl if d > 0 else cx.m15[j].high > lvl)
                       and true_sweep(cx.m15[j], cx.at15[j])), None)
            if js is None:
                continue
            back = next((j for j in range(js, min(js + 4, len(cx.m15))) if (cx.m15[j].close > lvl if d > 0 else cx.m15[j].close < lvl)), None)
            if back is None:
                continue
            ext = min(cx.m15[q].low for q in range(js, back + 1)) if d > 0 else max(cx.m15[q].high for q in range(js, back + 1))
            sw = next((q for q in range(js - 1, max(js - 40, 0), -1) if (cx.hi15[q] if d > 0 else cx.lo15[q])), None)
            if sw is None:
                continue
            mss_lvl = cx.m15[sw].high if d > 0 else cx.m15[sw].low
            jm = next((j for j in range(back, min(back + 12, len(cx.m15), j1)) if (cx.m15[j].close > mss_lvl if d > 0 else cx.m15[j].close < mss_lvl)), None)
            if jm is None:
                watch.append({"sid": "S4", "time": cx.m15[back].time + M15S, "dir": d, "steps": [
                    (f"{'PDL' if d > 0 else 'PDH'} taken and an M15 close back inside", True, f"{lvl:.2f}"), ("M15 MSS", False, "waiting")]})
                continue
            t_set = cx.m15[jm].time + M15S
            k0 = m5_index_at_close(cx.t5, t_set)
            if k0 is None or m5[k0].time + M5S != t_set:
                continue
            entry = m5[k0].close
            sl = ext - d * 0.25 * (cx.at5[k0] or 0)
            steps = [(f"{'PDL' if d > 0 else 'PDH'} taken and an M15 close back inside", True, f"{lvl:.2f}"), ("M15 MSS", True, f"{mss_lvl:.2f}")]
            s = _make("XAUUSD", "S4", d, m5, k0, entry, sl, (pd[0] + pd[1]) / 2, pd[0] if d > 0 else pd[1], 0.5, True, 0, D + 20 * H1S, steps,
                      {"levels": {"PDH": pd[0], "PDL": pd[1]}, "sweep": (ext, cx.m15[js].time)}, cost)
            if s:
                out.append(s)


# ---------------------------------------------------------------- EUR/USD · INST-AMD S1–S4
def amd(cx: Ctx, pip: float, cost: float) -> tuple[list, list]:
    """Accumulation: the Asian range 00:00-07:00 UTC. Range position: the close in the 48-candle H1 dealing range
    (CHOICE: the spec's "H1 swing"). Buys only under 40 %, sells only over 60 %.
    S1 buy: H1 higher highs and lows, position < 40 %; in London 07:00-09:30 or NY 12:00-14:30 UTC a true sweep of the
       Asian low (London: also the previous day's low; NY: the London low) that reaches the daily VWAP - 1.5σ OR an
       H1 bullish true FVG of the last 48 candles (CHOICE: the POI); M5 MSS + displacement + true FVG; limit at the FVG
       start; stop 2 pips under the manipulated low; target the session's opposite high (1:2 at least).
    S2 sell: the mirror (H1 bearish, > 60 %, VWAP + 1.5σ or an H1 bearish FVG).
    S3 NY raid of the London extremes: 12:00-14:30 UTC a true sweep of the London high (low) [London 07:00-12:00 UTC],
       M5 MSS + displacement; limit at the OTE (70 % of the displacement leg, CHOICE the middle of 62-79 %); stop 2 pips
       beyond the raid; target the opposite London extreme.
    S4 VWAP rotation: H1 bias, the M5 low (high) reaches the daily VWAP in a killzone and the next M5 candle closes as a
       displacement away from it in the bias's direction: entry at that close; stop 2 pips beyond the touch; target 2 R
       (CHOICE: the spec gives no target).
    No trade outside 07:00-10:30 / 12:00-16:30 UTC or in the 40-60 % middle without a sweep. Closed at 20:00 UTC."""
    out, watch = [], []
    m5, h1 = cx.m5, cx.h1
    if len(m5) < 300 or len(h1) < 60:
        return out, watch
    for D in _days(m5):
        asia = cx.day_hilo(D, D + 7 * H1S)
        pd = cx.day_hilo(D - DAY, D)
        lon = cx.day_hilo(D + 7 * H1S, D + 12 * H1S)
        if not asia:
            continue
        for w0, w1, kz in ((D + 7 * H1S, D + 9 * H1S + 1800, "London"), (D + 12 * H1S, D + 14 * H1S + 1800, "NY")):
            i1 = cx.h1_at(w0)
            rp = range_pos(h1, i1, 48)
            if not rp:
                continue
            bias = cx.bias(w0)
            fv1 = [true_fvg(h1, j, H1S, cx.at1[j]) for j in range(max(2, i1 - 47), i1 + 1)]
            for d in (1, -1):
                if bias != d or not ((rp[2] < 40) if d > 0 else (rp[2] > 60)):
                    continue
                lv = {"Asian low": asia[1]} if d > 0 else {"Asian high": asia[0]}
                if kz == "London" and pd:
                    lv["previous day " + ("low" if d > 0 else "high")] = pd[1] if d > 0 else pd[0]
                if kz == "NY" and lon:
                    lv["London " + ("low" if d > 0 else "high")] = lon[1] if d > 0 else lon[0]
                ks = bisect_left(cx.t5, w0)
                vw_band = (cx.vw[ks] - 1.5 * cx.vsd[ks]) if d > 0 else (cx.vw[ks] + 1.5 * cx.vsd[ks]) if ks < len(m5) and cx.vw[ks] is not None else None
                pois = [g for g in fv1 if g and g[0] == d]
                poi_lv = {}
                for n, v in lv.items():  # the swept level must sit at a POI: VWAP ∓ 1.5σ or an H1 FVG of the same side
                    at_vw = vw_band is not None and ((v <= vw_band) if d > 0 else (v >= vw_band))
                    at_fvg = any(g[1] - (cx.at1[i1] or 0) * 0.25 <= v <= g[2] + (cx.at1[i1] or 0) * 0.25 for g in pois)
                    if at_vw or at_fvg:
                        poi_lv[n] = v
                pre = [(f"{kz} killzone (manipulation)", True, ""), ("H1 bullish, discount < 40 %" if d > 0 else "H1 bearish, premium > 60 %", True, f"{rp[2]:.0f} %"),
                       ("The swept level sits at a POI (VWAP ∓ 1.5σ or an H1 FVG)", bool(poi_lv), "")]
                if not poi_lv:
                    continue
                opp = asia[0] if d > 0 else asia[1]
                _raid(cx, "EURUSD", "S1" if d > 0 else "S2", d, w0, w1, poi_lv, None, lambda sx, e, k, d=d: sx - d * 2 * pip,
                      lambda e, opp=opp, d=d: [("the Asian " + ("high" if d > 0 else "low"), opp)], 2.0, pre, cost, w1 + 2 * H1S, D + 20 * H1S,
                      {"levels": {"Asian high": asia[0], "Asian low": asia[1]}, "window": (w0, w1)}, out, watch)
            if kz == "NY" and lon:
                for d in (1, -1):  # S3: buy after the London LOW is raided
                    lv = {"London low": lon[1]} if d > 0 else {"London high": lon[0]}
                    opp = lon[0] if d > 0 else lon[1]
                    _raid(cx, "EURUSD", "S3", d, w0, w1, lv, None, lambda sx, e, k, d=d: sx - d * 2 * pip,
                          lambda e, opp=opp, d=d: [("the opposite London extreme", opp)], 2.0, [("NY raid of the London extreme", True, "")],
                          cost, w1 + 2 * H1S, D + 20 * H1S, {"levels": {"London high": lon[0], "London low": lon[1]}, "window": (w0, w1)}, out, watch, ote=True)
        # S4 · VWAP rotation in the H1 trend
        for w0, w1 in ((D + 7 * H1S, D + 10 * H1S + 1800), (D + 12 * H1S, D + 16 * H1S + 1800)):
            bias = cx.bias(w0)
            if not bias:
                continue
            ks, ke = bisect_left(cx.t5, w0), bisect_left(cx.t5, w1)
            for k in range(max(ks, 1), ke - 1):
                x, y = m5[k], m5[k + 1]
                v = cx.vw[k]
                if v is None:
                    continue
                touch = (x.low <= v < x.close) if bias > 0 else (x.high >= v > x.close)
                if touch and displacement(y, cx.at5[k + 1]) and ((y.close > y.open) if bias > 0 else (y.close < y.open)):
                    entry = y.close
                    sl = (x.low - 2 * pip) if bias > 0 else (x.high + 2 * pip)
                    tp = entry + bias * 2 * abs(entry - sl)
                    steps = [("H1 trend", True, "bullish" if bias > 0 else "bearish"), ("M5 touch of the daily VWAP", True, f"{v:.5f}"),
                             ("Displacement candle away from the VWAP", True, "")]
                    s = _make("EURUSD", "S4", bias, m5, k + 1, entry, sl, None, tp, 1.0, True, 0, D + 20 * H1S, steps, {"vwap": True}, cost)
                    if s:
                        out.append(s)
                    break
    return out, watch


# ---------------------------------------------------------------- GBP/USD · CABLE-RAID S1–S4
def cable(cx: Ctx, pip: float, cost: float) -> tuple[list, list]:
    """S1 buy: in London 07:00-10:00 or NY 12:30-15:30 UTC an M15 candle takes the PDL or the Asian low (00:00-07:00) by
    0.15-0.85 ATR H1 with a rejection wick >= 45 % of its range, and closes back ABOVE the level (the reclaim: never
    enter on the touch); then an M5 close above the last M5 swing high (MSS); limit at the M5 breaker (the top of the
    last bullish M5 candle before the sweep low, CHOICE); stop 0.3 ATR M15 under the sweep; target 3 R (the spec:
    2.5-3.5 R).
    S2 sell: the mirror on the PDH / Asian high (a failed breakout).
    S3 London squeeze: the Asian M15 Bollinger (20, 2) width under the 20th percentile of its last 100 candles; London's
    first two hours give an M15 displacement candle closing outside the Asian range: limit at its 38.2 % retracement;
    stop 0.3 ATR M15 beyond its origin; target 2.5 R (CHOICE).
    S4 NY overlap pullback: H1 bias; in 12:30-15:30 UTC price returns into the H1 order block of the last H1 BOS impulse
    (the last opposite H1 candle before it, CHOICE) and an M5 displacement candle closes away from it: entry at that
    close; stop 0.3 ATR M15 beyond the order block; target 2.5 R. Closed at 20:00 UTC."""
    out, watch = [], []
    m5, h1, m15 = cx.m5, cx.h1, cx.m15
    if len(m5) < 300 or len(h1) < 60:
        return out, watch
    for D in _days(m5):
        asia = cx.day_hilo(D, D + 7 * H1S)
        pd = cx.day_hilo(D - DAY, D)
        if not asia:
            continue
        for w0, w1, kz in ((D + 7 * H1S, D + 10 * H1S, "London"), (D + 12 * H1S + 1800, D + 15 * H1S + 1800, "NY overlap")):
            i1 = cx.h1_at(w0)
            at1 = cx.at1[i1] if i1 >= 0 else None
            if not at1:
                continue
            j0, j1 = cx.m15_at(w0) + 1, cx.m15_at(w1) + 1
            for d in (1, -1):
                lv = {"Asian low": asia[1], "PDL": pd[1] if pd else None} if d > 0 else {"Asian high": asia[0], "PDH": pd[0] if pd else None}
                lv = {k: v for k, v in lv.items() if v is not None}
                hit = None
                for j in range(max(j0, 3), min(j1, len(m15))):
                    y = m15[j]
                    for n, v in lv.items():
                        depth = (v - y.low) if d > 0 else (y.high - v)
                        rngy = y.high - y.low
                        wick = (min(y.open, y.close) - y.low) if d > 0 else (y.high - max(y.open, y.close))
                        if 0.15 * at1 <= depth <= 0.85 * at1 and rngy > 0 and wick / rngy >= 0.45 and \
                           ((y.close > v) if d > 0 else (y.close < v)) and true_sweep(y, cx.at15[j]):
                            hit = (j, n, v)
                            break
                    if hit:
                        break
                if not hit:
                    continue
                j, n, v = hit
                y = m15[j]
                ext = y.low if d > 0 else y.high
                k_rc = m5_index_at_close(cx.t5, y.time + M15S)
                k_ext = bisect_left(cx.t5, y.time)
                k_ext = min(range(k_ext, min(k_ext + 3, len(m5))), key=lambda q: m5[q].low if d > 0 else -m5[q].high)
                pre = [(f"{kz}: deep sweep of the {n} ({((v - ext) if d > 0 else (ext - v)) / at1:.2f} ATR H1, 0.15-0.85)", True, ""),
                       ("M15 close back inside (reclaim) with a rejection wick >= 45 %", True, "")]
                if k_rc is None:
                    continue
                ref = next((q for q in range(k_ext - 1, max(k_ext - 60, 0), -1) if (cx.hi5[q] if d > 0 else cx.lo5[q])), None)
                brk = next((q for q in range(k_ext - 1, max(k_ext - 30, 0), -1) if (m5[q].close > m5[q].open if d > 0 else m5[q].close < m5[q].open)), None)
                if ref is None or brk is None:
                    continue
                mss_lvl = m5[ref].high if d > 0 else m5[ref].low
                km = next((q for q in range(max(k_rc + 1, ref + 2), min(k_rc + 36, len(m5))) if (m5[q].close > mss_lvl if d > 0 else m5[q].close < mss_lvl)), None)
                if km is None:
                    watch.append({"sid": "S1" if d > 0 else "S2", "time": y.time + M15S, "dir": d, "steps": pre + [("M5 MSS after the reclaim", False, "waiting")]})
                    continue
                entry = m5[brk].high if d > 0 else m5[brk].low
                if (entry - m5[km].close) * d >= 0:
                    entry = m5[brk].low if d > 0 else m5[brk].high  # price already below the breaker's top: its other edge
                sl = ext - d * 0.3 * (cx.at15[j] or 0)
                if (entry - sl) * d <= 0:
                    continue
                tp = entry + d * 3.0 * abs(entry - sl)
                steps = pre + [("M5 MSS after the reclaim", True, f"{mss_lvl:.5f}"), ("Limit at the M5 breaker block", True, f"{entry:.5f}")]
                s = _make("GBPUSD", "S1" if d > 0 else "S2", d, m5, km, entry, sl, None, tp, 1.0, False, 24, D + 20 * H1S, steps,
                          {"levels": {"Asian high": asia[0], "Asian low": asia[1], **({"PDH": pd[0], "PDL": pd[1]} if pd else {})},
                           "ob": (m5[brk].high, m5[brk].low, m5[brk].time), "sweep": (ext, y.time), "window": (w0, w1)}, cost,
                          zone=(m5[brk].low, m5[brk].high))
                if s:
                    out.append(s)
        _cable_s3(cx, D, asia, cost, out, watch)
    _cable_s4(cx, cost, out, watch)
    return out, watch


def _cable_s3(cx: Ctx, D: int, asia, cost, out, watch) -> None:
    m15, m5 = cx.m15, cx.m5
    ja, jb = cx.m15_at(D) + 1, cx.m15_at(D + 7 * H1S) + 1
    if jb - ja < 20 or jb < 120:
        return
    cl = [x.close for x in m15]

    def width(j):
        w = cl[j - 19:j + 1]
        mu = sum(w) / 20
        return 4 * (sum((v - mu) ** 2 for v in w) / 20) ** 0.5 / mu
    wa = width(jb - 1)
    hist = sorted(width(q) for q in range(jb - 100, jb))
    if wa >= hist[19]:
        return
    for j in range(jb, min(cx.m15_at(D + 9 * H1S) + 1, len(m15))):
        y = m15[j]
        d = 1 if y.close > asia[0] else -1 if y.close < asia[1] else 0
        if not d or not displacement(y, cx.at15[j]) or (y.close - y.open) * d <= 0:
            continue
        o = y.open if abs(y.open - (asia[0] if d > 0 else asia[1])) > 0 else y.low
        top = y.high if d > 0 else y.low
        base = y.low if d > 0 else y.high
        entry = top - d * 0.382 * abs(top - base)
        sl = base - d * 0.3 * (cx.at15[j] or 0)
        tp = entry + d * 2.5 * abs(entry - sl)
        t_set = y.time + M15S
        k0 = m5_index_at_close(cx.t5, t_set)
        if k0 is None or m5[k0].time + M5S != t_set:
            return
        steps = [("Asian M15 Bollinger width under its 20th percentile (squeeze)", True, ""),
                 ("London M15 displacement candle out of the Asian range", True, f"{y.close:.5f}"), ("Limit at its 38.2 % pullback", True, f"{entry:.5f}")]
        s = _make("GBPUSD", "S3", d, m5, k0, entry, sl, None, tp, 1.0, False, 24, D + 20 * H1S, steps,
                  {"levels": {"Asian high": asia[0], "Asian low": asia[1]}}, cost)
        if s:
            out.append(s)
        del o
        return


def _cable_s4(cx: Ctx, cost, out, watch) -> None:
    m5, h1 = cx.m5, cx.h1
    last = None
    for D in _days(m5):
        w0, w1 = D + 12 * H1S + 1800, D + 15 * H1S + 1800
        bias = cx.bias(w0)
        i1 = cx.h1_at(w0)
        if not bias or i1 < 20:
            continue
        brk = next((i for i in range(i1, max(i1 - 30, 2), -1) if (h1[i].close > max(x.high for x in h1[i - 10:i]) if bias > 0 else h1[i].close < min(x.low for x in h1[i - 10:i]))), None)
        if brk is None:
            continue
        ob = next((j for j in range(brk - 1, max(brk - 6, 0), -1) if (h1[j].close < h1[j].open if bias > 0 else h1[j].close > h1[j].open)), None)
        if ob is None or ob == last:
            continue
        lo, hi = h1[ob].low, h1[ob].high
        ks, ke = bisect_left(cx.t5, w0), bisect_left(cx.t5, w1)
        for k in range(max(ks, 1), ke - 1):
            x, y = m5[k], m5[k + 1]
            inside = (x.low <= hi and x.low >= lo) if bias > 0 else (x.high >= lo and x.high <= hi)
            if inside and displacement(y, cx.at5[k + 1]) and (y.close - y.open) * bias > 0:
                j15 = cx.m15_at(y.time + M5S)
                sl = (lo - 0.3 * (cx.at15[j15] or 0)) if bias > 0 else (hi + 0.3 * (cx.at15[j15] or 0))
                entry = y.close
                if (entry - sl) * bias <= 0:
                    break
                steps = [("H1 trend + a BOS impulse", True, ""), ("NY overlap pullback into the H1 order block", True, f"{lo:.5f} - {hi:.5f}"),
                         ("M5 displacement away from it", True, "")]
                s = _make("GBPUSD", "S4", bias, m5, k + 1, entry, sl, None, entry + bias * 2.5 * abs(entry - sl), 1.0, True, 0, D + 20 * H1S, steps,
                          {"ob": (hi, lo, h1[ob].time)}, cost)
                if s:
                    out.append(s)
                    last = ob
                break


# ---------------------------------------------------------------- EUR/CHF · SWISS-REV S1–S3
def swiss(cx: Ctx, pip: float, cost: float, ecb_snb: Optional[list[int]] = None) -> tuple[list, list]:
    """Z_50 on H1 (EMA 50 mean). Regime: ADX H1 < 28 (veto over 32: REGIME BREAK). European hours 06:30-15:30 UTC.
    S1 buy: H1 Z <= -2.2 and the close in the lowest 12 % of the last 50 H1 candles; then an M15 candle sweeps a prior
       M15 swing low (true sweep), with RSI 14 (M15) under 28 or a bullish RSI divergence, and closes as a bullish engulfing
       or pin bar (or an M15 CHoCH: close above the last M15 swing high): buy at that close (CHOICE: the M15 close, the
       M5 structure shift folded into the CHoCH). Stop 1.2 ATR H1 under the low; TP1 Z = -0.5 (half, BE), TP2 the EMA 50
       (Z = 0); the reward to the mean at least 1:1.8 (Risk Manager).
    S2 sell: the mirror (Z >= 2.2, >= 88 %, RSI over 72 or a bearish divergence).
    S3: an M15 close beyond the daily VWAP ± 2.5σ in European hours, then a reversal M15 candle (engulfing / pin): entry
       at its close toward the VWAP; stop 1.2 ATR H1 beyond the extreme; target the VWAP (1:1.8 at least).
    Veto: ECB / SNB releases (the calendar) stop the engine 30 min around them (REGIME BREAK VETO). Held 24 h."""
    out, watch = [], []
    m5, h1, m15 = cx.m5, cx.h1, cx.m15
    if len(h1) < 80 or len(m15) < 80:
        return out, watch
    z, mu, sg = zscore(cx.c1, 50)
    c15 = [x.close for x in m15]
    r15 = rsi(c15, 14)
    shock = sorted(ecb_snb or [])
    used = set()
    for j in range(60, len(m15)):
        y = m15[j]
        t_close = y.time + M15S
        tod = t_close % DAY
        if not (6 * H1S + 1800 < tod <= 15 * H1S + 1800) or r15[j] is None:
            continue
        if shock and any(abs(n - t_close) <= 30 * 60 for n in shock[bisect_left(shock, t_close - 1800):bisect_left(shock, t_close + 1801)]):
            continue
        i1 = cx.h1_at(t_close)
        if i1 < 55 or z[i1] is None or cx.ad1[i1] is None:
            continue
        if cx.ad1[i1] > 32:
            continue
        rp = range_pos(h1, i1, 50)
        at1 = cx.at1[i1]
        prev = m15[j - 1]
        for d in (1, -1):
            ext_z = z[i1] <= -2.2 if d > 0 else z[i1] >= 2.2
            ext_r = rp and ((rp[2] <= 12) if d > 0 else (rp[2] >= 88))
            if not (ext_z and ext_r) or cx.ad1[i1] >= 28 or (i1, d) in used:
                continue
            sw = next((q for q in range(j - 3, max(j - 40, 0), -1) if (cx.lo15[q] if d > 0 else cx.hi15[q])), None)
            if sw is None:
                continue
            lvl = m15[sw].low if d > 0 else m15[sw].high
            took = (y.low < lvl) if d > 0 else (y.high > lvl)
            div = r15[sw] is not None and ((y.low < lvl and r15[j] > r15[sw]) if d > 0 else (y.high > lvl and r15[j] < r15[sw]))
            exh = (r15[j] < 28) if d > 0 else (r15[j] > 72)
            pin = (min(y.open, y.close) - y.low >= 2 * body(y)) if d > 0 else (y.high - max(y.open, y.close) >= 2 * body(y))
            eng = (y.close > y.open and prev.close < prev.open and y.close > prev.open) if d > 0 else (y.close < y.open and prev.close > prev.open and y.close < prev.open)
            sh = next((q for q in range(j - 3, max(j - 30, 0), -1) if (cx.hi15[q] if d > 0 else cx.lo15[q])), None)
            choch = sh is not None and ((y.close > m15[sh].high) if d > 0 else (y.close < m15[sh].low))
            steps = [(f"Range regime: ADX {cx.ad1[i1]:.0f} < 28", True, ""), (f"H1 Z-score {z[i1]:+.2f}σ ({'<= -2.2' if d > 0 else '>= +2.2'})", True, ""),
                     (f"Extreme {'discount' if d > 0 else 'premium'}: {rp[2]:.0f} % of the 50-candle range", True, ""),
                     ("M15 sweep of a prior swing", took and true_sweep(y, cx.at15[j]), f"{lvl:.5f}"),
                     (f"M15 exhaustion: RSI {r15[j]:.0f} or a divergence", exh or div, ""),
                     ("M15 reversal: engulfing / pin bar / CHoCH", pin or eng or choch, "")]
            if not (took and true_sweep(y, cx.at15[j]) and (exh or div) and (pin or eng or choch)):
                if took:
                    watch.append({"sid": "S1" if d > 0 else "S2", "time": t_close, "dir": d, "steps": steps})
                continue
            k0 = m5_index_at_close(cx.t5, t_close)
            if k0 is None or m5[k0].time + M5S != t_close or not at1:
                continue
            entry = m5[k0].close
            sl = (y.low - 1.2 * at1) if d > 0 else (y.high + 1.2 * at1)
            tp2, tp1 = mu[i1], mu[i1] - d * 0.5 * sg[i1]
            used.add((i1, d))
            s = _make("EURCHF", "S1" if d > 0 else "S2", d, m5, k0, entry, sl, tp1, tp2, 0.5, True, 0, t_close + 24 * H1S, steps,
                      {"zscore": (z[i1], mu[i1], sg[i1]), "sweep": (y.low if d > 0 else y.high, y.time)}, cost)
            if s:
                out.append(s)
        # S3 · VWAP ± 2.5σ exhaustion
        kx = m5_index_at_close(cx.t5, prev.time + M15S)
        if kx is None or cx.vw[kx] is None or not at1:
            continue
        v, vs = cx.vw[kx], cx.vsd[kx]
        for d in (1, -1):
            beyond = (prev.close < v - 2.5 * vs) if d > 0 else (prev.close > v + 2.5 * vs)
            pin = (min(y.open, y.close) - y.low >= 2 * body(y)) if d > 0 else (y.high - max(y.open, y.close) >= 2 * body(y))
            eng = (y.close > y.open and y.close > prev.open) if d > 0 else (y.close < y.open and y.close < prev.open)
            if not (beyond and (pin or eng)) or (j, "S3") in used:
                continue
            k0 = m5_index_at_close(cx.t5, t_close)
            if k0 is None or m5[k0].time + M5S != t_close:
                continue
            entry = m5[k0].close
            ext = min(prev.low, y.low) if d > 0 else max(prev.high, y.high)
            sl = ext - d * 1.2 * at1
            used.add((j, "S3"))
            steps = [(f"M15 close {'under VWAP - 2.5σ' if d > 0 else 'over VWAP + 2.5σ'} in European hours", True, f"VWAP {v:.5f}"),
                     ("Reversal M15 candle", True, ""), (f"Range regime: ADX {cx.ad1[i1]:.0f} < 28", cx.ad1[i1] < 28, "")]
            if cx.ad1[i1] >= 28:
                continue
            s = _make("EURCHF", "S3", d, m5, k0, entry, sl, None, v, 1.0, True, 0, t_close + 24 * H1S, steps, {"vwap": True}, cost)
            if s:
                out.append(s)
    return out, watch


# ---------------------------------------------------------------- AUD/CHF · RISK-REGIME S1–S4
def regime(cx: Ctx, i: int, er: list) -> str:
    a, e = cx.ad1[i], er[i]
    if a is None or e is None:
        return "TRANSITION_WAIT"
    if a >= 25 and e >= 0.35:
        return "TREND_PULLBACK"
    if a < 22 and e < 0.25:
        return "RANGE_FADE"
    return "TRANSITION_WAIT"


def risk_regime(cx: Ctx, pip: float, cost: float) -> tuple[list, list]:
    """Regime on H1: TREND_PULLBACK when ADX 14 >= 25 and the 30-candle efficiency ratio >= 0.35; RANGE_FADE when ADX < 22
    and ER < 0.25; otherwise TRANSITION_WAIT (no trade).
    S1 / S2 (trend, direction = the sign of C - C[30]): the H1 pullback reaches the OTE 61.8-78.6 % of the last impulse
       (from the lowest low of the 30 candles to the highest high after it, CHOICE) where an H1 order block or true FVG
       sits; then an M15 internal inducement sweep (a prior M15 swing low taken) and an M15 BOS (close above the last M15
       swing high) in the trend: entry at that close; stop 2 pips beyond the order block / pullback low; TP1 the impulse
       high (half, BE), TP2 its -0.27 extension.
    S3 / S4 (range): the close in the lowest 15 % (highest 85 %) of the 60-candle H1 range with Z_50 <= -1.8 (>= +1.8);
       an M15 sweep of a prior swing low (high) and an M15 CHoCH back: entry at that close; target the range's 50 %;
       stop 0.25 ATR H1 beyond the sweep. Never 21:00-23:00 UTC (rollover). Held 72 h (trend) / 24 h (range)."""
    out, watch = [], []
    m5, h1, m15 = cx.m5, cx.h1, cx.m15
    if len(h1) < 80 or len(m15) < 80:
        return out, watch
    er = efficiency(cx.c1, 30)
    z, _mu, _sg = zscore(cx.c1, 50)
    fired = set()
    for j in range(60, len(m15)):
        y = m15[j]
        t_close = y.time + M15S
        if 21 * H1S <= t_close % DAY < 23 * H1S:
            continue
        i1 = cx.h1_at(t_close)
        if i1 < 60:
            continue
        mode = regime(cx, i1, er)
        if mode == "TRANSITION_WAIT":
            continue
        sh = next((q for q in range(j - 3, max(j - 40, 0), -1) if cx.hi15[q]), None)
        sl_ = next((q for q in range(j - 3, max(j - 40, 0), -1) if cx.lo15[q]), None)
        if sh is None or sl_ is None:
            continue
        if mode == "TREND_PULLBACK":
            d = 1 if cx.c1[i1] > cx.c1[i1 - 30] else -1
            seg = h1[i1 - 29:i1 + 1]
            if d > 0:
                a_k = min(range(len(seg)), key=lambda q: seg[q].low)
                A = seg[a_k].low
                B = max(x.high for x in seg[a_k:])
            else:
                a_k = max(range(len(seg)), key=lambda q: seg[q].high)
                A = seg[a_k].high
                B = min(x.low for x in seg[a_k:])
            leg = abs(B - A)
            if leg <= 0:
                continue
            o62, o79 = B - d * 0.618 * leg, B - d * 0.786 * leg
            zlo, zhi = min(o62, o79), max(o62, o79)
            touch = (y.low <= zhi and y.low >= zlo - 0.1 * leg) if d > 0 else (y.high >= zlo and y.high <= zhi + 0.1 * leg)
            if not touch:
                continue
            pois = [true_fvg(h1, q, H1S, cx.at1[q]) for q in range(max(2, i1 - 29), i1 + 1)]
            obs = [h1[q] for q in range(max(1, i1 - 29), i1) if (h1[q].close < h1[q].open if d > 0 else h1[q].close > h1[q].open) and zlo <= (h1[q].low if d > 0 else h1[q].high) <= zhi]
            poi = any(g and g[0] == d and g[1] <= zhi and g[2] >= zlo for g in pois) or bool(obs)
            ind = (y.low < m15[sl_].low) if d > 0 else (y.high > m15[sh].high)
            bos = (y.close > m15[sh].high) if d > 0 else (y.close < m15[sl_].low)
            steps = [(f"Regime TREND_PULLBACK (ADX {cx.ad1[i1]:.0f} >= 25, ER {er[i1]:.2f} >= 0.35)", True, "risk-on" if d > 0 else "risk-off"),
                     ("H1 pullback into the OTE 61.8-78.6 %", True, f"{zlo:.5f} - {zhi:.5f}"), ("An H1 order block / FVG in the OTE", poi, ""),
                     ("M15 internal inducement sweep", ind, ""), ("M15 BOS in the trend", bos, "")]
            if not (poi and bos):
                if poi:
                    watch.append({"sid": "S1" if d > 0 else "S2", "time": t_close, "dir": d, "steps": steps})
                continue
            if not ind and not any(((m15[q].low < m15[sl_].low) if d > 0 else (m15[q].high > m15[sh].high)) for q in range(max(j - 8, 0), j)):
                continue
            key = ("T", d, round(A, 5))
            if key in fired:
                continue
            k0 = m5_index_at_close(cx.t5, t_close)
            if k0 is None or m5[k0].time + M5S != t_close:
                continue
            entry = m5[k0].close
            pull = min(x.low for x in m15[max(j - 8, 0):j + 1]) if d > 0 else max(x.high for x in m15[max(j - 8, 0):j + 1])
            ob_ext = min([o.low for o in obs] + [pull]) if d > 0 else max([o.high for o in obs] + [pull])
            sl = ob_ext - d * 2 * pip
            fired.add(key)
            s = _make("AUDCHF", "S1" if d > 0 else "S2", d, m5, k0, entry, sl, B, B + d * 0.27 * leg, 0.5, True, 0, t_close + 72 * H1S, steps,
                      {"fib": (o62, o79, o79, B, A, h1[i1 - 29 + a_k].time)}, cost, zone=(zlo, zhi))
            if s:
                out.append(s)
        else:  # RANGE_FADE
            rp = range_pos(h1, i1, 60)
            if not rp or z[i1] is None:
                continue
            for d in (1, -1):
                ext = (rp[2] < 15 and z[i1] <= -1.8) if d > 0 else (rp[2] > 85 and z[i1] >= 1.8)
                if not ext:
                    continue
                took = (y.low < m15[sl_].low) if d > 0 else (y.high > m15[sh].high)
                choch = (y.close > m15[sh].high) if d > 0 else (y.close < m15[sl_].low)
                recent = any(((m15[q].low < m15[sl_].low) if d > 0 else (m15[q].high > m15[sh].high)) for q in range(max(j - 8, 0), j + 1))
                steps = [(f"Regime RANGE_FADE (ADX {cx.ad1[i1]:.0f} < 22, ER {er[i1]:.2f} < 0.25)", True, ""),
                         (f"Range extreme {rp[2]:.0f} % with Z {z[i1]:+.2f}σ", True, ""), ("M15 boundary sweep", took or recent, ""), ("M15 CHoCH back", choch, "")]
                if not (recent and choch):
                    if recent:
                        watch.append({"sid": "S3" if d > 0 else "S4", "time": t_close, "dir": d, "steps": steps})
                    continue
                key = ("R", d, i1)
                if key in fired:
                    continue
                k0 = m5_index_at_close(cx.t5, t_close)
                if k0 is None or m5[k0].time + M5S != t_close:
                    continue
                entry = m5[k0].close
                sw_ext = min(x.low for x in m15[max(j - 8, 0):j + 1]) if d > 0 else max(x.high for x in m15[max(j - 8, 0):j + 1])
                sl = sw_ext - d * 0.25 * (cx.at1[i1] or 0)
                fired.add(key)
                s = _make("AUDCHF", "S3" if d > 0 else "S4", d, m5, k0, entry, sl, None, (rp[0] + rp[1]) / 2, 1.0, True, 0, t_close + 24 * H1S, steps,
                          {"range": (rp[1], rp[0], h1[i1 - 59].time)}, cost)
                if s:
                    out.append(s)
    return out, watch


# ---------------------------------------------------------------- what each team reads now (the agents' badges)
def context(key: str, m5, h1, daily: Daily, now: int) -> dict:
    """The pair profile's live numbers for the 7 agents and the header badge (computed on closed candles)."""
    cx = Ctx(m5, h1, daily)
    i1 = len(h1) - 1
    out = {"feed": feed_check(m5, cx.at5)}
    rp = range_pos(h1, i1, 48 if key in ("XAUUSD", "EURUSD", "GBPUSD") else 60 if key == "AUDCHF" else 50)
    out["rangePct"] = rp[2] if rp else None
    out["adx"] = cx.ad1[i1]
    z, mu, _ = zscore(cx.c1, 50)
    out["z"], out["ema50"] = z[i1], mu[i1]
    er = efficiency(cx.c1, 30)
    out["er"] = er[i1]
    out["regime"] = regime(cx, i1, er)
    k = len(m5) - 1
    out["vwap"], out["vwapSd"] = cx.vw[k], cx.vsd[k]
    D = m5[-1].time - m5[-1].time % DAY
    asia = cx.day_hilo(D, D + (7 if key in ("EURUSD", "GBPUSD") else 6) * H1S)
    out["asia"] = asia
    adr = daily.adr(now, 14)
    today = cx.day_hilo(D, D + DAY)
    out["adrUsed"] = (today[0] - today[1]) / adr * 100 if adr and today else None
    out["asiaCompressed"] = bool(asia and adr and asia[0] - asia[1] <= 0.85 * adr)
    tod = now % DAY
    if key == "EURUSD":
        out["amd"] = "Accumulation (Asia)" if tod < 7 * H1S else "Manipulation / Judas window" if tod < 9.5 * H1S or 12 * H1S <= tod < 14.5 * H1S else "Distribution"
    return out


def data_fitness(n: int, feed: dict) -> str:
    """The spec's tiers: DATA_FIT_HIGH (N >= 30 and feed defects < 1 %), DATA_FIT_DEGRADED (15 <= N < 30), DATA_UNFIT_CRITICAL
    (N < 15, or a feed gap in the last 20 candles). Shown as FIT / LIMITED SAMPLE / NOT FIT."""
    if n < 15 or feed.get("recentGap") or feed.get("share", 1) > 0.05:
        return "NOT FIT"
    if n < 30 or feed.get("share", 1) >= 0.01:
        return "LIMITED SAMPLE"
    return "FIT"
