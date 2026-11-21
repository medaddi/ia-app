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

# The traded forex pairs → (assumed spread in pips, Yahoo ticker): FXAlexG's full watchlist (28 forex pairs; gold has its
# own feeds), from the user's spec fxalexg_set_and_forget_strategy_claude_implementation_prompt.md, section 2.1
PAIRS = {
    "EUR/USD": (1.0, "EURUSD=X"),
    "GBP/USD": (1.5, "GBPUSD=X"),
    "USD/JPY": (1.2, "USDJPY=X"),
    "USD/CAD": (1.5, "USDCAD=X"),
    "USD/CHF": (1.5, "USDCHF=X"),
    "AUD/USD": (1.2, "AUDUSD=X"),
    "NZD/USD": (1.5, "NZDUSD=X"),
    "GBP/JPY": (2.5, "GBPJPY=X"),
    "GBP/AUD": (3.0, "GBPAUD=X"),
    "GBP/NZD": (4.0, "GBPNZD=X"),
    "GBP/CAD": (3.0, "GBPCAD=X"),
    "GBP/CHF": (3.0, "GBPCHF=X"),
    "EUR/GBP": (1.2, "EURGBP=X"),
    "EUR/JPY": (1.8, "EURJPY=X"),
    "EUR/AUD": (2.5, "EURAUD=X"),
    "EUR/NZD": (3.5, "EURNZD=X"),
    "EUR/CAD": (2.5, "EURCAD=X"),
    "EUR/CHF": (1.5, "EURCHF=X"),
    "AUD/JPY": (1.8, "AUDJPY=X"),
    "AUD/CAD": (2.0, "AUDCAD=X"),
    "AUD/CHF": (2.0, "AUDCHF=X"),
    "AUD/NZD": (2.5, "AUDNZD=X"),
    "NZD/JPY": (2.2, "NZDJPY=X"),
    "NZD/CAD": (3.0, "NZDCAD=X"),
    "NZD/CHF": (3.0, "NZDCHF=X"),
    "CAD/JPY": (2.2, "CADJPY=X"),
    "CAD/CHF": (2.5, "CADCHF=X"),
    "CHF/JPY": (2.5, "CHFJPY=X"),
}
# Price feeds only (never traded, never shown): USD/CAD converts AUD/CAD's profit from Canadian dollars to dollars
CONVERSION_FEEDS: dict = {}  # every conversion rate (USD/JPY, USD/CAD, USD/CHF, GBP/USD, AUD/USD, NZD/USD) is a traded pair now  # also the trader skill: CHF pip value, AUD margin

CCY_NAMES = {"XAU": "Gold", "USD": "US Dollar", "EUR": "Euro", "GBP": "British Pound", "JPY": "Japanese Yen", "CHF": "Swiss Franc",
             "CAD": "Canadian Dollar", "AUD": "Australian Dollar", "NZD": "New Zealand Dollar"}
NAMES = {p: f"{CCY_NAMES[p[:3]]} / {CCY_NAMES[p[4:]]}" for p in ["XAU/USD", *PAIRS]}


def decimals_of(symbol: str) -> int:
    """Price precision: gold 2, JPY-quoted pairs 3, the other pairs 5."""
    return 2 if symbol.startswith("XAU") else 3 if symbol.endswith("/JPY") else 5


def plausible(symbol: str, price: float) -> bool:
    """A sane price for the pair (a feed glitch or another pair's price is refused)."""
    if symbol.startswith("XAU"):
        return 1500 < price < 10000
    return 40 < price < 400 if symbol.endswith("/JPY") else 0.2 < price < 5.0
