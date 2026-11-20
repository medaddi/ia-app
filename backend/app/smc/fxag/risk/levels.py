"""
Agent 6 · RiskGovernor (spec 3.7, 5.3): the mechanical stop (structural invalidation + 6 lambda pips + the live
spread), the structural target (the nearest respected D / W HH or LL, 4 lambda pips before it, capped before an opposing
Weekly AOI), R:R >= 2.0, the No-Trap runway, the seasonal risk % and the grade multiplier, the lot formula, and the
deterministic ranking of the signals of one candle close.

The owner's decisions (2026-11-20): every pair's trade is sent, one per pair at a time (no currency exposure matrix,
no concurrent / weekly quota, no drawdown breaker); each user's own $ risk sizes the lot.
"""

import math
from datetime import datetime, timezone

from ..strategy.zones import opposing_weekly
from ..config import GRADE_MULT, RUNWAY_SL, SEASON_LIVE, SL_PIPS, TP_BUF_PIPS


def plan(entry: float, d: int, z: dict, ext: float, ecandle, zones: list[dict], sts: dict, idx: dict, pip: float, lam: float,
         spread: float, counter: bool) -> dict | None:
    """SL / TP / R:R at this entry price; None when there is no structural target or no risk."""
    buf = SL_PIPS * lam * pip + spread
    sl = (min(z["sl_lo"], ext, ecandle.low) - buf) if d > 0 else (max(z["sl_hi"], ext, ecandle.high) + buf)
    risk = (entry - sl) * d
    if risk <= 0:
        return None
    anchor = "W" if ("W" in z["tfs"] and not counter) else "D"
    st, i = sts[anchor], idx[anchor]
    heads = [e[2] for e in st.elbows_at(i) if e[1] == d and (e[2] - entry) * d > 0]
    if not heads:
        return None
    target = min(heads) if d > 0 else max(heads)
    b = TP_BUF_PIPS * lam * pip
    tp = target - d * b
    opp, runway = opposing_weekly(zones, z, d, entry)
    capped = False
    if opp is not None:
        cap = (opp["lo"] - b) if d > 0 else (opp["hi"] + b)
        if (cap - tp) * d < 0:
            tp, capped = cap, True
    rr = (tp - entry) * d / risk
    trap = bool(counter and opp is not None and runway < RUNWAY_SL * risk)
    return {"entry": entry, "sl": sl, "tp": tp, "rr": rr, "risk": risk, "target": target, "anchor": anchor, "capped": capped,
            "opp": opp["id"] if opp else None, "runway": runway, "trap": trap}


def risk_pct(T: int, grade: str) -> float:
    """3.7.4 x the grade multiplier: the Live account's seasonal R_base (CHOICE: the low end of each range) x 1.00 (A+, A)
    or 0.75 (B)."""
    m = datetime.fromtimestamp(T, timezone.utc).month
    return round(SEASON_LIVE[m] * GRADE_MULT.get(grade, 0.0), 2)


def lots(risk_amount: float, sl_pips: float, pip_value: float, lot_min: float = 0.01, lot_max: float = 100.0, step: float = 0.01) -> float:
    """3.7.5: Lots = RiskAmount / (d_SL x V_pip), floored to the step, then max(Lot_min, min(Lot_max, .))."""
    if sl_pips <= 0 or pip_value <= 0:
        return 0.0
    raw = risk_amount / (sl_pips * pip_value)
    floored = math.floor(raw / step + 1e-9) * step
    return round(max(lot_min, min(lot_max, floored)), 2)


def rank_key(s: dict) -> tuple:
    """5.3.2: (S_total, AlignmentStrength, RR, Phi(SoS)), descending."""
    return (s.get("score") or 0, s.get("alignmentStrength") or 0, s.get("rr") or 0, (s.get("sosInfo") or {}).get("phi") or 0)
