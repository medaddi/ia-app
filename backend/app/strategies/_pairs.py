"""Shared per-currency data: the high-impact news keywords of each central bank / release."""

BANKS = {
    "USD": ["CPI", "Non-Farm", "NFP", "FOMC", "Federal Funds", "Fed Chair", "Powell"],
    "EUR": ["ECB", "Lagarde", "Main Refinancing"],
    "GBP": ["BoE", "Bank of England", "Official Bank Rate", "MPC", "Bailey"],
    "CHF": ["SNB", "Policy Rate"],
    "CAD": ["BoC", "Overnight Rate", "Employment Change"],
    "AUD": ["RBA", "Cash Rate"],
    "NZD": ["RBNZ", "Official Cash Rate"],
}

# The traded forex pairs → (assumed spread in pips, Yahoo ticker): only the pairs whose strategy held up in its test
PAIRS = {
    "EUR/USD": (1.0, "EURUSD=X"),
    "GBP/USD": (1.5, "GBPUSD=X"),
    "AUD/CHF": (2.0, "AUDCHF=X"),
}
# Price feeds only (never traded, never shown): EUR/CHF converts AUD/CHF's profit from francs to dollars
CONVERSION_FEEDS = {"EUR/CHF": "EURCHF=X"}

NAMES = {"XAU/USD": "Gold / US Dollar", "EUR/USD": "Euro / US Dollar", "GBP/USD": "British Pound / US Dollar",
         "AUD/CHF": "Australian Dollar / Swiss Franc"}
