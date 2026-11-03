"""
One strategy per pair, designed from the pair's own behaviour (docs/STRATEGIES.md):

1. Analysis, 2 years of H1 / H4: does a close beyond the 20-candle channel go on 2 ATR before 1 ATR back (follow) or come
   back (fade)? The break-even at 2:1 is 33 %. Trending pairs follow (gold 40 % vs 28 % on H4), reverting pairs fade
   (AUD/CHF 43 % vs 19 %), the others sit near 33 % both ways.
2. Design: the family the behaviour favours (breakout in the trend, or a fade of the stretched close), one target at 2R.
3. Test: tuned on the first 60 % of the history only, then judged on the last 40 % it never saw, with the pair's spread +
   slippage and the stop counted first. A plan is live only if it is positive on the unseen part, still positive with
   double costs, and its neighbouring settings agree. A pair where nothing passes is not traded (not in the app).
"""

import copy

from .._pairs import BANKS, PAIRS
from ..engines.config import AGENTS

BASE = {
    "version": "1.0.0",
    "atrPeriod": 14,
    "risk": {"tp1R": 1, "tp2R": 1.5, "capR": 2.0, "partials": [0, 0, 1], "breakeven": False, "maxBars": 24,
             "marketValidMin": 60, "riskPct": 1, "balances": [500, 1000, 5000, 10000], "showLastSetupBars": 4},
    "filters": {"maxSpreadPips": 4, "slippagePips": 0.2, "news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30},
                "maxTradesPerDay": 2, "maxLossesPerDay": 2},
    "scoring": {"thresholds": {"signal": 75, "watch": 60}},
}

# The analysis of each pair (2 years, H1 and H4): a close beyond the 20-candle channel, how often price then goes 2 ATR
# on (follow) or back (fade) before 1 ATR the other way; VR(24) > 1 trends over a day, < 1 comes back.
PROFILES = {
    "XAU/USD": {"character": "trending", "follow": 40, "fade": 28, "tf": "H4", "vr24": 1.13, "activeHours": "12:00–16:00 GMT (New York)"},
    "EUR/USD": {"character": "mixed", "follow": 32, "fade": 36, "tf": "H1", "vr24": 0.89, "activeHours": "07:00–08:00 and 12:00–15:00 GMT"},
    "GBP/USD": {"character": "mixed", "follow": 32, "fade": 35, "tf": "H4", "vr24": 0.90, "activeHours": "07:00–08:00 and 12:00–15:00 GMT"},
    "AUD/CHF": {"character": "reverting", "follow": 19, "fade": 43, "tf": "H4", "vr24": 0.82, "activeHours": "07:00–08:00 and 13:00–15:00 GMT"},
}

# pair → plan. `test`: tuned on the first 60 % ("tuned"), judged on the last 40 % ("unseen"); tp2R = % of trades that
# reached the 2R target. EUR/USD, GBP/USD and AUD/CHF are run by their own agents (engines/config.py).
PLANS = {
    "XAU/USD": {
        "name": "Channel breakout in the trend", "rule": "channel_breakout", "tf": "H1", "style": "trend",
        "params": {"channel": 20, "slAtr": 2.0}, "maxBars": 48,
        "why": "Gold trends: a close beyond its 20-hour channel in the EMA50 / EMA200 trend runs on more often than it comes back. "
               "The stop at 2 ATR leaves room for the noise of the New York session; the 2R target sits 4 ATR away, which gold covers within two days.",
        "test": {"tuned": {"trades": 142, "winRate": 44.4, "totalR": 24.9, "tp2R": 33.8},
                 "unseen": {"trades": 87, "winRate": 47.1, "totalR": 31.3, "tp2R": 42.5}, "costsX2": 53.7,
                 "neighbours": "every channel (10 / 20 / 40 / 55) and stop (1 / 1.5 / 2 ATR) positive on the unseen part (+21R to +57R)"},
    },
}


def _config(pair: str) -> dict:
    sym = pair.replace("/", "")
    gold = pair == "XAU/USD"
    plan = PLANS[pair]
    cfg = copy.deepcopy(BASE)
    tf = plan["tf"]
    cfg.update(strategy=f"Pair_{plan['rule']}", name=f"{sym} · {plan['name']} {tf}", timeframes={"bias": tf, "setup": tf, "entry": tf},
               rule=plan["rule"], params=plan["params"], style=plan["style"], live=True, why=plan["why"], test=plan["test"],
               note=plan.get("note"), profile=PROFILES[pair], history=12500 if tf == "H1" else 3200)
    cfg["risk"]["maxBars"] = plan["maxBars"]
    cfg["spec"] = ({"symbol": sym, "displaySymbol": pair, "decimals": 2, "pipSize": 0.1, "contractSize": 100, "minLot": 0.01, "lotStep": 0.01} if gold
                   else {"symbol": sym, "displaySymbol": pair, "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01})
    ccys = ["USD"] if gold else [pair[:3], pair[4:]]
    cfg["filters"]["news"].update(currencies=ccys, keywords=[k for c in ccys for k in BANKS[c]])
    if gold:
        cfg["filters"].update(assumedSpread=0.25, slippage=0.05, maxSpread=0.5)
    else:
        cfg["filters"]["assumedSpreadPips"] = PAIRS[pair][0]
    return cfg


def _agent_config(pair: str) -> dict:
    """EUR/USD, GBP/USD, AUD/CHF: each run by its own agent and strategy (engines/)."""
    a = AGENTS[pair]
    sym = pair.replace("/", "")
    cfg = copy.deepcopy(BASE)
    tf = a["tf"]
    cfg.update(strategy=f"Agent{a['agent']}_{a['name']}", name=f"{sym} · Agent {a['agent']} · {a['name']} {tf}", engine=a["name"], agent=a["agent"],
               timeframes={"bias": "H4" if tf == "H1" else "M15", "setup": tf, "entry": tf}, rule=a["rule"], params=copy.deepcopy(a["params"]),
               style="reversal", live=True, why=a["why"], steps=a["steps"], test=None, note=None, profile=PROFILES[pair], history=a["history"],
               minBars=a["minBars"], peer=a.get("peer"), agentWindows=a.get("sessions"), targetRange=a["targetRange"], entryTypes=a["entryTypes"])
    cfg["risk"].update(tp1R=None, tp2R=None, capR=None, partials=None, breakeven=True, maxBars=None)
    cfg["spec"] = {"symbol": sym, "displaySymbol": pair, "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01}
    ccys = [pair[:3], pair[4:]]
    cfg["filters"]["news"].update(currencies=ccys, keywords=[])  # every red (high-impact) event of the two currencies
    cfg["filters"].update(assumedSpreadPips=PAIRS[pair][0], maxSpreadPips=a["maxSpreadPips"])
    return cfg


PAIR_CONFIGS: dict[str, dict] = {"XAU/USD": _config("XAU/USD"), **{pair: _agent_config(pair) for pair in PAIRS}}
