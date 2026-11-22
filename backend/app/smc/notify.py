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

TRADE_UPDATES = True  # the trade's end is told (FILLED for a limit, TP, SL, expired); False keeps the manager silent
READ_AT_ONCE = 8  # the spec: 29 teams read 8 at a time (asyncio.Semaphore(8))


def _f(v: float, dec: int) -> str:
    return f"{v:.{dec}f}"


def side(s: dict) -> str:
    """BUY / SELL, with LIMIT when the entry waits for a pullback."""
    limit = s.get("orderType") == "LIMIT_PULLBACK" or s.get("market") is False
    return f"{s['direction']} LIMIT" if limit else s["direction"]


def line(s: dict, pair: str, dec: int, lot: Optional[str] = None) -> str:
    """The trade on ONE line (the phone notification, the app's toast and bell): pair, side, entry, SL, TP and the lot."""
    dot = "🟢" if s["direction"] == "BUY" else "🔴"
    out = f"{dot} {pair} {side(s)} · Entry {_f(s['entry'], dec)} · SL {_f(s['sl'], dec)} · TP {_f(s['tp'], dec)}"
    return out + (f" · Lot {lot}" if lot else "")


def message(s: dict, pair: str, dec: int) -> str:
    """The Telegram trade, only what is needed to place it: pair, side, entry, SL, TP. A private chat adds its owner's own
    lot (sizing.py) as the last line."""
    dot = "🟢" if s["direction"] == "BUY" else "🔴"
    return "\n".join([f"{dot} <b>{html.escape(pair)} · {side(s)}</b>",
                      f"Entry <code>{_f(s['entry'], dec)}</code>",
                      f"SL <code>{_f(s['sl'], dec)}</code>",
                      f"TP <code>{_f(s['tp'], dec)}</code>"])


async def user_lot(db, u, sig_id: str) -> Optional[str]:
    """This user's own lot for the trade, from their own USD risk; None when they have no risk set or it cannot be sized."""
    from .sizing import size_for, valid_risk
    sig = db.get(Signal, sig_id)
    if not u or not sig or valid_risk(u.risk_usd) is None:
        return None
    z = await size_for(db, u, sig, source="notify")
    return f"{z['lots']:g}" if z.get("status") == "ok" else None


async def personal(db, chat: str, sig_id: str) -> tuple[Optional[str], Optional[str]]:
    """(the lot line, the lot) of THE user this private chat is linked to. (None, None) for a group, a channel or a chat no
    account owns: a shared chat never sees anyone's risk or lot."""
    if not chat or str(chat).startswith("-"):  # groups and channels have negative ids
        return None, None
    u = bot.account_of(db, str(chat))
    if not u:
        return None, None
    lot = await user_lot(db, u, sig_id)
    return (f"Lot <code>{lot}</code>", lot) if lot else ("Lot: set your risk with /risk 50", None)


async def personal_line(db, chat: str, sig_id: str) -> Optional[str]:
    return (await personal(db, chat, sig_id))[0]


def copy_keyboard(s: dict, dec: int, lot: Optional[str], app_url: Optional[str]) -> dict:
    """The trade's buttons: one tap on Entry, SL, TP or Lot copies that number (Telegram's copy_text), ready to paste in
    MetaTrader; the app link under them."""
    def b(label: str, v: str) -> dict:
        return {"text": f"📋 {label} {v}", "copy_text": {"text": v}}
    rows = [[b("Entry", _f(s["entry"], dec)), b("SL", _f(s["sl"], dec))], [b("TP", _f(s["tp"], dec))] + ([b("Lot", lot)] if lot else [])]
    if app_url:
        rows.append([{"text": "📈 Open in the app", "url": app_url}])
    return {"inline_keyboard": rows}


def _app_link(pair: str) -> str:
    return f"{settings.public_app_url or 'http://localhost:3000'}/?symbol={pair}"


async def broadcast(pair: str, text: str, title: str, body: str, tag: str, signal: Optional[dict] = None) -> dict:
    """One message to every chat linked to an approved account (+ the admin chat) and a one-line push to every approved
    account's devices. With `signal`: each linked PRIVATE chat, and each account's push, gets that user's own lot."""
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
            dec = BY_SYMBOL[pair]["decimals"] if signal and pair in BY_SYMBOL else None
            for chat in chats:
                mine, lot = await personal(db, chat, signal["id"]) if signal and chat != admin_chat else (None, None)
                body_text = text + "\n" + mine if mine else text
                keys = copy_keyboard(signal, dec, lot, public) if dec is not None else markup
                out = await bot.send_message(token, chat, body_text, keys)
                if not out.get("success") and keys is not markup:  # a Telegram that refuses the copy buttons still gets the trade
                    out = await bot.send_message(token, chat, body_text, markup)
                tg_sent += bool(out.get("success"))
        rows = db.scalars(select(PushSubscription).join(User, User.id == PushSubscription.user_id)
                          .where(User.active.is_(True), or_(User.status.is_(None), User.status != "pending"))).all()
        by_user: dict[int, list] = {}
        for r in rows:
            by_user.setdefault(r.user_id, []).append(r)
        for uid, subs in by_user.items():
            t = title
            if signal:
                lot = await user_lot(db, db.get(User, uid), signal["id"])
                if lot:
                    t = f"{title} · Lot {lot}"
            pushed += await send_push(db, subs, {"title": t, "body": body, "tag": tag, "symbol": pair})
    return {"telegram": tg_sent, "push": pushed}


async def _send(pair: str, s: dict) -> dict:
    dec = BY_SYMBOL[pair]["decimals"]
    return await broadcast(pair, message(s, pair, dec), line(s, pair, dec), "", f"ld-{s['id']}", s)


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
    try:  # Friday after the close: the week's summary, once
        sent = await weekly_summary()
        if sent:
            results["weekly"] = f"{sent['week']} → telegram {sent['telegram']} · push {sent['push']}"
    except Exception as err:  # the summary never stops the teams
        results["weekly"] = f"error: {err!r}"
    try:
        with SessionLocal() as db:
            prev = get_setting(db, "engine")
            set_setting(db, "engine", {"lastTickAt": int(started), "durationSec": round(time.time() - started, 1), "results": results,
                                       "ticks": int(prev.get("ticks") or 0) + 1})
            _save_overview(db, summaries)
    except Exception as err:  # the heartbeat never breaks a tick
        print(f"[smc] heartbeat: {err!r}")
    return results


def weekly_due(now: Optional[float] = None) -> Optional[str]:
    """The Friday whose weekly summary is due now, or None: after the week's close (Friday 17:05 New York, summer time
    followed) until the market reopens (Sunday 17:00 New York), so a summary missed on Friday (server down) still goes."""
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    ny = datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).astimezone(ZoneInfo("America/New_York"))
    minutes = ny.hour * 60 + ny.minute
    wd = ny.weekday()  # Monday 0 … Friday 4, Saturday 5, Sunday 6
    if (wd == 4 and minutes >= 17 * 60 + 5) or wd == 5 or (wd == 6 and minutes < 17 * 60):
        return (ny.date() - timedelta(days=wd - 4)).isoformat()
    return None


async def weekly_summary(now: Optional[float] = None) -> Optional[dict]:
    """Friday after the close: the week's summary to every linked chat (+ the admin chat) and a one-line push, ONCE per
    week (claimed in the settings before sending, so two passes at once never send it twice). None when not due."""
    from .manager import week_line, week_message, week_summary
    from datetime import datetime, timezone
    from .manager import CALENDAR_FROM
    friday = weekly_due(now)
    if not friday or friday < datetime.fromtimestamp(CALENDAR_FROM, timezone.utc).date().isoformat():
        return None  # not due, or a week before the count began (the first summary is the first counted week's)
    with SessionLocal() as db:
        if get_setting(db, "weeklySummary").get("sent") == friday:
            return None
        set_setting(db, "weeklySummary", {"sent": friday, "at": int(time.time())})
    w = week_summary(now)
    out = await broadcast("", week_message(w), week_line(w), "", f"ld-week-{friday}")
    return {"week": friday, **out}


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

