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


def test_levels_snap_to_the_tick_safely():
    from app.strategies.shared.risk import snap_sl, snap_tp

    # BUY: stop rounds down (wider), target rounds down (closer); SELL: the mirror. Never tighter stop or further target.
    assert snap_sl(1.123456, True, 5) == 1.12345 and snap_tp(1.134569, True, 5) == 1.13456
    assert snap_sl(1.123451, False, 5) == 1.12346 and snap_tp(1.110001, False, 5) == 1.11001
    assert snap_sl(1.12345, True, 5) == 1.12345 and snap_sl(2650.004, False, 2) == 2650.01  # already on the tick: unchanged


def test_past_trades_are_tp_sl_or_be_and_score_the_pair():
    from app.strategies.shared.common import history_stats, trade_class

    assert (trade_class(1.75), trade_class(-1.03), trade_class(0.02), trade_class(None)) == ("TP", "SL", "BE", "BE")
    past = [{"r": 2.0, "signalTime": 1}, {"r": -1.0, "signalTime": 2}, {"r": -1.0, "signalTime": 3}, {"r": 0.01, "signalTime": 4}, {"r": 0.5, "signalTime": 5}]
    st = history_stats(past)
    assert (st["trades"], st["tp"], st["sl"], st["be"], st["winRate"]) == (5, 2, 2, 1, 50)
    assert st["totalR"] == 0.51 and st["profitFactor"] == 1.25 and st["maxDrawdownR"] == 2.0 and st["maxLosingRun"] == 2
    assert history_stats([])["winRate"] is None


def test_signal_shows_how_often_past_trades_reached_its_tp():
    from app.strategies.shared.common import target_hit_pct
    from app.telegram.bot import format_signal_message

    past = [{"reachR": x} for x in (0.4, 1.6, 2.5, 1.5, 0.9)]
    assert target_hit_pct(past, {"entry": 1.1, "sl": 1.099, "tp3": 1.1015}) == 60  # 1.5R: 3 of 5 got there
    assert target_hit_pct([], {"entry": 1.1, "sl": 1.099, "tp3": 1.1015}) is None
    msg = format_signal_message({"symbol": "EUR/USD", "signalType": "BUY", "entryPrice": 1.1, "stopLoss": 1.099, "target1": 1.101, "target2": 1.10125,
                                 "target3": 1.1015, "confidence": 80, "targetHitPct": 60, "signalJson": {"setup": "RSI2", "entry_type": "MARKET"}})
    assert "TP <code>1.10150</code> · 1:1.5" in msg and "reached by 60%" in msg
