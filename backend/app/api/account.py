"""Login, user accounts (admin), each user's trades with the lot they took, history, statistics and daily loss limit."""

import secrets
import time
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import admin_user, bearer, current_user, hash_code, login, logout, user_json
from ..db import get_db
from ..models import Signal, Subscriber, Trade, User
from ..strategies.service import normalize_symbol
from ..store import get_setting
from ..telegram import bot as tg
from ..trading import close_trade, effective_risk, lot_for_risk, signal_json, stats, today_status, trade_json

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


# ---------------------------------------------------------------- profile (daily loss limit)

class ProfileIn(BaseModel):
    dailyLossLimit: Optional[float] = Field(None, ge=0)  # $; 0 = no limit
    riskUsd: Optional[float] = Field(None, ge=0)  # $ per signal (fixed); 0 = use the % of the capital instead
    capital: Optional[float] = Field(None, ge=0)  # $ account size; 0 = not set
    riskPct: Optional[float] = Field(None, ge=0, le=100)  # % of the capital per trade (used when no fixed $ risk)
    telegramChatId: Optional[str] = None
    accessCode: Optional[str] = Field(None, min_length=6)


def _user_trades(db: Session, user_id: int) -> list[Trade]:
    return db.scalars(select(Trade).where(Trade.user_id == user_id).order_by(Trade.opened_at.desc())).all()


def _stats_with_today(trades: list[Trade], u: User) -> dict:
    return {**stats(trades, "trade"), "today": today_status(trades, u.daily_loss_limit)}


@router.get("/me")
def me(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"user": user_json(u), "stats": _stats_with_today(_user_trades(db, u.id), u)}


@router.put("/me")
def me_update(body: ProfileIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.dailyLossLimit is not None:
        u.daily_loss_limit = body.dailyLossLimit or None
    if body.telegramChatId is not None:
        u.telegram_chat_id = body.telegramChatId.strip() or None
    if body.riskUsd is not None:
        u.risk_usd = body.riskUsd or None
    if body.capital is not None:
        u.capital = body.capital
    if body.riskPct is not None:
        u.risk_pct = body.riskPct or 1
    sub = db.get(Subscriber, u.telegram_chat_id) if u.telegram_chat_id else None
    if sub:  # one risk for the app and the Telegram bot
        if body.riskUsd is not None or body.capital is not None or body.riskPct is not None:
            sub.risk_usd, sub.capital, sub.risk_pct = u.risk_usd, u.capital or 0, u.risk_pct
        elif u.risk_usd is None and not u.capital:
            u.risk_usd = sub.risk_usd  # linking keeps the risk already set with /risk
    if body.accessCode:
        u.access_code_hash = hash_code(body.accessCode)
    db.commit()
    return {"success": True, "user": user_json(u)}


@router.get("/lot")
def lot(symbol: str, entry: float, sl: float, riskUsd: Optional[float] = None, u: User = Depends(current_user)):
    """The lot for my risk ($, or % of my capital) with the signal's own stop."""
    risk = riskUsd if riskUsd is not None else (effective_risk(u.risk_usd, u.capital, u.risk_pct) or 0)
    return {"success": True, "symbol": normalize_symbol(symbol), **lot_for_risk(symbol, entry, sl, risk)}


LINK_TTL = 15 * 60  # code the user makes for themself
ADMIN_LINK_TTL = 24 * 3600  # code the admin makes and sends to the user
_LINK_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


async def _new_link_code(u: User, db: Session, ttl: int) -> dict:
    """A one-time code the user sends to the bot: the bot then links that Telegram chat to this account."""
    code = "LD-" + "".join(secrets.choice(_LINK_ALPHABET) for _ in range(6))
    u.telegram_link_code, u.telegram_link_expires = code, int(time.time()) + ttl
    db.commit()
    cfg = get_setting(db, "telegram")
    info = await tg.bot_info(cfg["botToken"]) if cfg.get("botToken") else {"success": False}
    name = info.get("username") if info.get("success") else None
    return {"success": True, "code": code, "expiresAt": u.telegram_link_expires, "bot": name,
            "deepLink": f"https://t.me/{name}?start={code.replace('-', '')}" if name else None, "user": user_json(u)}


@router.post("/me/telegram-link")
async def telegram_link_code(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return await _new_link_code(u, db, LINK_TTL)


@router.post("/users/{user_id}/telegram-link")
async def admin_telegram_link_code(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    """The admin makes the code for a user; whichever Telegram account sends it to the bot becomes that user's chat."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return await _new_link_code(u, db, ADMIN_LINK_TTL)


@router.delete("/users/{user_id}/telegram-link")
def admin_telegram_unlink(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.telegram_chat_id, u.telegram_link_code, u.telegram_link_expires = None, None, None
    db.commit()
    return {"success": True, "user": user_json(u)}


@router.delete("/me/telegram-link")
def telegram_unlink(u: User = Depends(current_user), db: Session = Depends(get_db)):
    u.telegram_chat_id, u.telegram_link_code, u.telegram_link_expires = None, None, None
    db.commit()
    return {"success": True, "user": user_json(u)}


# ---------------------------------------------------------------- users (admin: accounts only)

class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    accessCode: str = Field(min_length=6)
    role: Literal["admin", "user"] = "user"


class UserPatch(BaseModel):
    role: Optional[Literal["admin", "user"]] = None
    active: Optional[bool] = None
    accessCode: Optional[str] = Field(None, min_length=6)


@router.get("/users")
def users_list(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    out = []
    for u in db.scalars(select(User).order_by(User.id)):
        trades = _user_trades(db, u.id)
        s = stats(trades, "trade")
        out.append({**user_json(u), "stats": {k: s[k] for k in ("total", "open", "closed", "wins", "losses", "winRate", "totalPnl", "totalLots")},
                    "today": today_status(trades, u.daily_loss_limit)})
    return {"users": out}


@router.get("/users/stats")
def users_stats(db: Session = Depends(get_db)):
    """Aggregate of every user's trades (no personal details)."""
    s = stats(db.scalars(select(Trade)).all(), "trade")
    s.pop("pnlCurve", None)
    return {"success": True, "users": db.query(User).count(), "stats": s}


@router.get("/users/{user_id}")
def users_detail(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    """One user's statistics and full trade history (admin)."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    trades = _user_trades(db, u.id)
    return {"user": user_json(u), "stats": _stats_with_today(trades, u), "trades": [trade_json(t) for t in trades]}


@router.post("/users")
def users_create(body: UserIn, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    name = body.username.strip().lower()
    if db.scalar(select(User.id).where(User.username == name)):
        raise HTTPException(409, "Username already exists")
    u = User(username=name, access_code_hash=hash_code(body.accessCode), role=body.role)
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
    if body.role is not None:
        u.role = body.role
    if body.active is not None:
        u.active = body.active
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


# ---------------------------------------------------------------- trades (each with the lot the user took)

class TradeIn(BaseModel):
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry: float = Field(gt=0)
    sl: float = Field(gt=0)
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    lots: float = Field(gt=0, le=100)
    signalId: Optional[str] = None
    notes: str = ""


class TradeClose(BaseModel):
    exitPrice: float = Field(gt=0)


class TradePatch(BaseModel):
    sl: Optional[float] = Field(None, gt=0)
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    lots: Optional[float] = Field(None, gt=0, le=100)
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
    today = today_status(_user_trades(db, u.id), u.daily_loss_limit)
    if today["reached"]:
        raise HTTPException(403, f"Daily loss limit reached ({today['pnl']}$ / -{today['limit']}$): no new trades until the next trading day")
    sig = db.get(Signal, body.signalId.removeprefix("sig-")) if body.signalId else None
    t = Trade(user_id=u.id, signal_id=sig.id if sig else None, symbol=sym, direction=body.direction, entry=body.entry, sl=body.sl,
              tp1=body.tp1, tp2=body.tp2, tp3=body.tp3, lots=body.lots, source="app", notes=body.notes)
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
    t.notes = (t.notes + "\n" if t.notes else "") + f"SL moved to breakeven {t.entry} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)"
    db.commit()
    return {"success": True, "trade": trade_json(t)}


@router.delete("/trades/{trade_id}")
def trades_delete(trade_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_trade(db, u, trade_id))
    db.commit()
    return {"success": True}


@router.get("/stats")
def my_stats(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return _stats_with_today(_user_trades(db, u.id), u)


# ---------------------------------------------------------------- strategy signal performance (public)

@router.get("/signals/performance")
def signals_performance(db: Session = Depends(get_db)):
    rows = db.scalars(select(Signal).order_by(Signal.sent_at.desc())).all()
    return {"success": True, "stats": stats(rows, "signal"), "signals": [signal_json(s) for s in rows[:100]],
            "activeTrades": [signal_json(s) for s in rows if s.state in ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")]}
