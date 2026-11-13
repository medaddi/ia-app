"""
The CandleSanitizer (the user's spec data_feed_charting_engine_architecture_prompt.md, Phase 1.3): every candle series
goes through it before the charts or the 7 agents see it.

1. UTC: a candle off its timeframe's grid is moved to its slot; duplicates merged, the series sorted.
2. Gaps: missing intraday slots while the market is open (Sunday 17:00 to Friday 17:00 New York, the 16:55-18:10 New
   York daily break excepted: gold's closed hour and the rollover, CHOICE) are listed so the feed manager can backfill them. A gap the
   provider cannot fill stays a gap: no candle is ever invented.
3. Bad ticks: a wick longer than 4.5 × ATR 20 beyond the candle's body that the next candle does not revisit, on a candle
   with no volume follow-through (volume <= 20 % of its 20-candle average, or none), is a FEED_ARTIFACT: its wick is cut
   back to the body ± 1 ATR 20 (CHOICE: the spec's tick-level "reverts within 500 ms" cannot be seen on candles).

The OHLC the analysis reads is the provider's mid price when it gives bid / ask (OANDA); the spread travels apart.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from .types import Candle

DAY = 86400
NY = ZoneInfo("America/New_York")


def market_open(t: int) -> bool:
    """Is a candle opening at t inside FX / gold trading hours? Both follow New York time (so the UTC hours move with
    daylight saving): the week runs Sunday 17:00 to Friday 17:00 New York, and the daily break 16:55-18:10 New York
    holds the FX rollover (17:00) and gold's closed hour (17:00-18:00)."""
    d = datetime.fromtimestamp(t, NY)
    wd, m = d.weekday(), d.hour * 60 + d.minute  # Monday = 0
    if wd == 5 or (wd == 4 and m >= 16 * 60 + 55) or (wd == 6 and m < 18 * 60 + 10):
        return False
    return not (16 * 60 + 55 <= m < 18 * 60 + 10)


def _atr(c: list[Candle], n: int = 20) -> list:
    out = [None] * len(c)
    a = None
    for i in range(1, len(c)):
        tr = max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close)
        a = tr if a is None else (a * (n - 1) + tr) / n
        out[i] = a if i >= n else None
    return out


def missing_slots(c: list[Candle], step: int, since: int = 0) -> list[int]:
    """Intraday slots in market hours with no candle, between the first and the last candle (from `since`)."""
    if step >= DAY or len(c) < 2:
        return []
    have = {x.time for x in c}
    out = []
    t = max(c[0].time, since - since % step)
    while t < c[-1].time:
        if t not in have and market_open(t):
            out.append(t)
        t += step
    return out


def sanitize(c: list[Candle], step: int) -> tuple[list[Candle], dict]:
    """Returns (clean candles, report). The report: bars, offGrid, duplicates, missing (slot times), artifacts (times)."""
    rep = {"bars": 0, "offGrid": 0, "duplicates": 0, "missing": [], "artifacts": [], "continuity": 1.0}
    if not c:
        return c, rep
    slots: dict[int, Candle] = {}
    for x in c:
        if not all(isinstance(v, (int, float)) and v == v for v in (x.open, x.high, x.low, x.close)) or x.high < x.low:
            continue
        t = int(x.time)
        if step < DAY and t % step:
            t -= t % step
            rep["offGrid"] += 1
        if t in slots:  # two pieces of one slot: merged
            rep["duplicates"] += 1
            y = slots[t]
            y.high, y.low, y.close = max(y.high, x.high), min(y.low, x.low), x.close
            y.volume = (y.volume or 0) + (x.volume or 0)
            continue
        slots[t] = Candle(t, x.open, x.high, x.low, x.close, x.volume, getattr(x, "spread", 0.0))
    out = [slots[t] for t in sorted(slots)]
    at = _atr(out, 20)
    for i in range(20, len(out) - 1):
        x, nx = out[i], out[i + 1]
        a = at[i - 1]
        if not a:
            continue
        vols = [y.volume or 0 for y in out[i - 20:i]]
        avg = sum(vols) / 20
        quiet = (x.volume or 0) <= 0.2 * avg if avg > 0 else True
        top, bot = max(x.open, x.close), min(x.open, x.close)
        if x.high - top > 4.5 * a and nx.high < x.high - 0.5 * (x.high - top) and quiet:
            x.high = top + a
            rep["artifacts"].append(x.time)
        if bot - x.low > 4.5 * a and nx.low > x.low + 0.5 * (bot - x.low) and quiet:
            x.low = bot - a
            rep["artifacts"].append(x.time)
    rep["bars"] = len(out)
    rep["missing"] = missing_slots(out, step)
    expected = len(out) + len(rep["missing"])
    rep["continuity"] = len(out) / expected if expected else 1.0
    return out, rep


def merge(base: list[Candle], extra: list[Candle]) -> list[Candle]:
    """The backfill: candles from `extra` fill slots `base` lacks (base wins where both have one)."""
    have = {x.time for x in base}
    return sorted(base + [x for x in extra if x.time not in have], key=lambda x: x.time)
