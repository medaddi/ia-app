"""
Independent re-check of a signal before it is sent. It recomputes the rules from the signal's
own numbers and the strategy config. It can only LOWER the score or REJECT, never approve
something the strategy rejected.
"""

from ..strategies.eurusd.config import EUR_CONFIG
from ..strategies.shared.jsnum import js_str, to_fixed
from ..strategies.shared.risk import rr, score_checklist
from ..strategies.xauusd.config import XAU_CONFIG


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

    rr_tp2 = rr(s["entry"], s["sl"], s["tp2"])
    dist = abs(s["entry"] - s["sl"])
    if r["symbol"] == "XAUUSD":
        R = XAU_CONFIG["risk"]
        if rr_tp2 < R["minRrTp2"] - 1e-9:
            issues.append(f"R:R to TP2 {to_fixed(rr_tp2, 2)} < {R['minRrTp2']}")
        if dist < R["minSl"] or dist > R["maxSl"]:
            issues.append(f"Stop ${to_fixed(dist, 2)} outside ${R['minSl']}–${R['maxSl']}")
        if s["entryType"] != "LIMIT":
            issues.append("Gold entries must be LIMIT orders")
    else:
        R = EUR_CONFIG["risk"]
        pips = dist / r["spec"]["pipSize"]
        if rr_tp2 < R["minRr"] - 1e-9:
            issues.append(f"R:R to TP2 {to_fixed(rr_tp2, 2)} < {R['minRr']}")
        if pips < R["minSlPips"] - 1e-6 or pips > R["maxSlPips"] + 1e-6:
            issues.append(f"Stop {to_fixed(pips, 1)} pips outside {R['minSlPips']}–{R['maxSlPips']}")
    for c in r["checklist"]:
        if c["required"] and not c["passed"]:
            issues.append(f"Required rule failed: {c['rule']}")
    thresholds = (XAU_CONFIG if r["symbol"] == "XAUUSD" else EUR_CONFIG)["scoring"]["thresholds"]
    score = min(r["score"], score_checklist(r["checklist"]))
    if score < thresholds["signal"]:
        issues.append(f"Score {js_str(score)} < {thresholds['signal']}")
    return {"approved": not issues, "score": score, "issues": issues}
