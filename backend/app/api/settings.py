"""App parameters, Telegram configuration, and the accounts linked to Telegram."""

import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import admin_user
from ..config import settings
from ..db import SessionLocal, get_db
from ..models import User
from ..store import get_setting, public_telegram, set_setting
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


@router.get("/telegram/subscribers")
def telegram_subscribers(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    """The accounts linked to Telegram."""
    subs = {s.chat_id: s for s in bot.active_subscribers(db)}
    out = [{"chatId": u.telegram_chat_id, "username": u.username, "firstName": (subs.get(u.telegram_chat_id).first_name if subs.get(u.telegram_chat_id) else ""),
            "active": u.telegram_chat_id in subs, "muted": bool(subs.get(u.telegram_chat_id) and subs[u.telegram_chat_id].muted)}
           for u in db.scalars(select(User).where(User.telegram_chat_id.is_not(None)).order_by(User.username))]
    return {"subscribers": out}


@router.delete("/telegram/subscribers/{chat_id}")
def telegram_subscriber_delete(chat_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    bot.unlink_chat(db, chat_id)
    db.commit()
    return {"success": True}
