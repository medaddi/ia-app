"""
Risk notes for the 4 pair agents. Nothing here blocks an order: every setup an agent sees is sent, and each trader
controls their own risk (their $ or % per trade on their account and on Telegram).

What the trader is told with each order (notes, not vetoes):
- the rules re-checked and live, fresh data (a technical sanity check of the agent's own numbers)
- whether the limit is still valid / how far a market entry drifted
- red news of the pair's currencies within ±30 min, the spread
- correlated USD exposure: EURUSD, GBPUSD and XAUUSD all quote against the dollar; the other same-direction USD trades
  still open (stop not at break-even) are listed, so the trader can size down if they want
- the orders open on the desk and today's result
The lot table of every signal is for 1 % of the balance; each trader's own risk replaces it on Telegram.
"""

import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal
from .instrument_specs import INSTRUMENT_CONFIG, USD_PAIRS, key, usd_direction
from .quant_primitives import day_start

BASE_RISK_PCT = 1.0
MAX_DRIFT_R = 0.35
OPEN_STATES = ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")
UNPROTECTED = ("OPEN",)  # IN_TRADE with the stop not yet at break-even (TP1_HIT = stop moved)


def _check(key_: str, label: str, passed: bool, detail: str) -> dict:
    return {"key": key_, "label": label, "passed": bool(passed), "detail": detail}


def usd_exposure(symbol: str, direction: str, db: Optional[Session], exclude_id: str = "") -> dict:
    """{"count", "with"}: the other open same-direction USD trades not yet at break-even (information only)."""
    me = usd_direction(symbol, direction)
    if not me or db is None:
        return {"count": 0, "with": []}
    same = []
    for o in db.scalars(select(Signal).where(Signal.state.in_(UNPROTECTED), Signal.id != exclude_id)):
        if key(o.symbol) in USD_PAIRS and key(o.symbol) != key(symbol) and usd_direction(o.symbol, o.direction) == me:
            same.append(f"{o.symbol} {o.direction}")
    return {"count": len(same), "with": same}


def daily_pct(db: Session, now: int) -> tuple[float, int]:
    rs = db.scalars(select(Signal.r_multiple).where(Signal.exit_time.is_not(None), Signal.exit_time >= day_start(now),
                                                    Signal.r_multiple.is_not(None))).all()
    return sum(rs) * BASE_RISK_PCT, len(rs)


def coordinate(r: dict, db: Optional[Session] = None, now: Optional[int] = None) -> dict:
    """The agent's order and the risk notes that go with it. `approved` follows the agent alone: a fresh, valid setup
    is always sent. Same shape the Telegram / push senders read: {"approved", "agreed", "agents", "summary", "issues", "notes"}."""
    now = now or int(time.time())
    s = r.get("setup")
    sym = r["spec"]["displaySymbol"]
    ov = r.get("overlay") or {}
    agree = bool(s and r["status"] == "SIGNAL" and s["lifecycle"]["state"] in ("PENDING", "OPEN"))  # the candle-close send also needs canNotify
    agent_vote = {"key": "agent", "name": ov.get("agentId") or "Pair agent", "agree": agree, "summary": ov.get("statusBannerText") or r.get("headline", ""),
                  "fsmState": ov.get("fsmState"), "checks": [{"label": c["rule"], "passed": c["passed"], "detail": c["detail"]} for c in r.get("checklist", [])]}
    if not s:
        notes_vote = {"key": "risk", "name": "Risk notes", "agree": True, "summary": "No order", "checks": []}
        return {"approved": False, "agreed": 0, "agents": [agent_vote, notes_vote], "summary": "No order", "issues": [], "notes": [], "riskPct": BASE_RISK_PCT}

    d = r["spec"]["decimals"]
    f = lambda v: f"{v:.{d}f}"  # noqa: E731
    checks = []
    from ..agent.validator import validate_signal

    v = validate_signal(r)
    checks.append(_check("rules", "Agent rules re-checked", v["approved"], "All rules pass" if v["approved"] else "; ".join(v["issues"])))
    dq = r["dataQuality"]
    checks.append(_check("data", "Live, fresh data", dq["ok"] and not dq.get("stale"), dq.get("reason", "")))
    price = r.get("price") or s["entry"]
    buy = s["direction"] == "BUY"
    risk = abs(s["entry"] - s["sl"])
    beyond_sl = (price <= s["sl"]) if buy else (price >= s["sl"])
    if s["entryType"] == "LIMIT":
        lvl = s["params"].get("cancelLevel") or s["tp3"]
        passed = (price >= lvl) if buy else (price <= lvl)
        checks.append(_check("limit", "Limit order still valid", not beyond_sl and not passed and s["lifecycle"]["state"] in ("PENDING", "OPEN"),
                             f"live {f(price)} · limit {f(s['entry'])} · SL {f(s['sl'])} · cancel at {f(lvl)}"))
    else:
        drift = ((price - s["entry"]) / risk if risk else 0) * (1 if buy else -1)
        checks.append(_check("drift", f"Price within {MAX_DRIFT_R}R of the entry", abs(drift) <= MAX_DRIFT_R and not beyond_sl,
                             f"live {f(price)} vs entry {f(s['entry'])} ({drift:+.2f}R)"))
    checks.append(_check("news", "Red news ±30 min", not r["news"]["blocked"], r["news"]["detail"]))
    spec = INSTRUMENT_CONFIG.get(key(sym))
    if spec:
        sp_pips = ((r.get("facts") or {}).get("spread") or 0) / spec["pip_size"]
        checks.append(_check("spread", f"Spread (usual ≤ {spec['max_spread_pips']:g} pips)", sp_pips <= spec["max_spread_pips"] + 1e-9, f"{sp_pips:.1f} pips"))
    if key(sym) in USD_PAIRS:
        expo = usd_exposure(sym, s["direction"], db, s["id"])
        side = "short" if usd_direction(sym, s["direction"]) < 0 else "long"
        checks.append(_check("usd", "Correlated USD trades", expo["count"] == 0,
                             f"{expo['count']} other {side}-USD trade(s) not at break-even: {', '.join(expo['with'])} (size down if you want)" if expo["count"]
                             else f"no other {side}-USD trade at risk"))
    if db is not None:
        n = len(db.scalars(select(Signal.id).where(Signal.state.in_(OPEN_STATES), Signal.id != s["id"])).all())
        pct, k = daily_pct(db, now)
        checks.append(_check("book", "Orders open on the desk", True, f"{n} open · today {pct:+.2f} % on {k} closed trade(s)"))

    warn = [c for c in checks if not c["passed"]]
    notes_vote = {"key": "risk", "name": "Risk notes", "agree": True, "riskPct": BASE_RISK_PCT, "checks": checks,
                  "summary": ("Sent · your own risk · notes: " + "; ".join(c["label"] for c in warn)) if warn else "Sent · your own risk · no warning"}
    return {"approved": agree, "agreed": int(agree) + 1, "agents": [agent_vote, notes_vote], "riskPct": BASE_RISK_PCT,
            "summary": "Setup sent: the trader sets the risk" if agree else "No fresh setup to send",
            "issues": [] if agree else [f"{agent_vote['name']}: {agent_vote['summary']}"], "notes": [f"{c['label']}: {c['detail']}" for c in warn]}
