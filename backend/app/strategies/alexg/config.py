"""
Forex strategy configuration: "FXAlexG · Set & Forget Break & Retest", the method FXAlexG trades
(weekly → daily → H4 top-down analysis, "look left" areas of interest, break and retest with an
engulfing or pin-bar confirmation, pro-trend only, one stop and one target, no management).
Every parameter lives here; strategy.py contains no magic numbers.
One config per pair: only the instrument, the costs and the news currencies differ.
2-year H1 backtest (Oct 2024 – Oct 2026, see docs/STRATEGIES.md): only GBP/USD was profitable and robust;
the pairs were added on the user's request anyway.
"""

import copy

from ..shared.sessions import LONDON

ALEXG_BASE = {
    "version": "1.0.0",
    "strategy": "FXAlexG_SetForget_BreakRetest",
    "timeframes": {"bias": "W1/D1", "setup": "H4", "entry": "H4"},
    "history": 3200,  # H4 candles analysed (~2 years, what the feed serves: the trades are replayed one at a time from the start)

    "trend": {
        "weeklyEma": 20,  # weekly bias: last closed weekly close vs EMA20 (weekly)
        "dailyEma": 20,  # daily must agree: last closed daily close vs EMA20 (daily)
    },
    "atrPeriod": 14,
    "aoi": {
        "swingN": 3,  # H4 fractal swing (3 candles each side) = an area of interest on the left
        "lookbackBars": 120,  # H4 candles to look left for areas of interest (~4 weeks)
        "minTouches": 2,  # the level must have been touched at least twice (an area price respected before)
        "touchAtr": 0.3,  # a touch is a high / low within 0.3 × ATR(H4) of the level
    },
    "breakRetest": {
        "maxBarsSinceBreak": 30,  # the break (H4 close beyond the level) happened within the last 30 H4 candles
        "invalidAtr": 0.5,  # an H4 close back through the level by more than 0.5 × ATR cancels the break
        "minMoveAtr": 1.5,  # after the break, price moved at least 1.5 × ATR away (a real break, not a poke)
        "retestTolAtr": 0.5,  # the retest candle trades within 0.5 × ATR of the level and closes on the right side
        "engulfing": True,
        "pinBar": True,
        "pinWickBody": 2,  # pin bar: rejection wick ≥ 2 × body …
        "pinWickRange": 0.6,  # … and ≥ 60% of the candle
    },

    "risk": {
        "slBufferAtr": 0.5,  # stop beyond the confirmation and previous candle, ± 0.5 × ATR
        "minSlPips": 15,
        "maxSlPips": 120,
        "targetR": 3,  # set & forget: the whole position runs to 3R
        "tp1R": 1,  # TP1 / TP2 are progress marks only (no partial close, no breakeven)
        "tp2R": 2,
        "partials": [0, 0, 1],
        "breakeven": False,
        "marketValidMin": 60,  # do not enter later than 60 min after the H4 close
        "riskPct": 1,
        "balances": [500, 1000, 5000, 10000],
        "showLastSetupBars": 6,  # keep showing a closed trade on the chart for one day
    },

    "sessions": {
        # Labels for reports; the strategy is evaluated at every H4 close while the market is open
        "windows": [
            {"name": "Asia", "tz": LONDON, "start": "00:00", "end": "07:00"},
            {"name": "London", "tz": LONDON, "start": "07:00", "end": "13:00"},
            {"name": "New York", "tz": LONDON, "start": "13:00", "end": "22:00"},
        ],
    },

    "filters": {
        "maxSpreadPips": 4,
        "slippagePips": 0.2,
        "news": {"currencies": [], "keywords": [], "minutesBefore": 30, "minutesAfter": 30},
        "maxTradesPerDay": 2,
        "maxLossesPerDay": 1,
    },

    "scoring": {
        "weights": {"trend": 25, "aoi": 20, "break": 20, "retest": 20, "stop": 5, "target": 10},
        "thresholds": {"signal": 75, "watch": 60},
    },
}

_BANKS = {
    "USD": ["CPI", "Non-Farm", "NFP", "FOMC", "Federal Funds", "Fed Chair", "Powell"],
    "EUR": ["ECB", "Lagarde", "Main Refinancing"],
    "GBP": ["BoE", "Bank of England", "Official Bank Rate", "MPC", "Bailey"],
    "CHF": ["SNB", "Policy Rate"],
    "CAD": ["BoC", "Overnight Rate", "Employment Change"],
    "AUD": ["RBA", "Cash Rate"],
    "NZD": ["RBNZ", "Official Cash Rate"],
}

# pair → (assumed spread in pips, Yahoo ticker)
PAIRS = {
    "EUR/USD": (1.0, "EURUSD=X"),
    "GBP/USD": (1.5, "GBPUSD=X"),
    "USD/CAD": (1.5, "USDCAD=X"),
    "NZD/USD": (1.5, "NZDUSD=X"),
    "EUR/CHF": (1.5, "EURCHF=X"),
    "NZD/CAD": (2.5, "NZDCAD=X"),
    "AUD/CAD": (2.0, "AUDCAD=X"),
    "AUD/CHF": (2.0, "AUDCHF=X"),
}

NAMES = {"EUR/USD": "Euro / US Dollar", "GBP/USD": "British Pound / US Dollar", "USD/CAD": "US Dollar / Canadian Dollar",
         "NZD/USD": "New Zealand Dollar / US Dollar", "EUR/CHF": "Euro / Swiss Franc", "NZD/CAD": "New Zealand Dollar / Canadian Dollar",
         "AUD/CAD": "Australian Dollar / Canadian Dollar", "AUD/CHF": "Australian Dollar / Swiss Franc"}


def _config(pair: str, spread: float) -> dict:
    sym = pair.replace("/", "")
    cfg = copy.deepcopy(ALEXG_BASE)
    cfg["name"] = f"{sym} · FXAlexG Set & Forget Break & Retest"
    cfg["spec"] = {"symbol": sym, "displaySymbol": pair, "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01}
    cfg["filters"]["assumedSpreadPips"] = spread
    ccys = [pair[:3], pair[4:]]
    cfg["filters"]["news"].update(currencies=ccys, keywords=[k for c in ccys for k in _BANKS[c]])
    return cfg


ALEXG_CONFIGS: dict[str, dict] = {pair: _config(pair, spread) for pair, (spread, _) in PAIRS.items()}
