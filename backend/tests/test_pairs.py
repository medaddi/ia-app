"""The pair strategies: one plan per pair where it held up on the unseen part of its test, none elsewhere."""
import math

from app.agent.validator import validate_signal
from app.strategies.pairs.config import PAIR_CONFIGS
from app.strategies.pairs.engine import evaluate_pair
from app.strategies.pairs.rules import RULES, in_hours
from app.strategies.service import STRATEGY_DEFS
from app.strategies.shared.types import Candle

H1, H4 = 3600, 14400
DAY = 1_790_985_600  # a Monday 00:00 UTC


def _inp(c, step):
    return {"candles": {"H1" if step == H1 else "H4": c}, "nowSec": c[-1].time + step + 60, "livePrice": 0, "spread": None, "isRealData": True,
            "dataSource": "test", "isMarketOpen": True, "day": {"trades": 0, "losses": 0}, "news": {"events": [], "source": "test"}}


def test_the_plans_and_the_pairs_without_one():
    live = {p for p, c in PAIR_CONFIGS.items() if c["rule"]}
    assert live == {"XAU/USD", "EUR/USD", "GBP/USD", "AUD/CHF"}
    for p, c in PAIR_CONFIGS.items():
        assert c["risk"]["capR"] == 2.0 and c["profile"]["character"] in ("trending", "reverting", "mixed")
        if c["rule"]:
            u = c["test"]["unseen"]
            assert u["totalR"] > 0 and u["trades"] >= 30 and c["test"]["costsX2"] > 0  # held up on the part it never saw
        else:
            assert c["why"] and not STRATEGY_DEFS[p].canSignalAt(DAY + 3 * H1)  # no plan: never signals
    assert STRATEGY_DEFS["XAU/USD"].entryTf == "H1" and STRATEGY_DEFS["GBP/USD"].entryTf == "H4"
    # EUR/USD fades in the Asian hours only: a candle opened 02:00 → its close at 03:00 may signal; 09:00 may not
    assert STRATEGY_DEFS["EUR/USD"].canSignalAt(DAY + 3 * H1) and not STRATEGY_DEFS["EUR/USD"].canSignalAt(DAY + 10 * H1)
    assert in_hours(DAY + 23 * H1, [22, 5]) and in_hours(DAY + 4 * H1, [22, 5]) and not in_hours(DAY + 6 * H1, [22, 5])


def _trend_then_break(n=320, step=H1):
    """An uptrend (EMA50 > EMA200), then a flat zig-zag (no close beyond the channel), then a candle closing well above
    the 20-candle high."""
    c = []
    for i in range(n):
        m = 3000 + 0.5 * min(i, 250) + 3 * math.sin(i)
        c.append(Candle(DAY + i * step, m - 1, m + 4, m - 4, m + 1, 0))
    t, top = c[-1].time, max(x.high for x in c[-20:])
    c.append(Candle(t + step, top - 1, top + 12, top - 2, top + 10, 0))
    return c


def test_gold_breakout_signal_with_one_2r_target():
    c = _trend_then_break()
    cfg = PAIR_CONFIGS["XAU/USD"]
    ind = RULES["channel_breakout"]["prep"](c, cfg["params"])
    b = RULES["channel_breakout"]["at"](c, len(c) - 1, ind, cfg["params"])
    assert b and b["buy"] and abs((b["entry"] - b["sl"]) - 2.0 * ind["atr"][-1]) < 1e-9
    assert not RULES["channel_breakout"]["at"](c, len(c) - 2, ind, cfg["params"])  # inside the channel: nothing
    r = evaluate_pair(_inp(c, H1), cfg)
    s = r["setup"]
    assert r["status"] == "SIGNAL" and r["canNotify"] and s["direction"] == "BUY" and s["isFresh"]
    assert abs(s["rrTarget"] - 2.0) < 0.05 and s["params"]["maxBars"] == 48 and s["params"]["partials"] == [0, 0, 1]
    assert r["pairStrategy"]["live"] and r["pairStrategy"]["test"]["unseen"]["totalR"] > 0
    assert validate_signal(r)["approved"]


def test_fade_only_inside_its_hours():
    """EUR/USD: a close under the 10-candle low is bought back at 02:00 GMT, ignored at 10:00 GMT."""
    cfg = PAIR_CONFIGS["EUR/USD"]
    rule = RULES["channel_fade"]

    def market(hour):
        c = []
        start = DAY + 24 * H1 * 14 + hour * H1 - 299 * H1
        for i in range(300):
            m = 1.10 + 0.0008 * math.sin(i / 2)
            c.append(Candle(start + i * H1, m, m + 0.0004, m - 0.0004, m + 0.0001, 0))
        low = min(x.low for x in c[-10:])
        c.append(Candle(c[-1].time + H1, low + 0.0002, low + 0.0003, low - 0.0030, low - 0.0025, 0))
        return c

    c = market(1)  # the last candle opens at 02:00
    ind = rule["prep"](c, cfg["params"])
    b = rule["at"](c, len(c) - 1, ind, cfg["params"])
    assert b and b["buy"] and abs((b["entry"] - b["sl"]) - 1.5 * ind["atr"][-1]) < 1e-12 and "00:00–06:00" in b["why"][1]
    c = market(9)  # opens at 10:00: outside the Asian window
    ind = rule["prep"](c, cfg["params"])
    assert not rule["at"](c, len(c) - 1, ind, cfg["params"])


def test_a_pair_without_a_plan_gets_its_analysis_and_no_trade():
    c = _trend_then_break(step=H4)
    r = evaluate_pair(_inp(c, H4), PAIR_CONFIGS["USD/CAD"])
    assert r["status"] == "NO_TRADE" and not r["setup"] and not r["canNotify"]
    assert r["bias"]["direction"] == "BULLISH" and "No validated strategy" in r["headline"] and r["pairStrategy"]["live"] is False
