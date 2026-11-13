"""
Telegram bot: the link between a Telegram chat and an app account, and a few information commands (news, market hours).
It sends no analysis and no trade: the app's analysis is being rebuilt.
"""

import asyncio
import html
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..market.data import market_session_status
from ..market.jsnum import fmt_utc_minute
from ..market.news import load_news_calendar
from ..market.pairs import PAIRS
from ..models import Subscriber, TelegramConnect, User
from ..store import get_setting, set_setting

API = "https://api.telegram.org/bot{token}/{method}"

_client: Optional[httpx.AsyncClient] = None
_log: list[dict] = []


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10, read=35))
    return _client


LOG_MAX = 50


def log_event(kind: str, title: str, details: str, ok: bool, error: Optional[str] = None) -> None:
    """The bot's event log, kept in the database: on serverless hosting every call may run on a new instance."""
    entry = {"id": f"log-{int(time.time() * 1000)}", "type": kind, "title": title, "details": details,
             "sentAt": datetime.now(timezone.utc).strftime("%m-%d %H:%M:%S"), "status": "SUCCESS" if ok else "FAILED", "error": error}
    _log.insert(0, entry)
    del _log[LOG_MAX:]
    try:
        with SessionLocal() as db:
            items = [entry, *get_setting(db, "eventLog").get("items", [])][:LOG_MAX]
            set_setting(db, "eventLog", {"items": items})
    except Exception as err:  # the log never breaks a send
        print(f"[log] {err!r}")


def history() -> list[dict]:
    try:
        with SessionLocal() as db:
            return get_setting(db, "eventLog").get("items", []) or list(_log)
    except Exception:
        return list(_log)


async def call(token: str, method: str, payload: dict) -> dict:
    try:
        r = await client().post(API.format(token=token, method=method), json=payload)
        data = r.json()
    except (httpx.HTTPError, ValueError) as err:
        return {"ok": False, "description": str(err) or "Telegram unreachable"}
    return data if isinstance(data, dict) else {"ok": False, "description": "Bad response"}


async def send_message(token: str, chat_id: str, text: str, reply_markup: Optional[dict] = None, protect: bool = False) -> dict:
    if not token or not chat_id:
        return {"success": False, "error": "Telegram bot token or chat id missing"}
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if protect:
        # Telegram blocks forwarding, saving and copying of protected messages
        payload["protect_content"] = True
    for attempt in range(3):
        data = await call(token, "sendMessage", payload)
        if data.get("ok"):
            break
        retry = (data.get("parameters") or {}).get("retry_after")
        transient = data.get("error_code") in (429, 500, 502, 503, 504) or "error_code" not in data  # rate limit, Telegram or network down
        if attempt == 2 or not transient:
            return {"success": False, "error": data.get("description") or "Telegram error"}
        await asyncio.sleep(min(float(retry or 1 + attempt), 5))  # Telegram says how long to wait on a 429
    return {"success": True, "messageId": (data.get("result") or {}).get("message_id")}


async def send_photo(token: str, chat_id: str, png: bytes, caption: str = "") -> dict:
    """A picture with an HTML caption."""
    try:
        r = await client().post(API.format(token=token, method="sendPhoto"),
                                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                                files={"photo": ("chart.png", png, "image/png")})
        data = r.json()
    except (httpx.HTTPError, ValueError) as err:
        return {"success": False, "error": str(err) or "Telegram unreachable"}
    return {"success": True} if data.get("ok") else {"success": False, "error": data.get("description") or "Telegram error"}


async def bot_info(token: str) -> dict:
    if not token:
        return {"success": False, "error": "No bot token"}
    data = await call(token, "getMe", {})
    if not data.get("ok"):
        return {"success": False, "error": data.get("description")}
    me = data["result"]
    return {"success": True, "id": me.get("id"), "username": me.get("username"), "firstName": me.get("first_name")}


async def set_webhook(token: str, url: str, secret: str) -> dict:
    """Register Telegram command delivery for a serverless deployment."""
    if not token or not url or not secret:
        return {"success": False, "error": "Telegram webhook URL and secret are required"}
    data = await call(token, "setWebhook", {"url": url, "secret_token": secret, "allowed_updates": ["message"]})
    return {"success": bool(data.get("ok")), "error": data.get("description")}



def _link(db: Session, u: User, chat_id: str, first_name: str) -> str:
    """Links this chat to the app account `u` (one Telegram per account, one account per Telegram): the bot then works
    with that account (access, risk, lot)."""
    u.telegram_chat_id, u.telegram_link_code, u.telegram_link_expires = chat_id, None, None
    now = datetime.now(timezone.utc)
    sub = db.get(Subscriber, chat_id) or Subscriber(chat_id=chat_id)
    sub.first_name = first_name or sub.first_name
    sub.code, sub.activated_at, sub.expires_at, sub.expired_notified = "ACCOUNT", now, None, False  # access = the account
    sub.muted = False
    db.merge(sub)
    db.commit()
    return f"✅ <b>Connected</b> · {html.escape(u.username)}\n{LINE}\nThis Telegram is now linked to your app account.\n\n📋 /help · all commands"


CONNECT_TTL = 15 * 60


def connect_button(db: Session, chat_id: str, first_name: str) -> tuple[str, Optional[dict]]:
    """The invitation: a one-time link that opens the app, where the person logs in and accepts the link."""
    token = secrets.token_urlsafe(24)
    db.add(TelegramConnect(token=token, chat_id=chat_id, first_name=first_name, expires_at=int(time.time()) + CONNECT_TTL))
    db.commit()
    url = f"{settings.public_app_url or 'http://localhost:3000'}/?tg={token}"
    text = (f"🔗 <b>Link your account</b>\n{LINE}\n1. Tap the button\n2. Log in to the app\n3. Tap <b>Accept</b>\n\n"
            "<i>The link works once, for 15 minutes.</i>")
    if "localhost" in url or "127.0.0.1" in url:  # Telegram refuses local addresses on buttons: the link goes in the text
        return f"{text}\n\n{url}", None
    return text, {"inline_keyboard": [[{"text": "🔗 Open the app and link", "url": url}]]}


def _connect_row(db: Session, token: str) -> Optional[TelegramConnect]:
    row = db.get(TelegramConnect, token.strip()) if token else None
    if row and row.expires_at < time.time():
        db.delete(row)
        db.commit()
        return None
    return row


def connect_info(db: Session, token: str, u: User) -> dict:
    """What the app shows before Accept: whose Telegram asks, and whether this account may take it."""
    row = _connect_row(db, token)
    if not row:
        return {"success": False, "error": "This Telegram link has expired: press Start in the bot again."}
    problem = _link_problem(db, row.chat_id, u)
    return {"success": True, "firstName": row.first_name, "problem": problem}


def _link_problem(db: Session, chat_id: str, u: User) -> Optional[str]:
    """One Telegram per account and one account per Telegram."""
    if u.telegram_chat_id and u.telegram_chat_id != chat_id:
        return "This account is already linked to another Telegram. Unlink it first in My account."
    other = db.scalar(select(User).where(User.telegram_chat_id == chat_id, User.id != u.id))
    if other:
        return "This Telegram is already linked to another account."
    return None


def connect_chat(db: Session, token: str, u: User) -> dict:
    """Accept: the logged-in account `u` takes the chat that asked for `token` (one-to-one)."""
    row = _connect_row(db, token)
    if not row:
        return {"success": False, "error": "This Telegram link has expired: press Start in the bot again."}
    problem = _link_problem(db, row.chat_id, u)
    if problem:
        return {"success": False, "error": problem}
    chat_id, name = row.chat_id, row.first_name
    db.delete(row)
    message = _link(db, u, chat_id, name)
    return {"success": True, "chatId": chat_id, "message": message}


def account_of(db: Session, chat_id: str) -> Optional[User]:
    """The app account linked to this chat, (active and approved)."""
    return db.scalar(select(User).where(User.telegram_chat_id == chat_id, User.active.is_(True),
                                        or_(User.status.is_(None), User.status != "pending")))


def active_subscribers(db: Session) -> list[Subscriber]:
    """The chats linked to an active, approved app account."""
    linked = {u.telegram_chat_id for u in db.scalars(select(User).where(User.telegram_chat_id.is_not(None), User.active.is_(True),
                                                                        or_(User.status.is_(None), User.status != "pending")))}
    return [s for s in db.scalars(select(Subscriber).where(Subscriber.chat_id.in_(linked)))] if linked else []


def unlink_chat(db: Session, chat_id: Optional[str]) -> None:
    """The account is gone, disabled or unlinked: forget its chat (it must link again)."""
    if not chat_id:
        return
    for u in db.scalars(select(User).where(User.telegram_chat_id == chat_id)):
        u.telegram_chat_id = None
    sub = db.get(Subscriber, chat_id)
    if sub:
        db.delete(sub)


# ---------------------------------------------------------------- commands

SECTIONS = [
    ("📊 Market", [
        ("news", "Next high-impact news"),
        ("market", "Market hours and session"),
    ]),
    ("👤 My account", [
        ("connect", "Link this Telegram to my app account"),
        ("status", "My account"),
        ("risk", "My USD risk per trade, e.g. /risk 50"),
    ]),
    ("ℹ️ Info", [
        ("help", "All commands"),
    ]),
]
COMMANDS = [("start", "Start / link my account"), *(c for _, cmds in SECTIONS for c in cmds)]
LINE = "━━━━━━━━━━━━━━"
HELP = "🤖 <b>LiquidityDissection</b>\n" + LINE + "\n\n" + "\n\n".join(
    f"<b>{title}</b>\n" + "\n".join(f"/{c}\n<i>{d}</i>" for c, d in cmds) for title, cmds in SECTIONS)
DESCRIPTION = "LiquidityDissection: gold and forex. Press Start, then link this Telegram to your app account."
SHORT_DESCRIPTION = "LiquidityDissection · gold & forex."
NEWS_CCYS = {"USD", *(c for pair in PAIRS for c in pair.split("/"))}


async def set_commands(token: str) -> None:
    """The bot's profile: the "/" menu (with what each command does) and the text shown before /start."""
    await call(token, "setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMMANDS]})
    await call(token, "setMyDescription", {"description": DESCRIPTION})
    await call(token, "setMyShortDescription", {"short_description": SHORT_DESCRIPTION})


_profile_token: Optional[str] = None


async def sync_profile(token: str) -> None:
    """Once per process: keeps the menu and the description of a running bot up to date (no admin step needed)."""
    global _profile_token
    if _profile_token != token:
        _profile_token = token
        await set_commands(token)


async def _news_text() -> str:
    cal = await load_news_calendar()
    now = int(time.time())
    up = sorted((e for e in cal["events"] if e["time"] > now - 1800 and e.get("impact") == "High" and e.get("currency") in NEWS_CCYS),
                key=lambda e: e["time"])[:8]
    if not up:
        return f"📰 <b>High-impact news</b>\n{LINE}\nNothing scheduled for the app's currencies."
    return (f"📰 <b>High-impact news</b> (UTC)\n{LINE}\n"
            + "\n".join(f"🕐 {fmt_utc_minute(e['time'])} · <b>{e['currency']}</b> {html.escape(e['title'])}" for e in up))


def _market_text() -> str:
    now = datetime.now(timezone.utc)
    m = now.hour * 60 + now.minute
    session = "Asia" if m < 7 * 60 else "London" if m < 12 * 60 else "London / New York" if m < 16 * 60 else "New York" if m < 21 * 60 else "Rollover"
    st = market_session_status("XAU/USD")
    return (f"🕒 <b>Market</b> · {now:%a %H:%M} UTC\n{LINE}\n{'🟢 Open' if st['isOpen'] else '🔴 Closed'}\n🌍 Session: <b>{session}</b>\n\n"
            "<i>Gold and forex: Sunday 22:00 → Friday 21:00 UTC.</i>")


async def handle_update(token: str, upd: dict) -> None:
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    if not chat_id or not text or not text.startswith("/"):
        return  # the bot is not a chat: it reads its commands only
    sender = msg.get("from") or {}
    name = html.escape(sender.get("first_name") or "")
    # how the app names this Telegram once linked: "Ali · @ali_fx"
    display = " · ".join(x for x in (sender.get("first_name") or "", f"@{sender['username']}" if sender.get("username") else "") if x)[:120]
    cmd = text.split()[0].split("@")[0].lower()
    markup: Optional[dict] = None
    with SessionLocal() as db:
        account = account_of(db, chat_id)  # the app account linked to this chat (active, approved)
        if cmd in ("/connect", "/start") and not account:
            reply, markup = connect_button(db, chat_id, display)
            reply = f"👋 Welcome, <b>{name}</b>\n\n" + reply
        elif cmd == "/connect":
            reply = (f"✅ Connected to <b>{html.escape(account.username)}</b>.\n"
                     "One Telegram per account: to use another one, unlink this one in the app (My account).")
        elif cmd == "/start":
            reply = f"👋 Welcome back, <b>{html.escape(account.username)}</b>\n✅ Your account is connected\n\n📋 /help · all commands"
        elif cmd == "/help":
            reply = HELP
        elif cmd == "/myid":
            reply = f"🆔 Your chat id: <code>{chat_id}</code>"
        elif cmd in ("/market", "/time", "/session"):
            reply = _market_text()
        elif cmd == "/news":
            reply = await _news_text()
        elif not account:
            reply, markup = connect_button(db, chat_id, display)
            reply = "🔒 <b>Connect your app account first</b>\n\n" + reply
        elif cmd == "/risk":  # this linked account's own USD risk per trade: each signal then shows its own lot
            from ..smc.sizing import valid_risk
            arg = text.split()[1] if len(text.split()) > 1 else None
            if arg is None:
                cur = valid_risk(account.risk_usd)
                reply = (f"⚖️ Your risk per trade: <b>${cur:g}</b>\nChange it: /risk 50" if cur is not None else
                         "⚖️ No risk set yet: each signal shows your lot once you set it.\nExample: /risk 50 (USD)")
            else:
                v = valid_risk(arg.replace(",", ".").lstrip("$"))
                if v is None:
                    reply = "⚠️ Send a positive amount in USD, for example /risk 50"
                else:
                    account.risk_usd = v
                    db.commit()
                    reply = f"✅ Risk per trade: <b>${v:g}</b>\nYour next signals show your lot for it (already-sized signals keep theirs)."
        elif cmd == "/status":
            full = " ".join(x for x in (account.first_name, account.last_name) if x)
            reply = f"👤 <b>My account</b>\n{LINE}\n👤 Account: <b>{html.escape(account.username)}</b>" + (f" · {html.escape(full)}" if full else "")
        else:
            reply = HELP
    await send_message(token, chat_id, reply, markup)


async def poll_forever(stop: asyncio.Event) -> None:
    """Long polling for chat commands. Only one process may poll a bot token at a time."""
    offset = 0
    while not stop.is_set():
        with SessionLocal() as db:
            token = get_setting(db, "telegram")["botToken"]
        if not token:
            await asyncio.sleep(30)
            continue
        await sync_profile(token)
        data = await call(token, "getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": ["message"]})
        if not data.get("ok"):
            await asyncio.sleep(5)
            continue
        for upd in data.get("result") or []:
            offset = max(offset, upd["update_id"] + 1)
            try:
                await handle_update(token, upd)
            except Exception as err:  # one bad update must never stop the bot
                print(f"[telegram] update failed: {err!r}")


__all__ = ["send_message", "bot_info", "set_webhook", "handle_update", "active_subscribers", "poll_forever", "history", "market_session_status"]
