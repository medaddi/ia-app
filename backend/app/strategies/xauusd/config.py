"""
XAUUSD strategy configuration: "H1 Trend Breakout".
Every parameter of the strategy lives here; strategy.py contains no magic numbers.
Chosen from a 2-year H1 backtest (Oct 2024 – Oct 2026) and kept because it was profitable in both
halves of the period, on buys and sells, and with trading costs tripled (see docs/STRATEGIES.md).
"""

from ..shared.sessions import LONDON

XAU_CONFIG = {
    "version": "2.0.0",
    "strategy": "H1_TrendBreakout",
    "name": "XAUUSD · H1 Trend Breakout",
    "spec": {"symbol": "XAUUSD", "displaySymbol": "XAU/USD", "decimals": 2, "pipSize": 0.1, "contractSize": 100, "minLot": 0.01, "lotStep": 0.01},
    "timeframes": {"bias": "H1", "setup": "H1", "entry": "H1"},
    "history": 900,  # H1 candles analysed (EMA200 needs ~200, the rest replays one-trade-at-a-time)

    "trend": {"emaFast": 50, "emaSlow": 200},  # BUY only if EMA50 > EMA200 and close > EMA200 (mirror for SELL)
    "atrPeriod": 14,
    "breakout": {
        "lookback": 20,  # close beyond the highest high / lowest low of the previous 20 H1 candles
        "minBodyAtr": 0.5,  # breakout candle body > 0.5 × ATR(14, H1)
    },

    "risk": {
        "stopRefBars": 4,  # stop beyond the lowest low / highest high of the last 4 candles (incl. the breakout candle)
        "stopBufferAtr": 0.2,  # … minus / plus 0.2 × ATR
        "minSlAtr": 1.0,  # stop at least 1 × ATR from the entry
        "maxSlAtr": 3.0,  # no trade if the stop would be wider than 3 × ATR
        "tp1R": 1,  # close 50%, stop to breakeven
        "tp2R": 2,  # close 25%
        "tp3R": 3,  # close the rest
        "partials": [0.5, 0.25, 0.25],
        "marketValidMin": 30,  # do not enter later than 30 min after the candle close
        "riskPct": 1,
        "balances": [500, 1000, 5000, 10000],
        "showLastSetupBars": 24,  # keep showing a closed trade on the chart for 24 hours
    },

    "sessions": {
        # Only used to label trades in reports; the strategy trades every H1 close while the market is open
        "windows": [
            {"name": "Asia", "tz": LONDON, "start": "00:00", "end": "07:00"},
            {"name": "London", "tz": LONDON, "start": "07:00", "end": "13:00"},
            {"name": "New York", "tz": LONDON, "start": "13:00", "end": "22:00"},
        ],
    },

    "filters": {
        "maxSpread": 0.5,  # $ (price units)
        "assumedSpread": 0.25,  # used when the feed has no live spread
        "slippage": 0.05,
        "news": {
            "currencies": ["USD"],
            "keywords": ["CPI", "Non-Farm", "NFP", "FOMC", "Federal Funds", "Fed Chair", "Powell", "PCE", "GDP"],
            "minutesBefore": 30,
            "minutesAfter": 30,
        },
        "maxTradesPerDay": 3,
        "maxLossesPerDay": 2,
    },

    "scoring": {
        "weights": {"trend": 25, "breakout": 25, "momentum": 20, "stop": 10, "targets": 20},
        "thresholds": {"signal": 75, "watch": 60},
    },
}
