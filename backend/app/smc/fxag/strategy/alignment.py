"""
Agent 1 · alignment (blueprint 2.3): the W / D / H4 matrix (M1 full sync, M2 HTF retracement, M3 daily counter-weekly,
M4 conflict) and the "where are we in the move" filter Pos_leg. A timeframe in CHOP counts as neutral (0).
"""

from ..config import M3_RUNWAY_R, POS_BUY_MAX, POS_BUY_VETO, POS_SELL_MIN, POS_SELL_VETO


def matrix(bw: int, bd: int, b4: int, d: int) -> dict:
    """The scenario for direction d. M1: W = D = H4 = d. M2: W = D = d, H4 opposite or CHOP. M3: D = H4 = d, W opposite or
    CHOP (needs the runway to the opposing Weekly AOI, checked with the plan). Anything else: M4, HTF_MISALIGNED."""
    if bd == d and bw == d and b4 == d:
        return {"scenario": "M1", "bonus": 25, "label": "Full Sync (W + D + 4H)", "anchor": "WD"}
    if bw == d and bd == d:
        return {"scenario": "M2", "bonus": 20, "label": "HTF Retracement (W + D, 4H against)", "anchor": "WD"}
    if bd == d and b4 == d and bw != d:
        return {"scenario": "M3", "bonus": 15, "label": "Daily Swing / Counter-Weekly (D + 4H)", "anchor": "D", "needs_runway": M3_RUNWAY_R}
    return {"scenario": "M4", "bonus": 0, "label": "HTF_MISALIGNED", "anchor": None}


def direction(bw: int, bd: int, b4: int) -> int:
    """The direction an alignment allows: +1 / -1 / 0 (none)."""
    for d in (1, -1):
        if matrix(bw, bd, b4, d)["scenario"] != "M4":
            return d
    return 0


def pos_leg(close: float, low: float, high: float) -> float | None:
    """2.3: the position inside the active Daily / 4H leg [low, high], 0 at the low and 1 at the high."""
    return None if high <= low else (close - low) / (high - low)


def chasing(close: float, low: float, high: float, d: int) -> str | None:
    """CHASING_HIGH for a buy above 0.80 of the leg, CHASING_LOW for a sell below 0.20; None when the price is in value."""
    p = pos_leg(close, low, high)
    if p is None:
        return None
    if d > 0 and p > POS_BUY_VETO:
        return "CHASING_HIGH"
    if d < 0 and p < POS_SELL_VETO:
        return "CHASING_LOW"
    return None


def in_value(close: float, low: float, high: float, d: int) -> bool:
    p = pos_leg(close, low, high)
    return p is None or (p <= POS_BUY_MAX if d > 0 else p >= POS_SELL_MIN)
