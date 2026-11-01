"""The three agents: market analysis objects to trades against the daily trend, in a volatility spike or right before major
news; the strategy agent needs a valid fresh signal that fits the market; a trade needs all three."""

import time

from app.agent.agents import consensus, market_agent, strategy_agent
from app.strategies.shared.types import Candle

H = 3600
T0 = (int(time.time()) - 91 * 86400) // 86400 * 86400  # the series ends about now (consensus reads the real clock)


def trend(direction: int, days: int = 90):
    """Hourly candles drifting up (or down) for `days` days."""
    c, p = [], 3000.0
    for k in range(days * 24):
        o = p
        p += direction * 0.4 + (0.3 if k % 2 else -0.3)
        c.append(Candle(T0 + k * H, o, max(o, p) + 0.5, min(o, p) - 0.5, p))
    return c


def result(direction: str, entry: float):
    sl = entry - 10 if direction == "BUY" else entry + 10
    tp = entry + 20 if direction == "BUY" else entry - 20
    return {"spec": {"decimals": 2, "displaySymbol": "XAU/USD"}, "status": "SIGNAL", "score": 90, "canNotify": True, "headline": "",
            "setup": {"id": "XAUUSD-BO-1", "direction": direction, "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": entry, "tp2": entry, "tp3": tp,
                      "lifecycle": {"state": "OPEN"}}}


def test_market_agent_follows_the_daily_trend():
    c = trend(+1)
    now = c[-1].time + H
    buy, sell = result("BUY", c[-1].close), result("SELL", c[-1].close)
    m_buy, m_sell = market_agent(buy, c, [], now), market_agent(sell, c, [], now)
    assert m_buy["bias"] == "bullish" and m_buy["agree"]
    assert not m_sell["agree"] and "daily trend" in m_sell["summary"]
    # Major USD news in 20 minutes: no new trade even with the trend
    news = [{"time": now + 1200, "currency": "USD", "title": "CPI", "impact": "High"}]
    m = market_agent(buy, c, news, now)
    assert not m["agree"] and m["report"]["newsAhead"][0]["inMin"] == 20


def test_strategy_agent_and_consensus_need_all_three(monkeypatch):
    from app.agent import agents

    monkeypatch.setattr(agents, "risk_agent", lambda r, db: agents._vote("risk", "Risk & execution", True, "Order approved", []))
    c = trend(+1)
    now = c[-1].time + H
    buy = result("BUY", c[-1].close)
    m = market_agent(buy, c, [], now)
    s = strategy_agent(buy, m)
    assert s["agree"] and s["plan"]["rr"] == 2.0
    assert not strategy_agent({**buy, "status": "WATCH"}, m)["agree"]
    sell = result("SELL", c[-1].close)
    out = consensus(sell, c, [], None)  # the market objects (counter-trend): no trade, even with risk approving
    assert not out["approved"] and out["agreed"] < 3 and any("Market analysis" in i for i in out["issues"])
    ok = consensus(buy, c, [], None)
    assert ok["approved"] and ok["agreed"] == 3 and ok["summary"].startswith("3/3")


def test_trade_manager_agent():
    from app.agent.agents import manager_agent
    from app.strategies.shared.types import Candle

    now = 1_800_000_000
    base = {"spec": {"decimals": 5}, "timeframes": {"entry": "H4"}, "facts": {}, "price": 1.1010}
    setup = {"direction": "BUY", "entryType": "MARKET", "entry": 1.1000, "sl": 1.0980, "tp3": 1.1040, "signalTime": now - 4 * 14400,
             "setup": "GPA", "params": {}, "expiresAt": None, "lifecycle": {"state": "OPEN", "fillTime": now - 4 * 14400}}
    candles = [Candle(time=now - 4 * 14400, open=1.1, high=1.1025, low=1.0995, close=1.102, volume=0)]
    m = manager_agent({**base, "setup": setup}, candles, None, now)
    assert m["verdict"] == "HOLD" and m["rNow"] == 0.5 and m["bestR"] == 1.25 and "Hold" in m["action"]["en"]
    # gave back a +1.25R gain: caution, still hold
    m = manager_agent({**base, "price": 1.1002, "setup": setup}, candles, None, now)
    assert m["verdict"] == "CAUTION" and "Hold" in m["action"]["en"]
    # news within the hour from the market agent
    market = {"report": {"newsAhead": [{"currency": "USD", "title": "CPI", "inMin": 20}], "volatility": "normal", "dailyTrend": "bullish"}}
    m = manager_agent({**base, "setup": setup}, candles, market, now)
    assert m["verdict"] == "CAUTION" and "USD news in 20 min" in m["action"]["en"]
    # RSI(2): price back above EMA5 → exit forming at the H4 close
    rsi = {**setup, "setup": "RSI2", "params": {"maxBars": 48}}
    m = manager_agent({**base, "facts": {"ema5": 1.1005}, "setup": rsi}, candles, None, now)
    assert m["verdict"] == "EXIT_SOON" and "close the trade" in m["action"]["en"] and m["exitAt"] % 14400 == 0
    # time exit within one candle
    old = {**setup, "params": {"maxBars": 5}}
    assert manager_agent({**base, "setup": old}, candles, None, now)["verdict"] == "EXIT_SOON"
    # a limit order about to expire, and no trade at all
    pend = {**setup, "entryType": "LIMIT", "expiresAt": now + 600, "lifecycle": {"state": "PENDING", "fillTime": None}}
    assert manager_agent({**base, "setup": pend}, [], None, now)["verdict"] == "CANCEL"
    assert manager_agent({**base, "setup": None}, [], None, now) is None
