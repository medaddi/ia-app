"""
Independent re-check of a signal before it is sent. It recomputes the rules from the signal's
own numbers and the strategy config. It can only LOWER the score or REJECT, never approve
something the strategy rejected.
"""

from ..strategies.alexg.config import ALEXG_CONFIGS
from ..strategies.rsi2.config import RSI2_CONFIGS
from ..strategies.shared.jsnum import js_str, to_fixed
from ..strategies.shared.risk import TARGET_MAX_R, TARGET_MIN_R, rr, score_checklist
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

    dist = abs(s["entry"] - s["sl"])
    # App rule, every strategy: one target between 1.5R and 2R (a tick of rounding allowed)
    rr_target = rr(s["entry"], s["sl"], s["tp3"])
    if not (TARGET_MIN_R - 0.02 <= rr_target <= TARGET_MAX_R + 0.01):
        issues.append(f"Target at 1:{to_fixed(rr_target, 2)}, outside 1:{TARGET_MIN_R}–1:{TARGET_MAX_R}")
    if r["symbol"] == "XAUUSD":
        # The stop size (1–3 × ATR) is the strategy's own required "stop" rule
        if dist <= 0:
            issues.append("Stop distance is zero")
        if s["entryType"] != "MARKET":
            issues.append("Gold entries are MARKET orders")
    elif r["strategy"] == "RSI2_Connors_H4":
        if dist <= 0:
            issues.append("Stop distance is zero")
        if s["entryType"] != "MARKET":
            issues.append("RSI(2) entries are MARKET orders")
    else:
        cfg = ALEXG_CONFIGS[r["spec"]["displaySymbol"]]
        R = cfg["risk"]
        pips = dist / r["spec"]["pipSize"]
        # Set & forget: the whole position runs to the single target (the next W1 / D1 zone, capped at 2R)
        if pips < R["minSlPips"] - 0.01 or pips > R["maxSlPips"] + 0.01:
            issues.append(f"Stop {to_fixed(pips, 1)} pips outside {R['minSlPips']}–{R['maxSlPips']}")
        if s["entryType"] != "MARKET":
            issues.append("GPA entries are MARKET orders (close of the engulfing)")
    for c in r["checklist"]:
        if c["required"] and not c["passed"]:
            issues.append(f"Required rule failed: {c['rule']}")
    thresholds = (XAU_CONFIG if r["symbol"] == "XAUUSD" else RSI2_CONFIGS[r["spec"]["displaySymbol"]] if r["strategy"] == "RSI2_Connors_H4"
                  else ALEXG_CONFIGS[r["spec"]["displaySymbol"]])["scoring"]["thresholds"]
    score = min(r["score"], score_checklist(r["checklist"]))
    if score < thresholds["signal"]:
        issues.append(f"Score {js_str(score)} < {thresholds['signal']}")
    return {"approved": not issues, "score": score, "issues": issues}
