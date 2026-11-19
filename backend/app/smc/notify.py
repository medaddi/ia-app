"""
The notifier (the FXAlexG spec of 2026-11-19, section 5; the owner chose "follow the md exactly"): every minute the 29
teams are read again and three kinds of alerts go out, each to Telegram (every chat linked to an approved account and
the active subscribers, plus the admin chat), as a web push to every approved account's devices, and into the app's
live feed (/api/smc/signals):

  1 · RADAR_WATCH     trend_director ok, aoi_architect ok, S_AlexG >= 65 %, the LTF SoS just confirmed (trigger_sniper
                      warn): only the engulfing is missing. Once per AOI visit (a watermark keeps it from repeating).
  2 · SIGNAL_EXECUTE  the full Set & Forget trade, once: the desk executes and the portfolio check agrees.
  3 · TRADE_MANAGER   every step of a sent trade (manager.py): FILLED, BREAKEVEN (+1.5R), TP_HIT, SL_HIT, BE_CLOSED, EXPIRED.

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
from ..models import PushSubscription, Signal, User, Watermark
from ..push import send_push
from ..store import get_setting, set_setting
from ..telegram import bot
from .desk import BY_SYMBOL, PAIRS, summary, team
from .skill import portfolio

RULE = "━━━━━━━━━━━━━━━━━━"
TRADE_UPDATES = True  # the spec 5.3: the trade manager tells every step (False keeps them silent, the results still saved)
RADAR_KEEP = 30
READ_AT_ONCE = 8  # the spec: 29 teams read 8 at a time (asyncio.Semaphore(8))


def _f(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def head(s: dict, pair: str) -> str:
    """The first line, the same everywhere (Telegram, push, the app's toast and bell): pair, side, timeframe, UTC time."""
    t = datetime.fromtimestamp(int(s["time"]), timezone.utc).strftime("%H:%M")
    return f"{pair} {s['direction']} · {s.get('etf') or 'H1'} · {t} UTC"


def levels(s: dict, dec: int) -> str:
    return f"Entry {_f(s['entry'], dec)} · SL {_f(s['sl'], dec)} · TP {_f(s['tp'], dec)} · 1:{s['rr']:.1f}"


AGENT_NAMES = {"trend": "Trend Director", "aoi": "AOI Architect", "confluence": "Confluence Grader", "trigger": "Trigger Sniper",
               "risk": "Risk Guardian"}


def _zone_tf(zi: dict) -> str:
    return "D1+W1" if zi.get("overlap") else "+".join(t for t in ("D1", "W1") if t in (zi.get("tfs") or [])) or "D1"


def message(s: dict, pair: str, dec: int) -> str:
    """Stage 2 · SIGNAL_EXECUTE, the spec's 5.2 example: pair, side, grade and score, the order, entry (and its zone),
    stop, the break-even step at +1.5R, the target, risk and lots per $10k, R:R, the confluence breakdown and the 5
    agents' verdicts. A private chat adds its owner's own lot (sizing.py) just above the last line."""
    d = 1 if s["direction"] == "BUY" else -1
    e = html.escape
    zi = s.get("zoneInfo") or {}
    zone = s.get("zone") or [s["entry"], s["entry"]]
    pip = BY_SYMBOL[pair]["pip"]
    order = f"{s['direction']} MARKET" if s.get("market") else f"{s['direction']} LIMIT"
    tp_r = abs(s["tp"] - s["entry"]) / abs(s["entry"] - s["sl"]) if s["entry"] != s["sl"] else 0
    struct = s.get("struct")
    tp_why = "pre-structure" if struct is not None and abs(s["tp"] - (struct - d * 5 * pip)) < pip else "3.5R cap"
    lots = s.get("lots10k")
    if lots is None:
        lots = (s.get("lots") or {}).get("10000") or 0
    news = "Clear News" if s.get("newsClear") else "News not checked" if not s.get("newsChecked") else "News"
    score = s.get("score") or s.get("gpa")
    lines = [f"🎯 <b>FXAlexG SET &amp; FORGET — {e(pair)} {'LONG' if d > 0 else 'SHORT'} (GRADE {e(str(s.get('grade')))} · {score}%)</b>",
             RULE,
             f"📈 <b>Action:</b> {order} @ <code>{_f(s['entry'], dec)}</code>" + ("" if s.get("market") else
                 f" <i>(Entry Zone: <code>{_f(min(zone), dec)}</code> – <code>{_f(max(zone), dec)}</code>)</i>"),
             f"🛑 <b>Stop Loss:</b> <code>{_f(s['sl'], dec)}</code> <i>(-{s.get('slPips')} pips · {'below' if d > 0 else 'above'} {_zone_tf(zi)} AOI)</i>"]
    if s.get("tp1") is not None:
        lines.append(f"🛡️ <b>Break-Even Trigger (+1.5R):</b> <code>{_f(s['tp1'], dec)}</code> <i>(+{s.get('bePips')} pips)</i>")
    lines += [f"💰 <b>Take Profit (+{tp_r:.1f}R):</b> <code>{_f(s['tp'], dec)}</code> <i>(+{s.get('tpPips')} pips · {tp_why})</i>",
              f"⚖️ <b>Risk / Sizing:</b> <code>{s.get('riskPct', 1.0):g}%</code> (<code>{lots:g} Lots</code> per $10k) · <b>R:R:</b> <code>1 : {s['rr']:.2f}</code>",
              RULE, f"🧩 <b>Confluence Breakdown ({score}% — Grade {e(str(s.get('grade')))}):</b>"]
    lines += [f"✅ {e(c['label'])} (<code>+{c['pts']}%</code>)" for c in s.get("checklistGpa") or [] if c.get("ok")]
    lines += [RULE, "🤖 <b>5-Agent Desk Verdict:</b>"]
    lines += [f"• <b>{AGENT_NAMES.get(a['key'], a['key'])}:</b> <code>{a['status'].upper()}</code> {e(a['badge'])}" for a in s.get("desk") or []]
    lines.append(f"<i>Research software — does not place orders. Spread {s.get('spreadPct')}% of SL · {news}.</i>")
    return "\n".join(lines)


def radar_message(pair: str, r: dict, dec: int) -> str:
    """Stage 1 · RADAR_WATCH, the spec's 5.1 example."""
    d = 1 if r["direction"] == "BUY" else -1
    side = "Bullish" if d > 0 else "Bearish"
    loc = f"Inside {r['tf'].replace('W1+D1', 'D1+W1')} AOI (<code>{_f(r['low'], dec)} – {_f(r['high'], dec)}</code>)"
    if r.get("psych") is not None:
        loc += f" + Psych <code>{_f(r['psych'], dec)}</code>"
    return "\n".join([f"📡 <b>SET &amp; FORGET RADAR — {html.escape(pair)} ({r['direction']} WATCH)</b>",
                      f"• <b>Trend Sync:</b> {' + '.join((r.get('trend') or 'D1').split('+'))} {side}",
                      f"• <b>Location:</b> {loc}",
                      f"• <b>Status:</b> {r['etf']} Shift of Structure (SoS) confirmed at <code>{_f(r['sosLevel'], dec)}</code> — "
                      f"Waiting for Retest &amp; {side} Engulfing trigger.",
                      f"<i>S_AlexG {r.get('score')}% · research software — does not place orders.</i>"])


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


def _radar_new(pair: str, r: dict) -> bool:
    """True the first time this radar (pair, side, zone, SoS wave: one AOI visit) is seen: a watermark row remembers it,
    and the app's live feed keeps the last 30."""
    with SessionLocal() as db:
        if db.scalar(select(Watermark).where(Watermark.ref == "RADAR", Watermark.signal_id == r["id"][:80])):
            return False
        db.add(Watermark(ref="RADAR", chat_id="*", signal_id=r["id"][:80], symbol=pair, offset=0.0))
        db.commit()
        feed = get_setting(db, "radar").get("items") or []
        feed.insert(0, {**r, "symbol": pair, "at": int(time.time())})
        set_setting(db, "radar", {"items": feed[:RADAR_KEEP]})
        return True


def recent_radar() -> list[dict]:
    """The last radar alerts (the app's live feed)."""
    with SessionLocal() as db:
        return get_setting(db, "radar").get("items") or []


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
        rd = t.get("radar")
        if rd and _radar_new(pair, rd):  # stage 1, once per AOI visit
            dec = BY_SYMBOL[pair]["decimals"]
            out = await broadcast(pair, radar_message(pair, rd, dec), f"📡 Radar · {pair} {rd['direction']} watch",
                                  f"{rd['etf']} SoS at {_f(rd['sosLevel'], dec)} · awaiting the engulfing", f"ld-{rd['id']}")
            notes.append(f"radar {rd['direction']} → telegram {out['telegram']} · push {out['push']}")
        for s in t["signals"]:  # stage 2
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

