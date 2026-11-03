"""London breakout (GBP/USD): Asian range, strong breakout candle in the window, stop at the other side, 2R."""
from app.strategies.london.config import LONDON_CONFIGS
from app.strategies.london.strategy import _setup_at, asian_ranges
from app.strategies.shared.indicators import atr_series
from app.strategies.shared.types import Candle

CFG = LONDON_CONFIGS["GBP/USD"]
DAY = 1_800_000_000 // 86400 * 86400  # a midnight (UTC)


def _day(breakout: Candle) -> list[Candle]:
    c = []
    for h in range(-30, 0):  # some history before the day, for the ATR
        t = DAY + h * 3600
        c.append(Candle(t, 1.2700, 1.2715, 1.2685, 1.2702, 0))
    for h in range(7):  # Asian range 1.2690 – 1.2710
        c.append(Candle(DAY + h * 3600, 1.2700, 1.2710, 1.2690, 1.2701, 0))
    c.append(breakout)
    return c


def test_strong_close_above_the_asian_range_is_a_buy():
    c = _day(Candle(DAY + 7 * 3600, 1.2702, 1.2730, 1.2700, 1.2728, 0))  # strong body, close in the top third
    s = _setup_at(c, len(c) - 1, atr_series(c, 14), asian_ranges(c, CFG), CFG)
    assert s and s["buy"] and s["entry"] == 1.2728 and s["sl"] == 1.2690  # stop at the low of the range


def test_pin_bar_or_late_breakout_or_wide_range_is_no_trade():
    pin = _day(Candle(DAY + 7 * 3600, 1.2702, 1.2740, 1.2700, 1.2712, 0))  # closes just above, long wick back in
    assert _setup_at(pin, len(pin) - 1, atr_series(pin, 14), asian_ranges(pin, CFG), CFG) is None
    late = _day(Candle(DAY + 11 * 3600, 1.2702, 1.2730, 1.2700, 1.2728, 0))  # 11:00 GMT: after the window
    assert _setup_at(late, len(late) - 1, atr_series(late, 14), asian_ranges(late, CFG), CFG) is None
    sell = _day(Candle(DAY + 8 * 3600, 1.2698, 1.2700, 1.2668, 1.2670, 0))
    s = _setup_at(sell, len(sell) - 1, atr_series(sell, 14), asian_ranges(sell, CFG), CFG)
    assert s and not s["buy"] and s["sl"] == 1.2710  # stop at the high of the range


def test_gbpusd_runs_the_london_breakout():
    from app.strategies.service import STRATEGY_DEFS

    d = STRATEGY_DEFS["GBP/USD"]
    assert d.entryTf == "H1" and d.canSignalAt(DAY + 8 * 3600) and not d.canSignalAt(DAY + 13 * 3600)
    assert STRATEGY_DEFS["EUR/USD"].entryTf == "H4"  # EUR/USD: sweep + break of structure H4
