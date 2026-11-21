"""
Agent 2 · stop loss, take profit and lot (blueprint step 3).

SL   behind the protected anchor pivot (the lower of the SoS swing low and the engulfing's low for a buy) minus a buffer
     max(6 lambda pips, 0.30 ATR14(H1)) + the spread; never tighter than max(12 lambda pips, 0.65 ATR14(H1)), vetoed above
     1.8 ATR14(D) (SL_TOO_WIDE).
TP   the first major target (the last Daily True Elbow of the trade's side, or the near edge of the opposing Weekly AOI)
     at least 2.0 x the stop away, taken max(4 lambda pips, 0.15 ATR14(H4)) before it, at most 4.5 x the stop.
     An opposing Weekly AOI nearer than 1.85 x the stop is WEEKLY_TRAP; the daily counter-weekly needs 2.2 x. R:R >= 2.0.
Lot  per user: the user's own $ risk x the grade multiplier x the season multiplier (December 0.5), floored to the lot step.
"""

import math
from datetime import datetime, timezone

from ..config import (GRADE_MULT, M3_RUNWAY_R, SEASON_MULT, SL_ATR_H1, SL_MAX_ATR_D, SL_MIN_ATR_H1, SL_MIN_PIPS, SL_PIPS, TP_ATR_H4,
                      TP_CAP_R, TP_PIPS, TRAP_RR)
from ..strategy.zones import opposing_weekly


def plan(entry: float, d: int, z: dict, anchor: float, zones: list[dict], sts: dict, idx: dict, pip: float, lam: float, spread: float,
         scenario: str) -> dict | None:
    """SL / TP / R:R at this entry price; None when the anchor is on the wrong side of the entry or there is no target."""
    a_h1 = (sts["H1"].atr[idx["H1"]] or 0) if idx["H1"] >= 0 else 0
    a_d = (sts["D"].atr[idx["D"]] or 0) if idx["D"] >= 0 else 0
    a_h4 = (sts["H4"].atr[idx["H4"]] or 0) if idx["H4"] >= 0 else 0
    buf = max(SL_PIPS * lam * pip, SL_ATR_H1 * a_h1) + spread
    sl = anchor - buf if d > 0 else anchor + buf
    risk = (entry - sl) * d
    floor = max(SL_MIN_PIPS * lam * pip, SL_MIN_ATR_H1 * a_h1)
    if risk < floor:
        sl, risk = entry - d * floor, floor
    if risk <= 0:
        return None
    wide = bool(a_d) and risk > SL_MAX_ATR_D * a_d
    margin = max(TP_PIPS * lam * pip, TP_ATR_H4 * a_h4)
    opp, runway = opposing_weekly(zones, z, d, entry)
    cands = []
    for tf in ("D", "W"):
        st, i = sts[tf], idx[tf]
        cands += [e[2] for e in st.elbows_at(i) if e[1] == d and (e[2] - entry) * d > 0]
    if opp is not None:
        cands.append(opp["lo"] if d > 0 else opp["hi"])
    cands = sorted(set(cands), key=lambda p: (p - entry) * d)
    trap = opp is not None and runway < TRAP_RR * risk
    if opp is not None and scenario == "M3" and runway < M3_RUNWAY_R * risk:
        trap = True
    tp = None
    for p in cands:
        t = p - d * margin
        if (t - entry) * d >= 2.0 * risk:
            tp = t
            break
    if tp is None:
        return {"entry": entry, "sl": sl, "tp": None, "rr": 0.0, "risk": risk, "trap": trap, "slWide": wide, "target": None, "opp": opp["id"] if opp else None}
    capped = (tp - entry) * d > TP_CAP_R * risk
    if capped:
        tp = entry + d * TP_CAP_R * risk
    return {"entry": entry, "sl": sl, "tp": tp, "rr": (tp - entry) * d / risk, "risk": risk, "trap": trap, "slWide": wide, "capped": capped,
            "target": tp, "opp": opp["id"] if opp else None, "runway": runway}


def season_mult(T: int) -> float:
    return SEASON_MULT.get(datetime.fromtimestamp(T, timezone.utc).month, 1.0)


def risk_mult(T: int, grade: str) -> float:
    """m_grade x m_season: 1.00 for A+ / A, 0.75 for B+, halved in December."""
    return round(GRADE_MULT.get(grade, 0.0) * season_mult(T), 3)


def lots(risk_amount: float, sl_pips: float, pip_value: float, lot_min: float = 0.01, lot_max: float = 100.0, step: float = 0.01) -> float:
    """Lots = floor(R_eff / (d_SL x V_pip) / step) x step, then max(Lot_min, min(Lot_max, .)); never rounded up."""
    if sl_pips <= 0 or pip_value <= 0:
        return 0.0
    raw = risk_amount / (sl_pips * pip_value)
    floored = math.floor(raw / step + 1e-9) * step
    return round(max(lot_min, min(lot_max, floored)), 2)


def rank_key(s: dict) -> tuple:
    """(score, alignment bonus, R:R, SoS clarity), descending: the order of the signals of one close."""
    return (s.get("score") or 0, s.get("alignmentStrength") or 0, s.get("rr") or 0, (s.get("sosInfo") or {}).get("phi") or 0)
