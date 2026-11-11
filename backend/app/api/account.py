"""Login, the profile, user accounts (admin), notifications and the Telegram link. No analysis and no trade: they are being rebuilt."""

import time
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import admin_user, bearer, current_user, hash_code, login, logout, password_problems, register, session_user, user_json
from ..db import get_db
from .. import push
from ..models import PushSubscription, Signal, User, UserSignalSize
from ..store import get_setting
from ..telegram import bot as tg

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


class RegisterIn(BaseModel):
    firstName: str = Field(..., max_length=64)
    lastName: str = Field(..., max_length=64)
    username: str = Field(..., max_length=32)
    password: str = Field(..., max_length=128)


_signups: dict[str, list[float]] = {}  # client → recent sign-up times (a few accounts per hour at most)
SIGNUPS_PER_HOUR = 5


@router.post("/auth/register")
def auth_register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    """Self sign-up: the account is created "pending" and logged in; it sees only the waiting page until an admin approves it."""
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    now = time.time()
    recent = [t for t in _signups.get(ip, []) if now - t < 3600]
    if len(recent) >= SIGNUPS_PER_HOUR:
        raise HTTPException(429, "Too many sign-ups from this connection, try again later")
    out = register(db, body.firstName, body.lastName, body.username, body.password)
    _signups[ip] = recent + [now]
    return {"success": True, **out}


@router.get("/auth/password-check")
def auth_password_check(password: str = "", username: str = ""):
    """The rules a password still misses (the sign-up form shows them live; nothing is stored)."""
    return {"missing": password_problems(password, username.strip().lower())}


@router.get("/auth/me")
def auth_me(u: User = Depends(session_user)):
    return {"authenticated": True, "user": user_json(u)}


@router.post("/auth/logout")
def auth_logout(token: str = Depends(bearer), db: Session = Depends(get_db)):  # also for a pending account
    if token:
        logout(db, token)
    return {"success": True}


# ---------------------------------------------------------------- app notifications (Web Push)

class PushKeysIn(BaseModel):
    p256dh: str = Field(..., max_length=200)
    auth: str = Field(..., max_length=100)


class PushSubIn(BaseModel):
    endpoint: str = Field(..., max_length=600, pattern=r"^https://")
    keys: PushKeysIn


@router.get("/push/key")
def push_key(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """The public VAPID key the browser subscribes with."""
    return {"publicKey": push.vapid_keys(db)["publicKey"]}


@router.post("/push/subscribe")
def push_subscribe(body: PushSubIn, request: Request, u: User = Depends(current_user), db: Session = Depends(get_db)):
    push.save_subscription(db, u, body.model_dump(), request.headers.get("user-agent", ""))
    return {"success": True}


@router.post("/push/unsubscribe")
def push_unsubscribe(body: dict = Body(...), _: User = Depends(current_user), db: Session = Depends(get_db)):
    push.remove_subscription(db, str(body.get("endpoint") or ""))
    return {"success": True}


@router.post("/push/test")
async def push_test(u: User = Depends(current_user), db: Session = Depends(get_db)):
    """A test notification to this account's devices: proves the push reaches the phone with the app closed."""
    rows = db.scalars(select(PushSubscription).where(PushSubscription.user_id == u.id)).all()
    n = await push.send_push(db, list(rows), {"title": "LiquidityDissection", "body": "Notifications OK.", "tag": "ld-test", "symbol": ""})
    return {"success": n > 0, "devices": len(rows), "delivered": n}


@router.post("/telegram/test-me")
async def telegram_test_me(u: User = Depends(current_user), db: Session = Depends(get_db)):
    """A test message to this account's linked Telegram chat (the in-app bell's test button)."""
    cfg = get_setting(db, "telegram")
    if not u.telegram_chat_id:
        return {"success": False, "error": "no Telegram chat linked to this account"}
    if not cfg.get("botToken"):
        return {"success": False, "error": "the bot is not configured"}
    out = await tg.send_message(cfg["botToken"], u.telegram_chat_id, "✅ <b>LiquidityDissection</b> · test notification (Set &amp; Forget alerts reach you here).")
    return {"success": bool(out.get("success")), "error": out.get("error")}


# ---------------------------------------------------------------- profile

class ProfileIn(BaseModel):
    accessCode: Optional[str] = Field(None, min_length=6)


@router.get("/me")
def me(u: User = Depends(current_user)):
    return {"user": user_json(u)}


@router.put("/me")
def me_update(body: ProfileIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.accessCode:
        u.access_code_hash = hash_code(body.accessCode)
    db.commit()
    return {"success": True, "user": user_json(u)}


# ---------------------------------------------------------------- my USD risk, my lot sizes, signal import (private)
# Every route below reads and writes ONLY the signed-in user's rows: the user id comes from the session, never from the
# request. No route returns another user's risk, lots or imports; the admin's user list does not include them either.

class RiskIn(BaseModel):
    riskUsd: Optional[float] = None  # None clears it


@router.get("/me/risk")
def my_risk(u: User = Depends(current_user)):
    from ..smc.sizing import valid_risk
    return {"riskUsd": valid_risk(u.risk_usd)}


@router.put("/me/risk")
def my_risk_set(body: RiskIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Saves THIS user's USD risk per trade. It applies to signals sized from now on: a saved size is never rewritten."""
    from ..smc.sizing import valid_risk
    if body.riskUsd is None:
        u.risk_usd = None
    else:
        v = valid_risk(body.riskUsd)
        if v is None:
            raise HTTPException(422, "The risk must be a positive amount in USD (at most 1,000,000)")
        u.risk_usd = v
    db.commit()
    return {"success": True, "riskUsd": valid_risk(u.risk_usd)}


@router.get("/me/sizing/{signal_id}")
async def my_sizing(signal_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """My lot for a signal the app sent: my saved snapshot, or computed now from MY risk and saved."""
    from ..smc.sizing import size_for
    sig = db.get(Signal, signal_id)
    if sig is None or not sig.id.startswith("SMC-") or sig.state == "BLOCKED":
        return {"status": "unavailable", "reason": "this setup has not been sent as a signal yet: its size appears once it is sent", "signalId": signal_id}
    return await size_for(db, u, sig)


@router.get("/me/sizings")
def my_sizings(u: User = Depends(current_user), db: Session = Depends(get_db)):
    """My saved sizes and imports, newest first (mine only)."""
    from ..smc.sizing import snapshot_json
    rows = db.scalars(select(UserSignalSize).where(UserSignalSize.user_id == u.id).order_by(UserSignalSize.created_at.desc()).limit(100)).all()
    return {"items": [snapshot_json(r) for r in rows]}


class ImportIn(BaseModel):
    text: str = Field(..., max_length=4000)


async def _import(body: ImportIn, u: User, db: Session, commit: bool) -> dict:
    from ..smc import signal_copy
    from ..smc.sizing import size_for, compute, conversion, own_snapshot, snapshot_json, valid_risk
    f, errs = signal_copy.parse(body.text)
    if errs:
        return {"success": False, "errors": errs}
    sig, errs = signal_copy.check_against_app(db, f, time.time())
    if errs:
        return {"success": False, "errors": errs, "signal": f}
    preview = {"id": sig.id, "symbol": sig.symbol, "side": sig.direction, "entry": sig.entry, "sl": sig.sl, "tp": sig.tp2, "tf": f["tf"], "time": f["time"]}
    if commit:  # the lot of the SIGNED-IN user, from their own risk (a lot in the pasted text is never read)
        return {"success": True, "signal": preview, "sizing": await size_for(db, u, sig, source="import"), "imported": True}
    row = own_snapshot(db, u.id, sig.id)
    if row:
        return {"success": True, "signal": preview, "sizing": snapshot_json(row), "imported": False}
    from ..smc.desk import BY_SYMBOL
    risk = valid_risk(u.risk_usd)
    sizing = compute(BY_SYMBOL[sig.symbol], sig.entry, sig.sl, risk, await conversion(sig.symbol) if risk is not None else {})
    return {"success": True, "signal": preview, "sizing": {**sizing, "saved": False}, "imported": False}


@router.post("/me/import/preview")
async def my_import_preview(body: ImportIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Parses and checks a pasted signal and shows MY lot for it; saves nothing. No order is placed."""
    return await _import(body, u, db, commit=False)


@router.post("/me/import")
async def my_import(body: ImportIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Imports a pasted signal into MY history with MY lot (saved once). No order is placed."""
    return await _import(body, u, db, commit=True)


@router.get("/telegram/bot")
async def telegram_bot_link(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """The bot to open from the app (Start there gives the invitation link back)."""
    cfg = get_setting(db, "telegram")
    info = await tg.bot_info(cfg["botToken"]) if cfg.get("botToken") else {"success": False}
    name = info.get("username") if info.get("success") else None
    return {"success": bool(name), "bot": name, "link": f"https://t.me/{name}" if name else None}


@router.get("/telegram/connect/{token}")
def telegram_connect_info(token: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Before Accept: which Telegram asks to be linked, and whether this account may take it."""
    out = tg.connect_info(db, token, u)
    if not out["success"]:
        raise HTTPException(400, out["error"])
    return out


@router.post("/telegram/connect")
async def telegram_connect(body: dict = Body(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Accept: that Telegram chat becomes this account's (one Telegram per account)."""
    out = tg.connect_chat(db, str(body.get("token") or ""), u)
    if not out["success"]:
        raise HTTPException(400, out["error"])
    cfg = get_setting(db, "telegram")
    if cfg.get("botToken"):
        await tg.send_message(cfg["botToken"], out["chatId"], out["message"])
    return {"success": True, "user": user_json(u)}


@router.delete("/users/{user_id}/telegram-link")
async def admin_telegram_unlink(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    await _cut_bot(db, u, "🔒 Your Telegram was unlinked from your account. Press Start to link it again.")
    db.commit()
    return {"success": True, "user": user_json(u)}


@router.delete("/me/telegram-link")
async def telegram_unlink(u: User = Depends(current_user), db: Session = Depends(get_db)):
    await _cut_bot(db, u, "🔒 You unlinked this Telegram from your account. Press Start to link it again.")
    db.commit()
    return {"success": True, "user": user_json(u)}


async def _cut_bot(db: Session, u: User, message: Optional[str]) -> None:
    """The account loses its bot: the chat is told once, then forgotten."""
    chat = u.telegram_chat_id
    if not chat:
        return
    tg.unlink_chat(db, chat)
    cfg = get_setting(db, "telegram")
    if message and cfg.get("botToken"):
        await tg.send_message(cfg["botToken"], chat, message)


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
        out.append(user_json(u))
    return {"users": out}


@router.get("/users/{user_id}")
def users_detail(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    """One user's account (admin)."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return {"user": user_json(u)}


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


@router.post("/users/{user_id}/approve")
def users_approve(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Validates a self sign-up: from now on the account sees the whole app."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.status = "approved"
    db.commit()
    return {"success": True, "user": user_json(u)}


@router.delete("/users/{user_id}")
async def users_delete(user_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete yourself")
    await _cut_bot(db, u, "⛔ Your account was removed: the bot stops here.")  # a deleted account takes its bot with it
    db.delete(u)
    db.commit()
    return {"success": True}
