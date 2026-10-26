"""FXAlexG Set & Forget Break & Retest on a hand-built H4 pattern: pro-trend, look left, break, retest, confirmation, one 3R target."""

from app.agent.validator import validate_signal
from app.strategies.alexg.config import ALEXG_CONFIGS
from app.strategies.alexg.strategy import evaluate_alexg
from app.strategies.service import STRATEGY_DEFS, normalize_symbol
from app.strategies.shared.types import Candle
from app.telegram.bot import format_signal_message

H4 = 14400
T0 = 1767571200  # Monday 2026-01-05 00:00 UTC
CFG = ALEXG_CONFIGS["GBP/USD"]


def _h4_bars() -> list[tuple]:
    """(open, high, low, close) per H4 candle: a steady uptrend, then the break & retest of a level touched twice."""
    bars, p = [], 1.2000
    for _ in range(1300):  # ~31 weeks of small bullish candles: weekly and daily trend up, no swings, no patterns
        bars.append((p, p + 0.00015, p - 0.00005, p + 0.0001))
        p += 0.0001
    lv = p + 0.0040  # the area of interest
    path = [  # (open, high, low, close) relative to the level
        (-0.0040, -0.0018, -0.0042, -0.0020), (-0.0020, -0.0002, -0.0022, -0.0005),  # touch 1 (2 points under the level)
        (-0.0005, -0.0003, -0.0030, -0.0028), (-0.0028, -0.0026, -0.0045, -0.0043), (-0.0043, -0.0040, -0.0050, -0.0047),
        (-0.0047, -0.0025, -0.0049, -0.0027), (-0.0027, -0.0006, -0.0029, -0.0008), (-0.0008, 0.0000, -0.0012, -0.0004),  # touch 2 = swing high
        (-0.0004, -0.0002, -0.0026, -0.0024), (-0.0024, -0.0022, -0.0040, -0.0038), (-0.0038, -0.0036, -0.0048, -0.0046),
        (-0.0046, -0.0020, -0.0048, -0.0022), (-0.0022, 0.0015, -0.0024, 0.0012),  # break: H4 close above the level
        (0.0012, 0.0050, 0.0010, 0.0048), (0.0048, 0.0085, 0.0046, 0.0082),  # moves away
        (0.0082, 0.0084, 0.0060, 0.0062), (0.0062, 0.0064, 0.0040, 0.0042), (0.0042, 0.0044, 0.0024, 0.0026),
        (0.0026, 0.0028, 0.0007, 0.0009),  # back to the level (bearish)
        (0.0007, 0.0034, -0.0003, 0.0032),  # retest: bullish engulfing that closes above the level
    ]
    bars += [(lv + o, lv + h, lv + lo, lv + c) for o, h, lo, c in path]
    return bars


def _candles(bars):
    h4, h1 = [], []
    for k, (o, h, lo, c) in enumerate(bars):
        t = T0 + k * H4
        h4.append(Candle(t, round(o, 5), round(h, 5), round(lo, 5), round(c, 5)))
        pts = [o, lo, h, c] if c >= o else [o, h, lo, c]
        for j in range(4):  # four H1 candles that aggregate exactly into the H4 candle
            a, b = (pts[j], pts[j + 1]) if j < 3 else (c, c)
            h1.append(Candle(t + j * 3600, round(a, 5), round(max(a, b), 5), round(min(a, b), 5), round(b, 5)))
    return h4, h1


def _run(bars, extra=()):
    bars = list(bars) + list(extra)
    h4, h1 = _candles(bars)
    now = h4[len(bars) - len(extra) - 1].time + H4 if not extra else h4[-1].time + H4
    return evaluate_alexg({"candles": {"H4": h4, "H1": h1}, "nowSec": now, "livePrice": 0, "spread": None, "isRealData": True, "dataSource": "test",
                           "news": {"events": [], "source": "test"}, "isMarketOpen": True, "day": {"trades": 0, "losses": 0}}, CFG)


def _mirror(bars):
    return [(2.6 - o, 2.6 - lo, 2.6 - h, 2.6 - c) for o, h, lo, c in bars]


def test_break_and_retest_buy():
    r = _run(_h4_bars())
    s = r["setup"]
    assert r["status"] == "SIGNAL" and r["canNotify"] and s["direction"] == "BUY" and s["entryType"] == "MARKET", r["headline"]
    assert s["setup"] == "BREAK_RETEST" and s["anchors"]["breakRetest"]["pattern"] == "engulfing" and s["anchors"]["breakRetest"]["touches"] >= 2
    risk = s["entry"] - s["sl"]
    assert abs(s["tp3"] - (s["entry"] + 3 * risk)) < 1e-5 and abs(s["tp1"] - (s["entry"] + risk)) < 1e-5
    assert s["params"]["partials"] == [0, 0, 1] and s["params"]["breakeven"] is False
    assert r["bias"]["direction"] == "BULLISH" and all(c["passed"] for c in r["checklist"])
    assert validate_signal(r)["approved"]


def test_mirror_gives_a_sell():
    r = _run(_mirror(_h4_bars()))
    assert r["status"] == "SIGNAL" and r["setup"]["direction"] == "SELL", r["headline"]


def test_no_anticipation_without_confirmation():
    bars = _h4_bars()
    o, h, lo, c = bars[-1]
    bars[-1] = (o, h, lo, o + 0.0005)  # small bullish close: not an engulfing, not a pin bar
    r = _run(bars)
    assert r["setup"] is None and r["status"] == "NO_TRADE"


def test_set_and_forget_keeps_the_original_stop():
    bars = _h4_bars()
    r0 = _run(bars)["setup"]
    risk = r0["entry"] - r0["sl"]
    e = r0["entry"]
    # Reaches 1R and 2R, then falls back to the stop: no breakeven, a full -1R loss
    path = [(e, e + 2.2 * risk, e - 0.1 * risk, e + 2 * risk), (e + 2 * risk, e + 2 * risk, r0["sl"] - 0.0005, r0["sl"] - 0.0003)]
    lc = _run(bars, path)["setup"]["lifecycle"]
    assert lc["state"] == "CLOSED" and lc["outcome"] == "LOSS" and lc["rMultiple"] < -1
    assert not any(ev["type"] == "BE" for ev in lc["events"])


def test_pairs_and_message():
    assert list(STRATEGY_DEFS) == ["XAU/USD", "EUR/USD", "GBP/USD", "USD/CAD", "NZD/USD", "EUR/CHF", "NZD/CAD", "AUD/CAD", "AUD/CHF"]
    assert all(STRATEGY_DEFS[p].entryTf == "H4" for p in ALEXG_CONFIGS)
    assert normalize_symbol("eurchf") == "EUR/CHF" and normalize_symbol("EUR") == "EUR/USD" and normalize_symbol("nzd") == "NZD/USD"
    assert normalize_symbol("AUD/CAD") == "AUD/CAD" and normalize_symbol("xau") == "XAU/USD"
    assert ALEXG_CONFIGS["NZD/CAD"]["filters"]["news"]["currencies"] == ["NZD", "CAD"]
    msg = format_signal_message({"symbol": "GBP/USD", "signalType": "BUY", "entryPrice": 1.3, "stopLoss": 1.298, "target1": 1.302, "target2": 1.304,
                                 "target3": 1.306, "confidence": 90, "signalJson": {"setup": "BREAK_RETEST", "entry_type": "MARKET"}})
    assert "TP:</b> <code>1.30600</code> (1:3.0 · set & forget" in msg and "TP1" not in msg
