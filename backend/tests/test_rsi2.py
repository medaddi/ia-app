"""RSI(2) Connors pullback on hand-built H4 candles: the entry at the oversold close inside the trend, the stop, and the EMA5 exit."""

from app.agent.trade_desk import review
from app.agent.validator import validate_signal
from app.strategies.rsi2.config import RSI2_CONFIGS
from app.strategies.rsi2.strategy import evaluate_rsi2
from app.strategies.shared.types import Candle

H4 = 4 * 3600
T0 = 1_790_000_000 - 1_790_000_000 % H4
CFG = RSI2_CONFIGS["EUR/USD"]


def series(direction: int = 1, extra: list | None = None):
    """300 trending H4 candles (+/-5 pips each, small zig-zag), then 2 candles against the trend (RSI(2) extreme)."""
    c, price = [], 1.1000
    for k in range(300):
        o = price
        price += direction * (0.0005 if k % 3 else -0.0002)
        c.append(Candle(T0 + k * H4, o, max(o, price) + 0.0003, min(o, price) - 0.0003, price))
    for _ in range(2):
        o = price
        price -= direction * 0.0015
        c.append(Candle(c[-1].time + H4, o, max(o, price) + 0.0002, min(o, price) - 0.0002, price))
    for x in extra or []:
        c.append(Candle(c[-1].time + H4, *x))
    return c


def run(c, now=None, **over):
    inp = {"candles": {"H4": c}, "nowSec": now or c[-1].time + H4, "livePrice": 0, "spread": None, "isMarketOpen": True, "isRealData": True,
           "dataSource": "test", "news": {"events": [], "source": "test"}, "day": {"trades": 0, "losses": 0}}
    inp.update(over)
    return evaluate_rsi2(inp, CFG)


def test_buy_at_the_oversold_close_inside_the_uptrend():
    c = series(1)
    r = run(c)
    s = r["setup"]
    assert r["status"] == "SIGNAL" and s["direction"] == "BUY" and s["setup"] == "RSI2" and s["entryType"] == "MARKET"
    assert s["entry"] == round(c[-1].close, 5) and s["sl"] < s["entry"]
    assert s["anchors"]["rsi2"]["rsi"] < CFG["rsiBuyBelow"]
    assert validate_signal(r)["approved"] and review(r)["approved"]


def test_sell_mirror_in_the_downtrend():
    r = run(series(-1))
    assert r["status"] == "SIGNAL" and r["setup"]["direction"] == "SELL" and r["setup"]["sl"] > r["setup"]["entry"]


def test_exit_at_the_first_close_back_above_ema5():
    c = series(1)
    p = c[-1].close
    after = series(1, extra=[(p, p + 0.0025, p - 0.0001, p + 0.0022)])  # strong close back above EMA5
    lc = run(after)["setup"]["lifecycle"]
    assert lc["state"] == "CLOSED" and lc["outcome"] == "WIN" and 0 < lc["rMultiple"] < 1  # closed at market, not at a fixed target
    assert lc["exitTime"] == after[-1].time and lc["events"][-1]["type"] == "SIGNAL_EXIT"


def test_no_trade_without_trend_or_on_news():
    flat = [Candle(T0 + k * H4, 1.1, 1.1003, 1.0997, 1.1 + (0.0002 if k % 2 else -0.0002)) for k in range(300)]
    assert run(flat)["status"] != "SIGNAL"
    c = series(1)
    news = {"events": [{"time": c[-1].time + H4, "currency": "USD", "title": "Non-Farm Payrolls", "impact": "High"}], "source": "test"}
    r = run(c, now=c[-1].time + H4 + 60, news=news)
    assert r["news"]["blocked"] and r["status"] != "SIGNAL"
