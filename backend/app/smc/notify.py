"""
The notifier: every minute each pair's team is read again; a NEW setup that passes its rules and the 7 questions is saved
once (signals table, id = the setup) and sent once, to Telegram (every account linked to the bot, plus the admin chat)
and as a push to every approved account's devices. A setup already sent is never sent again.
Research, not advice: the message says so.
"""

import html
import time
from datetime import datetime, timezone

from sqlalchemy import or_, select

from ..config import settings
from ..db import SessionLocal
from ..market.data import market_session_status
from ..models import PushSubscription, Signal, User
from ..push import send_push
from ..store import get_setting, set_setting
from ..telegram import bot
from .desk import BY_SYMBOL, PAIRS, team


def _f(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def message(s: dict, pair: str, dec: int) -> str:
    buy = s["direction"] == "BUY"
    until = datetime.fromtimestamp(s["validUntil"], timezone.utc).strftime("%H:%M")
    return (f"{'🟢' if buy else '🔴'} <b>{s['direction']} {pair}</b> · {s['strategy']} {html.escape(s['name'])}\n"
            f"{bot.LINE}\n"
            f"Limit <code>{_f(s['entry'], dec)}</code>\nSL <code>{_f(s['sl'], dec)}</code>\nTP <code>{_f(s['tp'], dec)}</code>\n"
            f"RR 1:{s['rr']} · 7/7 questions ✅ · valid until {until} UTC\n"
            f"1 % risk: {s['lots']['1000']} lot per $1,000 · {s['lots']['10000']} per $10,000\n\n"
            "<i>Research setup, not financial advice. Check it on the chart before any trade.</i>")


def _app_link(pair: str) -> str:
    return f"{settings.public_app_url or 'http://localhost:3000'}/?symbol={pair}"


async def _send(pair: str, s: dict) -> dict:
    dec = BY_SYMBOL[pair]["decimals"]
    text = message(s, pair, dec)
    url = _app_link(pair)
    markup = None if ("localhost" in url or "127.0.0.1" in url) else {"inline_keyboard": [[{"text": "📈 Open in the app", "url": url}]]}
    tg_sent = pushed = 0
    with SessionLocal() as db:
        cfg = get_setting(db, "telegram")
        token = cfg.get("botToken")
        if token and cfg.get("enabled", True):
            chats = {x.chat_id for x in bot.active_subscribers(db) if not x.muted}
            if cfg.get("chatId"):
                chats.add(str(cfg["chatId"]))
            for chat in chats:
                out = await bot.send_message(token, chat, text, markup)
                tg_sent += bool(out.get("success"))
        rows = db.scalars(select(PushSubscription).join(User, User.id == PushSubscription.user_id)
                          .where(User.active.is_(True), or_(User.status.is_(None), User.status != "pending"))).all()
        if rows:
            pushed = await send_push(db, list(rows), {"title": f"{'🟢' if s['direction'] == 'BUY' else '🔴'} {s['direction']} {pair} · {s['strategy']}",
                                                      "body": f"Limit {_f(s['entry'], dec)} | SL {_f(s['sl'], dec)} | TP {_f(s['tp'], dec)} | 1:{s['rr']}",
                                                      "tag": f"ld-{s['id']}", "symbol": pair})
    return {"telegram": tg_sent, "push": pushed}


def _claim(pair: str, s: dict) -> bool:
    """Saves the setup once; False when it was already saved (already sent)."""
    with SessionLocal() as db:
        if db.get(Signal, s["id"]):
            return False
        db.add(Signal(id=s["id"], symbol=pair, setup=s["strategy"], direction=s["direction"], entry_type="LIMIT", entry=s["entry"], sl=s["sl"],
                      tp1=s["tp"], tp2=s["tp"], tp3=s["tp"], rr_tp2=s["rr"], score=7, signal_time=s["time"], state="PENDING",
                      params={"validUntil": s["validUntil"], "lots": s["lots"]}, payload=s))
        db.commit()
        return True


async def tick() -> dict:
    """One pass over the six teams. Called every minute (the in-process loop, or the host's cron)."""
    started = time.time()
    results: dict[str, str] = {}
    for pair in PAIRS:
        if not market_session_status(pair)["isOpen"]:
            results[pair] = "market closed"
            continue
        try:
            t = await team(pair, fresh=True)
        except Exception as err:  # one pair failing never stops the others
            results[pair] = f"error: {err!r}"
            continue
        if not t.get("success"):
            results[pair] = t.get("error") or "no read"
            continue
        sent = []
        for s in t["signals"]:
            if _claim(pair, s):
                out = await _send(pair, s)
                sent.append(f"{s['strategy']} {s['direction']} → telegram {out['telegram']} · push {out['push']}")
        results[pair] = "; ".join(sent) if sent else ("watching" if not t["signals"] else "signal already sent")
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
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%")).order_by(Signal.signal_time.desc()).limit(limit)).all()
        return [{**(r.payload or {}), "symbol": r.symbol, "sentAt": r.sent_at.isoformat() if r.sent_at else None} for r in rows]
