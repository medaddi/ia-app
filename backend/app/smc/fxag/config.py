"""
FX Alex G "Set & Forget" v2 — the owner's blueprint of 2026-11-20 ("fx_alex_g_set_forget_v2_blueprint_complet_..."),
applied to the letter. This is its config: the 29 pairs in 5 volatility groups (lambda_p, "500" step), the 4 shards S0-S3,
and every threshold of steps 2 and 3.

Product constraints (the blueprint's header, the owner's choices): signals only (never a broker order) · 2 agents ·
one active trade per pair · each user's own $ risk sizes the lot · Set & Forget locked (no break-even, no partial, no radar).

Numbers the blueprint leaves open are marked CHOICE and were fixed before any result was seen.
"""

import json
from pathlib import Path

_CFG = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parents[1] / "configs").glob("*.json"))}

# 5.1 the five volatility groups: lambda_p ("1.10 - 1.20" -> 1.15 CHOICE), the "500" step, the typical spread
GROUPS = {
    "G1": {"pairs": ["EURUSD", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"], "lam": 1.00},
    "G2": {"pairs": ["GBPUSD", "EURGBP", "EURCHF", "EURCAD", "AUDCAD", "AUDCHF", "NZDCAD", "NZDCHF", "CADCHF", "AUDNZD", "EURAUD", "EURNZD"], "lam": 1.15},
    "G3": {"pairs": ["USDJPY", "EURJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"], "lam": 1.15},
    "G4": {"pairs": ["GBPJPY", "GBPAUD", "GBPNZD", "GBPCAD", "GBPCHF"], "lam": 1.35},
    "G5": {"pairs": ["XAUUSD"], "lam": 2.50},
}
# 5.3 the four shards
SHARDS = {"S0": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"],
          "S1": ["NZDUSD", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"],
          "S2": ["EURGBP", "EURAUD", "EURNZD", "EURCAD", "EURCHF", "GBPAUD", "GBPNZD", "GBPCAD"],
          "S3": ["GBPCHF", "AUDNZD", "AUDCAD", "AUDCHF", "NZDCAD", "NZDCHF", "CADCHF"]}
UNIVERSE = [k for s in SHARDS.values() for k in s]


def group_of(key: str) -> str:
    return next(g for g, v in GROUPS.items() if key in v["pairs"])


def pip_size(key: str) -> float:
    """2.1: 0.01 for JPY pairs, 0.10 for XAUUSD, 0.0001 otherwise."""
    return 0.01 if key.endswith("JPY") else 0.10 if key == "XAUUSD" else 0.0001


def lam(key: str) -> float:
    return GROUPS[group_of(key)]["lam"]


def step_500(key: str) -> float:
    """2.4.3: "every 500" = 500 pipettes = 50 pips: 0.0050, JPY 0.500, gold 25.0."""
    return 25.0 if key == "XAUUSD" else 0.5 if key.endswith("JPY") else 0.005


def shard_of(key: str) -> str:
    return next(s for s, ks in SHARDS.items() if key in ks)


def meta(key: str) -> dict:
    c = _CFG[key]
    return {"key": key, "symbol": c["symbol"], "pip": pip_size(key), "lam": lam(key), "step500": step_500(key), "shard": shard_of(key),
            "group": group_of(key), "decimals": c["decimals"], "spread_pips": c["spread_pips"], "slippage_pips": c["slippage_pips"],
            "pip_value_usd_per_lot": c.get("pip_value_usd_per_lot", 10.0), "currencies": c.get("currencies") or [],
            "min_lot": c.get("min_lot", 0.01), "lot_step": c.get("lot_step", 0.01), "max_lot": c.get("max_lot", 100.0)}


# ---- 2.2 structure: window w and the elbow amplitude alpha (x ATR14)
K = {"W": 2, "D": 3, "H4": 3, "H2": 2, "H1": 2, "M30": 2, "M15": 2}
ALPHA = {"W": 0.85, "D": 0.90, "H4": 0.85, "H2": 0.80, "H1": 0.75, "M30": 0.65, "M15": 0.60}  # H2: CHOICE between H4 and H1
EPS_PIPS = 0.5                    # the shift needs a body close 0.5 pip beyond the protected level
CHOP_N, CHOP_ER, CHOP_OVERLAP = 12, 0.18, 0.72
ATH_ATR_W = 0.5
POS_BUY_MAX, POS_BUY_VETO, POS_SELL_MIN, POS_SELL_VETO = 0.65, 0.80, 0.35, 0.20
# ---- 2.4 AOIs
N_AOI = {"W": 150, "D": 250, "H4": 200}
WMAX = {"D": (60.0, 20.0, 0.55), "H4": (60.0, 20.0, 0.55), "W": (80.0, 30.0, 0.40)}  # (cap pips x lam, floor pips x lam, ATR share)
MIN_BODY_TOUCHES, TOUCH_GAP, FLIP_MERGE_PIPS = 3, 3, 15.0
PSYCH_PIPS, BREAK_ATR_H4 = 5.0, 0.35
# ---- 2.5 confluences
WINDOW_H1, WINDOW_H4 = 12, 6
EMA_TOL_ATR, EMA_CLOSE_ATR, PREV_TOL_ATR, REJ_WICK = 0.25, 0.15, 0.35, 0.45
PATTERN_GAP = (4, 35)
PATTERN_TOL_ATR = 0.40
W_C1 = {"M1": 25, "M2": 20, "M3": 15}
W_C2_MERGED, W_C2_STRONG, W_C2_H4 = 15, 12, 8
W_C3, W_C4, W_C5, W_C6, W_C7 = 15, 10, 5, 10, 10
W_C8 = {"E1": 10, "E2": 8, "E3": 8}
GRADE_A_PLUS, GRADE_A, GRADE_BP = 85, 75, 68
GRADE_MULT = {"A+": 1.00, "A": 1.00, "B+": 0.75}
# ---- 2.6 entry
PROX_PIPS, PROX_ATR_H1 = 5.0, 0.25
EXT_ATR_H4 = 1.35
ENG_TOL_BODY, ENG_BODY_ATR, ENG_BODY_RANGE, ENG_OPP_WICK = 0.15, 0.55, 0.50, 0.30
E1_MAX_CANDLES = 8
HUGE_BODY_ATR, MIN_RR, LIMIT_RR, LIMIT_HOURS = 1.60, 2.0, 2.2, 8
SOS_TFS, ENG_TFS = ("M15", "M30", "H1"), ("M30", "H1", "H2", "H4")
SOS_VALID_SEC = 12 * 3600  # CHOICE: the blueprint gives no SoS expiry; the 12 h of the first specification is kept
# ---- 3 risk
SL_PIPS, SL_ATR_H1, SL_MIN_PIPS, SL_MIN_ATR_H1, SL_MAX_ATR_D = 6.0, 0.30, 12.0, 0.65, 1.80
TP_PIPS, TP_ATR_H4, TRAP_RR, TP_CAP_R, M3_RUNWAY_R = 4.0, 0.15, 1.85, 4.5, 2.2
SEASON_MULT = {12: 0.5}  # December 0.5, every other month 1.0
HOLD_DAYS = 60  # CHOICE: Set & Forget runs to its SL or TP; a record still open after 60 days is closed at market for the books
# ---- 4 gates
NEWS_BEFORE, NEWS_AFTER = 45 * 60, 30 * 60
SPREAD_MULT = 2.5
CURRENCY_CAP = 3
