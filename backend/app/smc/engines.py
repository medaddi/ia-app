"""
What is left of the master spec's pair engines (quantitative_trading_teams_claude_master_prompt.md, 2026-11-08) after
the user's rule of 2026-11-08: "remove the strategies without profit, keep only those with a high win rate" (written:
kept = win rate >= 55 % and profitable in both halves of the one-year Dukascopy test). Kept here: EUR/CHF SWISS-REV S2
(the bearish extreme premium fade, Z >= +2.2). Kept in playbook.py: EUR/USD SnapBack 3σ and AUD/CAD range reversion.
Removed (git history has them): GOLD-QUANT S1–S4, INST-AMD S1–S4 (re-coded by the spec's logic first: still no
profit), CABLE-RAID S1–S4, SWISS-REV S1 and S3, RISK-REGIME S1–S4.

Still here for every team: the spec's indicators (daily VWAP ± σ, Z-score, Kaufman ER, the dealing range), the data
hygiene (true FVG, true sweep, the live feed check, the FIT / LIMITED SAMPLE / NOT FIT tiers) and each pair's context
for the agents and the header badge.
"""

from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from typing import Optional

from .playbook import (DAY, H1S, M5S, M15S, Daily, _h1_bias, _make, adx, atr, body, ema, fractals, hilo,
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


# ---------------------------------------------------------------- EUR/CHF · SWISS-REV S2 (the one that passed)
# ---------------------------------------------------------------- the regime (AUD/CHF's badge: ADX + Kaufman ER)
def regime(cx: Ctx, i: int, er: list) -> str:
    a, e = cx.ad1[i], er[i]
    if a is None or e is None:
        return "TRANSITION_WAIT"
    if a >= 25 and e >= 0.35:
        return "TREND_PULLBACK"
    if a < 22 and e < 0.25:
        return "RANGE_FADE"
    return "TRANSITION_WAIT"


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
