"""
The notifier: every minute the 29 teams are read again and two kinds of alerts go out, each to Telegram (every chat
linked to an approved account, plus the admin chat), as a web push to every approved account's devices, and into the
app's live feed (/api/smc/signals):

  SIGNAL_EXECUTE       the full Set & Forget trade, once: the desk executes and the portfolio check agrees.
  MANAGER_LIVE_UPDATE  every step of a sent trade (manager.py): FILLED, BREAKEVEN LOCKED, TP HIT, SL HIT, CLOSED.

The radar (AOI_WATCH_ALERT: inside a zone, the trigger still missing) is NOT a notification any more (the owner,
2026-11-11): nothing about it goes to Telegram, to web push or to the app's feed. The team read still carries its
`radar` field (the "Watching" status of a setup row on the pair's own card), and what was stored before is left as it is.

Research, not advice: every message says so. Nothing here places an order.
"""

import asyncio
import html
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_, select

from ..config import settings
from ..db import SessionLocal
from ..market.data import market_session_status
from ..models import PushSubscription, Signal, User
from ..push import send_push
from ..store import get_setting, set_setting
from ..telegram import bot
from .desk import BY_SYMBOL, PAIRS, team
from .skill import portfolio

RULE = "━━━━━━━━━━━━━━━━━━"
READ_AT_ONCE = 8  # the spec: 29 teams read 8 at a time (asyncio.Semaphore(8))


def _f(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def message(s: dict, pair: str, dec: int) -> str:
    """SIGNAL_EXECUTE, short (the owner's prompt, 2026-11-11): symbol, side, grade, entry, stop, target, R:R, timeframe,
    UTC time, the signal id, and the copy payload as plain text (Telegram's "Copy setup data" button copies the same).
    It holds market data only: never anyone's USD risk or lot. A private chat gets its own line under it (personal_line)."""
    from .signal_copy import payload
    t = datetime.fromtimestamp(int(s["time"]), timezone.utc)
    return "\n".join([
        f"🎯 <b>{pair} — {s['direction']}</b> · Grade {s.get('grade', '?')}",
        f"Entry <code>{_f(s['entry'], dec)}</code> | SL <code>{_f(s['sl'], dec)}</code> | TP <code>{_f(s['tp'], dec)}</code> | R:R 1:{s['rr']:.1f}",
        f"{s.get('etf') or 'H1'} | {t.strftime('%H:%M')} UTC {t.strftime('%d %b')} · {html.escape(s.get('setupType') or s['strategy'])} · ID <code>{html.escape(s['id'])}</code>",
        f"<code>{html.escape(payload(s, pair))}</code>",
        "<i>Research signal — not an order. Stop fixed for this signal. Not financial advice.</i>"])


def copy_markup(s: dict, pair: str, url: Optional[str]) -> dict:
    """The one-tap copy button (Bot API 7.11+ InlineKeyboardButton.copy_text, which the bot sends as raw Bot API JSON),
    plus "Open in the app" when the app has a public address. Clients without copy buttons still have the plain-text line."""
    from .signal_copy import payload
    row = [{"text": "📋 Copy setup data", "copy_text": {"text": payload(s, pair)}}]
    if url:
        row.append({"text": "📈 Open in the app", "url": url})
    return {"inline_keyboard": [row]}


async def personal_line(db, chat: str, sig_id: str) -> Optional[str]:
    """The lot of THE user this private chat is linked to, from that user's own USD risk (saved as their snapshot).
    None for a group, a channel or a chat no account owns: a shared chat never sees anyone's risk or lot."""
    if not chat or str(chat).startswith("-"):  # groups and channels have negative ids
        return None
    u = bot.account_of(db, str(chat))
    sig = db.get(Signal, sig_id)
    if not u or not sig:
        return None
    from .sizing import size_for
    z = await size_for(db, u, sig, source="telegram")
    if z.get("status") != "ok":
        return f"👤 <b>Your size:</b> unavailable — {html.escape(z.get('reason') or '')}"
    return (f"👤 <b>Your size:</b> <code>{z['lots']:g}</code> lot for your ${z['riskUsd']:g} risk "
            f"(est. loss at the stop ${z['estLossUsd']:g}, costs included) — from your profile only")


def _app_link(pair: str) -> str:
    return f"{settings.public_app_url or 'http://localhost:3000'}/?symbol={pair}"


async def broadcast(pair: str, text: str, title: str, body: str, tag: str, signal: Optional[dict] = None) -> dict:
    """One message to every chat linked to an approved account (+ the admin chat) and a push to every approved account's
    devices. With `signal`: the copy button, and in each linked PRIVATE chat (not the admin chat) that user's own lot."""
    url = _app_link(pair)
    public = None if ("localhost" in url or "127.0.0.1" in url) else url
    markup = copy_markup(signal, pair, public) if signal else ({"inline_keyboard": [[{"text": "📈 Open in the app", "url": public}]]} if public else None)
    tg_sent = pushed = 0
    with SessionLocal() as db:
        cfg = get_setting(db, "telegram")
        token = cfg.get("botToken")
        if token and cfg.get("enabled", True):
            chats = {x.chat_id for x in bot.active_subscribers(db) if not x.muted}
            if cfg.get("chatId"):
                chats.add(str(cfg["chatId"]))
            admin_chat = str(cfg.get("chatId") or "")
            for chat in chats:
                mine = await personal_line(db, chat, signal["id"]) if signal and chat != admin_chat else None
                out = await bot.send_message(token, chat, text + ("\n" + mine if mine else ""), markup)
                tg_sent += bool(out.get("success"))
        rows = db.scalars(select(PushSubscription).join(User, User.id == PushSubscription.user_id)
                          .where(User.active.is_(True), or_(User.status.is_(None), User.status != "pending"))).all()
        if rows:
            pushed = await send_push(db, list(rows), {"title": title, "body": body, "tag": tag, "symbol": pair})
    return {"telegram": tg_sent, "push": pushed}


async def _send(pair: str, s: dict) -> dict:
    dec = BY_SYMBOL[pair]["decimals"]
    return await broadcast(pair, message(s, pair, dec), f"🎯 {s['direction']} {pair} · Grade {s.get('grade', '?')}",
                           f"Entry {_f(s['entry'], dec)} | SL {_f(s['sl'], dec)} | TP {_f(s['tp'], dec)} | 1:{s['rr']} · {s.get('etf') or 'H1'}", f"ld-{s['id']}", s)


def _claim(pair: str, s: dict, state: str = "PENDING") -> bool:
    """Saves the setup once; False when it was already saved (already sent, or already blocked)."""
    with SessionLocal() as db:
        if db.get(Signal, s["id"]):
            return False
        db.add(Signal(id=s["id"], symbol=pair, setup=s["strategy"], direction=s["direction"], entry_type="MARKET" if s.get("market") else "LIMIT",
                      entry=s["entry"], sl=s["sl"], tp1=s.get("tp1") or s["tp"], tp2=s["tp"], tp3=s["tp"], rr_tp2=s["rr"], score=s.get("gpa") or 0,
                      signal_time=s["time"], state=state, params={"validUntil": s["validUntil"], "lots": s["lots"]}, payload=s))
        db.commit()
        return True


def _seen(sid: str) -> bool:
    with SessionLocal() as db:
        return db.get(Signal, sid) is not None


def sent_setups(limit: int = 80) -> list[dict]:
    """The setups actually sent (not the blocked ones), newest first: what the portfolio check counts as live."""
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state != "BLOCKED").order_by(Signal.signal_time.desc()).limit(limit)).all()
        return [{**(r.payload or {}), "symbol": r.symbol, "state": r.state} for r in rows]


async def tick() -> dict:
    """One pass over the 29 teams. Called every minute (the in-process loop, or the host's cron)."""
    started = time.time()
    results: dict[str, str] = {}
    open_pairs = [p for p in PAIRS if market_session_status(p)["isOpen"]]
    gate = asyncio.Semaphore(READ_AT_ONCE)

    async def read(pair: str):
        async with gate:
            try:
                return await team(pair, fresh=True)
            except Exception as err:  # one pair failing never stops the others
                return err
    reads = dict(zip(open_pairs, await asyncio.gather(*(read(p) for p in open_pairs))))  # the feeds are fetched side by side
    for pair in PAIRS:
        if pair not in reads:
            results[pair] = "market closed"
            continue
        t = reads[pair]
        if isinstance(t, Exception):
            results[pair] = f"error: {t!r}"
            continue
        if not t.get("success"):
            results[pair] = t.get("error") or "no read"
            continue
        notes = []
        for s in t["signals"]:  # a radar read (t["radar"]) is never sent anywhere
            if _seen(s["id"]):
                continue
            chk = portfolio.check(pair, s, sent_setups(), int(time.time()))
            if chk["verdict"] == "BLOCK":  # saved with its reasons, never sent, never checked again
                _claim(pair, {**s, "portfolio": chk}, state="BLOCKED")
                notes.append(f"{s['direction']} BLOCKED by the portfolio check: {'; '.join(chk['reasons'])}")
                continue
            if chk.get("riskPct", 1.0) < 1.0:  # two correlated trades the same way: the risk is split
                k = chk["riskPct"]
                s = {**s, "riskPct": round(s.get("riskPct", 1.0) * k, 3), "riskNote": "; ".join(chk.get("notes") or []),
                     "lots": {q: int(v * k * 100 + 1e-6) / 100 for q, v in s["lots"].items()}}
            if _claim(pair, {**s, "portfolio": chk}):
                out = await _send(pair, s)
                notes.append(f"{s['direction']} {s.get('setupType')} grade {s.get('grade')} → telegram {out['telegram']} · push {out['push']}")
        results[pair] = "; ".join(notes) if notes else (t.get("decision") or "watching").lower()
    try:  # the trade manager
        from .manager import manage_all
        steps = await manage_all(broadcast)
        if steps:
            results["manager"] = "; ".join(f"{k.split('-')[1]} {'/'.join(v)}" for k, v in steps.items())
    except Exception as err:  # managing never stops the teams
        results["manager"] = f"error: {err!r}"
    try:
        with SessionLocal() as db:
            prev = get_setting(db, "engine")
            set_setting(db, "engine", {"lastTickAt": int(started), "durationSec": round(time.time() - started, 1), "results": results,
                                       "ticks": int(prev.get("ticks") or 0) + 1})
    except Exception as err:  # the heartbeat never breaks a tick
        print(f"[smc] heartbeat: {err!r}")
    return results


def recent(limit: int = 30) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state != "BLOCKED").order_by(Signal.signal_time.desc()).limit(limit)).all()
        return [{**(r.payload or {}), "symbol": r.symbol, "sentAt": r.sent_at.isoformat() if r.sent_at else None, "status": r.state,
                 "outcome": r.outcome, "resultR": r.r_multiple, "events": (r.params or {}).get("events", [])} for r in rows]

