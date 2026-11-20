"""
Agent 7 · SetupAuditor (spec 4): the devil's advocate. Re-verifies every non-negotiable invariant of a proposal and
holds absolute VETO power (it can reject, never create or force a trade). Deterministic rule engine; the spec's optional
LLM / VLM critic is not used.
"""

from ..config import LIMIT_AOI_PIPS, MIN_RR, PROX_PIPS
from ..time_utils import blackout, in_session, news_block


def audit(p: dict, T: int, news: list[int] | None, news_checked: bool, spread_live: float, spread_median: float, pip: float,
          lam: float, health: dict) -> dict:
    """AuditVerdict(APPROVE | VETO, reason_codes)."""
    r: list[str] = []
    if p.get("score", 0) < 80:
        r.append("ERR_SCORE_BELOW_80")
    if not p.get("sos"):
        r.append("ERR_NO_BODY_CLOSE_SOS")
    if not p.get("engulf"):
        r.append("ERR_NO_ENGULFING")
    if p.get("rr", 0) < MIN_RR:
        r.append("ERR_RR_BELOW_2")
    lim = LIMIT_AOI_PIPS if p.get("orderType") == "LIMIT_PULLBACK" else PROX_PIPS
    if p.get("entryDistPips", 1e9) > lim * lam:
        r.append("ERR_OUTSIDE_AOI_PROXIMITY")
    if p.get("trap"):
        r.append("ERR_OPPOSING_WEEKLY_AOI_TRAP")
    if p.get("suspended"):
        r.append("ERR_AOI_SUSPENDED")
    if p.get("extreme"):
        r.append("ERR_EXTREME_NO_DATA")
    sl_pips = p.get("slPips") or 0
    if spread_live > min(2.5 * spread_median, 0.15 * sl_pips * pip):
        r.append("ERR_SPREAD_ANOMALY")
    if news_block(T, news) is not None:
        r.append("ERR_NEWS_BLACKOUT")
    b = blackout(T)
    if b:
        r.append(b)
    elif not in_session(T):
        r.append("ERR_OUTSIDE_SESSION")
    if not health.get("ok", True):
        r.append("ERR_DATA_GAPS")
    return {"verdict": "VETO" if r else "APPROVE", "reasons": r, "newsChecked": news_checked}
