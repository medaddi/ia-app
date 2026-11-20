"""
FX Alex G "Set & Forget" — the owner's specification of 2026-11-20 ("fx_alex_g_set_forget_ai_multi_agent_quantitative_
specification.md"), applied to the letter. This file is the spec's config/: the 29 instruments (section 2), their pip
size, volatility scalar lambda_s, shard and "every 500" step, and every threshold of section 3.

The owner's decisions (2026-11-20) where the spec and the app differ:
  * signals only: Agent 8 builds and locks the order and alerts; nothing is sent to a broker
  * every pair's trade is sent (one per pair at a time): no currency / concurrent / weekly / drawdown limits, no
    24 h cooldown
  * each user's own $ risk per trade sizes the lot (the spec's lot formula with that amount)
  * notifications: the trade and its end only (FILLED for a limit, TP, SL, expired); no radar

Numbers the spec leaves open are marked CHOICE and were fixed before any result was seen.
"""

import json
from pathlib import Path

_CFG = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parents[1] / "configs").glob("*.json"))}

SHARDS = {"A": ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "XAUUSD"],
          "B": ["EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD", "CHFJPY"],
          "C": ["GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD", "CADJPY", "CADCHF"],
          "D": ["AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD", "NZDJPY", "NZDCHF", "NZDCAD"]}
UNIVERSE = [k for s in SHARDS.values() for k in s]


def pip_size(key: str) -> float:
    """2.2: 0.01 for JPY pairs, 0.10 for XAUUSD, 0.0001 otherwise."""
    return 0.01 if key.endswith("JPY") else 0.10 if key == "XAUUSD" else 0.0001


def lam(key: str) -> float:
    """2.2: lambda_s = 2.5 gold, 1.25 GBPJPY / GBPAUD / GBPNZD, 1.0 otherwise."""
    return 2.5 if key == "XAUUSD" else 1.25 if key in ("GBPJPY", "GBPAUD", "GBPNZD") else 1.0


def step_500(key: str) -> float:
    """3.4.2: the "every 500" grid: 0.0500 FX, 0.500 JPY, 50.00 gold (Tier-1 levels only)."""
    return 50.0 if key == "XAUUSD" else 0.5 if key.endswith("JPY") else 0.05


def shard_of(key: str) -> str:
    return next(s for s, ks in SHARDS.items() if key in ks)


def meta(key: str) -> dict:
    c = _CFG[key]
    return {"key": key, "symbol": c["symbol"], "pip": pip_size(key), "lam": lam(key), "step500": step_500(key), "shard": shard_of(key),
            "decimals": c["decimals"], "spread_pips": c["spread_pips"], "slippage_pips": c["slippage_pips"],
            "pip_value_usd_per_lot": c.get("pip_value_usd_per_lot", 10.0), "currencies": c.get("currencies") or [],
            "min_lot": c.get("min_lot", 0.01), "lot_step": c.get("lot_step", 0.01), "max_lot": c.get("max_lot", 100.0)}


# ---- 3.1 structure
K = {"W": 2, "D": 3, "H4": 3, "H2": 2, "H1": 2, "M30": 2, "M15": 2}  # k_W 2, k_D 3, k_H4 3, k_LTF 2 (H2 as LTF: CHOICE)
GAMMA = 1.0  # CHOICE in the spec's [1.0, 1.5]: the leg of a True Elbow >= 1.0 ATR14
N_CHOP, ER_MAX, CHOP_RANGE_ATR = 20, 0.20, 3.5
# ---- 3.3 AOIs
N_AOI = {"W": 150, "D": 250}
W_MAX_PIPS, MIN_TOUCHES, TOUCH_GAP, DELTA_PIPS, CAPTURE = 60.0, 3, 3, 2.0, 0.80
PROX_PIPS, BREAK_PIPS, RUNWAY_SL = 5.0, 5.0, 2.0
# ---- 3.4 confluences
LIVE_K = 2  # the last 0, 1, 2 closed bars
EMA_EPS_PIPS, EMA_AOI_PIPS, PSYCH_TOUCH_PIPS, GAP_PIPS = 3.0, 15.0, 3.0, 2.0
# ---- 3.5 entry
SOS_TFS, ENTRY_TFS = ("M15", "M30", "H1"), ("H4", "H2", "H1")  # entry: the higher timeframe preferred
SOS_VALID_SEC, BODY_RATIO, HUGE_ATR, LIMIT_SEC, LIMIT_AOI_PIPS = 12 * 3600, 0.55, 2.2, 6 * 3600, 10.0
MIN_RR, LIMIT_RR = 2.0, 2.2
# ---- 3.7 SL / TP
SL_PIPS, TP_BUF_PIPS = 6.0, 4.0
SEASON_LIVE = {1: 2.0, 2: 2.0, 3: 2.0, 10: 2.0, 11: 2.0, 12: 2.0, 4: 2.0, 5: 2.0, 8: 2.0, 9: 2.0, 6: 1.5, 7: 1.5}  # Live account, low end of each range (CHOICE)
GRADE_MULT = {"A+": 1.0, "A": 1.0, "B": 0.75}
# ---- 3.6 weights (%)
W_ALIGN = {"full": 20, "retrace": 15, "counter": 10}
W_AOI_W = W_AOI_D = 15
W_EMA = 5
W_PREV, W_PSYCH, W_HTF_CANDLE, W_H4_CANDLE, W_PATTERN, W_ENTRY = 10, 5, 10, 10, 5, 10
HOLD_DAYS = 60  # CHOICE: Set & Forget runs to its SL or TP; a record still open after 60 days is closed at market for the books
