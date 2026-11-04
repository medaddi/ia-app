"""
Shared quantitative primitives of the pair agents. Everything only looks back, so it is computed once on a series and read
at any candle without look-ahead (a swing is known 2 candles after its pivot, which every caller respects).

In the spec's notation [-1] is the last closed candle; here the same rules are written on absolute indices:
candle k with k = the last index ⇔ [-1].

1. 5-bar fractal: a swing high at k (= [-3] when k + 2 is the last closed candle) when High[k] is above High[k-2],
   High[k-1], High[k+1], High[k+2]; a swing low the same with Low and "below". Confirmed at k + 2.
2. FVG on k-2, k-1, k (= [-3], [-2], [-1]): bullish Low[k] > High[k-2] (bottom High[k-2], top Low[k]); bearish
   High[k] < Low[k-2] (top Low[k-2], bottom High[k]); ce_50 = (top + bottom) / 2; size ≥ min_fvg (2.5 pips forex,
   6 pips = $0.60 gold).
3. Order block: on a bullish MSS the LOWEST bearish candle (Close < Open) of the 10 candles before the break; on a
   bearish MSS the HIGHEST bullish candle. top = High, bottom = Low, mean = (Open + Close) / 2.
4. Fibonacci OTE of a displacement leg Swing_Start → Swing_End: 0.618, 0.705 (sweet spot) and 0.786 retracements.
5. Wilder RSI / ATR / ADX (14), EMA, higher-timeframe aggregation.
6. The clock: every session of the agents is written in UTC+1 (Morocco time), a fixed offset.
"""

import time as _time
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from ..strategies.shared.types import Candle

TZ_OFFSET_SEC = 3600  # UTC+1, Morocco time: every agent session below is in this clock


# ---------------------------------------------------------------- clock (UTC+1)
@lru_cache(maxsize=300_000)
def mt(ts: int) -> tuple[str, int, int]:
    """(UTC+1 date 'YYYY-MM-DD', minute of the day, weekday Sun=0) of a unix timestamp."""
    g = _time.gmtime(ts + TZ_OFFSET_SEC)
    return f"{g.tm_year}-{g.tm_mon:02d}-{g.tm_mday:02d}", g.tm_hour * 60 + g.tm_min, (g.tm_wday + 1) % 7


def day_start(ts: int) -> int:
    """00:00 UTC+1 of the day of `ts`, as a unix timestamp."""
    return (ts + TZ_OFFSET_SEC) // 86400 * 86400 - TZ_OFFSET_SEC


def at_minute(ts_day: int, minute: int) -> int:
    """The unix time of `minute` (UTC+1) on the day that contains ts_day."""
    return day_start(ts_day) + minute * 60


def hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def by_day(c: list[Candle]) -> list[tuple[str, int, int]]:
    """[(UTC+1 date, first index, last index)] in order."""
    out: list[tuple[str, int, int]] = []
    for i, x in enumerate(c):
        d = mt(x.time)[0]
        if out and out[-1][0] == d:
            out[-1] = (d, out[-1][1], i)
        else:
            out.append((d, i, i))
    return out


def trading_days(c: list[Candle]) -> list[tuple[str, int, int]]:
    """by_day without the weekend stubs (Saturday / Sunday evening open)."""
    return [d for d in by_day(c) if mt(c[d[1]].time)[2] not in (0, 6)]


def fingerprint(c: list[Candle], a: int, b: int) -> tuple:
    """What identifies a day's candles for the day cache: bounds, count, extremes and the last close."""
    seg = c[a:b + 1]
    return (c[a].time, c[b].time, b - a, max(x.high for x in seg), min(x.low for x in seg), c[b].close)


# ---------------------------------------------------------------- swings, FVG, OB, OTE
def swing_flags(c: list[Candle]) -> tuple[list[bool], list[bool]]:
    """(is_high[k], is_low[k]) of the 5-bar fractal, known at k + 2."""
    n = len(c)
    hi, lo = [False] * n, [False] * n
    for k in range(2, n - 2):
        h, l_ = c[k].high, c[k].low
        hi[k] = h > c[k - 2].high and h > c[k - 1].high and h > c[k + 1].high and h > c[k + 2].high
        lo[k] = l_ < c[k - 2].low and l_ < c[k - 1].low and l_ < c[k + 1].low and l_ < c[k + 2].low
    return hi, lo


def is_swing_high_now(c: list[Candle]) -> bool:
    """The spec's form: High[-3] above High[-5], High[-4], High[-2], High[-1]."""
    return len(c) >= 5 and all(c[-3].high > c[k].high for k in (-5, -4, -2, -1))


def is_swing_low_now(c: list[Candle]) -> bool:
    return len(c) >= 5 and all(c[-3].low < c[k].low for k in (-5, -4, -2, -1))


def last_swing(flags: list[bool], before: int, now: int, start: int = 0) -> Optional[int]:
    """The most recent swing k < `before`, already confirmed at candle `now` (k + 2 ≤ now), not earlier than `start`."""
    k = min(before - 1, now - 2)
    while k >= start:
        if flags[k]:
            return k
        k -= 1
    return None


@dataclass(slots=True)
class Gap:
    index: int  # the third candle ([-1] when it formed)
    bullish: bool
    top: float
    bottom: float

    @property
    def ce_50(self) -> float:
        return (self.top + self.bottom) / 2


def fvg_at(c: list[Candle], k: int, bullish: bool, min_size: float) -> Optional[Gap]:
    if k < 2:
        return None
    if bullish and c[k].low > c[k - 2].high and c[k].low - c[k - 2].high >= min_size:
        return Gap(k, True, c[k].low, c[k - 2].high)
    if not bullish and c[k].high < c[k - 2].low and c[k - 2].low - c[k].high >= min_size:
        return Gap(k, False, c[k - 2].low, c[k].high)
    return None


def gaps(c: list[Candle], frm: int, to: int, bullish: bool, min_size: float) -> list[Gap]:
    """Every FVG whose third candle lies in [frm, to]."""
    return [g for k in range(max(frm, 2), to + 1) if (g := fvg_at(c, k, bullish, min_size))]


@dataclass(slots=True)
class OrderBlock:
    index: int
    bullish: bool
    top: float
    bottom: float
    mean: float  # 50 % of the body


def order_block(c: list[Candle], break_index: int, bullish: bool, lookback: int = 10) -> Optional[OrderBlock]:
    """Bullish MSS → the lowest bearish candle of the `lookback` candles before the break; bearish MSS → the highest
    bullish candle."""
    best = None
    for j in range(max(0, break_index - lookback), break_index):
        x = c[j]
        if bullish and x.close < x.open and (best is None or x.low < c[best].low):
            best = j
        if not bullish and x.close > x.open and (best is None or x.high > c[best].high):
            best = j
    if best is None:
        return None
    x = c[best]
    return OrderBlock(best, bullish, x.high, x.low, (x.open + x.close) / 2)


@dataclass(slots=True)
class Ote:
    start: float
    end: float
    ote_618: float
    ote_705: float
    ote_786: float
    eq_50: float

    @property
    def top(self) -> float:
        return max(self.ote_618, self.ote_786)

    @property
    def bottom(self) -> float:
        return min(self.ote_618, self.ote_786)


def ote(swing_start: float, swing_end: float) -> Ote:
    """Fibonacci OTE of the leg swing_start → swing_end (bullish when the end is above the start)."""
    rng = abs(swing_end - swing_start)
    s = -1 if swing_end > swing_start else 1  # retrace back toward the start
    return Ote(swing_start, swing_end, swing_end + s * 0.618 * rng, swing_end + s * 0.705 * rng, swing_end + s * 0.786 * rng,
               swing_end + s * 0.5 * rng)


# ---------------------------------------------------------------- indicators (None until defined)
def ema(v: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    k, e = 2 / (n + 1), None
    for i, x in enumerate(v):
        e = x if e is None else x * k + e * (1 - k)
        out[i] = e if i >= n - 1 else None
    return out


def atr(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    a = None
    for i in range(len(c)):
        tr = c[i].high - c[i].low if i == 0 else max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close)
        a = tr if a is None else (a * (n - 1) + tr) / n
        out[i] = a if i >= n else None
    return out


def adx(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    tr_s = pdm_s = ndm_s = None
    a = None
    for i in range(1, len(c)):
        up, dn = c[i].high - c[i - 1].high, c[i - 1].low - c[i].low
        pdm = up if up > dn and up > 0 else 0
        ndm = dn if dn > up and dn > 0 else 0
        tr = max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close)
        if tr_s is None:
            tr_s, pdm_s, ndm_s = tr, pdm, ndm
        else:
            tr_s, pdm_s, ndm_s = tr_s - tr_s / n + tr, pdm_s - pdm_s / n + pdm, ndm_s - ndm_s / n + ndm
        if i < n or not tr_s:
            continue
        pdi, ndi = 100 * pdm_s / tr_s, 100 * ndm_s / tr_s
        dx = 0 if pdi + ndi == 0 else 100 * abs(pdi - ndi) / (pdi + ndi)
        a = dx if a is None else (a * (n - 1) + dx) / n
        if i >= 2 * n:
            out[i] = a
    return out


def rsi(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    if len(c) <= n:
        return out
    gain = loss = 0.0
    for i in range(1, n + 1):
        d = c[i].close - c[i - 1].close
        gain += max(d, 0)
        loss += max(-d, 0)
    gain, loss = gain / n, loss / n
    out[n] = 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
    for i in range(n + 1, len(c)):
        d = c[i].close - c[i - 1].close
        gain = (gain * (n - 1) + max(d, 0)) / n
        loss = (loss * (n - 1) + max(-d, 0)) / n
        out[i] = 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def aggregate(c: list[Candle], bucket: int, offset: int = 0) -> list[Candle]:
    """Higher-timeframe candles from lower ones; `offset` shifts the bucket grid (UTC+1 days: offset = 3600)."""
    out: list[Candle] = []
    for x in c:
        t = (x.time + offset) // bucket * bucket - offset
        if out and out[-1].time == t:
            o = out[-1]
            o.high, o.low, o.close = max(o.high, x.high), min(o.low, x.low), x.close
        else:
            out.append(Candle(t, x.open, x.high, x.low, x.close, x.volume))
    return out


def in_window(c: list[Candle], a: int, b: int, m0: int, m1: int) -> list[int]:
    """Indices of a day's candles whose open lies in [m0, m1) UTC+1 minutes."""
    return [i for i in range(a, b + 1) if m0 <= mt(c[i].time)[1] < m1]
