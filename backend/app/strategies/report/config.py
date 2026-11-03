"""
Each pair's strategy from the reports "Anja7 Stratigiyat Trading F Forex" (its per-pair table and chapters) and "Rapport
Stratégies Trading Or & Forex" (3 Nov 2026: EMA trend, London range, sweep + order block, EMA pullback, consolidation
breakout), as the closest rules the app's data allows, with the 2-year test that decided whether it sends signals.

A report strategy goes LIVE (replaces the pair's strategy) only when, on 2 years of the app's own candles with the pair's
spread + slippage and the stop counted first: ≥ 30 trades, positive in both halves, positive with double costs, and
better than the strategy it replaces. Otherwise it runs in OBSERVATION: drawn on the chart with its rules and its test,
no signal. GBP/USD's London breakout lives in strategies/london/ (live).
"""

import copy

from .._pairs import BANKS
from ..alexg.config import ALEXG_CONFIGS

BASE = {
    "version": "1.0.0",
    "atrPeriod": 14,
    "risk": {"tp1R": 1, "tp2R": 1.5, "capR": 2.0, "partials": [0, 0, 1], "breakeven": False, "maxBars": 12,
             "marketValidMin": 60, "riskPct": 1, "balances": [500, 1000, 5000, 10000], "showLastSetupBars": 4},
    "filters": {"maxSpreadPips": 4, "slippagePips": 0.2, "news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30},
                "maxTradesPerDay": 2, "maxLossesPerDay": 1},
    "scoring": {"thresholds": {"signal": 75, "watch": 60}},
}

MR = {"bbPeriod": 20, "bbDev": 2.0, "stochPeriod": 14, "stochSmooth": 3, "stochLow": 20, "adxMax": 25, "slAtr": 0.3, "minRiskAtr": 0.5}

# pair → plan. `report`: what the report recommends for the pair; `test`: the 2-year result of the rules below.
PLANS = {
    "XAU/USD": {
        "report": "Bollinger breakouts + ICT Silver Bullet in New York (strict contract management for the ADR expansion)",
        "rule": "bb_squeeze", "tf": "H1", "params": {"bbPeriod": 20, "bbDev": 2.0, "squeezeLookback": 20, "squeezePct": 0.5},
        "capR": 2.0, "maxBars": 24, "live": False,
        "test": {"trades": 104, "winRate": 29.8, "totalR": -18.4, "verdict": "Loses (−18.4R): the H1 breakout + reversion engines stay"},
        "note": "ICT Silver Bullet needs M1/M5 history: only ~50 days on the feed, too few trades to test",
    },
    "EUR/USD": {
        "report": "2nd report: liquidity sweep + order block (ICT / SMC): a high or low taken, a break of structure, a stop beyond the zone, "
                  "1:2 at least (1st report: order flow + ICT Silver Bullet, MACD + RSI H4)",
        "rule": "sweep_bos", "tf": "H4", "params": {"sweepLookback": 20, "within": 6, "structureLook": 3, "slAtr": 0.1},
        "capR": 2.0, "maxBars": 30, "live": True,
        "test": {"trades": 48, "winRate": 56.2, "totalR": 15.9, "verdict": "Live: +15.9R, every third positive (+5.4R / +4.7R / +5.7R), +14.9R with double costs (RSI(2) H4: +6.0R)"},
        "note": "Neighbouring settings: every 20-candle sweep variant stays positive (+6R to +21R); a 10-candle sweep is mixed",
    },
    "USD/CAD": {
        "report": "2nd report: pullback to the moving average in the trend: EMA 20 or 50, a confirmation candle, the stop under the pullback, "
                  "1:2 or more (1st report: crude-oil lead-lag + New York ADX trend)",
        "rule": "ema_pullback", "tf": "H4", "params": {"emaTouch": 20, "swingLook": 5, "slAtr": 0.1, "minRiskAtr": 0.3},
        "capR": 1.5, "maxBars": 30, "live": True,
        "test": {"trades": 77, "winRate": 54.5, "totalR": 18.1, "verdict": "Live: +18.1R, every third positive (+5.2R / +3.0R / +9.8R), +15.2R with double costs (GPA: few trades)"},
        "note": "Every EMA 20 / 30 variant stays positive in both halves; sells carry most of the result (+16.3R vs +1.8R for buys)",
    },
    "NZD/USD": {
        "report": "Global Dairy Trade auctions + structure breaks in the Asian session",
        "rule": "session_breakout", "tf": "H1",
        "params": {"rangeHours": [17, 22], "breakHours": [22, 2], "dayShift": 7, "maxRangeAtr": 3.0, "minBodyPct": 0.5, "closeOuterThird": 2 / 3},
        "capR": 2.0, "maxBars": 14, "live": False,
        "test": {"trades": 221, "winRate": 40.7, "totalR": -19.1, "verdict": "Loses (−19.1R): FXAlexG GPA stays"},
        "note": "Dairy auctions are events, not in the feed",
    },
    "EUR/CHF": {
        "report": "Mean reversion only (breakout and trend trading forbidden)",
        "rule": "mean_reversion", "tf": "H4", "params": {**MR}, "capR": 2.0, "maxBars": 12, "live": False,
        "test": {"trades": 57, "winRate": 47.4, "totalR": 2.0, "verdict": "Not enough (+2.0R, second half −7.0R, −4.0R with double costs): FXAlexG GPA stays"},
    },
    "NZD/CAD": {
        "report": "Mean reversion inside the range on H1 / H4",
        "rule": "mean_reversion", "tf": "H4", "params": {**MR}, "capR": 2.0, "maxBars": 12, "live": False,
        "test": {"trades": 82, "winRate": 40.2, "totalR": -6.0, "verdict": "Loses (−6.0R on H4, −45R on H1): FXAlexG GPA stays"},
    },
    "AUD/CAD": {
        "report": "Range trading between the commodity currencies with Stochastic / Bollinger",
        "rule": "mean_reversion", "tf": "H4", "params": {**MR}, "capR": 2.0, "maxBars": 12, "live": True,
        "test": {"trades": 67, "winRate": 49.3, "totalR": 15.4, "verdict": "Live: +15.4R, both halves positive (+5.5R / +9.9R), +10.2R with double costs"},
        "note": "Fragile: Bollinger 2.2σ / 1.8σ or Stochastic 25 / 75 instead of 2σ and 20 / 80 lose; a looser ADX or a wider stop stay positive",
    },
    "AUD/CHF": {
        "report": "Quiet carry in low-volatility periods (ADX below 20)",
        "rule": "mean_reversion", "tf": "H1", "params": {**MR, "adxMax": 20, "sessionHours": [7, 17]}, "capR": 1.5, "maxBars": 24, "live": False,
        "test": {"trades": 58, "winRate": 50.0, "totalR": 3.2, "verdict": "Not enough (+3.2R, second half −1.1R, −8.4R with double costs): FXAlexG GPA stays"},
        "note": "The carry part needs swap rates, not in the feed",
    },
}

NAMES = {"sweep_bos": "Liquidity sweep + break of structure", "ema_pullback": "EMA pullback in the trend", "mean_reversion": "Mean reversion Bollinger + Stochastic", "ny_adx_trend": "New York trend · ADX > 25", "macd_rsi": "MACD + RSI",
         "bb_squeeze": "Bollinger squeeze breakout", "session_breakout": "Sydney-open breakout"}


def _config(pair: str, plan: dict) -> dict:
    sym = pair.replace("/", "")
    gold = pair == "XAU/USD"
    cfg = copy.deepcopy(BASE)
    cfg.update(strategy=f"Report_{plan['rule']}", name=f"{sym} · {NAMES[plan['rule']]} {plan['tf']} (report)",
               timeframes={"bias": plan["tf"], "setup": plan["tf"], "entry": plan["tf"]}, rule=plan["rule"], params=plan["params"],
               live=plan["live"], report=plan["report"], test=plan["test"], note=plan.get("note"), history=12500 if plan["tf"] == "H1" else 3200)
    cfg["risk"]["capR"], cfg["risk"]["maxBars"] = plan["capR"], plan["maxBars"]
    cfg["spec"] = ({"symbol": sym, "displaySymbol": pair, "decimals": 2, "pipSize": 0.1, "contractSize": 100, "minLot": 0.01, "lotStep": 0.01} if gold
                   else {"symbol": sym, "displaySymbol": pair, "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01})
    ccys = ["USD"] if gold else [pair[:3], pair[4:]]
    cfg["filters"]["news"].update(currencies=ccys, keywords=[k for c in ccys for k in BANKS[c]])
    if gold:
        cfg["filters"].update(assumedSpread=0.3, slippage=0.05, maxSpread=0.5)
    else:  # the pair's spread as the app already assumes it
        cfg["filters"]["assumedSpreadPips"] = ALEXG_CONFIGS[pair]["filters"]["assumedSpreadPips"]
    return cfg


REPORT_CONFIGS: dict[str, dict] = {pair: _config(pair, plan) for pair, plan in PLANS.items()}
