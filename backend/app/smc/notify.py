"""
The notifier: every minute each pair's team is read again; a NEW setup that passes its rules and the 7 questions, then the
trader-skill's portfolio risk check across all the teams (skill/portfolio.py: one trade per pair, at most 2 bets the same
way on the dollar, 3 % total risk, 5 a day), is saved once (signals table, id = the setup) and sent once, to Telegram (every account linked to the bot, plus the admin chat)
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
from .skill import portfolio


def _f(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def message(s: dict, pair: str, dec: int) -> str:
    buy = s["direction"] == "BUY"
    until = datetime.fromtimestamp(s["validUntil"], timezone.utc).strftime("%H:%M")
    s = {"zone": [s["entry"], s["entry"]], "rrBest": s["rr"], **s}  # a setup saved before the entry zone existed
    side = "Buy" if buy else "Sell"
    if s.get("market"):  # the playbook's market entries: on the trigger candle's close
        entry = f"{side} at market <code>{_f(s['entry'], dec)}</code> (the trigger candle's close)\n"
    else:
        entry = (f"{side} zone <code>{_f(s['zone'][0], dec)} – {_f(s['zone'][1], dec)}</code>\n"
                 f"(limit at <code>{_f(s['entry'], dec)}</code>, the near edge: filled once price comes into the zone, valid until {until} UTC)\n")
    tp1 = f"TP1 <code>{_f(s['tp1'], dec)}</code> (close {round(s.get('part', 1) * 100)} %, stop to entry)\n" if s.get("tp1") is not None else ""
    rr = f"RR 1:{s['rr']}" + (f" at the limit, up to 1:{s['rrBest']} deeper in the zone" if s["rrBest"] > s["rr"] else "")
    n = len(s.get("checklist") or []) or 7
    return (f"{'🟢' if buy else '🔴'} <b>{s['direction']} {pair}</b> · {html.escape(s['name'])}\n"
            f"{bot.LINE}\n"
            f"{entry}SL <code>{_f(s['sl'], dec)}</code>\n{tp1}TP <code>{_f(s['tp'], dec)}</code>\n"
            f"{rr} · {n}/{n} questions ✅\n"
            f"{s.get('riskPct', 1.0):g} % risk: {s['lots']['1000']} lot per $1,000 · {s['lots']['10000']} per $10,000\n"
            + (f"⚖️ {html.escape(s['riskNote'])}\n" if s.get("riskNote") else "") + "\n"
            "<i>Research setup, not financial advice. Check it on the chart before any trade.</i>")


def _app_link(pair: str) -> str:
    return f"{settings.public_app_url or 'http://localhost:3000'}/?symbol={pair}"


async def broadcast(pair: str, text: str, title: str, body: str, tag: str) -> dict:
    """One message to every account linked to the bot (+ the admin chat) and a push to every approved account's devices."""
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
            pushed = await send_push(db, list(rows), {"title": title, "body": body, "tag": tag, "symbol": pair})
    return {"telegram": tg_sent, "push": pushed}


async def _send(pair: str, s: dict) -> dict:
    """The setup's first alert."""
    dec = BY_SYMBOL[pair]["decimals"]
    s = {"zone": [s["entry"], s["entry"]], **s}
    return await broadcast(pair, message(s, pair, dec), f"{'🟢' if s['direction'] == 'BUY' else '🔴'} {s['direction']} {pair} · {s['strategy']}",
                           (f"Market {_f(s['entry'], dec)}" if s.get("market") else f"Zone {_f(s['zone'][0], dec)}–{_f(s['zone'][1], dec)}") + f" | SL {_f(s['sl'], dec)} | TP {_f(s['tp'], dec)} | 1:{s['rr']}", f"ld-{s['id']}")


def _claim(pair: str, s: dict, state: str = "PENDING") -> bool:
    """Saves the setup once; False when it was already saved (already sent, or already blocked)."""
    with SessionLocal() as db:
        if db.get(Signal, s["id"]):
            return False
        db.add(Signal(id=s["id"], symbol=pair, setup=s["strategy"], direction=s["direction"], entry_type="LIMIT", entry=s["entry"], sl=s["sl"],
                      tp1=s["tp"], tp2=s["tp"], tp3=s["tp"], rr_tp2=s["rr"], score=7, signal_time=s["time"], state=state,
                      params={"validUntil": s["validUntil"], "lots": s["lots"]}, payload=s))
        db.commit()
        return True


def _seen(sid: str) -> bool:
    with SessionLocal() as db:
        return db.get(Signal, sid) is not None


def sent_setups(limit: int = 50) -> list[dict]:
    """The setups actually sent (not the blocked ones), newest first: what the portfolio check counts as live."""
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state != "BLOCKED").order_by(Signal.signal_time.desc()).limit(limit)).all()
        return [{**(r.payload or {}), "symbol": r.symbol} for r in rows]


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
            if _seen(s["id"]):
                continue
            chk = portfolio.check(pair, s, sent_setups(), int(time.time()))
            if chk["verdict"] == "BLOCK":  # saved with its reasons, never sent, never checked again
                _claim(pair, {**s, "portfolio": chk}, state="BLOCKED")
                sent.append(f"{s['strategy']} {s['direction']} BLOCKED by the risk check: {'; '.join(chk['reasons'])}")
                continue
            if chk.get("riskPct", 1.0) < 1.0:  # the guide's split (EUR/USD + GBP/USD): this one at 0.5 %, the lot halved
                s = {**s, "riskPct": chk["riskPct"], "riskNote": "; ".join(chk.get("notes") or []),
                     "lots": {k: int(v * chk["riskPct"] * 100 + 1e-6) / 100 for k, v in s["lots"].items()}}
            if _claim(pair, {**s, "portfolio": chk}):
                out = await _send(pair, s)
                sent.append(f"{s['strategy']} {s['direction']} → telegram {out['telegram']} · push {out['push']}")
        results[pair] = "; ".join(sent) if sent else ("watching" if not t["signals"] else "signal already sent")
    try:  # the trade manager: each sent setup followed step by step (filled, 1:3, BE, trailing, closed)
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
