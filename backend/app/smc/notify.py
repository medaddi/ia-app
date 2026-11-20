"""
The notifier (FX Alex G Set & Forget, the owner's specification of 2026-11-20; the owner's choice: "the trade and its
end"): every minute the 29 pairs are read again and, to Telegram (every chat linked to an approved account, plus the
admin chat), as a web push to every approved account's devices and into the app's live feed (/api/smc/signals):

  SIGNAL     an approved trade (the SetupAuditor's APPROVE), once, locked Set & Forget (Agent 8: signal only)
  UPDATES    the trade manager (manager.py): FILLED (a limit), TP_HIT, SL_HIT, EXPIRED. Set & Forget: no break-even,
             no partial, no trailing, no early close.

No radar alert. Research, not advice: every message says so. Nothing here places an order.
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
from .desk import BY_SYMBOL, PAIRS, summary, team
from .skill import portfolio

RULE = "━━━━━━━━━━━━━━━━━━"
TRADE_UPDATES = True  # the trade's end is told (FILLED for a limit, TP, SL, expired); False keeps the manager silent
READ_AT_ONCE = 8  # the spec: 29 teams read 8 at a time (asyncio.Semaphore(8))


def _f(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def head(s: dict, pair: str) -> str:
    """The first line, the same everywhere (Telegram, push, the app's toast and bell): pair, side, timeframe, UTC time."""
    t = datetime.fromtimestamp(int(s["time"]), timezone.utc).strftime("%H:%M")
    return f"{pair} {s['direction']} · {s.get('etf') or 'H1'} · {t} UTC"


def levels(s: dict, dec: int) -> str:
    return f"Entry {_f(s['entry'], dec)} · SL {_f(s['sl'], dec)} · TP {_f(s['tp'], dec)} · 1:{s['rr']:.1f}"


def message(s: dict, pair: str, dec: int) -> str:
    """The trade: pair, side, grade and score, the order, entry, stop, target, R:R, the SoS and engulfing timeframes, the
    alignment, the confluences that scored, the Set & Forget lock and the order id. A private chat adds its owner's own
    lot (sizing.py) just above the last line."""
    e = html.escape
    d = 1 if s["direction"] == "BUY" else -1
    score = s.get("score") or s.get("gpa")
    limit = s.get("orderType") == "LIMIT_PULLBACK" or not s.get("market")
    br = s.get("breakdown") or {}
    pid = ((s.get("proposal") or {}).get("client_order_id")) or "—"
    lines = [f"🎯 <b>FX ALEX G SET &amp; FORGET — {e(pair)} {s['direction']} (GRADE {e(str(s.get('grade')))} · {score}%)</b>",
             RULE,
             (f"📈 <b>Order:</b> {'LIMIT (50 % pullback, 6 h)' if limit else 'MARKET'} @ <code>{_f(s['entry'], dec)}</code>"),
             f"🛑 <b>SL</b> <code>{_f(s['sl'], dec)}</code> <i>(-{s.get('slPips')} pips)</i> · 💰 <b>TP</b> <code>{_f(s['tp'], dec)}</code> "
             f"<i>(+{s.get('tpPips')} pips)</i> · <b>R:R</b> <code>1 : {s['rr']:.2f}</code>",
             f"🧭 {e(s.get('setupName') or s.get('name') or '')} · SoS {e(str(s.get('sosTf') or ''))} · Engulfing {e(str(s.get('etf') or ''))}",
             "🧩 " + e(" · ".join(f"{k} +{v}%" for k, v in br.items())) if br else "🧩 —",
             f"🔒 Set &amp; Forget: SL and TP locked (no break-even, no partial) · risk {s.get('riskPct', 0):g}% · id <code>{pid}</code>",
             "<i>Signal only — no order placed. Research software, not advice.</i>"]
    return "\n".join(lines)


async def personal_line(db, chat: str, sig_id: str) -> Optional[str]:
    """The lot of THE user this private chat is linked to, from that user's own USD risk (saved as their snapshot).
    None for a group, a channel or a chat no account owns: a shared chat never sees anyone's risk or lot."""
    if not chat or str(chat).startswith("-"):  # groups and channels have negative ids
        return None
    u = bot.account_of(db, str(chat))
    sig = db.get(Signal, sig_id)
    if not u or not sig:
        return None
    from .sizing import size_for, valid_risk
    if valid_risk(u.risk_usd) is None:
        return "👤 Your lot: set your risk with /risk 50 (or in the app)"
    z = await size_for(db, u, sig, source="telegram")
    if z.get("status") != "ok":
        return "👤 Your lot: unavailable (see the app)"
    return f"👤 Your lot <code>{z['lots']:g}</code> · risk ${z['riskUsd']:g}"


def _app_link(pair: str) -> str:
    return f"{settings.public_app_url or 'http://localhost:3000'}/?symbol={pair}"


async def broadcast(pair: str, text: str, title: str, body: str, tag: str, signal: Optional[dict] = None) -> dict:
    """One message to every chat linked to an approved account (+ the admin chat) and a push to every approved account's
    devices. With `signal`: in each linked PRIVATE chat (not the admin chat) that user's own lot."""
    url = _app_link(pair)
    public = None if ("localhost" in url or "127.0.0.1" in url) else url
    markup = {"inline_keyboard": [[{"text": "📈 Open in the app", "url": public}]]} if public else None
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
                if mine:  # the owner's lot goes just above the last line
                    body, _, last = text.rpartition("\n")
                    out = await bot.send_message(token, chat, f"{body}\n{mine}\n{last}", markup)
                else:
                    out = await bot.send_message(token, chat, text, markup)
                tg_sent += bool(out.get("success"))
        rows = db.scalars(select(PushSubscription).join(User, User.id == PushSubscription.user_id)
                          .where(User.active.is_(True), or_(User.status.is_(None), User.status != "pending"))).all()
        if rows:
            pushed = await send_push(db, list(rows), {"title": title, "body": body, "tag": tag, "symbol": pair})
    return {"telegram": tg_sent, "push": pushed}


async def _send(pair: str, s: dict) -> dict:
    dec = BY_SYMBOL[pair]["decimals"]
    return await broadcast(pair, message(s, pair, dec), f"🎯 {head(s, pair)} · {s.get('grade')} {s.get('score') or s.get('gpa')}%",
                           levels(s, dec), f"ld-{s['id']}", s)


def recent_radar() -> list[dict]:
    """No radar alerts any more (the owner, 2026-11-20): the app's feed carries the trades only."""
    return []


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


async def _quiet(*_args, **_kw) -> dict:
    """The trade manager's messages when TRADE_UPDATES is off: nothing is sent."""
    return {"telegram": 0, "push": 0}


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
    summaries: dict[str, dict] = {}
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
        summaries[pair] = summary(pair, t)
        notes = []
        for s in t["signals"]:
            if _seen(s["id"]):
                continue
            chk = portfolio.check(pair, s, sent_setups(), int(time.time()))
            if chk["verdict"] == "BLOCK":  # saved with its reasons, never sent, never checked again
                _claim(pair, {**s, "portfolio": chk}, state="BLOCKED")
                notes.append(f"{s['direction']} BLOCKED by the portfolio check: {'; '.join(chk['reasons'])}")
                continue
            if _claim(pair, {**s, "portfolio": chk}):
                out = await _send(pair, s)
                notes.append(f"{s['direction']} {s.get('setupType')} grade {s.get('grade')} → telegram {out['telegram']} · push {out['push']}")
        results[pair] = "; ".join(notes) if notes else (t.get("decision") or "watching").lower()
    try:  # the trade manager
        from .manager import manage_all
        steps = await manage_all(broadcast if TRADE_UPDATES else _quiet)
        if steps:
            results["manager"] = "; ".join(f"{k.split('-')[1]} {'/'.join(v)}" for k, v in steps.items())
    except Exception as err:  # managing never stops the teams
        results["manager"] = f"error: {err!r}"
    try:
        with SessionLocal() as db:
            prev = get_setting(db, "engine")
            set_setting(db, "engine", {"lastTickAt": int(started), "durationSec": round(time.time() - started, 1), "results": results,
                                       "ticks": int(prev.get("ticks") or 0) + 1})
            _save_overview(db, summaries)
    except Exception as err:  # the heartbeat never breaks a tick
        print(f"[smc] heartbeat: {err!r}")
    return results


def _save_overview(db, summaries: dict) -> None:
    """Every pair's last summary (a pair not read this pass, e.g. the market closed, keeps its previous one)."""
    if not summaries:
        return
    prev = get_setting(db, "overview").get("pairs") or {}
    set_setting(db, "overview", {"at": int(time.time()), "pairs": {**prev, **summaries}})


_refreshing: list = []


async def refresh_overview() -> int:
    """Reads every pair's team and saves the summaries, WITHOUT sending anything (the dashboard asks for it when no pass of
    the notifier has run lately, e.g. a local server without its scheduler, or a weekend). One at a time."""
    if _refreshing:
        return 0
    _refreshing.append(1)
    try:
        gate = asyncio.Semaphore(READ_AT_ONCE)

        async def read(pair: str):
            async with gate:
                try:
                    return pair, await team(pair)
                except Exception:  # one pair failing never stops the others
                    return pair, None
        got = await asyncio.gather(*(read(p) for p in PAIRS))
        summaries = {p: summary(p, t) for p, t in got if t and t.get("success")}
        with SessionLocal() as db:
            _save_overview(db, summaries)
        return len(summaries)
    finally:
        _refreshing.clear()


def overview() -> dict:
    """The last saved summaries of every pair, and how old they are."""
    with SessionLocal() as db:
        o = get_setting(db, "overview")
    at = o.get("at")
    pairs = o.get("pairs") or {}
    return {"at": at, "ageSec": int(time.time() - at) if at else None, "pairs": [pairs[p] for p in PAIRS if p in pairs]}


def recent(limit: int = 30) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state != "BLOCKED").order_by(Signal.signal_time.desc()).limit(limit)).all()
        return [{**(r.payload or {}), "symbol": r.symbol, "sentAt": r.sent_at.isoformat() if r.sent_at else None, "status": r.state,
                 "outcome": r.outcome, "resultR": r.r_multiple, "events": (r.params or {}).get("events", [])} for r in rows]

