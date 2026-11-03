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

# forex pair → (assumed spread in pips, Yahoo ticker)
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

NAMES = {"XAU/USD": "Gold / US Dollar", "EUR/USD": "Euro / US Dollar", "GBP/USD": "British Pound / US Dollar",
         "USD/CAD": "US Dollar / Canadian Dollar", "NZD/USD": "New Zealand Dollar / US Dollar", "EUR/CHF": "Euro / Swiss Franc",
         "NZD/CAD": "New Zealand Dollar / Canadian Dollar", "AUD/CAD": "Australian Dollar / Canadian Dollar", "AUD/CHF": "Australian Dollar / Swiss Franc"}
