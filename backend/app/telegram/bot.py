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
from ..market.data import FX_TICKERS, market_session_status
from ..models import ActivationKey, Signal, Subscriber, User, Watermark
from ..store import get_setting
from ..strategies.exunu import run_exunu, to_ai_signal
from ..strategies.service import STRATEGY_DEFS, get_strategy_result, normalize_symbol
from ..strategies.shared.news import load_news_calendar
from ..strategies.shared.jsnum import fmt_time, fmt_utc_minute, js_round, to_fixed
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
            "single": sj.get("setup") in ("GPA", "BREAK_RETEST", "REVERSION") and tp3 is not None,  # one target (forex set & forget, gold reversion)
            "orderType": sj.get("entry_type") or signal.get("entryType") or "LIMIT", "expires": sj.get("expires_at"),
            "decimals": 2 if gold else 5, "pip": 0.1 if gold else 0.0001}


def format_signal_message(signal: dict, lot: Optional[dict] = None, ref: Optional[str] = None) -> str:
    """Short message: side, entry, SL, target(s) and this person's lot. Prices are tap-to-copy for MetaTrader.
    `lot`: None = no lot line (a group chat), {} = subscriber without a risk set, else lot_for_risk()."""
    L = _levels(signal)
    if not L:
        return f"⚠️ {normalize_symbol(signal.get('symbol', ''))}: signal levels incomplete, not sent."
    entry, sl = L["entry"], L["sl"]
    risk = abs(entry - sl)
    c = lambda v: f"<code>{to_fixed(v, L['decimals'])}</code>"  # noqa: E731
    pips = lambda v: int(js_round(abs(v - entry) / L["pip"]))  # noqa: E731
    rr_of = lambda v: to_fixed(abs(v - entry) / risk, 1) if risk > 0 else "—"  # noqa: E731
    order = "" if L["orderType"] == "MARKET" else f" {L['orderType'].lower()}"
    lines = [f"{'🟢' if L['buy'] else '🔴'} <b>{'BUY' if L['buy'] else 'SELL'}{order} {L['symbol']}</b>", "",
             f"Entry {c(entry)}", f"SL {c(sl)} · {pips(sl)} pips"]
    if L["single"]:
        lines.append(f"TP {c(L['tp3'])} · 1:{rr_of(L['tp3'])}")
    else:
        lines.append(f"TP1 {c(L['tp1'])} · close 50%, SL → entry")
        lines.append(f"TP2 {c(L['tp2'])} · 1:{rr_of(L['tp2'])}")
        if L["tp3"] is not None:
            lines.append(f"TP3 {c(L['tp3'])} · 1:{rr_of(L['tp3'])}")
    grade = signal.get("grade")
    if grade:
        lines.append(f"Grade <b>{grade}</b> · {signal.get('confidence')}%")
    if lot and lot.get("lots"):
        warn = " · min lot, above your risk" if lot["tooSmall"] else ""
        lines.append(f"Lot <code>{lot['lots']:.2f}</code> · risk ${lot['actualRisk']:g}{warn}")
    elif lot is not None:
        lines.append("Lot: send /risk 80 to get your lot for $80")
    if L["orderType"] == "LIMIT" and L["expires"]:
        lines.append(f"⏱ valid until {L['expires'][11:16]} UTC")
    if ref:
        lines.append(f"\n🔐 <i>Personal copy · Ref {ref}</i>")
    return "\n".join(lines)


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


LINK_RE = re.compile(r"LD-?([A-HJ-NP-Z2-9]{6})", re.I)


def link_account(db: Session, chat_id: str, code: str, first_name: str) -> str:
    """Links the app account that generated `code` to this chat; the account then receives the signals with its own risk."""
    m = LINK_RE.fullmatch(code.strip())
    if not m:
        return "⛔ Invalid link code."
    full = f"LD-{m.group(1).upper()}"
    u = db.scalar(select(User).where(User.telegram_link_code == full))
    if not u or not u.active or (u.telegram_link_expires or 0) < time.time():
        return "⛔ This link code is invalid or expired. Generate a new one in the app (Account → Telegram)."
    for other in db.scalars(select(User).where(User.telegram_chat_id == chat_id, User.id != u.id)):
        other.telegram_chat_id = None  # one account per chat
    u.telegram_chat_id, u.telegram_link_code, u.telegram_link_expires = chat_id, None, None
    now = datetime.now(timezone.utc)
    sub = db.get(Subscriber, chat_id) or Subscriber(chat_id=chat_id)
    sub.first_name = first_name or sub.first_name
    if not sub.expires_at or _aware(sub.expires_at) < now:  # app accounts are created by the admin: they get access
        sub.code, sub.activated_at, sub.expires_at, sub.expired_notified = "ACCOUNT", now, now + timedelta(days=3650), False
    sub.risk_usd, sub.capital, sub.risk_pct, sub.muted = u.risk_usd, u.capital or 0, u.risk_pct, False
    db.merge(sub)
    db.commit()
    risk = effective_risk(u.risk_usd, u.capital, u.risk_pct)
    how = (f"${risk:g} per trade" + (f" ({u.risk_pct:g}% of ${u.capital:g})" if not u.risk_usd and u.capital else "")) if risk else "not set yet (/risk 80 or /risk 1%)"
    return (f"✅ Linked to <b>{u.username}</b>.\nRisk: <b>{how}</b> · every signal comes with your lot.\n"
            "Change it in the app (Account) or here with /risk and /capital.")


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
    *((pair.replace("/", "").lower(), f"{pair} analysis") for pair in FX_TICKERS if pair not in ("EUR/USD", "GBP/USD")),
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
    ("risk", "Your risk per trade: /risk 80 ($) or /risk 1% (of your capital)"),
    ("capital", "Your capital in $ (/capital 5000), for a risk in %"),
    ("myid", "Your Telegram chat id"),
    ("help", "All commands"),
]
HELP = "<b>LiquidityDissection bot</b>\n" + "\n".join(f"/{c} — {d}" for c, d in COMMANDS) + "\nSend your activation code to activate."
NEWS_CCYS = {"USD", *(c for pair in FX_TICKERS for c in pair.split("/"))}
PAIR_ALIASES = {"/gold": "XAU/USD", "/xau": "XAU/USD", "/euro": "EUR/USD", "/eur": "EUR/USD", "/gbp": "GBP/USD", "/cable": "GBP/USD", "/pound": "GBP/USD",
                "/loonie": "USD/CAD", "/kiwi": "NZD/USD", **{"/" + pair.replace("/", "").lower(): pair for pair in FX_TICKERS}}
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
        return "📰 No high-impact news for the app's currencies in the calendar."
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
🥇 <b>Gold: two engines, one trade at a time</b>. Trend by EMA50 vs EMA200. <b>Breakout</b>: an H1 candle closes beyond the 20-hour high/low with a strong body → TP1 1R (close 50%, SL to entry), TP2 2R, TP3 3R. <b>Bollinger reversion</b> (London / New York): a close beyond the 2.2σ band against the trend, then a candle back inside with the trend → one target at 1R, closed after 24 H1 candles. 2 years: 59% winners, +49.9R.
💱 <b>Forex: EUR/USD, GBP/USD, USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD, AUD/CHF (FXAlexG Set &amp; Forget GPA)</b>: trend on W1, D1 and H4 by structure (body close only), trade the majority. Areas of interest only on W1 / D1 with 3+ touches. Entry after the AOI touch, an H4 rejection and a 30m engulfing at the London or New York open. SL beyond the pattern head, TP at the next W1 / D1 zone before a round level, minimum 1:2. Set &amp; forget.
🎓 Grade: 10 confluences × 10% → A+ 80%+, B 70%+, C+ 60%+ (minimum). Below 60%: no signal.
Only signals with every rule passed and a score ≥ 75 are sent, at the candle close. No signal around high-impact news.
⚠️ Past results do not guarantee future results: risk only what you can lose."""


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
    name = (msg.get("from") or {}).get("first_name") or ""
    cmd = text.split()[0].split("@")[0].lower()
    with SessionLocal() as db:
        sub = db.get(Subscriber, chat_id)
        active = bool(sub and sub.expires_at and _aware(sub.expires_at) > datetime.now(timezone.utc))
        start_arg = text.split(maxsplit=1)[1] if cmd == "/start" and len(text.split()) > 1 else ""
        if cmd == "/start" and start_arg and LINK_RE.fullmatch(start_arg):
            reply = link_account(db, chat_id, start_arg, name)  # t.me/<bot>?start=LDXXXXXX from the app
        elif LINK_RE.fullmatch(text):
            reply = link_account(db, chat_id, text, name)
        elif cmd == "/start":
            reply = (f"👋 <b>{name}</b>, your access is active until <b>{_aware(sub.expires_at):%Y-%m-%d}</b>.\n\n{HELP}" if active
                     else f"👋 Welcome <b>{name}</b>!\n🔑 Send your <b>activation code</b> to receive the signals.\n\n{HELP}")
        elif cmd == "/help":
            reply = HELP
        elif cmd == "/myid":
            reply = f"🆔 Your chat id: <code>{chat_id}</code>"
        elif cmd == "/risk":
            reply = _risk_reply(db, sub, active, text)
        elif cmd == "/capital":
            reply = _capital_reply(db, sub, active, text)
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
