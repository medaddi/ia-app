"""
Multi-Agent Risk Coordinator: every order of the 4 pair agents passes here before it leaves the app.

1. Base risk: 1.0 % of the equity per trade (the lot table of the signal is sized for it).
2. Correlated USD exposure (max 1.5 % unhedged): EURUSD, GBPUSD and XAUUSD all quote against the dollar. Count the
   agents of that group with an open trade (IN_TRADE) in the SAME dollar direction whose stop is not yet at
   break-even:  0 → full 1.0 % · 1 → the new trade at 0.5 % · 2 → the third correlated trade is BLOCKED until one of
   them reaches TP1 / break-even.
3. News blackout: no new entry and no pending limit from 30 min before to 30 min after a red event of the pair's
   currencies (USD, EUR, GBP, AUD, CHF; gold: USD — CPI, NFP, FOMC, Powell, PMI ...). The agents cut the expiry of their
   limits at news − 30 min, so a pending order is gone before it.
4. Spread guard (INSTRUMENT_CONFIG.max_spread_pips), live data, a limit still valid / a market entry not chased.
5. Day guard: at most 2 trades per pair a day, and the whole desk locked until 00:00 (UTC+1) once the day's closed
   trades reach −2.5 %. At most 4 orders open across the desk.
"""

import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal
from .instrument_specs import INSTRUMENT_CONFIG, USD_PAIRS, key, usd_direction
from .quant_primitives import day_start

BASE_RISK_PCT = 1.0
REDUCED_RISK_PCT = 0.5
DAILY_LOCK_PCT = -2.5
MAX_OPEN = 4
MAX_DRIFT_R = 0.35
OPEN_STATES = ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")
UNPROTECTED = ("OPEN",)  # IN_TRADE with the stop not yet at break-even (TP1_HIT = stop moved)


def _check(key_: str, label: str, passed: bool, detail: str) -> dict:
    return {"key": key_, "label": label, "passed": bool(passed), "detail": detail}


def usd_exposure(symbol: str, direction: str, db: Optional[Session], exclude_id: str = "") -> dict:
    """{"riskPct", "blocked", "count", "with"}: the risk the new trade may take given the open USD trades."""
    me = usd_direction(symbol, direction)
    if not me or db is None:
        return {"riskPct": BASE_RISK_PCT, "blocked": False, "count": 0, "with": []}
    same = []
    for o in db.scalars(select(Signal).where(Signal.state.in_(UNPROTECTED), Signal.id != exclude_id)):
        if key(o.symbol) in USD_PAIRS and key(o.symbol) != key(symbol) and usd_direction(o.symbol, o.direction) == me:
            same.append(f"{o.symbol} {o.direction}")
    n = len(same)
    return {"riskPct": BASE_RISK_PCT if n == 0 else REDUCED_RISK_PCT, "blocked": n >= 2, "count": n, "with": same}


def daily_pct(db: Session, now: int) -> tuple[float, int]:
    rs = db.scalars(select(Signal.r_multiple).where(Signal.exit_time.is_not(None), Signal.exit_time >= day_start(now),
                                                    Signal.r_multiple.is_not(None))).all()
    return sum(rs) * BASE_RISK_PCT, len(rs)


def _scale_lots(lots: dict, factor: float) -> dict:
    return {k: (round(int(v * factor / 0.01 + 1e-9) * 0.01, 2) if v else v) for k, v in (lots or {}).items()}


def coordinate(r: dict, db: Optional[Session] = None, now: Optional[int] = None) -> dict:
    """The decision on the pair agent's order: the agent's own vote, then the coordinator's. Same shape the Telegram /
    push senders read: {"approved", "agreed", "agents", "summary", "issues", "riskPct", "lots"}."""
    now = now or int(time.time())
    s = r.get("setup")
    sym = r["spec"]["displaySymbol"]
    ov = r.get("overlay") or {}
    agent_vote = {"key": "agent", "name": ov.get("agentId") or "Pair agent", "agree": bool(s and r["status"] == "SIGNAL" and r.get("canNotify")),
                  "summary": ov.get("statusBannerText") or r.get("headline", ""), "fsmState": ov.get("fsmState"),
                  "checks": [{"label": c["rule"], "passed": c["passed"], "detail": c["detail"]} for c in r.get("checklist", [])]}
    if not s:
        risk_vote = {"key": "risk", "name": "Risk coordinator", "agree": False, "summary": "Nothing to execute", "checks": []}
        return {"approved": False, "agreed": 0, "agents": [agent_vote, risk_vote], "summary": "No order", "issues": [], "riskPct": BASE_RISK_PCT,
                "lots": {}}

    from ..agent.validator import validate_signal

    d = r["spec"]["decimals"]
    f = lambda v: f"{v:.{d}f}"  # noqa: E731
    checks = []
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
        expired = bool(s.get("expiresAt")) and s["expiresAt"] <= now
        checks.append(_check("limit", "Limit order still valid", not beyond_sl and not passed and not expired and s["lifecycle"]["state"] in ("PENDING", "OPEN"),
                             f"live {f(price)} · limit {f(s['entry'])} · SL {f(s['sl'])} · cancel at {f(lvl)}"))
    else:
        drift = ((price - s["entry"]) / risk if risk else 0) * (1 if buy else -1)
        checks.append(_check("drift", f"Price within {MAX_DRIFT_R}R of the entry", abs(drift) <= MAX_DRIFT_R and not beyond_sl,
                             f"live {f(price)} vs entry {f(s['entry'])} ({drift:+.2f}R)"))
    checks.append(_check("market", "Market open, no news blackout (±30 min)", r["market"]["isOpen"] and not r["news"]["blocked"],
                         r["news"]["detail"] if r["news"]["blocked"] else ("Open" if r["market"]["isOpen"] else "Market closed")))
    spec = INSTRUMENT_CONFIG.get(key(sym))
    if spec:
        sp = (r.get("facts") or {}).get("spread")
        sp_pips = (sp or 0) / spec["pip_size"]
        checks.append(_check("spread", f"Spread ≤ {spec['max_spread_pips']:g} pips", sp_pips <= spec["max_spread_pips"] + 1e-9, f"{sp_pips:.1f} pips"))

    expo = usd_exposure(sym, s["direction"], db, s["id"])
    if key(sym) in USD_PAIRS:
        side = "short" if usd_direction(sym, s["direction"]) < 0 else "long"
        checks.append(_check("usd", "Correlated USD exposure ≤ 1.5 %", not expo["blocked"],
                             (f"{expo['count']} {side}-USD trade(s) not at break-even ({', '.join(expo['with'])}): " +
                              ("BLOCKED until one reaches TP1 / BE" if expo["blocked"] else f"this one at {expo['riskPct']:g} %"))
                             if expo["count"] else f"no other {side}-USD trade at risk: {BASE_RISK_PCT:g} %"))
    if db is not None:
        n = len(db.scalars(select(Signal.id).where(Signal.state.in_(OPEN_STATES), Signal.id != s["id"])).all())
        checks.append(_check("book", f"At most {MAX_OPEN} orders open on the desk", n < MAX_OPEN, f"{n} open"))
        pct, k = daily_pct(db, now)
        checks.append(_check("daily", f"Daily circuit breaker ({DAILY_LOCK_PCT:g} %)", pct > DAILY_LOCK_PCT,
                             f"today {pct:+.2f} % on {k} closed trade(s)" + (" · LOCK_UNTIL_NEXT_DAY 00:00 UTC+1" if pct <= DAILY_LOCK_PCT else "")))
    day = r.get("day") or {}
    checks.append(_check("pairday", "At most 2 trades on this pair today", day.get("trades", 0) < 2, f"{day.get('trades', 0)} today"))

    agree = all(c["passed"] for c in checks)
    risk_pct = expo["riskPct"]
    lots = _scale_lots(s.get("lots") or {}, risk_pct / BASE_RISK_PCT)
    risk_vote = {"key": "risk", "name": "Risk coordinator", "agree": agree, "riskPct": risk_pct, "lots": lots, "checks": checks,
                 "summary": (f"Order approved at {risk_pct:g} % risk" if agree else "Blocked: " + "; ".join(c["label"] for c in checks if not c["passed"]))}
    agents = [agent_vote, risk_vote]
    agreed = sum(a["agree"] for a in agents)
    approved = agreed == 2
    return {"approved": approved, "agreed": agreed, "agents": agents, "riskPct": risk_pct, "lots": lots,
            "summary": f"Agent + coordinator agree: order sent at {risk_pct:g} %" if approved else f"{agreed}/2: no order",
            "issues": [f"{a['name']}: {a['summary']}" for a in agents if not a["agree"]]}
