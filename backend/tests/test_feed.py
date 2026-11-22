"""The data feed spec (data_feed_charting_engine_architecture_prompt.md): sanitizer and OANDA parsing (the M5 / tick-volume audit was removed with the FXAlexG redesign)."""

from app.market import oanda
from app.market.sanitize import market_open, merge, sanitize
from app.market.types import Candle

T0 = 1_790_000_000 - 1_790_000_000 % 86400  # a UTC midnight
while not market_open(T0 + 8 * 3600) or not market_open(T0 + 20 * 3600):
    T0 += 86400
S = T0 + 8 * 3600  # 08:00 UTC on a trading day


def bars(n, start=S, step=300, vol=10.0):
    return [Candle(start + i * step, 1.0, 1.0004, 0.9996, 1.0, vol) for i in range(n)]


def test_off_grid_duplicates_and_gaps():
    c = bars(30)
    c[5].time += 17  # off its 5-minute slot
    del c[10]  # a missing candle
    c.append(Candle(c[3].time, 1.0, 1.0010, 0.9990, 1.0, 5))  # a second piece of slot 3
    out, rep = sanitize(c, 300)
    assert rep["offGrid"] == 1 and rep["duplicates"] == 1 and rep["missing"] == [S + 10 * 300]
    assert len(out) == 29 and out[3].high == 1.0010 and all(x.time % 300 == 0 for x in out)
    assert abs(rep["continuity"] - 29 / 30) < 1e-9
    back, rep2 = sanitize(merge(out, [Candle(S + 3000, 1.0, 1.0002, 0.9998, 1.0, 3)]), 300)
    assert rep2["missing"] == [] and rep2["continuity"] == 1.0


def test_a_lone_spike_without_volume_is_cut():
    c = bars(40)
    c[30] = Candle(c[30].time, 1.0, 1.0200, 0.9996, 1.0, 0.0)  # a 200-pip wick on no volume, never revisited
    out, rep = sanitize(c, 300)
    assert rep["artifacts"] == [c[30].time] and out[30].high < 1.002
    c[30].volume = 50.0  # the same wick on heavy volume is a real move: kept
    out, rep = sanitize(c, 300)
    assert rep["artifacts"] == [] and out[30].high == 1.0200


def test_market_hours_follow_new_york_time():
    from datetime import datetime, timezone
    win, summer = int(datetime(2026, 11, 10, 22, 30, tzinfo=timezone.utc).timestamp()), int(datetime(2026, 7, 7, 21, 30, tzinfo=timezone.utc).timestamp())
    assert not market_open(win) and not market_open(summer)  # 17:30 New York both times: gold's closed hour
    assert market_open(summer + 3600) and not market_open(win - 3600 * 24 * 4 + 3600 * 0)  # summer 22:30 UTC open; Friday 22:30 UTC shut
    out, rep = sanitize(bars(5, win - 50 * 60) + bars(5, win + 40 * 60), 300)
    assert rep["missing"] == []  # the break is not a gap


def test_oanda_mid_candles_carry_the_spread():
    body = {"candles": [{"time": "2026-11-09T13:05:00.000000000Z", "volume": 42, "complete": True,
                         "mid": {"o": "1.10001", "h": "1.10050", "l": "1.09990", "c": "1.10020"},
                         "bid": {"o": "1.09995", "h": "1.10044", "l": "1.09984", "c": "1.10014"},
                         "ask": {"o": "1.10007", "h": "1.10056", "l": "1.09996", "c": "1.10026"}}]}
    c = oanda.parse(body, 5)[0]
    assert c.time % 300 == 0 and c.close == 1.1002 and c.volume == 42 and abs(c.spread - 0.00012) < 1e-9
