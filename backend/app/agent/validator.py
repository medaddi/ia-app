"""
Independent re-check of a signal before it is sent. It recomputes the rules from the signal's
own numbers and the strategy config. It can only LOWER the score or REJECT, never approve
something the strategy rejected.
"""

from ..strategies.alexg.config import ALEXG_CONFIGS
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
        if s["setup"] == "REVERSION":  # one target at 1R (high win rate engine)
            RV = XAU_CONFIG["reversion"]
            rr_target = rr(s["entry"], s["sl"], s["tp3"])
            if rr_target < RV["tpR"] - 0.01:
                issues.append(f"R:R to the target {to_fixed(rr_target, 2)} < {RV['tpR']}")
        elif rr_tp2 < R["tp2R"] - 0.01:  # prices are rounded to the cent
            issues.append(f"R:R to TP2 {to_fixed(rr_tp2, 2)} < {R['tp2R']}")
        # The stop size (1–3 × ATR) is the strategy's own required "stop" rule
        if dist <= 0:
            issues.append("Stop distance is zero")
        if s["entryType"] != "MARKET":
            issues.append("Gold entries are MARKET orders")
    else:
        cfg = ALEXG_CONFIGS[r["spec"]["displaySymbol"]]
        R = cfg["risk"]
        pips = dist / r["spec"]["pipSize"]
        # Set & forget: the whole position runs to the single target (TP3, the next W1 / D1 zone)
        rr_target = rr(s["entry"], s["sl"], s["tp3"])
        if rr_target < R["minRr"] - 0.01:
            issues.append(f"R:R to the target {to_fixed(rr_target, 2)} < {R['minRr']}")
        if pips < R["minSlPips"] - 0.01 or pips > R["maxSlPips"] + 0.01:
            issues.append(f"Stop {to_fixed(pips, 1)} pips outside {R['minSlPips']}–{R['maxSlPips']}")
        if s["entryType"] != "MARKET":
            issues.append("GPA entries are MARKET orders (close of the engulfing)")
    for c in r["checklist"]:
        if c["required"] and not c["passed"]:
            issues.append(f"Required rule failed: {c['rule']}")
    thresholds = (XAU_CONFIG if r["symbol"] == "XAUUSD" else ALEXG_CONFIGS[r["spec"]["displaySymbol"]])["scoring"]["thresholds"]
    score = min(r["score"], score_checklist(r["checklist"]))
    if score < thresholds["signal"]:
        issues.append(f"Score {js_str(score)} < {thresholds['signal']}")
    return {"approved": not issues, "score": score, "issues": issues}
