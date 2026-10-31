"""
Timezone-aware session helpers. Windows are defined in local time (Europe/London,
America/New_York) and converted to UTC with the real DST offset of that date.
"""

import calendar
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

from .types import Candle

LONDON = "Europe/London"
NEW_YORK = "America/New_York"


@dataclass(slots=True, frozen=True)
class ZonedParts:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    weekday: int  # Sunday = 0 (JS convention)


@lru_cache(maxsize=16)
def _zone(tz: str) -> ZoneInfo:
    return ZoneInfo(tz)


@lru_cache(maxsize=400_000)
def zoned_parts(ts_sec: int, tz: str) -> ZonedParts:
    dt = datetime.fromtimestamp(math.floor(ts_sec), _zone(tz))
    return ZonedParts(dt.year, dt.month, dt.day, dt.hour, dt.minute, (dt.weekday() + 1) % 7)


def tz_offset_sec(ts_sec: int, tz: str) -> int:
    """Offset of `tz` from UTC at that instant, in seconds (London summer = +3600)."""
    z = zoned_parts(ts_sec, tz)
    return calendar.timegm((z.year, z.month, z.day, z.hour, z.minute, 0)) - math.floor(ts_sec / 60) * 60


def zoned_to_utc(year: int, month: int, day: int, hour: int, minute: int, tz: str) -> int:
    """Converts a local wall-clock time in `tz` to a UTC unix timestamp."""
    guess = calendar.timegm((year, month, day, hour, minute, 0))
    first = guess - tz_offset_sec(guess, tz)
    return guess - tz_offset_sec(first, tz)


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def minutes_of_day(ts_sec: int, tz: str) -> int:
    z = zoned_parts(ts_sec, tz)
    return z.hour * 60 + z.minute


def in_local_window(ts_sec: int, tz: str, start: str, end: str) -> bool:
    """True if ts_sec falls in [start, end) local time of `tz`."""
    m = minutes_of_day(ts_sec, tz)
    ah, am = _hm(start)
    bh, bm = _hm(end)
    return ah * 60 + am <= m < bh * 60 + bm


def local_date_key(ts_sec: int, tz: str) -> str:
    z = zoned_parts(ts_sec, tz)
    return f"{z.year}-{z.month:02d}-{z.day:02d}"


@lru_cache(maxsize=4096)
def window_bounds(date_key: str, tz: str, start: str, end: str) -> tuple[int, int]:
    """UTC bounds of a local window on a given local date."""
    y, mo, d = (int(x) for x in date_key.split("-"))
    ah, am = _hm(start)
    bh, bm = _hm(end)
    return zoned_to_utc(y, mo, d, ah, am, tz), zoned_to_utc(y, mo, d, bh, bm, tz)


def trading_day_key(ts_sec: int) -> str:
    """Forex trading day: rolls over at 17:00 New York (so the key is the NY date 7h later)."""
    return local_date_key(ts_sec + 7 * 3600, NEW_YORK)


@lru_cache(maxsize=8192)
def _monday_of(day_key: str) -> str:
    y, m, d = (int(x) for x in day_key.split("-"))
    dt = date(y, m, d)
    return (dt - timedelta(days=dt.weekday())).isoformat()


def trading_week_key(ts_sec: int) -> str:
    """Trading week key: the Monday of the trading day's week."""
    return _monday_of(trading_day_key(ts_sec))


@dataclass(slots=True)
class SessionRange:
    name: str
    dateKey: str
    startSec: int
    endSec: int
    high: float
    low: float
    highTime: int
    lowTime: int
    complete: bool

    def to_dict(self):
        return asdict(self)


def session_range(c: list[Candle], tf_sec: int, name: str, date_key: str, tz: str, start: str, end: str, now_sec: int) -> Optional[SessionRange]:
    """High/low of candles inside a session window, using only candles closed by now_sec."""
    start_sec, end_sec = window_bounds(date_key, tz, start, end)
    high, low, high_time, low_time = -math.inf, math.inf, 0, 0
    for x in c:
        if x.time < start_sec or x.time >= end_sec or x.time + tf_sec > now_sec:
            continue
        if x.high > high:
            high, high_time = x.high, x.time
        if x.low < low:
            low, low_time = x.low, x.time
    if math.isinf(high):
        return None
    return SessionRange(name, date_key, start_sec, end_sec, high, low, high_time, low_time, now_sec >= end_sec)
