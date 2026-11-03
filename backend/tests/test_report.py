"""The report's per-pair strategies: live only where the 2-year test won, observation everywhere else."""
import math

from app.agent.validator import validate_signal
from app.strategies.report.config import REPORT_CONFIGS
from app.strategies.report.engine import evaluate_report, observation_block
from app.strategies.report.signals import RULES
from app.strategies.service import STRATEGY_DEFS
from app.strategies.shared.types import Candle


def test_every_pair_has_its_report_plan_and_only_winners_are_live():
    assert set(REPORT_CONFIGS) == {"XAU/USD", "EUR/USD", "USD/CAD", "NZD/USD", "EUR/CHF", "NZD/CAD", "AUD/CAD", "AUD/CHF"}  # GBP/USD: strategies/london
    live = {p for p, c in REPORT_CONFIGS.items() if c["live"]}
    assert live == {"AUD/CAD", "EUR/USD", "USD/CAD"}  # EUR/USD, USD/CAD: the 2nd report (sweep + BOS, EMA pullback)
    for p, c in REPORT_CONFIGS.items():
        t = c["test"]
        assert c["report"] and t["verdict"] and (not c["live"] or (t["trades"] >= 30 and t["totalR"] > 0))
        assert c["risk"]["capR"] in (1.5, 2.0)  # the app's 1.5R–2R rule
    assert all(STRATEGY_DEFS[p].entryTf == "H4" and not STRATEGY_DEFS[p].exit_rule for p in live)  # live: the pair's own strategy now
    assert STRATEGY_DEFS["NZD/CAD"].entryTf == "M30"  # observation: GPA stays


def _range_market(n=400, step=14400):
    """A quiet range with a sharp dip under the lower band and a close back inside near the end."""
    c = []
    for i in range(n):
        m = 1.0 + 0.002 * math.sin(i / 6)
        c.append(Candle(1_790_000_000 + i * step, m, m + 0.0008, m - 0.0008, m + 0.0001, 0))
    t = c[-1].time
    c.append(Candle(t + step, 0.998, 0.9982, 0.9935, 0.9940, 0))  # closes below the band
    c.append(Candle(t + 2 * step, 0.9945, 0.9990, 0.9942, 0.9985, 0))  # closes back inside
    return c


def test_mean_reversion_rule_and_engine_on_a_range():
    cfg = REPORT_CONFIGS["AUD/CAD"]
    c = _range_market()
    rule = RULES["mean_reversion"]
    ind = rule["prep"](c, cfg["params"])
    b = rule["at"](c, len(c) - 1, ind, {**cfg["params"], "adxMax": 999})
    assert b and b["buy"] and b["sl"] < min(c[-2].low, c[-1].low) and len(b["why"]) == 3
    inp = {"candles": {"H4": c}, "nowSec": c[-1].time + 14400 + 60, "livePrice": 0, "spread": None, "isRealData": True,
           "dataSource": "test", "isMarketOpen": True, "day": {"trades": 0, "losses": 0}, "news": {"events": [], "source": "test"}}
    r = evaluate_report(inp, {**cfg, "params": {**cfg["params"], "adxMax": 999}})
    assert r["setup"] and r["setup"]["direction"] == "BUY" and r["status"] == "SIGNAL" and r["canNotify"]
    assert abs(r["setup"]["rrTarget"] - 2.0) < 0.05 and validate_signal(r)["approved"]
    # The same plan in observation never notifies, and its drawings sit on the "report" layer
    obs = evaluate_report(inp, {**cfg, "live": False, "params": {**cfg["params"], "adxMax": 999}})
    block = observation_block(obs)
    assert not obs["canNotify"] and block["live"] is False and all(d["layer"] == "report" for d in block["drawings"])


def test_sweep_and_break_of_structure():
    """A wick under the 20-candle low that closes back above, then a close over the last swing high: a BUY at that close."""
    step, c = 14400, []
    for i in range(300):
        m = 1.0 + 0.001 * math.sin(i / 3)
        c.append(Candle(1_790_000_000 + i * step, m, m + 0.0005, m - 0.0005, m + 0.0001, 0))
    t, low = c[-1].time, min(x.low for x in c[-20:])
    c.append(Candle(t + step, 1.0, 1.0004, low - 0.002, 1.0002, 0))  # the sweep: wick under, close back inside
    c.append(Candle(t + 2 * step, 1.0002, 1.0030, 1.0001, 1.0028, 0))  # the break of structure
    p = REPORT_CONFIGS["EUR/USD"]["params"]
    rule = RULES["sweep_bos"]
    ind = rule["prep"](c, p)
    b = rule["at"](c, len(c) - 1, ind, p)
    assert b and b["buy"] and b["entry"] == 1.0028 and b["sl"] < low - 0.002 and not rule["at"](c, len(c) - 2, ind, p)


def test_ema_pullback_needs_the_trend_and_a_confirmation():
    step, c = 14400, []
    for i in range(300):
        m = 1.0 + 0.0004 * i  # a steady uptrend: EMA50 > EMA200
        c.append(Candle(1_790_000_000 + i * step, m - 0.0002, m + 0.0006, m - 0.0006, m + 0.0002, 0))
    p = REPORT_CONFIGS["USD/CAD"]["params"]
    rule = RULES["ema_pullback"]
    e20 = rule["prep"](c, p)["touch"][-1]
    t, top = c[-1].time, c[-1].high
    c.append(Candle(t + step, top - 0.001, top + 0.001, e20 - 0.0005, top + 0.0008, 0))  # dips to EMA20, closes above the last high
    ind = rule["prep"](c, p)
    b = rule["at"](c, len(c) - 1, ind, p)
    assert b and b["buy"] and b["sl"] < c[-1].low and len(b["why"]) == 3
