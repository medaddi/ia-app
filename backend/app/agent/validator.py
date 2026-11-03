"""
Independent re-check of a signal before it is sent. It recomputes the rules from the signal's
own numbers and the strategy config. It can only LOWER the score or REJECT, never approve
something the strategy rejected.
"""

from ..strategies.pairs.config import PAIR_CONFIGS
from ..strategies.shared.jsnum import js_str, to_fixed
from ..strategies.shared.risk import TARGET_MAX_R, TARGET_MIN_R, rr, score_checklist


def validate_signal(r: dict) -> dict:
    issues: list[str] = []
    s = r["setup"]
    if r["status"] != "SIGNAL" or not s:
        return {"approved": False, "score": r["score"], "issues": ["Strategy status is not SIGNAL"]}
    if not r["dataQuality"]["ok"]:
        issues.append(f"Data not usable: {r['dataQuality']['reason']}")

    buy = s["direction"] == "BUY"
    if buy:
        ordered = s["sl"] < s["entry"] < s["tp1"] < s["tp2"] <= s["tp3"]
    else:
        ordered = s["sl"] > s["entry"] > s["tp1"] > s["tp2"] >= s["tp3"]
    if not ordered:
        issues.append("Levels are not in order (SL / entry / TP1 / TP2 / TP3)")

    dist = abs(s["entry"] - s["sl"])
    cfg = PAIR_CONFIGS[r["spec"]["displaySymbol"]]
    # The target's R:R: the agent's own range (EUR/USD ≥ 2, GBP/USD 3, AUD/CHF ≥ 1.8), else the app rule 1.5R–2R
    lo, hi = cfg.get("targetRange") or (TARGET_MIN_R, TARGET_MAX_R)
    rr_target = rr(s["entry"], s["sl"], s["tp3"])
    if not (lo - 0.02 <= rr_target <= hi + 0.02):
        issues.append(f"Target at 1:{to_fixed(rr_target, 2)}, outside 1:{js_str(lo)}–1:{js_str(hi)}")
    if not cfg["rule"]:
        issues.append("No validated strategy on this pair")
    # The stop is the plan's own ATR multiple: only its sanity is checked here
    if dist <= 0:
        issues.append("Stop distance is zero")
    allowed = cfg.get("entryTypes") or ["MARKET"]
    if s["entryType"] not in allowed:
        issues.append(f"This plan enters with {' / '.join(allowed)} orders, not {s['entryType']}")
    for c in r["checklist"]:
        if c["required"] and not c["passed"]:
            issues.append(f"Required rule failed: {c['rule']}")
    thresholds = cfg["scoring"]["thresholds"]
    score = min(r["score"], score_checklist(r["checklist"]))
    if score < thresholds["signal"]:
        issues.append(f"Score {js_str(score)} < {thresholds['signal']}")
    return {"approved": not issues, "score": score, "issues": issues}
