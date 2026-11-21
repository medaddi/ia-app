"""
2.3 and 3.7.6 of the spec: candles aligned to the New York 17:00 daily close (5 daily candles a week, no Sunday ghost
candle), the W / D / H4 / H2 buckets built from H1, and the UTC session and blackout windows. DST comes from the IANA
database (America/New_York), never a hard-coded offset.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from ..playbook import _Bar

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


@lru_cache(maxsize=200000)
def ny_day_open(t: int) -> int:
    """The UTC unix time of the NY 17:00 that opened the trading day holding instant t."""
    ny = datetime.fromtimestamp(t, UTC).astimezone(NY)
    base = ny.replace(hour=17, minute=0, second=0, microsecond=0)
    if ny < base:
        base -= timedelta(days=1)
    return int(base.astimezone(UTC).timestamp())


def ny_bucket(t: int, hours: int) -> int:
    """The start of the `hours`-hour bucket (4 or 2) counted from the NY 17:00 day open (H4: 17, 21, 01, 05, 09, 13 NY)."""
    d0 = ny_day_open(t)
    return d0 + ((t - d0) // (hours * 3600)) * hours * 3600


def trading_day(t: int) -> datetime:
    """The trading day's date (the NY 17:00 open + 7 h): Sunday 17:00 NY opens Monday."""
    return datetime.fromtimestamp(ny_day_open(t), UTC).astimezone(NY) + timedelta(hours=7)


def group(c, key) -> list:
    """Bigger candles from smaller ones by a bucket function; each bucket's candle starts at its first bar's bucket key."""
    out, cur, ck = [], None, None
    for x in c:
        k = key(x.time)
        if cur is None or k != ck:
            cur, ck = _Bar(k, x.open, x.high, x.low, x.close), k
            out.append(cur)
        else:
            cur.high, cur.low, cur.close = max(cur.high, x.high), min(cur.low, x.low), x.close
    return out


def daily_ny(h1) -> list:
    """D candles from H1 closing at NY 17:00 (a weekend bar, if any, joins Monday's candle: never a Sunday candle)."""
    return [d for d in group(h1, ny_day_open) if trading_day(d.time).weekday() < 5]


def weekly_ny(d) -> list:
    """W candles from NY-aligned D candles: Monday to Friday trading days (the week opens Sunday 17:00 NY)."""
    def wk(t):
        td = trading_day(t)
        return int((td - timedelta(days=td.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    return group(d, wk)


def h4_ny(h1) -> list:
    return group(h1, lambda t: ny_bucket(t, 4))


def h2_ny(h1) -> list:
    return group(h1, lambda t: ny_bucket(t, 2))


# ---- 3.7.6 sessions and blackouts (UTC)
def _hm(t: int) -> float:
    d = datetime.fromtimestamp(t, UTC)
    return d.hour + d.minute / 60


def in_session(t: int) -> bool:
    """London 07:00-11:30, London-New York 12:00-16:30, New York 16:30-19:00 UTC."""
    h = _hm(t)
    return 7 <= h < 11.5 or 12 <= h < 19


def blackout(t: int) -> str | None:
    """Step 4, S12: no new entry in the rollover 21:00-23:30 UTC, on Friday after 19:00 UTC, or in the weekend (the Sunday open
    included until 23:30 UTC)."""
    d = datetime.fromtimestamp(t, UTC)
    h = _hm(t)
    if d.weekday() == 5 or (d.weekday() == 6 and h < 23.5):
        return "SESSION_BLACKOUT"
    if d.weekday() == 4 and h >= 19:
        return "SESSION_BLACKOUT"
    if 21 <= h < 23.5:
        return "SESSION_BLACKOUT"
    return None


def news_block(t: int, news: list[int] | None) -> int | None:
    """A red-folder release of the pair's currencies (BOTH legs) with t in [T - 45 min, T + 30 min], or None."""
    for n in news or []:
        if n - 45 * 60 <= t <= n + 30 * 60:
            return n
    return None
