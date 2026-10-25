"""
Telegram bot: sending, the signal message, dispatch of strategy signals and the chat commands.

Dispatch rules (single path, used by the candle-close scheduler and the manual button):
only a SIGNAL (score >= 75, every required rule passed) from one of the two strategies, market
open, not sent before (persisted in the `signals` table), re-checked by the validator, sent in
parallel batches to activated subscribers + the admin chat, each with a personal offset and
reference code (protection.py) and protect_content.
"""

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..agent.validator import validate_signal
from ..db import SessionLocal
from ..market.data import market_session_status
from ..models import ActivationKey, Signal, Subscriber, Watermark
from ..store import get_setting
from ..strategies.exunu import run_exunu, to_ai_signal
from ..strategies.service import both_results, normalize_symbol
from ..strategies.shared.jsnum import fmt_time, js_round, to_fixed
from ..trading import signal_json, stats
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


def log_event(kind: str, title: str, details: str, ok: bool, error: Optional[str] = None) -> None:
    _log.insert(0, {"id": f"log-{int(time.time() * 1000)}", "type": kind, "title": title, "details": details,
                    "sentAt": datetime.now(timezone.utc).strftime("%H:%M:%S"), "status": "SUCCESS" if ok else "FAILED", "error": error})
    del _log[30:]


def history() -> list[dict]:
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
    data = await call(token, "sendMessage", payload)
    if not data.get("ok"):
        return {"success": False, "error": data.get("description") or "Telegram error"}
    return {"success": True, "messageId": (data.get("result") or {}).get("message_id")}


async def bot_info(token: str) -> dict:
    if not token:
        return {"success": False, "error": "No bot token"}
    data = await call(token, "getMe", {})
    if not data.get("ok"):
        return {"success": False, "error": data.get("description")}
    me = data["result"]
    return {"success": True, "id": me.get("id"), "username": me.get("username"), "firstName": me.get("first_name")}


# ---------------------------------------------------------------- message

def format_signal_message(signal: dict) -> str:
    """Only the strategy's own levels are printed; nothing is filled in by default."""
    buy = signal.get("signalType") == "BUY"
    symbol = normalize_symbol(signal.get("symbol", ""))
    gold = symbol == "XAU/USD"
    decimals = 2 if gold else 5
    pip = 0.1 if gold else 0.0001

    def num(v):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None

    entry, sl, tp1, tp2, tp3 = (num(signal.get(k)) for k in ("entryPrice", "stopLoss", "target1", "target2", "target3"))
    if None in (entry, sl, tp1, tp2):
        return f"⚠️ {symbol}: signal levels incomplete, not sent."
    risk = abs(entry - sl)
    pips = lambda v: int(js_round(abs(v - entry) / pip))  # noqa: E731
    rr_of = lambda v: to_fixed(abs(v - entry) / risk, 1) if risk > 0 else "—"  # noqa: E731
    p = lambda v: f"{'$' if gold else ''}{to_fixed(v, decimals)}"  # noqa: E731
    sj = signal.get("signalJson") or {}
    order_type = sj.get("entry_type") or signal.get("entryType") or "LIMIT"
    expires = sj.get("expires_at", "")[11:16] + " UTC" if sj.get("expires_at") else None
    setup = f" · Setup {sj['setup']}" if sj.get("setup") else ""
    lines = [
        f"{'🟢' if buy else '🔴'} <b>{'BUY' if buy else 'SELL'} {order_type} | {symbol}{setup}</b>",
        "",
        f"📍 <b>Entry:</b> <code>{p(entry)}</code>{f' (valid until {expires})' if order_type == 'LIMIT' and expires else ''}",
        f"🛑 <b>SL:</b> <code>{p(sl)}</code> ({pips(sl)} pips)",
        f"🎯 <b>TP1:</b> <code>{p(tp1)}</code> (1:{rr_of(tp1)} · close 50%, SL → breakeven)",
        f"🎯 <b>TP2:</b> <code>{p(tp2)}</code> (1:{rr_of(tp2)})",
    ]
    if tp3 is not None:
        lines.append(f"🎯 <b>TP3:</b> <code>{p(tp3)}</code> (1:{rr_of(tp3)})")
    conf = signal.get("confidence")
    lines.append(f"🧠 <code>{signal.get('strategyUsed') or 'EXUNU'}</code>")
    lines.append(f"⚖️ <b>Score:</b> <code>{conf if isinstance(conf, (int, float)) else '—'}/100</code>")
    if signal.get("confirmationCheckPassed") and signal.get("confirmationCloseTime"):
        lines.append(f"✅ <b>Signal:</b> {fmt_time(signal['confirmationCloseTime'])} candle close")
    if signal.get("invalidationCondition"):
        lines.append(f"⛔ <b>Invalidation:</b> {signal['invalidationCondition']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- subscribers

def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def active_subscribers(db: Session) -> list[Subscriber]:
    now = datetime.now(timezone.utc)
    return [s for s in db.scalars(select(Subscriber)) if s.expires_at and _aware(s.expires_at) > now]


def activate(db: Session, chat_id: str, code: str, first_name: str = "") -> dict:
    key = db.get(ActivationKey, code.strip().upper()) or db.get(ActivationKey, code.strip())
    if not key or key.revoked:
        return {"success": False, "error": "Invalid code"}
    if not key.multi_use and key.used_count > 0:
        sub = db.get(Subscriber, chat_id)
        if not sub or sub.code != key.code:
            return {"success": False, "error": "Code already used"}
    now = datetime.now(timezone.utc)
    sub = db.get(Subscriber, chat_id) or Subscriber(chat_id=chat_id)
    sub.first_name = first_name or sub.first_name
    sub.code = key.code
    sub.activated_at = now
    sub.expires_at = now + timedelta(hours=key.duration_hours)
    sub.expired_notified = False
    db.merge(sub)
    key.used_count += 1
    db.commit()
    return {"success": True, "expiresAt": sub.expires_at.isoformat(), "label": key.label}


# ---------------------------------------------------------------- dispatch

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
    # Manual sends are allowed while the order is still valid; automatic sends only on the signal candle
    if not manual and not r["canNotify"]:
        return {"success": False, "state": state, "error": r["headline"]}
    if manual and setup["lifecycle"]["state"] not in ("PENDING", "OPEN"):
        return {"success": False, "state": state, "error": f"Order is {setup['lifecycle']['state']}: too late to send"}
    if setup["id"] in _in_flight:
        return {"success": False, "state": state, "error": "Already being sent"}
    with SessionLocal() as db:
        if db.get(Signal, setup["id"]):
            return {"success": False, "state": state, "error": "This setup was already sent."}
        cfg = get_setting(db, "telegram")
        if not cfg["enabled"] or not cfg["botToken"]:
            return {"success": False, "state": state, "error": "Telegram is disabled or has no bot token"}
        if cfg.get("assets") and symbol not in cfg["assets"]:
            return {"success": False, "state": state, "error": f"{symbol} is not in the Telegram asset list"}
        # Independent re-check: can only reject, never approve what the strategy rejected
        check = validate_signal(r)
        if not check["approved"]:
            return {"success": False, "state": state, "error": f"Validator rejected: {'; '.join(check['issues'])}"}
        recipients = {s.chat_id: s for s in active_subscribers(db)}
        if cfg["chatId"]:
            recipients.setdefault(str(cfg["chatId"]), None)
        if not recipients:
            return {"success": False, "state": state, "error": "No active subscribers"}
        signal = to_ai_signal(res)
        # Claim the setup in the database first: its id is the primary key, so two concurrent ticks
        # (serverless functions, several workers) can never both send it
        row = Signal(id=setup["id"], symbol=symbol, setup=setup["setup"], direction=setup["direction"], entry_type=setup["entryType"],
                     entry=setup["entry"], sl=setup["sl"], tp1=setup["tp1"], tp2=setup["tp2"], tp3=setup["tp3"], rr_tp2=setup["rrTp2"],
                     score=r["score"], signal_time=setup["signalTime"], recipients=0, state=setup["lifecycle"]["state"],
                     params=setup["params"], payload=signal)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"success": False, "state": state, "error": "This setup was already sent."}
        _in_flight.add(setup["id"])
        try:
            sent, first_ack, last_error = await _send_to_all(cfg, signal, recipients, db)
        finally:
            _in_flight.discard(setup["id"])
        if not sent:
            db.delete(row)  # nobody received it: release the claim so it can be retried
            db.commit()
            log_event("SIGNAL", f"{signal['signalType']} {symbol}", "No chat received it", False, last_error)
            return {"success": False, "state": state, "error": last_error or "Send failed", "signal": signal}
        latency = int(first_ack - setup["signalTime"] * 1000) if first_ack else None
        row.recipients, row.latency_ms = sent, latency
        db.commit()
        details = f"Entry {setup['entry']} | SL {setup['sl']} | TP2 {setup['tp2']} | {sent}/{len(recipients)} chat(s)"
        if latency is not None:
            details += f" | {latency / 1000:.1f}s after candle close"
        log_event("SIGNAL", f"{signal['signalType']} {symbol} ({r['score']})", details, True)
        return {"success": True, "state": state, "signal": signal, "recipients": sent, "latencyMs": latency}


async def _send_to_all(cfg: dict, signal: dict, recipients: dict, db: Session) -> tuple[int, Optional[float], Optional[str]]:
    """Parallel delivery in batches under Telegram's ~30 messages/second limit."""
    ids = list(recipients)
    sent = 0
    first_ack: Optional[float] = None
    last_error: Optional[str] = None
    marks: list[Watermark] = []
    for b in range(0, len(ids), BATCH):
        batch = ids[b:b + BATCH]

        async def one(chat_id: str):
            personal, offset, ref = personalize_signal(signal, chat_id, cfg.get("personalOffsets", True))
            text = f"{format_signal_message(personal)}\n🔐 <i>Personal copy · Ref {ref} · do not share</i>"
            out = await send_message(cfg["botToken"], chat_id, text, None, cfg.get("protectContent", True))
            return chat_id, out, offset, ref

        for chat_id, out, offset, ref in await asyncio.gather(*(one(c) for c in batch)):
            if out["success"]:
                sent += 1
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

HELP = """<b>EXUNU bot</b>
/start — activation
/status — your subscription
/signal — current analysis of XAUUSD and EURUSD
/stats — signal win rate
Send your activation code to activate."""


async def handle_update(token: str, upd: dict) -> None:
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    if not chat_id or not text:
        return
    name = (msg.get("from") or {}).get("first_name") or ""
    low = text.lower()
    with SessionLocal() as db:
        sub = db.get(Subscriber, chat_id)
        active = bool(sub and sub.expires_at and _aware(sub.expires_at) > datetime.now(timezone.utc))
        reply = None
        if low.startswith("/start"):
            reply = (f"👋 <b>{name}</b>, your access is active until <b>{_aware(sub.expires_at):%Y-%m-%d}</b>.\n\n{HELP}" if active
                     else f"👋 Welcome <b>{name}</b>!\n🔑 Send your <b>activation code</b> to receive the signals.\n\n{HELP}")
        elif low.startswith("/help"):
            reply = HELP
        elif low.startswith("/status"):
            reply = (f"✅ Active until <b>{_aware(sub.expires_at):%Y-%m-%d %H:%M} UTC</b>" if active
                     else "⛔ Not activated. Send your activation code.")
        elif low.startswith(("/signal", "/live", "/now")):
            reply = await _analysis_text()
        elif low.startswith(("/stats", "/winrate", "/performance")):
            s = stats(db.scalars(select(Signal)).all(), "signal")
            reply = (f"📊 <b>Signals</b>: {s['total']} sent · {s['closed']} closed · {s['open']} open\n"
                     f"✅ {s['wins']} wins · ❌ {s['losses']} losses · ➖ {s['breakevens']} BE\n"
                     f"🎯 Win rate: <b>{s['winRate'] if s['winRate'] is not None else '—'}%</b> · total {s['totalR']}R")
        elif re.fullmatch(r"[A-Za-z0-9\-_]{4,64}", text) and not text.startswith("/"):
            out = activate(db, chat_id, text, name)
            reply = (f"🎉 Activated ({out.get('label') or 'access'}) until <b>{out['expiresAt'][:10]}</b>."
                     if out["success"] else f"⛔ {out['error']}.")
        else:
            reply = HELP
    await send_message(token, chat_id, reply)


async def _analysis_text() -> str:
    parts = []
    for r in await both_results():
        s = r["setup"]
        parts.append(f"<b>{r['displaySymbol']}</b> · {r['status']} · score {r['score']}\n{r['headline']}"
                     + (f"\nEntry {s['entry']} · SL {s['sl']} · TP2 {s['tp2']}" if s and r["status"] in ("SIGNAL", "WATCH") else ""))
    return "\n\n".join(parts)


async def poll_forever(stop: asyncio.Event) -> None:
    """Long polling for chat commands. Only one process may poll a bot token at a time."""
    offset = 0
    while not stop.is_set():
        with SessionLocal() as db:
            token = get_setting(db, "telegram")["botToken"]
        if not token:
            await asyncio.sleep(30)
            continue
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


__all__ = ["dispatch_setup", "send_message", "bot_info", "format_signal_message", "activate", "active_subscribers", "trace_leak",
           "poll_forever", "history", "recent_signals", "market_session_status"]
