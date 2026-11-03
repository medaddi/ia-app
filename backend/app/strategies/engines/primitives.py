"""
The building blocks of the three pair agents, as numbers (docs/STRATEGIES.md, part 1):

- Swing (fractal 5 bars): candle k is a swing high when High[k] is above the two candles on each side (a swing low:
  Low[k] below them). It is only known once the 2 right-side candles have closed: confirmed at k + 2.
- Sweep: price trades beyond a key level (its wick) and the strategy waits for the close back inside.
- MSS: a candle CLOSES beyond the last swing formed before the sweep (below the last swing low after a high was swept).
- FVG on the three candles k-2, k-1, k: bullish when Low[k] > High[k-2] (gap High[k-2] → Low[k]), bearish when
  High[k] < Low[k-2] (gap High[k] → Low[k-2]); its 50 % is the middle of the gap.

Everything here only looks back, so it can be computed once on a series and read at any candle without look-ahead
(the confirmation delay of a swing aside, which every caller respects).
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from ..shared.sessions import zoned_parts
from ..shared.types import Candle

LONDON = "Europe/London"


@dataclass(slots=True)
class Gap:
    index: int  # the third candle (the gap exists once it has closed)
    bullish: bool
    top: float
    bottom: float

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2


def swing_flags(c: list[Candle]) -> tuple[list[bool], list[bool]]:
    """(is_high[k], is_low[k]): the 5-bar fractal. Known at k + 2."""
    n = len(c)
    hi, lo = [False] * n, [False] * n
    for k in range(2, n - 2):
        h, l_ = c[k].high, c[k].low
        hi[k] = h > c[k - 1].high and h > c[k - 2].high and h > c[k + 1].high and h > c[k + 2].high
        lo[k] = l_ < c[k - 1].low and l_ < c[k - 2].low and l_ < c[k + 1].low and l_ < c[k + 2].low
    return hi, lo


def last_swing(flags: list[bool], before: int, now: int, start: int = 0) -> Optional[int]:
    """The most recent swing k < `before` already confirmed at candle `now` (k + 2 <= now), not earlier than `start`."""
    k = min(before - 1, now - 2)
    while k >= start:
        if flags[k]:
            return k
        k -= 1
    return None


def gaps(c: list[Candle], frm: int, to: int, bullish: bool, min_size: float) -> list[Gap]:
    """The FVGs whose third candle lies in [frm, to], at least `min_size` tall."""
    out = []
    for k in range(max(frm, 2), to + 1):
        if bullish and c[k].low > c[k - 2].high and c[k].low - c[k - 2].high > min_size:
            out.append(Gap(k, True, c[k].low, c[k - 2].high))
        if not bullish and c[k].high < c[k - 2].low and c[k - 2].low - c[k].high > min_size:
            out.append(Gap(k, False, c[k - 2].low, c[k].high))
    return out


def rsi(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    """Wilder's RSI on closes (None until defined)."""
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


def aggregate(c: list[Candle], bucket: int) -> list[Candle]:
    """Higher-timeframe candles from lower ones (UTC-aligned buckets, like the provider's H4)."""
    out: list[Candle] = []
    for x in c:
        t = x.time // bucket * bucket
        if out and out[-1].time == t:
            o = out[-1]
            o.high, o.low, o.close = max(o.high, x.high), min(o.low, x.low), x.close
        else:
            out.append(Candle(t, x.open, x.high, x.low, x.close, x.volume))
    return out


@lru_cache(maxsize=200_000)
def london(ts: int) -> tuple[str, int, int]:
    """(London date, minute of the day, weekday Sun=0) of a timestamp: the sessions follow London's clock, DST included
    (Morocco's clock in summer; one hour behind it in winter, when London opens at 09:00 Morocco time)."""
    z = zoned_parts(ts, LONDON)
    return f"{z.year}-{z.month:02d}-{z.day:02d}", z.hour * 60 + z.minute, z.weekday


def by_day(c: list[Candle]) -> list[tuple[str, int, int]]:
    """[(London date, first index, last index)] in order."""
    out: list[tuple[str, int, int]] = []
    for i, x in enumerate(c):
        d = london(x.time)[0]
        if out and out[-1][0] == d:
            out[-1] = (d, out[-1][1], i)
        else:
            out.append((d, i, i))
    return out


def hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def fingerprint(c: list[Candle], a: int, b: int) -> tuple:
    """What identifies a day's candles for the day cache: bounds, count, extremes and the last close."""
    seg = c[a:b + 1]
    return (c[a].time, c[b].time, b - a, max(x.high for x in seg), min(x.low for x in seg), c[b].close)
