"""
"RSI(2) Connors pullback" on H4 (Larry Connors' short-term mean reversion inside the trend), used on the pairs where it
held up over 2 years of H4 data, costs included:
  EUR/USD (RSI(2) < 10): 187 trades, 65.8% winners, +8.8R, profit factor 1.27, buys and sells both positive, +4.9R with double costs
  GBP/USD (RSI(2) < 5, stop 3 × ATR): 99 trades, 68.7% winners, +8.7R, profit factor 1.62, +6.7R with double costs
  (fragile: RSI(2) < 10 loses on GBP/USD, so only the stricter level is used)
Every parameter lives here; strategy.py contains no magic numbers.
"""

import copy

from .._pairs import BANKS

RSI2_BASE = {
    "version": "1.0.0",
    "strategy": "RSI2_Connors_H4",
    "timeframes": {"bias": "H4", "setup": "H4", "entry": "H4"},
    "history": 3200,  # H4 candles (~2 years from the 1h feed): the trades are replayed one at a time from the start
    "trend": {"emaFast": 50, "emaSlow": 200},  # BUY only if EMA50 > EMA200 and the close is above EMA200 (mirror for SELL)
    "rsiPeriod": 2,
    "exitEma": 5,  # exit at the first H4 close back above (buys) / below (sells) EMA5
    "atrPeriod": 14,
    "risk": {
        "tp1R": 1, "tp2R": 2, "capR": 5,  # TP1 / TP2 are progress marks; 5R is only a safety cap (the exit is EMA5)
        "partials": [0, 0, 1],
        "breakeven": False,
        "maxBars": 48,  # closed at market after 48 H4 candles (8 days) if still open
        "marketValidMin": 60,
        "riskPct": 1,
        "balances": [500, 1000, 5000, 10000],
        "showLastSetupBars": 6,
    },
    "filters": {
        "maxSpreadPips": 4,
        "slippagePips": 0.2,
        "news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30},
        "maxTradesPerDay": 2,
        "maxLossesPerDay": 1,
    },
    "scoring": {"weights": {"trend": 35, "rsi": 35, "stop": 15, "exit": 15}, "thresholds": {"signal": 75, "watch": 60}},
}

# pair → (RSI(2) extreme, stop in ATR, assumed spread in pips)
PAIRS = {"EUR/USD": (10, 2.5, 1.0), "GBP/USD": (5, 3.0, 1.5)}


def _config(pair: str, rsi_lo: float, sl_atr: float, spread: float) -> dict:
    sym = pair.replace("/", "")
    cfg = copy.deepcopy(RSI2_BASE)
    cfg["name"] = f"{sym} · RSI(2) Connors pullback H4"
    cfg["spec"] = {"symbol": sym, "displaySymbol": pair, "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01}
    cfg["rsiBuyBelow"] = rsi_lo  # buy when RSI(2) < this (sell when > 100 − this)
    cfg["slAtr"] = sl_atr
    cfg["filters"]["assumedSpreadPips"] = spread
    ccys = [pair[:3], pair[4:]]
    cfg["filters"]["news"].update(currencies=ccys, keywords=[k for c in ccys for k in BANKS[c]])
    return cfg


RSI2_CONFIGS: dict[str, dict] = {pair: _config(pair, *v) for pair, v in PAIRS.items()}
