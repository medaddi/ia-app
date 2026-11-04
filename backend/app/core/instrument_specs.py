"""
Pip & instrument normalisation. Forex pairs and spot gold have different decimal structures: every agent converts pips
with these helpers before computing stops, buffers or zone widths.

XAUUSD: 1 pip = $0.10, so $1.00 = 10 pips.
"""

INSTRUMENT_CONFIG = {
    "EURUSD": {"pip_size": 0.0001, "decimals": 5, "max_spread_pips": 1.5, "contract_size": 100000, "display": "EUR/USD"},
    "GBPUSD": {"pip_size": 0.0001, "decimals": 5, "max_spread_pips": 2.2, "contract_size": 100000, "display": "GBP/USD"},
    "AUDCHF": {"pip_size": 0.0001, "decimals": 5, "max_spread_pips": 3.0, "contract_size": 100000, "display": "AUD/CHF"},
    "XAUUSD": {"pip_size": 0.10, "decimals": 2, "max_spread_pips": 3.5, "contract_size": 100, "display": "XAU/USD"},  # $1.00 = 10 pips
}

USD_PAIRS = ("EURUSD", "GBPUSD", "XAUUSD")  # quoted against the US dollar: one USD move can trigger all three


def key(symbol: str) -> str:
    """'EUR/USD' or 'EURUSD' → 'EURUSD'."""
    return symbol.replace("/", "").upper()


def pip_size(symbol: str) -> float:
    return INSTRUMENT_CONFIG[key(symbol)]["pip_size"]


def pips_to_price(symbol: str, pips: float) -> float:
    return pips * INSTRUMENT_CONFIG[key(symbol)]["pip_size"]


def price_to_pips(symbol: str, price_diff: float) -> float:
    return abs(price_diff) / INSTRUMENT_CONFIG[key(symbol)]["pip_size"]


def usd_direction(symbol: str, direction: str) -> int:
    """+1 = long USD, −1 = short USD, 0 = no USD leg. BUY EUR/USD, GBP/USD or XAU/USD sells the dollar."""
    k = key(symbol)
    if k not in USD_PAIRS:
        return 0
    return -1 if direction in ("BUY", "LONG") else 1
