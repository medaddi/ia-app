"""
AI trade desk: the last, independent check before a signal is sent. It never creates or improves a trade;
it can only block one. Every check is recomputed at send time from live numbers:

1. Strategy rules re-checked (validator: levels in order, R:R, stop size, required rules, score / grade)
2. Data: real and fresh (not the "last good" fallback used while the feed is retrying)
3. Price still near the entry: the market has not run away since the candle closed
4. R:R still valid from the live price
5. Market open and no high-impact news window
6. Exposure: not more than MAX_SAME_SIDE open signals leaning the same way on one currency
   (EUR/USD SELL and GBP/USD SELL are both long USD: a third USD-long signal is blocked)
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal
from ..strategies.shared.jsnum import to_fixed
from .validator import validate_signal

MAX_DRIFT_R = 0.35  # the live price may be at most 0.35 × the stop distance away from the entry
MIN_LIVE_RR = 0.85  # the remaining R:R from the live price keeps at least 85% of the planned one
MAX_SAME_SIDE = 2  # open signals with the same currency on the same side
OPEN_STATES = ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")


def legs(symbol: str, direction: str) -> dict[str, int]:
    """Currency exposure of a trade: BUY EUR/USD = +EUR −USD (gold counts as XAU vs USD)."""
    base, quote = symbol.replace("XAUUSD", "XAU/USD").split("/") if "/" in symbol else (symbol[:3], symbol[3:])
    s = 1 if direction == "BUY" else -1
    return {base: s, quote: -s}


def _check(key: str, label: str, passed: bool, detail: str) -> dict:
    return {"key": key, "label": label, "passed": bool(passed), "detail": detail}


def review(r: dict, db: Optional[Session] = None) -> dict:
    """{"approved", "score", "checks": [...], "issues": [...]} for the strategy result `r` (with a setup)."""
    s = r.get("setup")
    if not s:
        return {"approved": False, "score": 0, "checks": [], "issues": ["No setup"]}
    d = r["spec"]["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    v = validate_signal(r)
    checks = [_check("rules", "Strategy rules re-checked", v["approved"], "All rules pass" if v["approved"] else "; ".join(v["issues"]))]

    dq = r["dataQuality"]
    checks.append(_check("data", "Live, fresh data", dq["ok"] and not dq.get("stale"), dq.get("reason", "")))

    price = r["price"] or s["entry"]
    risk = abs(s["entry"] - s["sl"])
    buy = s["direction"] == "BUY"
    drift = (price - s["entry"]) / risk if risk else 0
    drift = drift if buy else -drift  # > 0 = moved in the trade's favour (late entry), < 0 = moved toward the stop
    checks.append(_check("drift", f"Price within {MAX_DRIFT_R}R of the entry", abs(drift) <= MAX_DRIFT_R,
                         f"Live {f(price)} vs entry {f(s['entry'])} ({drift:+.2f}R)"))

    target = s["tp1"] if s["setup"] == "RSI2" else s["tp3"] if s["params"].get("breakeven", True) is False else s["tp2"]  # RSI(2): ~1R to EMA5
    planned = abs(target - s["entry"]) / risk if risk else 0
    live_risk = abs(price - s["sl"])
    live_rr = (abs(target - price) / live_risk) if live_risk and ((target > price) if buy else (target < price)) else 0
    beyond_sl = (price <= s["sl"]) if buy else (price >= s["sl"])
    checks.append(_check("liveRr", "R:R still valid from the live price", not beyond_sl and live_rr >= MIN_LIVE_RR * planned,
                         f"1:{live_rr:.2f} now vs 1:{planned:.2f} planned"))

    checks.append(_check("market", "Market open, no news window", r["market"]["isOpen"] and not r["news"]["blocked"],
                         r["news"]["detail"] if r["news"]["blocked"] else ("Open" if r["market"]["isOpen"] else "Market closed")))

    if db is not None:
        mine = legs(r["spec"]["displaySymbol"], s["direction"])
        expo: dict[str, int] = {}
        for o in db.scalars(select(Signal).where(Signal.state.in_(OPEN_STATES), Signal.id != s["id"])):
            for ccy, sign in legs(o.symbol, o.direction).items():
                expo[ccy] = expo.get(ccy, 0) + sign
        crowded = [ccy for ccy, sign in mine.items() if expo.get(ccy, 0) * sign >= MAX_SAME_SIDE]
        checks.append(_check("exposure", f"At most {MAX_SAME_SIDE} open signals on the same side of a currency", not crowded,
                             f"Already {', '.join(f'{c} ×{abs(expo[c])}' for c in crowded)} the same way" if crowded
                             else "Exposure OK" + (f" ({', '.join(f'{c} {expo[c]:+d}' for c in expo if expo[c])})" if any(expo.values()) else "")))

    passed = sum(c["passed"] for c in checks)
    return {"approved": all(c["passed"] for c in checks), "score": round(100 * passed / len(checks)), "checks": checks,
            "issues": [f"{c['label']}: {c['detail']}" for c in checks if not c["passed"]], "validator": v}
