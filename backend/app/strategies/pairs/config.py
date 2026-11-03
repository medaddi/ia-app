"""
One strategy per pair, designed from the pair's own behaviour (docs/STRATEGIES.md):

1. Analysis, 2 years of H1 / H4: does a close beyond the 20-candle channel go on 2 ATR before 1 ATR back (follow) or come
   back (fade)? The break-even at 2:1 is 33 %. Trending pairs follow (gold 40 % vs 28 % on H4), reverting pairs fade
   (AUD/CHF 43 % vs 19 %), the others sit near 33 % both ways.
2. Design: the family the behaviour favours (breakout in the trend, or a fade of the stretched close), one target at 2R.
3. Test: tuned on the first 60 % of the history only, then judged on the last 40 % it never saw, with the pair's spread +
   slippage and the stop counted first. A plan is live only if it is positive on the unseen part, still positive with
   double costs, and its neighbouring settings agree. A pair where nothing passes gets no strategy: no signal.
"""

import copy

from .._pairs import BANKS, PAIRS

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
    "USD/CAD": {"character": "trending", "follow": 36, "fade": 26, "tf": "H4", "vr24": 0.88, "activeHours": "12:00–17:00 GMT (New York)"},
    "NZD/USD": {"character": "mixed", "follow": 34, "fade": 33, "tf": "H4", "vr24": 1.04, "activeHours": "01:00, 07:00 and 12:00–15:00 GMT"},
    "EUR/CHF": {"character": "reverting", "follow": 26, "fade": 39, "tf": "H4", "vr24": 0.76, "activeHours": "07:00–09:00 and 13:00–15:00 GMT"},
    "NZD/CAD": {"character": "reverting", "follow": 27, "fade": 36, "tf": "H4", "vr24": 1.01, "activeHours": "12:00–15:00 and 21:00–22:00 GMT"},
    "AUD/CAD": {"character": "reverting", "follow": 20, "fade": 43, "tf": "H4", "vr24": 0.97, "activeHours": "00:00–01:00 and 12:00–15:00 GMT"},
    "AUD/CHF": {"character": "reverting", "follow": 19, "fade": 43, "tf": "H4", "vr24": 0.82, "activeHours": "07:00–08:00 and 13:00–15:00 GMT"},
}

# pair → plan. `test`: tuned on the first 60 % ("tuned"), judged on the last 40 % ("unseen"); tp2R = % of trades that
# reached the 2R target. rule None: nothing held up on the unseen part, so no strategy and no signal on that pair.
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
    "EUR/USD": {
        "name": "Asian-session channel fade", "rule": "channel_fade", "tf": "H1", "style": "reversal",
        "params": {"channel": 10, "slAtr": 1.5, "hours": [0, 6]}, "maxBars": 48,
        "why": "EUR/USD has no clear lean over the whole day, but in the quiet Asian hours a close beyond its 10-hour channel has no news "
               "or volume behind it and comes back. The stop at 1.5 ATR survives the late spike; the 2R target is back across the channel.",
        "test": {"tuned": {"trades": 160, "winRate": 41.2, "totalR": 26.3, "tp2R": 40.0},
                 "unseen": {"trades": 107, "winRate": 43.0, "totalR": 19.9, "tp2R": 42.1}, "costsX2": 26.3,
                 "neighbours": "every Asian window (21–06, 22–05, 00–06 GMT) positive on both parts (+13R to +26R); tighter stops lose"},
    },
    "GBP/USD": {
        "name": "Channel fade", "rule": "channel_fade", "tf": "H4", "style": "reversal",
        "params": {"channel": 10, "slAtr": 1.0, "adxMax": 35}, "maxBars": 12,
        "why": "GBP/USD's H4 closes beyond the 10-candle channel come back more often than they run (35 % vs 32 %), unless a strong trend "
               "is under way (ADX ≥ 35). The stop at 1 ATR, the 2R target back inside the channel, two days at most.",
        "test": {"tuned": {"trades": 144, "winRate": 43.1, "totalR": 27.4, "tp2R": 38.2},
                 "unseen": {"trades": 80, "winRate": 45.0, "totalR": 14.3, "tp2R": 37.5}, "costsX2": 29.3,
                 "neighbours": "positive on both parts with ADX < 25, < 35 or none (+12R to +27R); a 0.6 ATR stop or a 20-candle channel lose"},
        "note": "Fragile to the stop size and the channel length: only the 10-candle channel with a 1 ATR stop holds",
    },
    "AUD/CHF": {
        "name": "Asian-session channel fade", "rule": "channel_fade", "tf": "H1", "style": "reversal",
        "params": {"channel": 40, "slAtr": 1.0, "hours": [22, 5]}, "maxBars": 48,
        "why": "AUD/CHF reverts the most of the nine (a close beyond the channel comes back 43 % of the time vs 19 % on): a close beyond "
               "its 40-hour channel in the Asian hours is faded, stop 1 ATR, the 2R target back toward the middle.",
        "test": {"tuned": {"trades": 70, "winRate": 50.0, "totalR": 25.7, "tp2R": 50.0},
                 "unseen": {"trades": 36, "winRate": 44.4, "totalR": 6.3, "tp2R": 44.4}, "costsX2": 16.4,
                 "neighbours": "every Asian window positive on both parts with a 40-candle channel (+3R to +7R unseen)"},
        "note": "Small edge on the unseen part (+6.3R on 36 trades): the weakest of the four",
    },
}
NO_EDGE = {
    "USD/CAD": "Trending on H4, but no breakout or pullback design held up on the unseen 40 % (the best, a previous-day-high break in New York: +4R on 37 trades, with most of its neighbouring settings losing)",
    "NZD/USD": "No lean either way (34 % follow vs 33 % fade, the 33 % break-even): no design held up on the unseen 40 % (a fade that made +22R in the tuning lost −11R)",
    "EUR/CHF": "Reverting, but the fades that won in the tuning lost on the unseen 40 % (−5R to −37R); the best sweep made +5R with most neighbours negative",
    "NZD/CAD": "Reverting, but no fade or sweep held up on the unseen 40 %",
    "AUD/CAD": "The strongest fade profile (43 %), but every fade lost on the unseen 40 % once costs are counted",
}


def _config(pair: str) -> dict:
    sym = pair.replace("/", "")
    gold = pair == "XAU/USD"
    plan = PLANS.get(pair)
    cfg = copy.deepcopy(BASE)
    tf = plan["tf"] if plan else "H4"
    cfg.update(strategy=f"Pair_{plan['rule']}" if plan else "Pair_none", name=f"{sym} · {plan['name']} {tf}" if plan else f"{sym} · no validated strategy",
               timeframes={"bias": tf, "setup": tf, "entry": tf}, rule=plan["rule"] if plan else None, params=plan["params"] if plan else {},
               style=plan["style"] if plan else None, live=bool(plan), why=plan["why"] if plan else NO_EDGE[pair], test=plan["test"] if plan else None,
               note=(plan or {}).get("note"), profile=PROFILES[pair], history=12500 if tf == "H1" else 3200)
    if plan:
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


PAIR_CONFIGS: dict[str, dict] = {pair: _config(pair) for pair in ("XAU/USD", *PAIRS)}
