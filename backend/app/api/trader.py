"""
The trader skill on each pair (github.com/Jakeschincariol/trader-skill, MIT), next to the pair's own analysis:

  the pair's setup (the Analyse button's confirmed setup, or its BUY / SELL scenario)
  → budget: the lots that make ITS stop lose your risk % of the balance
  → risk check: PASS or BLOCK against your limits (risk, margin, lots, US dollar exposure, news, market hours, duplicates)
  → ticket: READY only if this exact order passed today; your explicit yes recorded word for word.
Nothing here places an order: you place it yourself at your broker.
"""

import asyncio
import time

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents.registry import AGENT_CONFIGS
from ..auth import current_user
from ..db import get_db
from ..market.data import fetch_live_price, market_session_status
from ..models import TraderFile, User
from ..strategies.service import normalize_symbol
from ..strategies.shared.news import load_news_calendar
from ..trader import budget as B, cot as C, risk as R, tickets as T

router = APIRouter(prefix="/api/trader")

NUM = {"balance": (100, 1e8), "risk_pct": (0.05, 10), "max_lots": (0.01, 100), "leverage": (1, 500), "max_risk_pct": (0.05, 10),
       "max_total_risk_pct": (0.1, 30), "margin_buffer_pct": (5, 100), "max_usd_same_side": (1, 6), "news_minutes": (0, 240),
       "max_orders_per_day": (1, 50)}
INTS = {"max_usd_same_side", "news_minutes", "max_orders_per_day"}


def _get(db: Session, u: User, name: str, default=None):
    row = db.get(TraderFile, (u.id, name))
    return row.data if row else default


def _put(db: Session, u: User, name: str, data) -> None:
    row = db.get(TraderFile, (u.id, name))
    if row:
        row.data = data
    else:
        db.add(TraderFile(user_id=u.id, name=name, data=data))
    db.commit()


def _config(db: Session, u: User) -> dict:
    base = {**B.DEFAULTS, **{k: v for k, v in R.DEFAULTS.items() if k not in B.DEFAULTS}}
    if u.capital:
        base["balance"] = float(u.capital)
    if u.capital and u.risk_pct:
        base["risk_pct"] = float(u.risk_pct)
    return {**base, **(_get(db, u, "config", {}) or {})}


def _pair(symbol: str) -> str:
    sym = normalize_symbol(symbol)
    if sym not in AGENT_CONFIGS:
        raise HTTPException(404, f"{sym} is not traded by the app")
    return sym


@router.get("/cot")
async def cot(fresh: bool = False, _: User = Depends(current_user)):
    """The big players' positioning on every pair (CFTC Commitments of Traders, weekly)."""
    try:
        rows = await C.cot_all(fresh=fresh)
    except Exception as err:
        raise HTTPException(502, f"The CFTC report is unavailable right now ({err.__class__.__name__})")
    return {"success": True, "rows": rows, "reportDate": rows[0]["reportDate"] if rows else None, "caveats": C.CAVEATS}


@router.get("/config")
def config_get(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"success": True, "config": _config(db, u)}


@router.put("/config")
def config_put(body: dict = Body(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    cfg = _get(db, u, "config", {}) or {}
    for k, (lo, hi) in NUM.items():
        if body.get(k) is None:
            continue
        try:
            v = float(body[k])
        except (TypeError, ValueError):
            raise HTTPException(422, f"{k} must be a number")
        if not lo <= v <= hi:
            raise HTTPException(422, f"{k} must be between {lo:g} and {hi:g}")
        cfg[k] = int(v) if k in INTS else v
    if isinstance(body.get("blocked"), list):
        cfg["blocked"] = [str(x).upper() for x in body["blocked"]][:10]
    _put(db, u, "config", cfg)
    return {"success": True, "config": _config(db, u)}


def _setup_of(a: dict, source: str) -> dict:
    """The levels of the pair's confirmed setup, or of one of its scenarios."""
    if source == "pick":
        pk = a.get("pick")
        if not pk:
            raise HTTPException(409, "No confirmed setup on this pair right now: use a scenario instead")
        rows = a["strategies"] if pk["family"] == "plan" else (a.get("smc") or {}).get("strategies") or []
        row = next((r for r in rows if r["id"] == pk["id"]), None)
        st = (row or {}).get("setup")
        if not st:
            raise HTTPException(409, "The confirmed setup is gone (the market moved): analyse again")
        return {"side": st["direction"], "entry": st["entry"], "sl": st["sl"], "tp": st["tp"], "name": row["name"],
                "condition": None, "family": pk["family"]}
    sc = ((a.get("scenarios") or {}).get(source) or {}).get("main")
    if not sc:
        raise HTTPException(409, f"No {source.upper()} scenario on this pair right now")
    return {"side": sc["dir"], "entry": sc["entry"], "sl": sc["sl"], "tp": sc["tp"], "name": sc["name"], "condition": sc["trigger"],
            "family": sc["family"]}


async def _fx() -> dict:
    keys = ["USD/CAD", "USD/CHF", "AUD/USD", "EUR/USD", "GBP/USD"]
    got = await asyncio.gather(*(fetch_live_price(k) for k in keys))
    return {k: p.get("price") for k, p in zip(keys, got)}


def _approved_today(db: Session, u: User) -> list[dict]:
    day = T.today()
    return [r for r in (_get(db, u, "broker", {}) or {}).get("log", []) if r.get("status") == "approved" and str(r.get("at", ""))[:10] == day]


def _ticket(db: Session, u: User, sym: str) -> dict:
    f = _get(db, u, f"order:{sym}")
    if not f:
        return {"ticket": None}
    o = f["order"]
    ready, label = T.status_of(o, f.get("risk"), (_get(db, u, "broker", {}) or {}).get("log", []), T.today())
    rv = next((r for r in (f.get("risk") or {}).get("results", []) if r.get("fingerprint") == R.fingerprint(o)), None)
    return {"ticket": {"order": o, "plain": T.plain(o), "ready": ready, "status": label, "verdict": rv, "source": f.get("source"),
                       "setup": f.get("setup"), "at": f.get("at")}}


@router.post("/ticket")
async def ticket_make(symbol: str, body: dict = Body(default={}), u: User = Depends(current_user), db: Session = Depends(get_db)):
    """The pair's setup (source: pick, buy or sell) sized to your risk and checked: a ticket that waits for your yes."""
    from ..analysis.engine import cached_analysis

    sym = _pair(symbol)
    source = str(body.get("source") or "pick").lower()
    if source not in ("pick", "buy", "sell"):
        raise HTTPException(422, "source must be pick, buy or sell")
    a = await cached_analysis(sym)
    if not a.get("success"):
        raise HTTPException(502, a.get("error") or "No analysis for this pair right now")
    st = _setup_of(a, source)
    cfg = _config(db, u)
    order = B.size_setup(sym, st["side"], st["entry"], st["sl"], st["tp"], cfg, await _fx())
    if not order["lots"]:
        raise HTTPException(422, order.get("why") or "This setup cannot be sized to your risk")
    cot_bias = ((a.get("skill") or {}).get("cot") or {}).get("bias")
    order["crowded"] = bool(((a.get("skill") or {}).get("cot") or {}).get("crowded")) and cot_bias == st["side"]
    cal = await load_news_calendar()
    res = R.check([order], cfg, cal["events"], int(time.time()), market_session_status(sym)["isOpen"], _approved_today(db, u))
    res["date"] = T.today()
    if cot_bias in ("BUY", "SELL") and cot_bias != st["side"]:
        res["results"][0]["warnings"].append(f"the big players (COT) are on the {cot_bias} side: this trade goes against them")
    _put(db, u, f"order:{sym}", {"order": order, "risk": res, "source": source, "setup": st, "at": int(time.time())})
    return {"success": True, **_ticket(db, u, sym)}


@router.get("/ticket")
def ticket_get(symbol: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"success": True, **_ticket(db, u, _pair(symbol))}


def _decide(db: Session, u: User, sym: str, status: str, reply: str) -> dict:
    f = _get(db, u, f"order:{sym}")
    if not f:
        raise HTTPException(404, "No ticket on this pair: make one first")
    o = f["order"]
    ready, label = T.status_of(o, f.get("risk"), (_get(db, u, "broker", {}) or {}).get("log", []), T.today())
    if not ready:
        raise HTTPException(409, label)
    if status == "approved":
        ok, why = T.parse_yes(reply, o, list(AGENT_CONFIGS))
        if not ok:
            raise HTTPException(422, why)
    broker = _get(db, u, "broker", {}) or {"log": []}
    broker.setdefault("log", []).append({"at": T.now_iso(), "status": status, "fingerprint": R.fingerprint(o), "symbol": sym, "side": o["side"],
                                         "lots": o["lots"], "plain": T.plain(o), "reply": reply[:200]})
    broker["log"] = broker["log"][-500:]
    _put(db, u, "broker", broker)
    return {"success": True, **_ticket(db, u, sym)}


@router.post("/ticket/approve")
def ticket_approve(symbol: str, body: dict = Body(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Your explicit yes for this one order (recorded word for word). You then place it yourself at your broker."""
    return _decide(db, u, _pair(symbol), "approved", str(body.get("reply") or ""))


@router.post("/ticket/decline")
def ticket_decline(symbol: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    return _decide(db, u, _pair(symbol), "declined", "no")


@router.get("/log")
def log(u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Today's decisions on every pair."""
    day = T.today()
    return {"success": True, "log": [r for r in (_get(db, u, "broker", {}) or {}).get("log", []) if str(r.get("at", ""))[:10] == day]}
