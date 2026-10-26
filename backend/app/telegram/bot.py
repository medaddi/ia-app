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
from ..strategies.service import STRATEGY_DEFS, get_strategy_result, normalize_symbol
from ..strategies.shared.news import load_news_calendar
from ..strategies.shared.jsnum import fmt_time, fmt_utc_minute, js_round, to_fixed
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


async def set_webhook(token: str, url: str, secret: str) -> dict:
    """Register Telegram command delivery for a serverless deployment."""
    if not token or not url or not secret:
        return {"success": False, "error": "Telegram webhook URL and secret are required"}
    data = await call(token, "setWebhook", {"url": url, "secret_token": secret, "allowed_updates": ["message"]})
    return {"success": bool(data.get("ok")), "error": data.get("description")}


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
    lines.append(f"🧠 <code>{signal.get('strategyUsed') or 'LiquidityDissection'}</code>")
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
        recipients = {s.chat_id: s for s in active_subscribers(db) if not s.muted}
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

COMMANDS = [
    ("start", "Activation and welcome"),
    ("signal", "Current analysis of every pair"),
    ("gold", "Gold (XAU/USD) analysis"),
    ("euro", "EUR/USD analysis"),
    ("gbp", "GBP/USD analysis"),
    ("open", "Signals still running"),
    ("history", "Last 10 signals and their result"),
    ("stats", "Win rate and results (30 days and all time)"),
    ("levels", "Key levels of every pair"),
    ("news", "Next high-impact news"),
    ("market", "Market hours and current session"),
    ("rules", "How the strategies work"),
    ("status", "Your subscription"),
    ("stop", "Pause signals"),
    ("resume", "Resume signals"),
    ("myid", "Your Telegram chat id"),
    ("help", "All commands"),
]
HELP = "<b>LiquidityDissection bot</b>\n" + "\n".join(f"/{c} — {d}" for c, d in COMMANDS) + "\nSend your activation code to activate."
PAIR_ALIASES = {"/gold": "XAU/USD", "/xau": "XAU/USD", "/euro": "EUR/USD", "/eur": "EUR/USD", "/gbp": "GBP/USD", "/cable": "GBP/USD", "/pound": "GBP/USD"}
STATE_TXT = {"PENDING": "⏳ pending", "OPEN": "🟡 open", "TP1_HIT": "🟢 TP1 hit, SL at entry", "TP2_HIT": "🟢 TP2 hit", "CLOSED": "closed",
             "CANCELLED": "⚪ cancelled", "EXPIRED": "⚪ expired"}


async def set_commands(token: str) -> None:
    """Shows the commands in Telegram's "/" menu."""
    await call(token, "setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMMANDS]})


def _res(sig: Signal) -> str:
    if sig.state == "CLOSED":
        icon = "✅" if sig.outcome == "WIN" else "❌" if sig.outcome == "LOSS" else "➖"
        return f"{icon} {sig.outcome} {sig.r_multiple:+.2f}R" if sig.r_multiple is not None else f"{icon} {sig.outcome}"
    return STATE_TXT.get(sig.state, sig.state)


def _p(sym: str, v: float) -> str:
    return to_fixed(v, 2 if sym == "XAU/USD" else 5)


async def _pair_text(sym: str, detailed: bool = False) -> str:
    r = (await get_strategy_result(sym))["result"]
    s = r["setup"]
    lines = [f"<b>{r['displaySymbol']}</b> · {r['strategyName'].split('·')[-1].strip()}",
             f"Price <code>{_p(sym, r['price'])}</code> · Bias <b>{r['bias']['direction']}</b>",
             f"Status: <b>{r['status']}</b>" + (f" · score {r['score']}" if r["setup"] else ""),
             r["headline"]]
    if s and r["status"] in ("SIGNAL", "WATCH"):
        lines.append(f"{s['direction']} {s['entryType']} <code>{_p(sym, s['entry'])}</code> · SL <code>{_p(sym, s['sl'])}</code> · "
                     f"TP1 <code>{_p(sym, s['tp1'])}</code> · TP2 <code>{_p(sym, s['tp2'])}</code> · TP3 <code>{_p(sym, s['tp3'])}</code> · "
                     f"{STATE_TXT.get(s['lifecycle']['state'], s['lifecycle']['state'])}")
    if detailed:
        lines.append("\n".join(f"{'✔' if c['passed'] else '✘'} {c['rule']}" for c in r["checklist"]))
    return "\n".join(lines)


async def _levels_text() -> str:
    out = []
    for sym in STRATEGY_DEFS:
        f = (await get_strategy_result(sym))["result"]["facts"] or {}
        lv = " · ".join(f"{x.get('label') or x['kind']} <code>{_p(sym, x['price'])}</code>" for x in (f.get("levels") or [])[:6])
        rng = f.get("range20h")
        extra = f"\n20h high <code>{_p(sym, rng['high'])}</code> · 20h low <code>{_p(sym, rng['low'])}</code>" if rng else ""
        out.append(f"<b>{sym}</b>\n{lv or '—'}{extra}")
    return "\n\n".join(out)


async def _news_text() -> str:
    cal = await load_news_calendar()
    now = int(time.time())
    up = sorted((e for e in cal["events"] if e["time"] > now - 1800 and e.get("impact") == "High" and e.get("currency") in ("USD", "EUR", "GBP")),
                key=lambda e: e["time"])[:8]
    if not up:
        return "📰 No high-impact USD/EUR/GBP news in the calendar."
    return "📰 <b>High-impact news (UTC)</b>\n" + "\n".join(f"{fmt_utc_minute(e['time'])} · {e['currency']} {e['title']}" for e in up) + \
        "\n<i>No signal is sent 30 min before and after these.</i>"


def _market_text() -> str:
    now = datetime.now(timezone.utc)
    m = now.hour * 60 + now.minute
    session = "Asia" if m < 7 * 60 else "London" if m < 12 * 60 else "London / New York" if m < 16 * 60 else "New York" if m < 21 * 60 else "Rollover"
    st = market_session_status("XAU/USD")
    return (f"🕒 {now:%a %H:%M} UTC · {'🟢 market open' if st['isOpen'] else '🔴 market closed'}\nSession: <b>{session}</b>\n"
            "Forex and gold trade Sunday 22:00 → Friday 21:00 UTC.")


RULES = """<b>How the signals work</b>
🥇 <b>Gold (H1 Trend Breakout)</b>: trend by EMA50 vs EMA200; an H1 candle closes beyond the 20-hour high/low with a strong body → market entry. SL beyond the last 4 candles (1–3× ATR). TP1 1R (close 50%, SL to entry), TP2 2R, TP3 3R.
💶 <b>EUR/USD and 💷 GBP/USD (Trend Pullback, same rules)</b>: H4 trend; pullback into H1 order block / Fib 50–61.8% / EMA50 with an engulfing, pin bar or CHoCH on M15 → market entry. TP1 1R, TP2 next H1 level (≥ 2R), runner trails.
Only signals with every rule passed and a score ≥ 75 are sent, at the candle close. No signal around high-impact news.
⚠️ Past results do not guarantee future results: risk only what you can lose."""


async def handle_update(token: str, upd: dict) -> None:
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    if not chat_id or not text:
        return
    name = (msg.get("from") or {}).get("first_name") or ""
    cmd = text.split()[0].split("@")[0].lower()
    with SessionLocal() as db:
        sub = db.get(Subscriber, chat_id)
        active = bool(sub and sub.expires_at and _aware(sub.expires_at) > datetime.now(timezone.utc))
        if cmd == "/start":
            reply = (f"👋 <b>{name}</b>, your access is active until <b>{_aware(sub.expires_at):%Y-%m-%d}</b>.\n\n{HELP}" if active
                     else f"👋 Welcome <b>{name}</b>!\n🔑 Send your <b>activation code</b> to receive the signals.\n\n{HELP}")
        elif cmd == "/help":
            reply = HELP
        elif cmd == "/myid":
            reply = f"🆔 Your chat id: <code>{chat_id}</code>"
        elif cmd == "/status":
            reply = ((f"✅ Active until <b>{_aware(sub.expires_at):%Y-%m-%d %H:%M} UTC</b>"
                      + ("\n⏸ Signals paused: send /resume" if sub.muted else "")) if active else "⛔ Not activated. Send your activation code.")
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
            reply = RULES
        elif cmd == "/news":
            reply = await _news_text()
        elif cmd == "/levels":
            reply = await _levels_text()
        elif cmd in ("/signal", "/live", "/now", "/analysis"):
            reply = "\n\n".join([await _pair_text(sym) for sym in STRATEGY_DEFS])
        elif cmd in PAIR_ALIASES:
            reply = await _pair_text(PAIR_ALIASES[cmd], detailed=True)
        elif cmd in ("/open", "/running", "/trades"):
            rows = db.scalars(select(Signal).where(Signal.state.not_in(("CLOSED", "CANCELLED", "EXPIRED"))).order_by(Signal.sent_at.desc())).all()
            reply = ("🟡 <b>Running signals</b>\n" + "\n".join(
                f"{x.symbol} {x.direction} <code>{_p(x.symbol, x.entry)}</code> · SL <code>{_p(x.symbol, x.sl)}</code> · TP2 <code>{_p(x.symbol, x.tp2)}</code> · {_res(x)}"
                for x in rows)) if rows else "No signal running right now."
        elif cmd in ("/history", "/last"):
            rows = db.scalars(select(Signal).order_by(Signal.sent_at.desc()).limit(10)).all()
            reply = ("🗂 <b>Last signals</b>\n" + "\n".join(
                f"{x.sent_at:%m-%d %H:%M} {x.symbol} {x.direction} <code>{_p(x.symbol, x.entry)}</code> · {_res(x)}" for x in rows)) if rows else "No signal sent yet."
        elif cmd in ("/stats", "/winrate", "/performance", "/results"):
            all_rows = db.scalars(select(Signal)).all()
            since = datetime.now(timezone.utc) - timedelta(days=30)
            recent = [x for x in all_rows if _aware(x.sent_at) >= since]

            def block(title, rows):
                s = stats(rows, "signal")
                per = " · ".join(f"{k} {v['winRate'] if v['winRate'] is not None else '—'}% ({v['totalR']:+}R)" for k, v in s["bySymbol"].items())
                return (f"<b>{title}</b>: {s['total']} signals · {s['closed']} closed · {s['open']} open\n"
                        f"✅ {s['wins']} · ❌ {s['losses']} · ➖ {s['breakevens']} · win rate <b>{s['winRate'] if s['winRate'] is not None else '—'}%</b> · "
                        f"total <b>{s['totalR']:+}R</b>" + (f"\n{per}" if per else ""))
            reply = f"📊 {block('Last 30 days', recent)}\n\n{block('All time', all_rows)}"
        elif re.fullmatch(r"[A-Za-z0-9\-_]{4,64}", text) and not text.startswith("/"):
            out = activate(db, chat_id, text, name)
            reply = (f"🎉 Activated ({out.get('label') or 'access'}) until <b>{out['expiresAt'][:10]}</b>. Send /help to see the commands."
                     if out["success"] else f"⛔ {out['error']}.")
        else:
            reply = HELP
    await send_message(token, chat_id, reply)


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


__all__ = ["dispatch_setup", "send_message", "bot_info", "set_webhook", "handle_update", "format_signal_message", "activate", "active_subscribers", "trace_leak",
           "poll_forever", "history", "recent_signals", "market_session_status"]
