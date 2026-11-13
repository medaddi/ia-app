"""
The notifier (the FXAlexG spec, section 5): every minute the 29 teams are read again and three kinds of alerts go out,
each to Telegram (every chat linked to an approved account, plus the admin chat), as a web push to every approved
account's devices, and into the app's live feed (/api/smc/signals):

  1 · AOI_WATCH_ALERT  trend ok, inside a 1W / 1D AOI, the LTF SoS is in, only the engulfing close is missing.
                       Once per wave (a watermark keeps it from repeating).
  2 · SIGNAL_EXECUTE   the full Set & Forget trade, once: the desk executes and the portfolio check agrees.
  3 · MANAGER_LIVE_UPDATE  every step of a sent trade (manager.py): FILLED, BREAKEVEN LOCKED, TP HIT, SL HIT, CLOSED.

Research, not advice: every message says so. Nothing here places an order.
"""

import asyncio
import html
import time

from sqlalchemy import or_, select

from ..config import settings
from ..db import SessionLocal
from ..market.data import market_session_status
from ..models import PushSubscription, Signal, User, Watermark
from ..push import send_push
from ..store import get_setting, set_setting
from ..telegram import bot
from .desk import BY_SYMBOL, PAIRS, team
from .skill import portfolio

RULE = "━━━━━━━━━━━━━━━━━━"
RADAR_KEEP = 30
READ_AT_ONCE = 8  # the spec: 29 teams read 8 at a time (asyncio.Semaphore(8))


def _f(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def message(s: dict, pair: str, dec: int) -> str:
    """Stage 2 · SIGNAL_EXECUTE: the full Set & Forget trade (the spec's Part 5.2 fields)."""
    buy = s["direction"] == "BUY"
    z = s.get("zone") or [s["entry"], s["entry"]]
    zi = s.get("zoneInfo") or {}
    where = f"{'below' if buy else 'above'} the {'1W/1D' if zi.get('overlap') else '/'.join(zi.get('tfs') or ['1D'])} AOI"
    psych = f" · before Psych <code>{_f(s['psychTp'], dec)}</code>" if s.get("psychTp") is not None else ""
    lines = [f"🎯 <b>SET &amp; FORGET — {pair} {s['direction']}</b> · <code>{s.get('setupType') or s['strategy']}</code>", RULE,
             f"🏅 <b>FXAlexG Grade:</b> {s.get('grade', '?')} (GPA {s.get('gpa', 0)}%) · <b>Consensus:</b> {s.get('consensus', 0)}/100",
             f"{'📈' if buy else '📉'} <b>Entry:</b> <code>{_f(s['entry'], dec)}</code> <i>(zone <code>{_f(z[0], dec)} – {_f(z[1], dec)}</code>)</i>",
             f"🛑 <b>Structural SL:</b> <code>{_f(s['sl'], dec)}</code> <i>(-{s.get('slPips', 0):.1f} pips · {where})</i>",
             f"🛡️ <b>Break-even at +1.5R:</b> <code>{_f(s['tp1'], dec)}</code> <i>(stop to entry + 2 pips)</i>" if s.get("tp1") is not None else "",
             f"💰 <b>Front-run TP:</b> <code>{_f(s['tp'], dec)}</code> <i>(+{s.get('tpPips', 0):.1f} pips{psych})</i>",
             f"⚖️ <b>R:R</b> <code>1 : {s['rr']:.2f}</code> · <b>Risk</b> <code>{s.get('riskPct', 1.0):g}%</code> (<code>{s['lots']['10000']} lots</code> per $10k)"]
    if s.get("riskNote"):
        lines.append(f"⚖️ {html.escape(s['riskNote'])}")
    if s.get("desk"):
        lines += [RULE, "🤖 <b>5-Agent Desk:</b>"]
        icon = {"ok": "✅", "warn": "⚠️", "wait": "⏳", "veto": "⛔"}
        lines += [f"{icon.get(a_['status'], '•')} <b>{html.escape(a_['role'])}</b> ({a_.get('score', 0)}): {html.escape(a_['badge'])}" for a_ in s["desk"]]
    lines.append("<i>Research software — does not place orders. Not financial advice.</i>")
    return "\n".join(x for x in lines if x)


def radar_message(pair: str, r: dict, dec: int) -> str:
    """Stage 1 · AOI_WATCH_ALERT (the spec's template)."""
    return (f"👀 [RADAR] {pair} ({r['direction']}) inside {r['tf']} AOI ({r['touches']} touches) · GPA {r['gpa']}% ({r['grade']}) · "
            "Waiting for LTF Engulfing close.\n<i>Research software — does not place orders.</i>")


def _app_link(pair: str) -> str:
    return f"{settings.public_app_url or 'http://localhost:3000'}/?symbol={pair}"


async def broadcast(pair: str, text: str, title: str, body: str, tag: str) -> dict:
    """One message to every chat linked to an approved account (+ the admin chat) and a push to every approved account's devices."""
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
    dec = BY_SYMBOL[pair]["decimals"]
    z = s.get("zone") or [s["entry"], s["entry"]]
    return await broadcast(pair, message(s, pair, dec), f"🎯 {s['direction']} {pair} · Grade {s.get('grade', '?')} ({s.get('gpa', 0)}%)",
                           f"Entry {_f(s['entry'], dec)} | SL {_f(s['sl'], dec)} | BE +1.5R | TP {_f(s['tp'], dec)} | 1:{s['rr']}", f"ld-{s['id']}")


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


def _radar_new(pair: str, r: dict) -> bool:
    """True the first time this radar (pair, side, zone, SoS wave) is seen: a watermark row remembers it."""
    with SessionLocal() as db:
        if db.scalar(select(Watermark).where(Watermark.ref == "RADAR", Watermark.signal_id == r["id"])):
            return False
        db.add(Watermark(ref="RADAR", chat_id="*", signal_id=r["id"], symbol=pair, offset=0.0))
        db.commit()
        feed = get_setting(db, "radar").get("items") or []
        feed.insert(0, {**r, "symbol": pair, "at": int(time.time())})
        set_setting(db, "radar", {"items": feed[:RADAR_KEEP]})
        return True


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
        dec = BY_SYMBOL[pair]["decimals"]
        rd = t.get("radar")
        if rd and _radar_new(pair, rd):  # stage 1
            out = await broadcast(pair, radar_message(pair, rd, dec), f"👀 Radar · {pair} {rd['direction']}",
                                  f"Inside {rd['tf']} AOI ({rd['touches']} touches) · GPA {rd['gpa']}% · waiting for the LTF engulfing close", f"ld-{rd['id']}")
            notes.append(f"radar {rd['direction']} → telegram {out['telegram']} · push {out['push']}")
        for s in t["signals"]:  # stage 2
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
    try:  # stage 3: the trade manager
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


def recent_radar() -> list[dict]:
    """The last radar alerts (the app's live feed)."""
    with SessionLocal() as db:
        return get_setting(db, "radar").get("items") or []
