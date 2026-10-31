"""XAUUSD H1 Trend Breakout on hand-built candles: entry, stop and targets to the cent, and every rejection rule."""

from app.agent.validator import validate_signal
from app.strategies.shared.types import Candle
from app.strategies.xauusd.config import XAU_CONFIG
from app.strategies.xauusd.strategy import evaluate_xauusd

T0 = 1_790_000_000 - 1_790_000_000 % 3600  # an hour boundary


def series(direction: int = 1, breakout_body: float = 4.0, breakout_low_extra: float = 0.0, flat: bool = False, extra: list | None = None,
           against: bool = False):
    """350 trending candles (+/-0.5 per hour), 25 flat candles around the last price, then a breakout candle."""
    c, price = [], 3000.0
    for k in range(350):
        o = price
        price += 0 if flat else 0.5 * direction
        c.append(Candle(T0 + k * 3600, o, max(o, price) + 1, min(o, price) - 1, price))
    level = price
    for k in range(25):
        o = level + (0.3 if k % 2 else -0.3)
        cl = level - (0.3 if k % 2 else -0.3)
        c.append(Candle(T0 + (350 + k) * 3600, o, max(o, cl) + 1, min(o, cl) - 1, cl))
    o = level
    cl = level + breakout_body * (-direction if against else direction)
    hi, lo = max(o, cl) + 0.3, min(o, cl) - 0.3
    if direction > 0:
        lo -= breakout_low_extra
    else:
        hi += breakout_low_extra
    c.append(Candle(T0 + 375 * 3600, o, hi, lo, cl))
    for x in extra or []:
        c.append(Candle(c[-1].time + 3600, *x))
    return c


def run(c, **over):
    inp = {"candles": {"H1": c}, "nowSec": c[-1].time + 3600, "livePrice": 0, "spread": None, "isMarketOpen": True, "isRealData": True,
           "dataSource": "test", "news": {"events": [], "source": "test"}, "day": {"trades": 0, "losses": 0}}
    inp.update(over)
    return evaluate_xauusd(inp)


def test_bullish_breakout_is_a_signal_with_exact_levels():
    c = series(+1)
    r = run(c)
    s = r["setup"]
    assert r["status"] == "SIGNAL" and r["canNotify"] and s["direction"] == "BUY" and s["entryType"] == "MARKET"
    bo = c[-1]
    assert s["entry"] == round(bo.close, 2)
    risk = s["entry"] - s["sl"]
    # Stop: below the lowest low of the last 4 candles − 0.2 × ATR, and at least 1 × ATR away
    ref = min(x.low for x in c[-4:])
    atr = r["setup"]["anchors"]["breakout"]["atr"]
    assert abs(s["sl"] - min(ref - 0.2 * atr, bo.close - atr)) < 0.02
    # App rule: one target at 2R (TP1 1R / TP2 1.5R are progress marks), no partials, the stop stays at the structure
    assert abs(s["tp1"] - (s["entry"] + risk)) < 0.02 and abs(s["tp2"] - (s["entry"] + 1.5 * risk)) < 0.02 and abs(s["tp3"] - (s["entry"] + 2 * risk)) < 0.02
    assert s["params"]["partials"] == [0, 0, 1] and s["params"]["breakeven"] is False
    assert abs(s["rrTp2"] - 1.5) < 0.01 and s["lifecycle"]["state"] == "OPEN"
    assert [x["key"] for x in r["checklist"] if not x["passed"]] == [] and r["score"] >= 75
    assert validate_signal(r)["approved"]
    assert any(d["layer"] == "trade" for d in r["drawings"]) and any(d["id"] == "XAU-RANGE-H" for d in r["drawings"])


def test_bearish_breakout_is_a_sell():
    r = run(series(-1))
    assert r["status"] == "SIGNAL" and r["setup"]["direction"] == "SELL" and r["setup"]["sl"] > r["setup"]["entry"] > r["setup"]["tp1"]


def test_breakout_against_the_trend_is_ignored():
    r = run(series(+1, against=True))  # uptrend, but the candle breaks the 20-hour LOW
    assert r["status"] == "NO_TRADE" and r["setup"] is None and "bullish trend" in r["headline"].lower()


def test_weak_breakout_candle_is_ignored():
    r = run(series(+1, breakout_body=0.6))  # body < 0.5 × ATR
    assert r["setup"] is None and r["status"] == "NO_TRADE"


def test_stop_wider_than_3_atr_is_skipped():
    r = run(series(+1, breakout_low_extra=25))
    assert r["setup"] is None


def test_news_blocks_the_signal():
    c = series(+1)
    close = c[-1].time + 3600
    r = run(c, news={"events": [{"time": close + 600, "currency": "USD", "title": "CPI m/m", "impact": "High"}], "source": "t"})
    assert r["status"] == "NO_TRADE" and not r["canNotify"] and "news" in r["rejection"].lower()


def test_daily_loss_limit_blocks_the_signal():
    r = run(series(+1), day={"trades": 0, "losses": XAU_CONFIG["filters"]["maxLossesPerDay"]})
    assert r["status"] == "NO_TRADE"


def test_one_trade_at_a_time():
    c = series(+1)
    first = run(c)["setup"]
    # The trade stays open (price holds above the stop, below TP1) and price breaks out again: no second trade
    risk = first["entry"] - first["sl"]
    p = first["entry"]
    follow = [(p, p + 0.4 * risk, p - 0.2, p + 0.3 * risk)] * 3
    r = run(c + [Candle(c[-1].time + 3600 * (k + 1), *x) for k, x in enumerate(follow)])
    assert r["setup"]["id"] == first["id"] and not r["setup"]["isFresh"] and not r["canNotify"]


def test_closed_trade_reports_its_result():
    c = series(+1)
    first = run(c)["setup"]
    risk = first["entry"] - first["sl"]
    p = first["entry"]
    # Next candle reaches the 2R target: the whole position closes there (≈2R less costs)
    r = run(c + [Candle(c[-1].time + 3600, p, p + 2.2 * risk, p - 0.1, p + 2 * risk)])
    lc = r["facts"]["lastTrade"]
    assert lc["state"] == "CLOSED" and lc["outcome"] == "WIN" and 1.85 < lc["r"] <= 2


def reversion_series(hour_utc: int):
    """Uptrend, a calm range, a candle that closes far below the lower Bollinger band, then a bullish close back inside."""
    midnight = 1_790_035_200  # 00:00 UTC
    t0 = midnight - 376 * 3600 + hour_utc * 3600  # the confirmation candle (index 376) opens at `hour_utc`
    c, price = [], 3000.0
    for k in range(350):
        o = price
        price += 0.5
        c.append(Candle(t0 + k * 3600, o, max(o, price) + 1, min(o, price) - 1, price))
    level = price
    for k in range(25):
        o = level + (0.3 if k % 2 else -0.3)
        cl = level - (0.3 if k % 2 else -0.3)
        c.append(Candle(t0 + (350 + k) * 3600, o, max(o, cl) + 0.5, min(o, cl) - 0.5, cl))
    c.append(Candle(t0 + 375 * 3600, level, level + 0.2, level - 8.6, level - 8.0))  # closes below the 2.2σ band
    c.append(Candle(t0 + 376 * 3600, level - 7.0, level - 1.6, level - 7.4, level - 2.0))  # bullish, back inside
    return c


def test_bollinger_reversion_in_the_session():
    c = reversion_series(10)
    r = run(c)
    s = r["setup"]
    assert r["status"] == "SIGNAL" and s["setup"] == "REVERSION" and s["direction"] == "BUY" and s["id"].startswith("XAUUSD-RV-"), r["headline"]
    risk = s["entry"] - s["sl"]
    assert abs(s["tp3"] - (s["entry"] + 1.5 * risk)) < 0.02 and s["tp1"] < s["tp2"] < s["tp3"]  # one target at 1.5R, marks before it
    assert abs(s["sl"] - (min(c[-1].low, c[-2].low) - 0.3 * s["anchors"]["reversion"]["atr"])) < 0.05
    assert s["params"]["partials"] == [0, 0, 1] and s["params"]["breakeven"] is False and s["params"]["maxBars"] == 24
    assert all(x["passed"] for x in r["checklist"]) and r["score"] == 100
    assert validate_signal(r)["approved"] and "reversion" in r["headline"]


def test_reversion_only_during_london_and_new_york():
    r = run(reversion_series(20))  # 20:00 UTC: outside 07:00–17:00
    assert not (r["setup"] and r["setup"]["setup"] == "REVERSION")


def test_reversion_time_exit_after_24_candles():
    c = reversion_series(10)
    e = c[-1].close
    # 24 quiet candles that touch neither the stop nor the 1R target: closed at the close of the 24th
    for k in range(24):
        c.append(Candle(c[-1].time + 3600, e, e + 0.5, e - 0.5, e + 0.1))
    lc = run(c)["setup"]["lifecycle"]
    assert lc["state"] == "CLOSED" and lc["events"][-1]["type"] == "TIME_EXIT" and lc["exitTime"] == c[-1].time


def test_m15_confirmation_takes_the_breakout_before_the_h1_close(monkeypatch):
    from app.strategies import service

    monkeypatch.setattr(service, "market_session_status", lambda sym: {"isOpen": True})  # the test may run on a weekend

    c = series(+1)
    bo = c[-1]  # the breakout candle: here it is still forming, seen through its first two 15-minute candles
    closed = c[:-1]
    mid = bo.open + (bo.close - bo.open) * 0.9
    m15 = [Candle(bo.time, bo.open, bo.open + 0.6 * (bo.close - bo.open), bo.open - 0.2, bo.open + 0.5 * (bo.close - bo.open)),
           Candle(bo.time + 900, bo.open + 0.5 * (bo.close - bo.open), mid + 0.2, bo.open + 0.4 * (bo.close - bo.open), mid)]
    base = {"candles": {"H1": closed + [bo], "M15": m15}, "livePrice": 0, "spread": None, "isRealData": True, "dataSource": "test",
            "news": {"events": [], "source": "test"}}
    service._early.pop("XAU/USD", None)
    now = bo.time + 2 * 900 + 5  # 30 min into the H1 candle
    r = service._early_signal("XAU/USD", base, now, {"trades": 0, "losses": 0})
    assert r and r["status"] == "SIGNAL" and r["setup"]["direction"] == "BUY" and r["facts"]["confirmation"]["tf"] == "M15"
    assert r["setup"]["entry"] == round(mid, 2) and r["setup"]["id"] == f"XAUUSD-BO-{bo.time}"  # same id as at the H1 close
    # Later in the same H1 candle the first signal stays as it was (its levels never move)
    m15.append(Candle(bo.time + 1800, mid, mid + 5, mid - 0.1, mid + 4))
    assert service._early_signal("XAU/USD", base, now + 900, {"trades": 0, "losses": 0})["setup"]["entry"] == r["setup"]["entry"]
    service._early.pop("XAU/USD", None)
    # Before any 15-minute candle has closed in the hour there is nothing to confirm
    assert service._early_signal("XAU/USD", base, bo.time + 60, {"trades": 0, "losses": 0}) is None
