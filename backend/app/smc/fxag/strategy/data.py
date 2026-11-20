"""
Agent 1 · DataGuard (spec 4): the closed candles of one pair on the 7 timeframes {W, D, H4, H2, H1, M30, M15}, aligned to
the NY 17:00 close; bar continuity (gaps, duplicates); the live spread; the pair's news blackout schedule.
Output: MarketSnapshot (the timeframes) + HealthStatus.
"""

from bisect import bisect_right

from ...playbook import M5S, _Bar, resample
from datetime import timedelta

from ..time_utils import daily_ny, h2_ny, h4_ny, ny_day_open, trading_day

TF_NOMINAL = {"W": 7 * 86400, "D": 86400, "H4": 14400, "H2": 7200, "H1": 3600, "M30": 1800, "M15": 900}


class Series:
    """One timeframe: candles and their close times (explicit: a NY day / week does not end on a UTC multiple)."""

    def __init__(self, name: str, c: list, close: list[int]):
        self.name, self.c, self.tc = name, c, close
        self.t = [x.time for x in c]

    def idx(self, T: int) -> int:
        """The last candle closed at T (-1 when none)."""
        return bisect_right(self.tc, T) - 1

    def __len__(self):
        return len(self.c)


def _closes(c: list, nominal: int) -> list[int]:
    return [min(c[i + 1].time, c[i].time + nominal) if i + 1 < len(c) else c[i].time + nominal for i in range(len(c))]


def _weekly(days: list) -> tuple[list, list[int]]:
    """W candles (Monday to Friday trading days); each starts at its first day's NY 17:00 open and closes with its last
    trading day (Friday 17:00 NY)."""
    out, close, cur, ck = [], [], None, None
    for d in days:
        td = trading_day(d.time)
        k = (td - timedelta(days=td.weekday())).date()
        if cur is None or k != ck:
            cur, ck = _Bar(d.time, d.open, d.high, d.low, d.close), k
            out.append(cur)
            close.append(d.time + 86400)
        else:
            cur.high, cur.low, cur.close = max(cur.high, d.high), min(cur.low, d.low), d.close
            close[-1] = d.time + 86400
    return out, close


def snapshot(m5: list, h1: list, d_hist: list | None = None) -> dict:
    """MarketSnapshot: the 7 timeframes from M5 (M15 / M30), H1 (H2 / H4 / D NY-aligned) and, for the weekly memory older
    than the H1 history, the feed's daily candles (d_hist) regrouped into NY weeks."""
    days = daily_ny(h1)
    older = []
    if d_hist and days:
        first = days[0].time
        older = [_Bar(ny_day_open(x.time + 3 * 3600), x.open, x.high, x.low, x.close) for x in d_hist
                 if ny_day_open(x.time + 3 * 3600) < first and trading_day(x.time + 3 * 3600).weekday() < 5]
    all_days = older + days
    w, wc = _weekly(all_days)
    h4, h2 = h4_ny(h1), h2_ny(h1)
    m15, m30 = resample(m5, 900), resample(m5, 1800)
    return {"W": Series("W", w, wc), "D": Series("D", days, _closes(days, 86400)), "H4": Series("H4", h4, _closes(h4, 14400)),
            "H2": Series("H2", h2, _closes(h2, 7200)), "H1": Series("H1", h1, [x.time + 3600 for x in h1]),
            "M30": Series("M30", m30, [x.time + 1800 for x in m30]), "M15": Series("M15", m15, [x.time + 900 for x in m15]),
            "W_hist_from": all_days[0].time if all_days else None}


def health(h1: list, m5: list, T: int) -> dict:
    """HealthStatus: H1 gaps and duplicates in the last 24 hours before T (a weekend is not a gap), and the data's end."""
    recent = [x for x in h1 if T - 24 * 3600 <= x.time < T]
    gaps, dups = [], 0
    for a, b in zip(recent, recent[1:]):
        if b.time == a.time:
            dups += 1
        elif b.time - a.time > 3600 and not (trading_day(a.time).weekday() >= 4 and b.time - a.time >= 24 * 3600):
            gaps.append((a.time + 3600, b.time))
    return {"gaps": gaps, "duplicates": dups, "h1End": h1[-1].time + 3600 if h1 else None, "m5End": m5[-1].time + M5S if m5 else None,
            "ok": not gaps and not dups}
