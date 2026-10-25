"""Login, users (admin), the user's own profile/capital, trades taken, history and statistics."""

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import admin_user, bearer, current_user, hash_code, login, logout, user_json
from ..db import get_db
from ..models import Signal, Trade, User
from ..strategies.service import normalize_symbol
from ..trading import close_trade, lot_for, signal_json, stats, trade_json

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- auth

class LoginIn(BaseModel):
    username: str
    accessCode: str


@router.post("/auth/login")
def auth_login(body: LoginIn, db: Session = Depends(get_db)):
    out = login(db, body.username, body.accessCode)
    if not out:
        raise HTTPException(401, "Wrong username or access code")
    return {"success": True, **out}


@router.get("/auth/me")
def auth_me(u: User = Depends(current_user)):
    return {"authenticated": True, "user": user_json(u)}


@router.post("/auth/logout")
def auth_logout(token: str = Depends(bearer), db: Session = Depends(get_db)):
    if token:
        logout(db, token)
    return {"success": True}


# ---------------------------------------------------------------- profile (capital / risk)

class ProfileIn(BaseModel):
    capital: Optional[float] = Field(None, gt=0)
    riskPct: Optional[float] = Field(None, gt=0, le=10)
    telegramChatId: Optional[str] = None
    accessCode: Optional[str] = Field(None, min_length=6)


@router.get("/me")
def me(u: User = Depends(current_user), db: Session = Depends(get_db)):
    trades = db.scalars(select(Trade).where(Trade.user_id == u.id)).all()
    return {"user": user_json(u), "stats": stats(trades, "trade", u.capital)}


@router.put("/me")
def me_update(body: ProfileIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.capital is not None:
        u.capital = body.capital
    if body.riskPct is not None:
        u.risk_pct = body.riskPct
    if body.telegramChatId is not None:
        u.telegram_chat_id = body.telegramChatId.strip() or None
    if body.accessCode:
        u.access_code_hash = hash_code(body.accessCode)
    db.commit()
    return {"success": True, "user": user_json(u)}


# ---------------------------------------------------------------- users (admin)

class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    accessCode: str = Field(min_length=6)
    role: Literal["admin", "user"] = "user"
    capital: float = Field(1000, gt=0)
    riskPct: float = Field(1, gt=0, le=10)


class UserPatch(BaseModel):
    role: Optional[Literal["admin", "user"]] = None
    active: Optional[bool] = None
    capital: Optional[float] = Field(None, gt=0)
    riskPct: Optional[float] = Field(None, gt=0, le=10)
    accessCode: Optional[str] = Field(None, min_length=6)


@router.get("/users")
def users_list(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    out = []
    for u in db.scalars(select(User).order_by(User.id)):
        s = stats(db.scalars(select(Trade).where(Trade.user_id == u.id)).all(), "trade", u.capital)
        out.append({**user_json(u), "stats": {k: s[k] for k in ("total", "open", "closed", "wins", "losses", "winRate", "totalPnl", "currentCapital")}})
    return {"users": out}


@router.post("/users")
def users_create(body: UserIn, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    name = body.username.strip().lower()
    if db.scalar(select(User.id).where(User.username == name)):
        raise HTTPException(409, "Username already exists")
    u = User(username=name, access_code_hash=hash_code(body.accessCode), role=body.role, capital=body.capital, risk_pct=body.riskPct)
    db.add(u)
    db.commit()
    return {"success": True, "user": user_json(u)}


@router.patch("/users/{user_id}")
def users_update(user_id: int, body: UserPatch, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (body.active is False or body.role == "user"):
        raise HTTPException(400, "You cannot disable or demote yourself")
    for field, attr in (("role", "role"), ("active", "active"), ("capital", "capital"), ("riskPct", "risk_pct")):
        v = getattr(body, field)
        if v is not None:
            setattr(u, attr, v)
    if body.accessCode:
        u.access_code_hash = hash_code(body.accessCode)
    db.commit()
    return {"success": True, "user": user_json(u)}


@router.delete("/users/{user_id}")
def users_delete(user_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete yourself")
    db.delete(u)
    db.commit()
    return {"success": True}


# ---------------------------------------------------------------- trades

class TradeIn(BaseModel):
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry: float = Field(gt=0)
    sl: float = Field(gt=0)
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    lots: Optional[float] = Field(None, gt=0)
    signalId: Optional[str] = None
    notes: str = ""


class TradeClose(BaseModel):
    exitPrice: float = Field(gt=0)


class TradePatch(BaseModel):
    sl: Optional[float] = Field(None, gt=0)
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    lots: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None


def _own_trade(db: Session, u: User, trade_id: int) -> Trade:
    t = db.get(Trade, trade_id)
    if not t or (t.user_id != u.id and u.role != "admin"):
        raise HTTPException(404, "Trade not found")
    return t


@router.get("/trades")
def trades_list(status: Optional[str] = None, symbol: Optional[str] = None, all_users: bool = False,
                u: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Trade).order_by(Trade.opened_at.desc())
    if not (all_users and u.role == "admin"):
        q = q.where(Trade.user_id == u.id)
    if status:
        q = q.where(Trade.status == status.upper())
    if symbol:
        q = q.where(Trade.symbol == normalize_symbol(symbol))
    rows = db.scalars(q).all()
    return {"trades": [trade_json(t) for t in rows], "count": len(rows)}


@router.post("/trades")
def trades_create(body: TradeIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    sym = normalize_symbol(body.symbol)
    if (body.direction == "BUY") != (body.sl < body.entry):
        raise HTTPException(400, "Stop loss must be below entry for a BUY and above entry for a SELL")
    lots = body.lots or lot_for(sym, u.capital, u.risk_pct, body.entry, body.sl) or 0.01
    sig = db.get(Signal, body.signalId.removeprefix("sig-")) if body.signalId else None
    t = Trade(user_id=u.id, signal_id=sig.id if sig else None, symbol=sym, direction=body.direction, entry=body.entry, sl=body.sl,
              tp1=body.tp1, tp2=body.tp2, tp3=body.tp3, lots=lots, capital=u.capital, risk_pct=u.risk_pct, source="app", notes=body.notes)
    db.add(t)
    db.commit()
    return {"success": True, "trade": trade_json(t)}


@router.patch("/trades/{trade_id}")
def trades_update(trade_id: int, body: TradePatch, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_trade(db, u, trade_id)
    for field in ("sl", "tp1", "tp2", "tp3", "lots", "notes"):
        v = getattr(body, field)
        if v is not None:
            setattr(t, field, v)
    db.commit()
    return {"success": True, "trade": trade_json(t)}


@router.post("/trades/{trade_id}/close")
def trades_close(trade_id: int, body: TradeClose, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_trade(db, u, trade_id)
    if t.status != "OPEN":
        raise HTTPException(400, "Trade is already closed")
    close_trade(t, body.exitPrice)
    db.commit()
    return {"success": True, "trade": trade_json(t)}


@router.post("/trades/{trade_id}/breakeven")
def trades_breakeven(trade_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_trade(db, u, trade_id)
    if t.status != "OPEN":
        raise HTTPException(400, "Trade is closed")
    t.breakeven = True
    t.notes = (t.notes + "\n" if t.notes else "") + f"SL moved to breakeven {t.entry} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC), risk recorded on the original stop"
    db.commit()
    return {"success": True, "trade": trade_json(t)}


@router.delete("/trades/{trade_id}")
def trades_delete(trade_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_trade(db, u, trade_id))
    db.commit()
    return {"success": True}


@router.get("/stats")
def my_stats(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return stats(db.scalars(select(Trade).where(Trade.user_id == u.id)).all(), "trade", u.capital)


# ---------------------------------------------------------------- strategy signal performance (public)

@router.get("/signals/performance")
def signals_performance(db: Session = Depends(get_db)):
    rows = db.scalars(select(Signal).order_by(Signal.sent_at.desc())).all()
    return {"success": True, "stats": stats(rows, "signal"), "signals": [signal_json(s) for s in rows[:100]],
            "activeTrades": [signal_json(s) for s in rows if s.state in ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")]}


@router.get("/users/stats")
def users_stats(db: Session = Depends(get_db)):
    """Aggregate of every user's trades (no personal details)."""
    trades = db.scalars(select(Trade)).all()
    s = stats(trades, "trade", 0)
    s.pop("equityCurve", None)
    return {"success": True, "users": db.query(User).count(), "stats": s}
