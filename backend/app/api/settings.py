"""App parameters, Telegram configuration, activation codes, and subscribers."""

import hmac
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import admin_user
from ..config import settings
from ..db import SessionLocal, get_db
from ..models import ActivationKey, Signal, Subscriber, User
from ..store import get_setting, public_telegram, set_setting
from ..strategies.service import STRATEGY_DEFS, normalize_symbol
from ..telegram import bot

router = APIRouter(prefix="/api")


async def _register_webhook(token: str) -> None:
    if not (settings.on_vercel and settings.telegram_webhook_url and settings.telegram_webhook_secret):
        return
    result = await bot.set_webhook(token, settings.telegram_webhook_url, settings.telegram_webhook_secret)
    if not result["success"]:
        raise HTTPException(502, f"Telegram webhook setup failed: {result.get('error') or 'unknown error'}")


@router.get("/settings")
def settings_get(db: Session = Depends(get_db)):
    return {"app": get_setting(db, "app")}


@router.put("/settings")
def settings_put(body: dict = Body(...), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    out = {}
    for key in ("app",):
        if isinstance(body.get(key), dict):
            out[key] = set_setting(db, key, body[key])
    return {"success": True, **settings_get(db), **out}


# ---------------------------------------------------------------- telegram

@router.get("/telegram/config")
def telegram_config(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"success": True, "config": public_telegram(get_setting(db, "telegram")), "subscribers": len(bot.active_subscribers(db)),
            "history": bot.history()}


@router.post("/telegram/config")
async def telegram_config_set(body: dict = Body(...), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    patch = {k: v for k, v in body.items() if k in ("chatId", "enabled", "minConfidence", "assets", "protectContent", "personalOffsets")}
    if body.get("botToken"):  # an empty token field keeps the saved one
        patch["botToken"] = str(body["botToken"]).strip()
    if patch.get("botToken"):
        await _register_webhook(patch["botToken"])
    return {"success": True, "config": public_telegram(set_setting(db, "telegram", patch))}


@router.get("/telegram/bot-info")
async def telegram_bot_info(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return await bot.bot_info(get_setting(db, "telegram")["botToken"])


@router.post("/telegram/switch-bot")
async def telegram_switch_bot(body: dict = Body(...), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    token = str(body.get("botToken") or "").strip()
    info = await bot.bot_info(token)
    if not info["success"]:
        raise HTTPException(400, f"Bot token rejected by Telegram: {info.get('error')}")
    await _register_webhook(token)
    await bot.set_commands(token)
    set_setting(db, "telegram", {"botToken": token, **({"chatId": str(body["chatId"])} if body.get("chatId") else {})})
    return {"success": True, "bot": info}


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
    """Telegram command receiver. Enabled when a webhook secret is configured on Vercel."""
    expected = settings.telegram_webhook_secret
    if not expected or not hmac.compare_digest(x_telegram_bot_api_secret_token or "", expected):
        raise HTTPException(403, "Invalid Telegram webhook secret")
    update = await request.json()
    if not isinstance(update, dict):
        raise HTTPException(400, "Invalid Telegram update")
    with SessionLocal() as db:
        token = get_setting(db, "telegram").get("botToken", "")
    if not token:
        raise HTTPException(503, "Telegram bot is not configured")
    await bot.handle_update(token, update)
    return {"ok": True}


@router.post("/telegram/test")
async def telegram_test(body: dict = Body(default={}), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    cfg = get_setting(db, "telegram")
    chat_id = str(body.get("chatId") or cfg["chatId"])
    out = await bot.send_message(cfg["botToken"], chat_id, f"✅ <b>LiquidityDissection</b> test message · {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    bot.log_event("TEST", "Test message", f"chat {chat_id}", out["success"], out.get("error"))
    return out


@router.post("/telegram/dispatch-now")
async def telegram_dispatch_now(body: dict = Body(default={}), _: User = Depends(admin_user)):
    symbols = [normalize_symbol(body["symbol"])] if body.get("symbol") else list(STRATEGY_DEFS)
    results = {s: await bot.dispatch_setup(s, manual=True) for s in symbols}
    return {"success": any(r["success"] for r in results.values()),
            "results": {s: {k: v for k, v in r.items() if k != "signal"} for s, r in results.items()}}


@router.get("/telegram/latency")
def telegram_latency(db: Session = Depends(get_db)):
    rows = db.scalars(select(Signal).where(Signal.latency_ms.is_not(None)).order_by(Signal.sent_at.desc()).limit(50))
    return {"success": True, "deliveries": [{"signalId": s.id, "latencyMs": s.latency_ms, "recipients": s.recipients, "at": s.sent_at.isoformat()} for s in rows]}


@router.get("/telegram/trace")
def telegram_trace(ref: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"success": True, "matches": bot.trace_leak(db, ref)}


@router.get("/telegram/subscribers")
def telegram_subscribers(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    out = []
    for s in db.scalars(select(Subscriber).order_by(Subscriber.activated_at.desc())):
        exp = s.expires_at.replace(tzinfo=timezone.utc) if s.expires_at and not s.expires_at.tzinfo else s.expires_at
        out.append({"chatId": s.chat_id, "firstName": s.first_name, "code": s.code, "activatedAt": s.activated_at.isoformat() if s.activated_at else None,
                    "expiresAt": exp.isoformat() if exp else None, "active": bool(exp and exp > now)})
    return {"subscribers": out}


@router.delete("/telegram/subscribers/{chat_id}")
def telegram_subscriber_delete(chat_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    s = db.get(Subscriber, chat_id)
    if s:
        db.delete(s)
        db.commit()
    return {"success": True}


class CodeIn(BaseModel):
    durationHours: int = Field(720, gt=0, le=24 * 365 * 10)
    label: str = ""
    multiUse: bool = False
    count: int = Field(1, ge=1, le=50)


@router.post("/telegram/activation/generate")
def activation_generate(body: CodeIn, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    codes = []
    for _i in range(body.count):
        code = f"EXU-{secrets.token_hex(3).upper()}-{secrets.token_hex(2).upper()}"
        db.add(ActivationKey(code=code, label=body.label, duration_hours=body.durationHours, multi_use=body.multiUse))
        codes.append(code)
    db.commit()
    return {"success": True, "codes": codes, "code": codes[0]}


@router.post("/telegram/activation/apply")
def activation_apply(body: dict = Body(...), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    chat_id, code = str(body.get("chatId") or "").strip(), str(body.get("code") or "").strip()
    if not chat_id or not code:
        raise HTTPException(400, "chatId and code are required")
    return bot.activate(db, chat_id, code, str(body.get("firstName") or ""))


@router.get("/telegram/activation/status")
def activation_status(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    keys = db.scalars(select(ActivationKey).order_by(ActivationKey.created_at.desc())).all()
    return {"success": True, "activeSubscribers": len(bot.active_subscribers(db)),
            "codes": [{"code": k.code, "label": k.label, "durationHours": k.duration_hours, "multiUse": k.multi_use, "usedCount": k.used_count,
                       "revoked": k.revoked, "createdAt": k.created_at.isoformat()} for k in keys]}


@router.delete("/telegram/activation/{code}")
def activation_revoke(code: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    k = db.get(ActivationKey, code)
    if not k:
        raise HTTPException(404, "Code not found")
    k.revoked = True
    db.commit()
    return {"success": True}
