"""
Global Risk & Execution Manager: the wrapper over the three pair agents, checked before any order leaves the app.

1. Dynamic lot: every order is sized for 1 % of the account (lot = balance × 1 % / (SL distance × contract size)),
   never a fixed lot (strategies/shared/risk.py, the lot table of each signal).
2. Spread guard: no entry above 1.5 pips on EUR/USD, 2.2 on GBP/USD, 3.0 on AUD/CHF (the agent's checklist).
3. USD correlation: EUR/USD and GBP/USD move together against the dollar. While one of them has an order that has not
   reached break-even (PENDING or OPEN), a new order on the other one in the same dollar direction is refused, so the
   USD exposure stays at 1 % (the first order already carries the full 1 %).
4. News: no new trade 30 min before / after a red event of the pair's currencies; pending limits are deleted 15 min before
   (the engine cuts the order's expiry there).
5. Daily circuit breaker: two trades per pair a day (the agent), and once the closed trades of the day add up to −2.5 %
   of the account every agent is locked until 00:00 (London) the next day.
"""

import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal
from ..strategies.engines.primitives import LONDON, london
from ..strategies.shared.sessions import zoned_to_utc
from .trade_desk import legs

RISK_PCT = 1.0
DAILY_LOCK_PCT = -2.5
USD_PAIRS = ("EURUSD", "GBPUSD")
NOT_SAFE_YET = ("PENDING", "OPEN")  # TP1_HIT = the stop is at break-even: no more risk on the dollar


def _check(label: str, passed: bool, detail: str) -> dict:
    return {"label": label, "passed": bool(passed), "detail": detail}


def day_start(now: int) -> int:
    d = london(now)[0]
    y, m, dd = (int(x) for x in d.split("-"))
    return zoned_to_utc(y, m, dd, 0, 0, LONDON)


def usd_check(r: dict, db: Session) -> Optional[dict]:
    sym = r["spec"]["symbol"]
    if sym not in USD_PAIRS:
        return None
    s = r["setup"]
    mine = legs(r["spec"]["displaySymbol"], s["direction"])["USD"]
    clash = []
    for o in db.scalars(select(Signal).where(Signal.state.in_(NOT_SAFE_YET), Signal.id != s["id"])):
        osym = o.symbol.replace("/", "")
        if osym in USD_PAIRS and osym != sym and legs(o.symbol if "/" in o.symbol else f"{o.symbol[:3]}/{o.symbol[3:]}", o.direction)["USD"] == mine:
            clash.append(f"{o.symbol} {o.direction} ({o.state})")
    side = "long" if mine > 0 else "short"
    return _check("USD exposure ≤ 1 %", not clash,
                  f"Already {side} USD without break-even: {', '.join(clash)}" if clash else f"No other open {side}-USD order at risk")


def daily_loss_check(db: Session, now: Optional[int] = None) -> dict:
    now = now or int(time.time())
    start = day_start(now)
    rs = db.scalars(select(Signal.r_multiple).where(Signal.exit_time.is_not(None), Signal.exit_time >= start, Signal.r_multiple.is_not(None))).all()
    pct = sum(rs) * RISK_PCT
    return _check(f"Daily circuit breaker (−{abs(DAILY_LOCK_PCT):g} %)", pct > DAILY_LOCK_PCT,
                  f"Today {pct:+.2f} % on {len(rs)} closed trade(s)" + (": LOCK_UNTIL_NEXT_DAY (00:00 London)" if pct <= DAILY_LOCK_PCT else ""))


def global_risk_checks(r: dict, db: Session, now: Optional[int] = None) -> list[dict]:
    out = []
    s = r.get("setup")
    if not s:
        return out
    lots = s.get("lots") or {}
    out.append(_check("Lot sized for 1 % risk", bool(lots) and any(v > 0 for v in lots.values()),
                      " · ".join(f"{k} → {v:g} lot" for k, v in lots.items()) or "no lot table"))
    u = usd_check(r, db)
    if u:
        out.append(u)
    out.append(daily_loss_check(db, now))
    return out
