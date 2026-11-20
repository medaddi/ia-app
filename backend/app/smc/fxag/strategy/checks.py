"""
Agent 1 · final gates (blueprint 2.6 and step 4): the grade, the extension guard, session / rollover, news (-45 / +30 min on
BOTH currencies), spread and data integrity, the one-trade-per-pair lock and the currency exposure cap. Every veto has the
blueprint's code. Returns APPROVE or the list of codes.
"""

from ..config import CURRENCY_CAP, EXT_ATR_H4, MIN_RR, SPREAD_MULT
from ..time_utils import blackout, news_block


def audit(p: dict, T: int, news: list[int] | None, news_checked: bool, spread_live: float, spread_typ: float, pip: float, health: dict,
          locked: bool = False, exposure: dict | None = None, currencies: tuple = ()) -> dict:
    """p: the candidate (grade, rr, model, ext_atr, slPips, trap, veto codes found earlier)."""
    r = list(p.get("early") or [])
    if p.get("grade") not in ("A+", "A", "B+"):
        r.append("SCORE_TOO_LOW")
    if p.get("rr", 0) < MIN_RR:
        r.append("RR_BELOW_MIN")
    if p.get("model") == "E2" and p.get("ext_atr", 0) > EXT_ATR_H4:
        r.append("EXTENDED_ENTRY")
    if p.get("slWide"):
        r.append("SL_TOO_WIDE")
    if p.get("trap"):
        r.append("WEEKLY_TRAP")
    if news_block(T, news) is not None:
        r.append("NEWS_BLACKOUT")
    if blackout(T):
        r.append("SESSION_BLACKOUT")
    if spread_live > SPREAD_MULT * spread_typ or not health.get("ok", True):
        r.append("DATA_OR_SPREAD_UNSAFE")
    if locked:
        r.append("PAIR_LOCKED")
    if exposure and p.get("side") and any(exposure.get(c, 0) * p["side_of"].get(c, 0) >= CURRENCY_CAP for c in currencies):
        r.append("CURRENCY_EXPOSURE_CAP")
    r = list(dict.fromkeys(r))
    return {"verdict": "VETO" if r else "APPROVE", "reasons": r, "newsChecked": news_checked}
