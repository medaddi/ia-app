"""
Telegram bot: sending, the signal message, dispatch of strategy signals and the chat commands.

Dispatch rules (single path, used by the candle-close scheduler and the manual button):
only a SIGNAL (score >= 75, every required rule passed) from one of the two strategies, market
open, not sent before (persisted in the `signals` table), re-checked by the validator, sent in
parallel batches to activated subscribers + the admin chat, each with a personal offset and
reference code (protection.py) and protect_content.
"""

import asyncio
import html
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..market.data import market_session_status
from ..config import settings
from ..models import Signal, Subscriber, TelegramConnect, User, Watermark
from ..store import get_setting, set_setting
from ..strategies.exunu import run_exunu, to_ai_signal
from ..strategies.service import STRATEGY_DEFS, get_strategy_result, normalize_symbol
from ..strategies._pairs import PAIRS
from ..agents.registry import AGENT_CONFIGS as PAIR_CONFIGS
from ..strategies.shared.news import load_news_calendar
from ..strategies.shared.jsnum import fmt_utc_minute, to_fixed
from ..trading import effective_risk, lot_for_risk, signal_json, stats
from .protection import personalize_signal

API = "https://api.telegram.org/bot{token}/{method}"
BATCH = 25

_client: Optional[httpx.AsyncClient] = None
_in_flight: set[str] = set()
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
    """A picture (the /chart image) with an HTML caption."""
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


# ---------------------------------------------------------------- message

def _levels(signal: dict) -> Optional[dict]:
    """The strategy's own levels of a signal, or None if one is missing."""
    def num(v):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None

    entry, sl, tp1, tp2, tp3 = (num(signal.get(k)) for k in ("entryPrice", "stopLoss", "target1", "target2", "target3"))
    if None in (entry, sl, tp1, tp2):
        return None
    sj = signal.get("signalJson") or {}
    symbol = normalize_symbol(signal.get("symbol", ""))
    gold = symbol == "XAU/USD"
    return {"symbol": symbol, "buy": signal.get("signalType") == "BUY", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "single": sj.get("setup") in ("PAIR", "GPA", "BREAK_RETEST", "REVERSION", "BREAKOUT", "RSI2", "LONDON", "REPORT") and tp3 is not None,  # one target between 1.5R and 2R
            "orderType": sj.get("entry_type") or signal.get("entryType") or "LIMIT", "expires": sj.get("expires_at"),
            "decimals": 2 if gold else 5, "pip": 0.1 if gold else 0.0001, "setup": sj.get("setup"), "hit": signal.get("targetHitPct")}


def format_signal_message(signal: dict, lot: Optional[dict] = None, ref: Optional[str] = None) -> str:
    """The trade, one value per line (prices tap-to-copy for MetaTrader):
    🟢 BUY | XAU/USD · 📍 Entry · 🎯 TP · 🛑 SL, then this person's lot when a risk is set.
    `lot`: None = no lot line (a group chat), {} = subscriber without a risk set, else lot_for_risk()."""
    L = _levels(signal)
    if not L:
        return f"⚠️ {normalize_symbol(signal.get('symbol', ''))}: signal levels incomplete, not sent."
    c = lambda v: f"<code>{to_fixed(v, L['decimals'])}</code>"  # noqa: E731
    order = "" if L["orderType"] == "MARKET" else f" {L['orderType']}"
    tp = L["tp3"] if L["tp3"] is not None else L["tp2"]
    lines = [f"{'🟢' if L['buy'] else '🔴'} <b>{'BUY' if L['buy'] else 'SELL'}{order} | {L['symbol']}</b>",
             f"📍 Entry: {c(L['entry'])}",
             f"🎯 TP: {c(tp)}",
             f"🛑 SL: {c(L['sl'])}"]
    if L["tp1"] and abs(L["tp1"] - tp) > 1e-9:  # the agent's TP1 (partial / break-even) before the final target
        lines.insert(2, f"🎯 TP1: {c(L['tp1'])}")
        lines[3] = f"🎯 TP2: {c(tp)}"
    if lot and lot.get("lots"):
        lines.append(f"📦 Lot: <code>{lot['lots']:.2f}</code>")
    if L["orderType"] == "LIMIT" and L.get("expires"):
        lines.append(f"⏳ Valid until {str(L['expires'])[11:16]} UTC")
    if ref:
        lines.append(f"<i>Ref {ref}</i>")
    return "\n".join(lines)


def close_message(sig: dict) -> tuple[str, str]:
    """How a sent trade ended, as (headline, result + what to do): TP hit, SL hit, breakeven, closed early by the strategy,
    or a limit order never filled."""
    r, outcome, state = sig.get("rMultiple"), sig.get("outcome"), sig.get("state")
    if state in ("CANCELLED", "EXPIRED"):
        return "⚪ CANCELLED", "Order not filled.\n👉 Delete your pending order."
    target = sig.get("rrTarget") or 0
    if outcome == "WIN" and r is not None and target and r >= target * 0.95:
        head, todo = "✅ TP HIT", "👉 Profit taken. Nothing to do."
    elif outcome == "WIN":
        head, todo = "✅ CLOSED IN PROFIT", "👉 The strategy closed it early: close it if it is still open."
    elif outcome == "LOSS" and r is not None and r <= -0.95:
        head, todo = "❌ SL HIT", "👉 The stop limited the loss. Wait for the next signal."
    elif outcome == "LOSS":
        head, todo = "❌ CLOSED AT A LOSS", "👉 The strategy closed it early: close it if it is still open."
    else:
        head, todo = "➖ BREAKEVEN", "👉 Closed at entry. Nothing to do."
    return head, f"Result: {r:+.2f}R\n{todo}" if r is not None else todo


def format_close_message(sig: dict) -> str:
    """✅ TP HIT | XAU/USD (BUY), the result in R, then what to do."""
    head, res = close_message(sig)
    return f"<b>{head} | {sig['symbol']} ({sig['direction']})</b>\n{res}"


async def send_update(sig: dict, head: str, body: str) -> int:
    """A follow-up notice of a running trade (filled, +1R, near SL, news) to the chats that got it."""
    with SessionLocal() as db:
        cfg = get_setting(db, "telegram")
        if not cfg["enabled"] or not cfg["botToken"]:
            return 0
        chats = {w.chat_id for w in db.scalars(select(Watermark).where(Watermark.signal_id == sig["id"]))}
    if cfg["chatId"]:
        chats.add(str(cfg["chatId"]))
    text = f"<b>{head} | {sig['symbol']} ({sig['direction']})</b>\n{body}"
    outs = await asyncio.gather(*(send_message(cfg["botToken"], c, text) for c in chats))
    return sum(1 for o in outs if o["success"])


async def notify_closed(closed: list[dict]) -> int:
    """Tells the chats that received each trade how it ended (once per trade: the state change is stored before)."""
    if not closed:
        return 0
    sent = 0
    with SessionLocal() as db:
        cfg = get_setting(db, "telegram")
        if not cfg["enabled"] or not cfg["botToken"]:
            return 0
        for sig in closed:
            chats = {w.chat_id for w in db.scalars(select(Watermark).where(Watermark.signal_id == sig["id"]))}
            if cfg["chatId"]:
                chats.add(str(cfg["chatId"]))
            text = format_close_message(sig)
            outs = await asyncio.gather(*(send_message(cfg["botToken"], c, text) for c in chats))
            sent += sum(1 for o in outs if o["success"])
            head, res = close_message(sig)
            log_event("RESULT", f"{sig['direction']} {sig['symbol']}", f"{head} · {res.splitlines()[0]} · {len(chats)} chat(s)", True)
    return sent


def copy_keyboard(signal: dict, lot: Optional[dict] = None) -> Optional[dict]:
    """One button per value (Telegram copy_text): tap, then paste it in MetaTrader."""
    L = _levels(signal)
    if not L:
        return None
    f = lambda v: to_fixed(v, L["decimals"])  # noqa: E731
    btn = lambda label, v: {"text": f"📋 {label}", "copy_text": {"text": v}}  # noqa: E731
    rows = [[btn("Entry", f(L["entry"])), btn("SL", f(L["sl"]))]]
    if L["single"]:
        rows[0].append(btn("TP", f(L["tp3"])))
    else:
        rows.append([btn("TP1", f(L["tp1"])), btn("TP2", f(L["tp2"]))] + ([btn("TP3", f(L["tp3"]))] if L["tp3"] is not None else []))
    if lot and lot.get("lots"):
        rows.append([btn(f"Lot {lot['lots']:.2f}", f"{lot['lots']:.2f}")])
    return {"inline_keyboard": rows}


# ---------------------------------------------------------------- subscribers

def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def chat_risks(db: Session, chat_ids: list[str]) -> dict[str, Optional[float]]:
    """$ risked per signal by each subscriber: the linked app account's risk ($ or % of its capital) first, else the bot's
    /risk and /capital. Non-subscriber chats are left out (no lot line)."""
    users = {u.telegram_chat_id: effective_risk(u.risk_usd, u.capital, u.risk_pct)
             for u in db.scalars(select(User).where(User.telegram_chat_id.in_(chat_ids)))}
    return {s.chat_id: users.get(s.chat_id) or effective_risk(s.risk_usd, s.capital, s.risk_pct)
            for s in db.scalars(select(Subscriber).where(Subscriber.chat_id.in_(chat_ids)))}


def _link(db: Session, u: User, chat_id: str, first_name: str) -> str:
    """Links this chat to the app account `u` (one Telegram per account, one account per Telegram): the bot then works
    with that account (access, risk, lot)."""
    u.telegram_chat_id, u.telegram_link_code, u.telegram_link_expires = chat_id, None, None
    now = datetime.now(timezone.utc)
    sub = db.get(Subscriber, chat_id) or Subscriber(chat_id=chat_id)
    sub.first_name = first_name or sub.first_name
    sub.code, sub.activated_at, sub.expires_at, sub.expired_notified = "ACCOUNT", now, None, False  # access = the account
    sub.risk_usd, sub.capital, sub.risk_pct, sub.muted = u.risk_usd, u.capital or 0, u.risk_pct, False
    db.merge(sub)
    db.commit()
    risk = effective_risk(u.risk_usd, u.capital, u.risk_pct)
    how = (f"${risk:g} per trade" + (f" ({u.risk_pct:g}% of ${u.capital:g})" if not u.risk_usd and u.capital else "")) if risk else "not set yet (/risk 80 or /risk 1%)"
    return (f"✅ <b>Connected</b> · {html.escape(u.username)}\n{LINE}\n💵 Risk: <b>{how}</b>\n"
            "Every trade arrives here with your lot, then its follow-up until it closes.\n\n📋 /help · all commands")


CONNECT_TTL = 15 * 60


def connect_button(db: Session, chat_id: str, first_name: str) -> tuple[str, Optional[dict]]:
    """The invitation: a one-time link that opens the app, where the person logs in and accepts the link."""
    token = secrets.token_urlsafe(24)
    db.add(TelegramConnect(token=token, chat_id=chat_id, first_name=first_name, expires_at=int(time.time()) + CONNECT_TTL))
    db.commit()
    url = f"{settings.public_app_url or 'http://localhost:3000'}/?tg={token}"
    text = (f"🔗 <b>Link your account</b>\n{LINE}\n1. Tap the button\n2. Log in to the app\n3. Tap <b>Accept</b>\n\n"
            "The bot then works with your account: your access, your risk and your lot.\n<i>The link works once, for 15 minutes.</i>")
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
    """The app account linked to this chat, when it may receive the signals (active and approved)."""
    return db.scalar(select(User).where(User.telegram_chat_id == chat_id, User.active.is_(True),
                                        or_(User.status.is_(None), User.status != "pending")))


def active_subscribers(db: Session) -> list[Subscriber]:
    """The chats that get the signals: exactly the ones linked to an active, approved app account."""
    linked = {u.telegram_chat_id for u in db.scalars(select(User).where(User.telegram_chat_id.is_not(None), User.active.is_(True),
                                                                        or_(User.status.is_(None), User.status != "pending")))}
    return [s for s in db.scalars(select(Subscriber).where(Subscriber.chat_id.in_(linked)))] if linked else []


def unlink_chat(db: Session, chat_id: Optional[str]) -> None:
    """The account is gone, disabled or unlinked: forget its chat (it gets no signal and must link again)."""
    if not chat_id:
        return
    for u in db.scalars(select(User).where(User.telegram_chat_id == chat_id)):
        u.telegram_chat_id = None
    sub = db.get(Subscriber, chat_id)
    if sub:
        db.delete(sub)


# ---------------------------------------------------------------- dispatch

RETRY_SEC = 15 * 60  # a signal Telegram did not deliver is retried this long after its candle closed


async def dispatch_setup(raw_symbol: str, manual: bool) -> dict:
    symbol = normalize_symbol(raw_symbol)
    res = await run_exunu(symbol)
    r = res["strategy"]
    setup = r["setup"]
    state = f"{r['status']}/{setup['lifecycle']['state']}" if setup else "NO_SETUP"
    if not r["market"]["isOpen"]:
        return {"success": False, "state": state, "error": f"Market closed for {symbol}: no signals are sent while it is closed."}
    if not setup or r["status"] != "SIGNAL":
        return {"success": False, "state": state, "error": f"{r['headlineAr']} ({r['headline']})"}
    # Manual sends are allowed while the order is still valid; automatic sends on the signal candle, and retried for
    # RETRY_SEC after it when the first Telegram attempt reached nobody (the trade is already recorded then)
    if not manual and not r["canNotify"]:
        with SessionLocal() as db:
            row = db.get(Signal, setup["id"])
            retry = (row is not None and (row.recipients or 0) == 0 and setup["lifecycle"]["state"] in ("PENDING", "OPEN")
                     and time.time() - setup["signalTime"] <= RETRY_SEC)
        if not retry:
            return {"success": False, "state": state, "error": r["headline"]}
    if manual and setup["lifecycle"]["state"] not in ("PENDING", "OPEN"):
        return {"success": False, "state": state, "error": f"Order is {setup['lifecycle']['state']}: too late to send"}
    if setup["id"] in _in_flight:
        return {"success": False, "state": state, "error": "Already being sent"}
    with SessionLocal() as db:
        # The pair agent's fresh setup is sent; the risk notes travel with it, they never block (the trader sets the risk)
        check = res.get("consensus") or {"approved": False, "issues": ["The agent did not decide"]}
        if not check["approved"]:
            log_event("SIGNAL", f"{setup['direction']} {symbol} not sent", "; ".join(check["issues"]), False)
            return {"success": False, "state": state, "error": f"Agent: {'; '.join(check['issues'])}", "check": check}
        signal = to_ai_signal(res)
        # 1. Record the trade first, whatever happens to Telegram: the trade-management agent and the app notifications
        #    follow it from here. The id is the primary key, so two concurrent ticks can never both create it
        row = db.get(Signal, setup["id"])
        if row is None:
            row = Signal(id=setup["id"], symbol=symbol, setup=setup["setup"], direction=setup["direction"], entry_type=setup["entryType"],
                         entry=setup["entry"], sl=setup["sl"], tp1=setup["tp1"], tp2=setup["tp2"], tp3=setup["tp3"], rr_tp2=setup["rrTp2"],
                         score=r["score"], signal_time=setup["signalTime"], recipients=0, state=setup["lifecycle"]["state"],
                         params=setup["params"], payload=signal)
            db.add(row)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                row = db.get(Signal, setup["id"])
        if row is not None and (row.recipients or 0) != 0:
            return {"success": False, "state": state, "error": "This setup was already sent."}
        cfg = get_setting(db, "telegram")
        if not cfg["enabled"] or not cfg["botToken"]:
            return {"success": False, "state": state, "recorded": True, "error": "Telegram is disabled or has no bot token (the trade is recorded)"}
        if cfg.get("assets") and symbol not in cfg["assets"]:
            return {"success": False, "state": state, "recorded": True, "error": f"{symbol} is not in the Telegram asset list"}
        recipients = {s.chat_id: s for s in active_subscribers(db) if not s.muted}
        if cfg["chatId"]:
            recipients.setdefault(str(cfg["chatId"]), None)
        if not recipients:
            return {"success": False, "state": state, "recorded": True, "error": "No active subscribers"}
        # 2. Claim this Telegram attempt (recipients 0 → −1): only one tick sends; a failed attempt goes back to 0 and the
        #    next tick retries while the order is still valid
        claimed = db.execute(update(Signal).where(Signal.id == setup["id"], Signal.recipients == 0).values(recipients=-1)).rowcount
        db.commit()
        if not claimed:
            return {"success": False, "state": state, "error": "Already being sent"}
        _in_flight.add(setup["id"])
        progress = {"sent": 0}
        try:
            sent, first_ack, last_error = await _send_to_all(cfg, signal, recipients, db, progress)
        except Exception as err:
            sent, first_ack, last_error = progress["sent"], None, repr(err)
        except BaseException:
            # the tick ran out of time mid-send: keep what went out (no double message), or free the retry if nothing did
            with SessionLocal() as db2:
                db2.execute(update(Signal).where(Signal.id == setup["id"]).values(recipients=progress["sent"]))
                db2.commit()
            raise
        finally:
            _in_flight.discard(setup["id"])
        row = db.get(Signal, setup["id"])
        if not sent:
            row.recipients = 0  # nobody received it: the next tick tries again
            db.commit()
            log_event("SIGNAL", f"{signal['signalType']} {symbol}", "No chat received it (retried at the next tick)", False, last_error)
            return {"success": False, "state": state, "error": last_error or "Send failed", "signal": signal}
        latency = int(first_ack - setup["signalTime"] * 1000) if first_ack else None
        row.recipients, row.latency_ms = sent, latency
        db.commit()
        details = f"Entry {setup['entry']} | SL {setup['sl']} | TP2 {setup['tp2']} | {sent}/{len(recipients)} chat(s)"
        if latency is not None:
            details += f" | {latency / 1000:.1f}s after candle close"
        log_event("SIGNAL", f"{signal['signalType']} {symbol} ({r['score']})", details, True)
        return {"success": True, "state": state, "signal": signal, "recipients": sent, "latencyMs": latency}


async def _send_to_all(cfg: dict, signal: dict, recipients: dict, db: Session, progress: Optional[dict] = None) -> tuple[int, Optional[float], Optional[str]]:
    """Parallel delivery in batches under Telegram's ~30 messages/second limit."""
    ids = list(recipients)
    sent = 0
    first_ack: Optional[float] = None
    last_error: Optional[str] = None
    marks: list[Watermark] = []
    risks = chat_risks(db, ids)
    for b in range(0, len(ids), BATCH):
        batch = ids[b:b + BATCH]

        async def one(chat_id: str):
            personal, offset, ref = personalize_signal(signal, chat_id, cfg.get("personalOffsets", True))
            # Lot for this person's $ risk with the strategy's stop (the offset moves entry and SL together)
            risk = risks.get(chat_id)
            lot = lot_for_risk(str(signal["symbol"]), personal["entryPrice"], personal["stopLoss"], risk) if risk else ({} if chat_id in risks else None)
            out = await send_message(cfg["botToken"], chat_id, format_signal_message(personal, lot, ref), copy_keyboard(personal, lot),
                                     cfg.get("protectContent", True))
            return chat_id, out, offset, ref

        for chat_id, out, offset, ref in await asyncio.gather(*(one(c) for c in batch)):
            if out["success"]:
                sent += 1
                if progress is not None:
                    progress["sent"] = sent
                first_ack = first_ack or time.time() * 1000
                marks.append(Watermark(ref=ref, chat_id=chat_id, signal_id=str(signal["id"]), symbol=str(signal["symbol"]), offset=offset))
            else:
                last_error = out["error"]
        if b + BATCH < len(ids):
            await asyncio.sleep(1.05)
    db.add_all(marks)
    return sent, first_ack, last_error


def trace_leak(db: Session, ref: str) -> list[dict]:
    rows = db.scalars(select(Watermark).where(Watermark.ref == ref.strip().upper()))
    return [{"ref": w.ref, "chatId": w.chat_id, "signalId": w.signal_id, "symbol": w.symbol, "offset": w.offset, "sentAt": w.sent_at.isoformat()} for w in rows]


# ---------------------------------------------------------------- commands

# The "/" menu: grouped, the most used first. Pair commands (/gold, /eurusd…) still work; /pairs lists them.
SECTIONS = [
    ("📊 Market", [
        ("signal", "Every pair right now"),
        ("pairs", "One pair in detail"),
        ("chart", "The chart of a pair (picture)"),
        ("open", "Trades running now"),
        ("news", "Next high-impact news"),
        ("market", "Market hours and session"),
    ]),
    ("📈 Results", [
        ("history", "Last 10 signals and their result"),
        ("stats", "Win rate and results"),
    ]),
    ("👤 My account", [
        ("connect", "Link this Telegram to my app account"),
        ("status", "My account and access"),
        ("risk", "My risk per trade: /risk 80 or /risk 1%"),
        ("stop", "Pause the signals"),
        ("resume", "Receive the signals again"),
    ]),
    ("ℹ️ Info", [
        ("rules", "How the strategies work"),
        ("help", "All commands"),
    ]),
]
COMMANDS = [("start", "Start / activate"), *(c for _, cmds in SECTIONS for c in cmds)]
LINE = "━━━━━━━━━━━━━━"
HELP = "🤖 <b>LiquidityDissection</b>\n" + LINE + "\n\n" + "\n\n".join(
    f"<b>{title}</b>\n" + "\n".join(f"/{c}\n<i>{d}</i>" for c, d in cmds) for title, cmds in SECTIONS)
WELCOME = "🔗 Send /connect and log in to the app: this Telegram is then linked to your account."
DESCRIPTION = ("Gold and forex signals: entry, TP, SL and your lot, then every step until the trade closes (filled, +1R, "
               "near SL, news, TP / SL).\n\nPress Start, then Connect with your app account.")
SHORT_DESCRIPTION = "Gold & forex signals · entry, TP, SL, lot and trade follow-up."
PAIR_EMOJI = {"XAU/USD": "🥇"}
CHART_PAIRS = {"gold": "XAU/USD", **{p.replace("/", "").lower(): p for p in ("XAU/USD", *PAIRS)}}  # /chart_gold, /chart_eurusd…
NEWS_CCYS = {"USD", *(c for pair in PAIRS for c in pair.split("/"))}
PAIR_ALIASES = {"/gold": "XAU/USD", "/xau": "XAU/USD", "/euro": "EUR/USD", "/eur": "EUR/USD", "/gbp": "GBP/USD", "/cable": "GBP/USD", "/pound": "GBP/USD",
                **{"/" + pair.replace("/", "").lower(): pair for pair in PAIRS}}
STATE_TXT = {"PENDING": "⏳ waiting for entry", "OPEN": "🟡 running", "TP1_HIT": "🟡 running", "TP2_HIT": "🟡 running", "CLOSED": "closed",
             "CANCELLED": "⚪ cancelled", "EXPIRED": "⚪ expired"}
STATUS_ICON = {"SIGNAL": "🟢", "WATCH": "🟡", "NO_TRADE": "⚪"}
TREND_TXT = {"BULLISH": "📈 Bullish", "BEARISH": "📉 Bearish"}


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


def _res(sig: Signal) -> str:
    if sig.state == "CLOSED":
        icon = "✅" if sig.outcome == "WIN" else "❌" if sig.outcome == "LOSS" else "➖"
        return f"{icon} {sig.outcome} {sig.r_multiple:+.2f}R" if sig.r_multiple is not None else f"{icon} {sig.outcome}"
    return STATE_TXT.get(sig.state, sig.state)


def _p(sym: str, v: float) -> str:
    return to_fixed(v, 2 if sym == "XAU/USD" else 5)


def _icon(sym: str) -> str:
    return PAIR_EMOJI.get(sym, "💱")


def _cmd_of(sym: str) -> str:
    return {"XAU/USD": "/gold"}.get(sym, "/" + sym.replace("/", "").lower())


def _levels_lines(sym: str, direction: str, entry: float, tp: float, sl: float, state: str) -> list[str]:
    return [f"{'🟢 BUY' if direction == 'BUY' else '🔴 SELL'} · {STATE_TXT.get(state, state)}",
            f"📍 Entry: <code>{_p(sym, entry)}</code>", f"🎯 TP: <code>{_p(sym, tp)}</code>", f"🛑 SL: <code>{_p(sym, sl)}</code>"]


async def _pair_text(sym: str, detailed: bool = False) -> str:
    """One pair: price, trend, status, then its trade (or why there is none)."""
    r = (await get_strategy_result(sym))["result"]
    s = r["setup"]
    running = bool(s) and r["status"] in ("SIGNAL", "WATCH") and s["lifecycle"]["state"] in ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")
    status = (f"{STATUS_ICON.get(r['status'], '⚪')} Status: <b>{r['status']}</b> · score {r['score']}" if running
              else "⚪ Status: <b>NO TRADE</b>")  # a finished trade is history, not a signal
    lines = [f"{_icon(sym)} <b>{r['displaySymbol']}</b> · {html.escape(r['strategyName'].split('·')[-1].strip())}", LINE,
             f"💲 Price: <code>{_p(sym, r['price'])}</code>",
             f"🧭 Trend: {TREND_TXT.get(r['bias']['direction'], '➖ Neutral')}", status]
    if running:
        lines += [LINE, *_levels_lines(sym, s["direction"], s["entry"], s["tp3"], s["sl"], s["lifecycle"]["state"])]
    elif s and s["lifecycle"].get("outcome"):
        o, rr = s["lifecycle"]["outcome"], s["lifecycle"].get("rMultiple")
        lines += ["", f"Last trade: {'✅' if o == 'WIN' else '❌' if o == 'LOSS' else '➖'} {o}" + (f" {rr:+.2f}R" if rr is not None else "")]
    else:
        lines += ["", f"<i>{html.escape(r['headline'])}</i>"]
    return "\n".join(lines)


async def _signal_text() -> str:
    """Every pair on one line: status, price and its trade."""
    rows = []
    for sym in STRATEGY_DEFS:
        try:
            r = (await get_strategy_result(sym))["result"]
        except Exception:
            rows.append(f"⚠️ <b>{sym}</b> · no data")
            continue
        s = r["setup"]
        running = s and s["lifecycle"]["state"] in ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT") and r["status"] in ("SIGNAL", "WATCH")
        trade = f"{'🟢 BUY' if s['direction'] == 'BUY' else '🔴 SELL'} · {STATE_TXT.get(s['lifecycle']['state'], '')}" if running else "no trade"
        rows.append(f"{STATUS_ICON.get(r['status'], '⚪') if running else '⚪'} <b>{sym}</b> <code>{_p(sym, r['price'])}</code>\n      {trade}")
    now = datetime.now(timezone.utc)
    return f"📊 <b>Market now</b> · {now:%H:%M} UTC\n{LINE}\n" + "\n".join(rows) + "\n\nDetails: /pairs"


def _pairs_text() -> str:
    return "💱 <b>Pairs</b>\n" + LINE + "\n" + "\n".join(f"{_icon(sym)} {_cmd_of(sym)} · {sym}" for sym in STRATEGY_DEFS)


async def _levels_text() -> str:
    out = []
    for sym in STRATEGY_DEFS:
        f = (await get_strategy_result(sym))["result"]["facts"] or {}
        lv = " · ".join(f"{x.get('label') or x['kind']} <code>{_p(sym, x['price'])}</code>" for x in (f.get("levels") or [])[:6])
        rng = f.get("range20h")
        extra = f"\n20h high <code>{_p(sym, rng['high'])}</code> · 20h low <code>{_p(sym, rng['low'])}</code>" if rng else ""
        aoi = f.get("areasOfInterest") or []
        if aoi:
            extra += "\nAOI " + " · ".join(f"{a['kind']} <code>{_p(sym, a['price'])}</code>" for a in aoi)
        out.append(f"<b>{sym}</b>\n{lv or '—'}{extra}")
    return "\n\n".join(out)


async def _news_text() -> str:
    cal = await load_news_calendar()
    now = int(time.time())
    up = sorted((e for e in cal["events"] if e["time"] > now - 1800 and e.get("impact") == "High" and e.get("currency") in NEWS_CCYS),
                key=lambda e: e["time"])[:8]
    if not up:
        return f"📰 <b>High-impact news</b>\n{LINE}\nNothing scheduled for the app's currencies."
    return (f"📰 <b>High-impact news</b> (UTC)\n{LINE}\n"
            + "\n".join(f"🕐 {fmt_utc_minute(e['time'])} · <b>{e['currency']}</b> {html.escape(e['title'])}" for e in up)
            + "\n\n<i>No new signal 30 min before and after.</i>")


def _market_text() -> str:
    now = datetime.now(timezone.utc)
    m = now.hour * 60 + now.minute
    session = "Asia" if m < 7 * 60 else "London" if m < 12 * 60 else "London / New York" if m < 16 * 60 else "New York" if m < 21 * 60 else "Rollover"
    st = market_session_status("XAU/USD")
    return (f"🕒 <b>Market</b> · {now:%a %H:%M} UTC\n{LINE}\n{'🟢 Open' if st['isOpen'] else '🔴 Closed'}\n🌍 Session: <b>{session}</b>\n\n"
            "<i>Gold and forex: Sunday 22:00 → Friday 21:00 UTC.</i>")


def _rules_text() -> str:
    """/rules: each pair's agent and its steps, from its config (the rules the code runs)."""
    flags = {"XAU/USD": "🥇", "EUR/USD": "💶", "GBP/USD": "💷", "AUD/CHF": "🇦🇺"}
    lines = ["<b>How the signals work</b>",
             "🤖 4 autonomous agents, one per pair, each with its own strategy and its own chart. Sessions in UTC+1 (Morocco time).",
             "🎛 One trade at a time per pair, one target at 2R. You control your risk: set it with /risk (e.g. /risk 50 or /risk 1%), "
             "every signal comes with your lot. News and correlated USD trades come as notes, never as a block."]
    for pair, c in PAIR_CONFIGS.items():
        steps = "; ".join(html.escape(x) for x in c["steps"])
        lines.append(f"{flags.get(pair, '💱')} <b>{pair} · {c['agent']}</b> ({c['timeframes']['entry']}): {steps}.")
    lines.append("Orders are sent at the candle close where the agent's setup completes.")
    return "\n".join(lines)


def _linked_users(db: Session, chat_id: str) -> list[User]:
    return list(db.scalars(select(User).where(User.telegram_chat_id == chat_id)))


def _risk_text(sub: Subscriber) -> str:
    risk = effective_risk(sub.risk_usd, sub.capital, sub.risk_pct)
    if not risk:
        return "No risk set. Send <code>/risk 80</code> ($ per trade) or <code>/capital 5000</code> then <code>/risk 1%</code>."
    pct = f" ({sub.risk_pct:g}% of ${sub.capital:g})" if not sub.risk_usd and sub.capital else ""
    return f"💵 Risk per trade: <b>${risk:g}</b>{pct}. Each signal comes with the lot for it; the SL stays where the strategy puts it."


def _risk_reply(db: Session, sub: Optional[Subscriber], active: bool, text: str) -> str:
    """/risk → current · /risk 80 → $80 per trade · /risk 1% → 1% of the capital · /risk 0 → off. Mirrored on the linked app account."""
    if not active or not sub:
        return "⛔ Not activated. Send your activation code or your app link code."
    parts = text.split()
    if len(parts) < 2:
        return _risk_text(sub)
    raw = parts[1].replace("$", "").replace(",", ".")
    try:
        value = float(raw.rstrip("%"))
    except ValueError:
        return "Send <code>/risk 80</code> ($) or <code>/risk 1%</code> (of your capital)."
    if raw.endswith("%"):
        if not (0 < value <= 100):
            return "The % must be between 0 and 100, for example <code>/risk 1%</code>."
        if not sub.capital:
            return "Send your capital first: <code>/capital 5000</code>, then <code>/risk 1%</code>."
        sub.risk_usd, sub.risk_pct = None, value
    else:
        if value < 0 or value > 1_000_000:
            return "Send a number in $, for example <code>/risk 80</code>."
        sub.risk_usd = value or None
    for u in _linked_users(db, sub.chat_id):
        u.risk_usd, u.risk_pct = sub.risk_usd, sub.risk_pct
    db.commit()
    return "✅ " + _risk_text(sub) if effective_risk(sub.risk_usd, sub.capital, sub.risk_pct) else "Risk removed: signals come without a lot."


def _capital_reply(db: Session, sub: Optional[Subscriber], active: bool, text: str) -> str:
    if not active or not sub:
        return "⛔ Not activated. Send your activation code or your app link code."
    parts = text.split()
    if len(parts) < 2:
        return f"🏦 Capital: <b>${sub.capital:g}</b>." if sub.capital else "🏦 No capital set. Send <code>/capital 5000</code>."
    try:
        value = float(parts[1].replace("$", "").replace(",", "."))
    except ValueError:
        return "Send a number in $, for example <code>/capital 5000</code>."
    if value < 0 or value > 1_000_000_000:
        return "Send a number in $, for example <code>/capital 5000</code>."
    sub.capital = value
    for u in _linked_users(db, sub.chat_id):
        u.capital = value
    db.commit()
    return f"✅ Capital set to <b>${value:g}</b>. " + _risk_text(sub)


async def handle_update(token: str, upd: dict) -> None:
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    if not chat_id or not text:
        return
    sender = msg.get("from") or {}
    name = html.escape(sender.get("first_name") or "")
    # how the app names this Telegram once linked: "Ali · @ali_fx"
    display = " · ".join(x for x in (sender.get("first_name") or "", f"@{sender['username']}" if sender.get("username") else "") if x)[:120]
    cmd = text.split()[0].split("@")[0].lower()
    markup: Optional[dict] = None
    pictures: list[str] = []  # pairs whose running trade follows the reply as pictures (chart, then its follow-up card)
    with SessionLocal() as db:
        sub = db.get(Subscriber, chat_id)
        account = account_of(db, chat_id)  # access comes only from a linked, active app account
        active = bool(account)
        if active and not sub:
            sub = Subscriber(chat_id=chat_id, first_name=name, code="ACCOUNT", activated_at=datetime.now(timezone.utc))
            db.add(sub)
            db.commit()
        if not text.startswith("/"):
            return  # the bot is not a chat: it reads its commands only
        if cmd in ("/connect", "/start") and not active:
            reply, markup = connect_button(db, chat_id, display)
            reply = f"👋 Welcome, <b>{name}</b>\n\n" + reply
        elif cmd == "/connect":
            reply = (f"✅ Connected to <b>{html.escape(account.username)}</b>.\n"
                     "One Telegram per account: to use another one, unlink this one in the app (My account).")
        elif cmd == "/start":
            reply = (f"👋 Welcome back, <b>{html.escape(account.username)}</b>\n✅ Your account is connected\n\n"
                     "Every trade arrives here: entry, TP, SL and your lot, then its follow-up until it closes.\n\n📋 /help · all commands")
        elif not active and cmd not in ("/help", "/myid"):
            reply, markup = connect_button(db, chat_id, display)
            reply = "🔒 <b>Connect your app account first</b>\n\n" + reply
        elif cmd == "/help":
            reply = HELP
        elif cmd == "/myid":
            reply = f"🆔 Your chat id: <code>{chat_id}</code>"
        elif cmd == "/risk":
            reply = _risk_reply(db, sub, active, text)
        elif cmd == "/capital":
            reply = _capital_reply(db, sub, active, text)
        elif cmd == "/status":
            who = (f"👤 Account: <b>{html.escape(account.username)}</b>"
                   + (f" · {html.escape(' '.join(x for x in (account.first_name, account.last_name) if x))}" if account.first_name or account.last_name else ""))
            reply = (f"👤 <b>My account</b>\n{LINE}\n{who}\n" + ("⏸ Signals paused · /resume" if sub.muted else "🔔 Signals on")
                     + f"\n{_risk_text(sub)}")
        elif cmd in ("/stop", "/pause"):
            if sub:
                sub.muted = True
                db.commit()
            reply = "⏸ Signals paused. Send /resume to receive them again." if active else "⛔ Not activated."
        elif cmd in ("/resume", "/unpause"):
            if sub:
                sub.muted = False
                db.commit()
            reply = "▶️ Signals resumed." if active else "⛔ Not activated. Send your activation code."
        elif cmd in ("/market", "/time", "/session"):
            reply = _market_text()
        elif cmd == "/rules":
            reply = _rules_text()
        elif cmd == "/news":
            reply = await _news_text()
        elif cmd == "/levels":
            reply = await _levels_text()
        elif cmd in ("/signal", "/live", "/now", "/analysis"):
            reply = await _signal_text()
            pictures = await _running_pairs()
        elif cmd == "/pairs":
            reply = _pairs_text()
        elif cmd == "/chart":
            reply = (f"📈 <b>Charts</b>\n{LINE}\nTap a pair:\n\n"
                     + "\n".join(f"{_icon(sym)} /chart_{_cmd_of(sym)[1:]} · {sym}" for sym in STRATEGY_DEFS))
        elif cmd.startswith("/chart_") and cmd[7:] in CHART_PAIRS:
            from .chart_image import pair_chart  # Pillow loads only when a chart is asked for
            try:
                png, caption = await pair_chart(CHART_PAIRS[cmd[7:]])
            except Exception as err:
                reply = f"⚠️ Chart unavailable right now ({err.__class__.__name__}). Try again in a minute."
            else:
                out = await send_photo(token, chat_id, png, caption)
                if out["success"]:
                    return
                reply = f"⚠️ The chart could not be sent: {html.escape(out['error'])}"
        elif cmd in PAIR_ALIASES:
            reply = await _pair_text(PAIR_ALIASES[cmd], detailed=True)
        elif cmd in ("/open", "/running", "/trades"):
            rows = db.scalars(select(Signal).where(Signal.state.not_in(("CLOSED", "CANCELLED", "EXPIRED"))).order_by(Signal.sent_at.desc())).all()
            reply = (f"🟡 <b>Running trades</b> ({len(rows)})\n{LINE}\n" + "\n\n".join(
                f"{_icon(x.symbol)} <b>{x.symbol}</b>\n" + "\n".join(_levels_lines(x.symbol, x.direction, x.entry, x.tp3 or x.tp2, x.sl, x.state))
                for x in rows)) if rows else f"🟡 <b>Running trades</b>\n{LINE}\nNo trade running right now."
            pictures = list(dict.fromkeys(x.symbol for x in rows))
        elif cmd in ("/history", "/last"):
            rows = db.scalars(select(Signal).order_by(Signal.sent_at.desc()).limit(10)).all()
            reply = (f"🗂 <b>Last signals</b>\n{LINE}\n" + "\n".join(
                f"<code>{x.sent_at:%m-%d %H:%M}</code> {'🟢' if x.direction == 'BUY' else '🔴'} <b>{x.symbol}</b> · {_res(x)}" for x in rows)
                ) if rows else f"🗂 <b>Last signals</b>\n{LINE}\nNo signal sent yet."
        elif cmd in ("/stats", "/winrate", "/performance", "/results"):
            all_rows = db.scalars(select(Signal)).all()
            since = datetime.now(timezone.utc) - timedelta(days=30)
            recent = [x for x in all_rows if _aware(x.sent_at) >= since]

            def block(title, rows):
                s = stats(rows, "signal")
                wr = f"{s['winRate']}%" if s["winRate"] is not None else "—"
                per = "\n".join(f"   {k} · {v['winRate'] if v['winRate'] is not None else '—'}% · {v['totalR']:+}R" for k, v in s["bySymbol"].items())
                return (f"<b>{title}</b>\n{s['total']} signals · {s['closed']} closed · {s['open']} running\n"
                        f"✅ {s['wins']}   ❌ {s['losses']}   ➖ {s['breakevens']}\n"
                        f"🎯 Win rate <b>{wr}</b> · total <b>{s['totalR']:+}R</b>" + (f"\n{per}" if per else ""))
            reply = f"📊 <b>Results</b>\n{LINE}\n{block('Last 30 days', recent)}\n\n{block('All time', all_rows)}"
        else:
            reply = HELP
    await send_message(token, chat_id, reply, markup)
    for sym in pictures[:4]:  # each running trade: how it was set up, then where it stands now
        try:
            from .chart_image import trade_pictures
            for png, caption in await trade_pictures(sym):
                await send_photo(token, chat_id, png, caption)
        except Exception as err:  # a picture that fails never hides the text reply
            print(f"[telegram] pictures for {sym} failed: {err!r}")


async def _running_pairs() -> list[str]:
    """The pairs with a trade running now (from the cached analyses)."""
    out = []
    for sym in STRATEGY_DEFS:
        try:
            r = (await get_strategy_result(sym))["result"]
        except Exception:
            continue
        s = r["setup"]
        if s and s["lifecycle"]["state"] in ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT") and r["status"] in ("SIGNAL", "WATCH"):
            out.append(sym)
    return out


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


def recent_signals(db: Session, limit: int = 50) -> list[dict]:
    return [signal_json(s) for s in db.scalars(select(Signal).order_by(Signal.sent_at.desc()).limit(limit))]


__all__ = ["dispatch_setup", "notify_closed", "send_update", "format_close_message", "send_message", "bot_info", "set_webhook", "handle_update", "format_signal_message", "active_subscribers", "trace_leak",
           "poll_forever", "history", "recent_signals", "market_session_status"]
