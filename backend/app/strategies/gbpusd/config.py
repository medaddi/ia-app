"""
GBPUSD strategy configuration: the EURUSD "Trend Pullback + London Breakout Filter" rules, unchanged,
applied to GBP/USD (same pip size). Only the instrument and the news currencies differ.
"""

import copy

from ..eurusd.config import EUR_CONFIG

GBP_CONFIG = copy.deepcopy(EUR_CONFIG)
GBP_CONFIG.update({
    "strategy": "TrendPullback_LondonBreakout_GBP",
    "name": "GBPUSD · Trend Pullback + London Breakout Filter",
    "spec": {"symbol": "GBPUSD", "displaySymbol": "GBP/USD", "decimals": 5, "pipSize": 0.0001, "contractSize": 100000, "minLot": 0.01, "lotStep": 0.01},
})
GBP_CONFIG["filters"]["news"] = {
    "currencies": ["GBP", "USD"],
    "keywords": ["BoE", "Bank of England", "Official Bank Rate", "MPC", "Bailey", "CPI", "Non-Farm", "NFP", "FOMC", "Federal Funds", "Fed Chair", "Powell"],
    "minutesBefore": 30,
    "minutesAfter": 30,
}
