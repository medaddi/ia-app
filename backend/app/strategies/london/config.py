"""
"London breakout" on H1 (GBP/USD), from the strategy report "Anja7 Stratigiyat Trading F Forex" (London Breakout
Strategy: DailyForex / KenyaForexFirm, win rate 50–65%, profit factor > 1.5), tested on the app's own data before use.

2 years of H1 (Nov 2024 – Nov 2026), spread 1.5 + 0.2 pip, stop first when a candle touches stop and target:
  274 trades, 48.5% winners, +28.6R, profit factor 1.25, both halves positive (+19.4R / +9.2R), +14.4R with double costs.
  Every neighbouring setting stayed positive (28 of 28: window 07–10 / 07–12, body 0.5 / 0.6, range ≤ 2 / 3 / 4 ATR,
  1.5R / 2R, exit 17:00 / 21:00 GMT); without the strong-candle filter it fails with double costs, so the filter is kept.
  The buys carried the result (+29.3R) while the sells were flat (−0.7R): GBP/USD rose over the period.
  RSI(2) H4, which it replaces on GBP/USD, made +3.0R on 58 trades over the same months.
Every parameter lives here; strategy.py contains no magic numbers.
"""

import copy

from .._pairs import BANKS

LONDON_BASE = {
    "version": "1.0.0",
    "strategy": "London_Breakout_H1",
    "timeframes": {"bias": "H1", "setup": "H1", "entry": "H1"},
    "history": 12500,  # H1 candles (~2 years): the trades are replayed one at a time from the start
    "session": {
        "asiaStartHour": 0,   # the Asian range: H1 candles opening 00:00 … 06:00 GMT
        "asiaEndHour": 7,
        "breakoutEndHour": 11,  # the breakout: an H1 close between 07:00 and 11:00 GMT (candles opening 07 … 10)
        "minAsiaCandles": 5,
    },
    "breakout": {
        "minBodyPct": 0.5,       # the breakout candle's body is at least half its range
        "closeOuterThird": 2 / 3,  # and it closes in its outer third (no pin bar, no long wick back into the range)
        "maxRangeAtr": 3.0,      # an Asian range wider than 3 × ATR(14, H1) is not a range: no trade
    },
    "trend": {"emaFast": 50, "emaSlow": 200},  # shown for context only (the strategy does not filter on it)
    "atrPeriod": 14,
    "risk": {
        # Stop at the opposite side of the Asian range; one target at 2R (app rule 1.5R–2R; 2R tested best)
        "tp1R": 1, "tp2R": 1.5, "capR": 2.0,
        "partials": [0, 0, 1],
        "breakeven": False,
        "maxBars": 14,  # closed at market at the end of the day (14 H1 candles ≈ 21:00 GMT) if neither is hit
        "marketValidMin": 60,
        "riskPct": 1,
        "balances": [500, 1000, 5000, 10000],
        "showLastSetupBars": 6,
    },
    "filters": {
        "maxSpreadPips": 4,
        "slippagePips": 0.2,
        "news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30},
        "maxTradesPerDay": 1,  # one breakout a day
        "maxLossesPerDay": 1,
    },
    "scoring": {"weights": {"range": 25, "breakout": 35, "strength": 20, "stop": 10, "target": 10}, "thresholds": {"signal": 75, "watch": 60}},
}

# pair → assumed spread in pips
PAIRS = {"GBP/USD": 1.5}


def _config(pair: str, spread: float) -> dict:
    sym = pair.replace("/", "")
    cfg = copy.deepcopy(LONDON_BASE)
    cfg["name"] = f"{sym} · London Breakout H1"
    cfg["spec"] = {"symbol": sym, "displaySymbol": pair, "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01}
    cfg["filters"]["assumedSpreadPips"] = spread
    ccys = [pair[:3], pair[4:]]
    cfg["filters"]["news"].update(currencies=ccys, keywords=[k for c in ccys for k in BANKS[c]])
    return cfg


LONDON_CONFIGS: dict[str, dict] = {pair: _config(pair, v) for pair, v in PAIRS.items()}
