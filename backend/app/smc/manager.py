"""
The trade manager (FX Alex G Set & Forget, spec 1.2 and 5.1): every minute it follows each trade the pairs sent, on the
pair's latest closed M5 candles, with the SAME function as the backtest (playbook.run), and tells each step once, on
Telegram, as a web push and in the app:

  🟢 FILLED     a limit (50 % pullback) filled; a market order is on at its signal: no line
  🏆 TP_HIT     the structural target
  🔴 SL_HIT     the structural stop
  ⏱️ EXPIRED    a limit not filled in its 8 hours (or the target reached first)

Set & Forget: the SL and TP are locked (SET_AND_FORGET_LOCKED): no break-even, no trailing, no partial, no early close.
Each step is saved with the trade (signals.params["events"]) so it is never sent twice; the result (outcome, R) is saved
when the trade ends: the app's history and win rate come from here. It places nothing.
"""

import html
import time
from typing import Optional

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Signal
from . import playbook
from .desk import BY_SYMBOL, LIVE

DONE = {"WIN", "LOSS", "BE", "TIME", "EXPIRED", "MISSED", "CLOSED"}
SILENT = {"BE"}  # run() logs the stop move next to TP1: one message says both


def _index_of(m5, t_close: int) -> int | None:
    """The M5 candle whose close is t_close (the signal's candle)."""
    for k in range(len(m5) - 1, -1, -1):
        if m5[k].time + playbook.M5S == t_close:
            return k
        if m5[k].time + playbook.M5S < t_close:
            return None
    return None


def follow(p: dict, m5, cost: float, news: list[int] | None = None) -> tuple[list[tuple], dict]:
    """The steps of one sent setup so far (index, kind, price) and its state, from the candles."""
    d = 1 if p["direction"] == "BUY" else -1
    k0 = _index_of(m5, p["time"])
    if k0 is None:
        return [], {"state": "UNKNOWN"}
    events: list[tuple] = []
    out = playbook.run(m5, k0, d, p["entry"], p["sl"], p.get("tp1"), p["tp"], p.get("part", 1.0), bool(p.get("market")),
                       int(p.get("expiry") or 0), int(p.get("holdUntil") or p["time"] + 30 * 86400), cost, events,
                       sorted(news) if news else None, None, (p["beOff"] if "beOff" in p else 0.0), None, int(p.get("newsMin") or 0),
                       bool(p.get("fridayExit")))
    return events, out


WORD = {"FILLED": "🟢 Filled", "TP": "🏆 TP hit", "STOP": "🔴 SL hit", "TIME": "⏱️ Closed (60 days)", "EXPIRED": "⏱️ Expired",
        "MISSED": "⏱️ Expired"}


def line(pair: str, p: dict, kind: str, price: float, out: dict) -> str:
    """The trade's step on ONE line, the same on Telegram and on the phone: pair, side, what happened, the result."""
    dec = BY_SYMBOL[pair]["decimals"]
    word = WORD.get(kind, kind)
    if kind in ("TP", "STOP", "BE_STOP", "TIME") and "r" in out:
        tail = f" · {out['r']:+.2f}R"
    elif kind == "FILLED":
        tail = f" at {price:.{dec}f}"
    else:
        tail = ""
    return f"{pair} {p['direction']} · {word}{tail}"


def message(pair: str, p: dict, kind: str, price: float, out: dict) -> str:
    """The Telegram text: the one line, the pair and side in bold."""
    head = f"{pair} {p['direction']}"
    return f"<b>{html.escape(head)}</b>" + html.escape(line(pair, p, kind, price, out)[len(head):])


async def manage_all(send) -> dict:
    """One pass over the open setups. `send(pair, text, push_title, push_body, tag)` delivers a step."""
    now = int(time.time())
    report = {}
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state.not_in(tuple(DONE) + ("BLOCKED",)))).all()
        todo = [(r.id, r.symbol, dict(r.payload or {}), dict(r.params or {})) for r in rows]
    for sid, pair, p, params in todo:
        live = LIVE.get(pair)
        if not live or not p.get("time"):
            continue
        m5, cost, news = live
        events, out = follow(p, m5, cost, news)
        done = set(params.get("events") or [])
        new = []
        for j, kind, price in events:
            key = f"{kind}@{m5[j].time}"
            if key in done:
                continue
            done.add(key)
            if kind in SILENT or (kind == "FILLED" and p.get("market")):  # a market order: on at its signal, no FILLED line
                continue
            new.append(kind)
            await send(pair, message(pair, p, kind, price, out), line(pair, p, kind, price, out), "", f"ld-{sid}-{kind}")
        state = out.get("state", "PENDING")
        with SessionLocal() as db:
            r = db.get(Signal, sid)
            if r is None:
                continue
            r.params = {**params, "events": sorted(done)}
            if state in ("WIN", "LOSS", "BE", "TIME"):
                r.state, r.r_multiple = "CLOSED", round(out["r"], 3)
                r.outcome = "WIN" if out["r"] > 0.05 else "LOSS" if out["r"] < -0.05 else "BREAKEVEN"
                r.exit_time = m5[out["at"]].time if "at" in out else now
            elif state in ("EXPIRED", "MISSED"):
                r.state, r.outcome = state, None
            elif "fill" in out:
                r.state = "OPEN"
            db.commit()
        if new:
            report[sid] = new
    return report


def history_since(db) -> int:
    """When the app's history starts: the first time this is asked (the owner, 2026-11-19: "count from now"), saved once
    so every later count starts from the same moment. Trades sent before it are kept in the database, never counted."""
    from ..store import get_setting, set_setting
    h = get_setting(db, "history")
    if not h.get("since"):
        h = {"since": int(time.time())}
        set_setting(db, "history", h)
    return int(h["since"])


def history(limit: int = 500) -> dict:
    """Every trade sent since the history began (newest first) with its state and result, the counts (given, running,
    closed, won / break-even / lost, not filled), the win rate (won / closed) and the R total, and the win rate and R
    after each closed trade (oldest first): what the app's history shows."""
    with SessionLocal() as db:
        since = history_since(db)
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state != "BLOCKED", Signal.signal_time >= since)
                          .order_by(Signal.signal_time.desc()).limit(limit)).all()
        items = [{"id": r.id, "symbol": r.symbol, "direction": r.direction, "time": r.signal_time, "entry": r.entry, "sl": r.sl, "tp": r.tp2,
                  "rr": r.rr_tp2, "state": r.state, "outcome": r.outcome, "resultR": r.r_multiple, "exitTime": r.exit_time,
                  "setupType": (r.payload or {}).get("setupType"), "grade": (r.payload or {}).get("grade"), "etf": (r.payload or {}).get("etf"),
                  "score": (r.payload or {}).get("score") or (r.payload or {}).get("gpa"), "market": (r.payload or {}).get("market")} for r in rows]
    closed = sorted((x for x in items if x["state"] == "CLOSED"), key=lambda x: x["exitTime"] or x["time"])
    wins = sum(1 for x in closed if x["outcome"] == "WIN")
    curve, w, tot = [], 0, 0.0
    for k, x in enumerate(closed, 1):
        w += x["outcome"] == "WIN"
        tot += x["resultR"] or 0.0
        curve.append({"time": x["exitTime"] or x["time"], "winRate": round(100 * w / k), "totalR": round(tot, 2)})
    summary = {"given": len(items), "running": sum(1 for x in items if x["state"] in ("PENDING", "OPEN")), "closed": len(closed),
               "wins": wins, "breakeven": sum(1 for x in closed if x["outcome"] == "BREAKEVEN"),
               "losses": sum(1 for x in closed if x["outcome"] == "LOSS"), "notFilled": sum(1 for x in items if x["state"] in ("EXPIRED", "MISSED")),
               "winRate": round(100 * wins / len(closed)) if closed else None, "totalR": round(sum(x["resultR"] or 0.0 for x in closed), 2)}
    return {"since": since, "summary": summary, "curve": curve, "items": items}


# The pips calendar starts on Monday 2026-11-23 00:00 UTC (the forex week) (the owner, 2026-11-22: "count from next week").
CALENDAR_FROM = 1795392000


def trade_pips(symbol: str, entry: float, sl: float, r: float) -> float:
    """A closed trade's result in pips: its R times its stop distance in pips (0.01 for JPY pairs, 0.10 for gold)."""
    from .fxag.config import pip_size

    risk = abs((entry or 0.0) - (sl or 0.0)) / pip_size(symbol.replace("/", ""))
    return round((r or 0.0) * risk, 1)


def calendar() -> dict:
    """Every trade closed since the calendar began, with its result in pips and when it closed: the app groups them by
    day, week and month in the viewer's own time zone (net pips = pips won minus pips lost)."""
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state == "CLOSED", Signal.exit_time >= CALENDAR_FROM)
                          .order_by(Signal.exit_time)).all()
        trades = [{"id": r.id, "symbol": r.symbol, "direction": r.direction, "outcome": r.outcome, "r": r.r_multiple,
                   "pips": trade_pips(r.symbol, r.entry, r.sl, r.r_multiple), "exitTime": r.exit_time} for r in rows]
    return {"since": CALENDAR_FROM, "trades": trades}


def week_start(now: float) -> int:
    """Monday 00:00 UTC of the week `now` is in."""
    from datetime import datetime, timedelta, timezone
    d = datetime.fromtimestamp(now, timezone.utc)
    return int((d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def week_summary(now: Optional[float] = None) -> dict:
    """The week so far (Monday 00:00 UTC → now): the trades closed in it, their net pips (won − lost), won / lost / break
    even, the best and the worst pair by pips, and the trades still running. What Friday's summary and /week tell."""
    now = time.time() if now is None else now
    start = max(week_start(now), CALENDAR_FROM)
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state == "CLOSED", Signal.exit_time >= start,
                                               Signal.exit_time <= now)).all()
        running = db.query(Signal).filter(Signal.id.like("SMC-%"), Signal.state.in_(("PENDING", "OPEN"))).count()
        closed = [(r.symbol, r.outcome, trade_pips(r.symbol, r.entry, r.sl, r.r_multiple)) for r in rows]
    by_pair: dict[str, float] = {}
    for sym, _, pips in closed:
        by_pair[sym] = round(by_pair.get(sym, 0.0) + pips, 1)
    ranked = sorted(by_pair.items(), key=lambda kv: kv[1], reverse=True)
    wins = sum(1 for _, o, _ in closed if o == "WIN")
    losses = sum(1 for _, o, _ in closed if o == "LOSS")
    return {"from": week_start(now), "to": int(now), "trades": len(closed), "wins": wins, "losses": losses,
            "breakeven": len(closed) - wins - losses, "pips": round(sum(p for _, _, p in closed), 1),
            "winRate": round(100 * wins / (wins + losses)) if wins + losses else None,
            "best": ranked[0] if ranked else None, "worst": ranked[-1] if len(ranked) > 1 and ranked[-1][1] < 0 else None,
            "running": running}


def _pips(v: float) -> str:
    return f"{v:+,.1f}".replace(".0", "") + " pips"


def week_line(w: dict) -> str:
    """The week on ONE line (the phone notification)."""
    if not w["trades"]:
        return "📊 This week: no trade closed"
    best = f" · best {w['best'][0]}" if w["best"] and w["best"][1] > 0 else ""
    return f"📊 This week: {_pips(w['pips'])} · {w['wins']} won · {w['losses']} lost{best}"


def week_message(w: dict, title: str = "Weekly summary") -> str:
    """The week for Telegram: net pips first, then won / lost and the win rate, the best and worst pair, what still runs."""
    from datetime import datetime, timezone
    a = datetime.fromtimestamp(w["from"], timezone.utc)
    b = datetime.fromtimestamp(w["to"], timezone.utc)
    span = f"{a.day}–{b.day} {b.strftime('%b')}" if a.month == b.month else f"{a.day} {a.strftime('%b')} – {b.day} {b.strftime('%b')}"
    out = [f"📊 <b>{title}</b> · {span}"]
    if not w["trades"]:
        out.append("No trade closed this week.")
    else:
        out.append(f"This week: <b>{_pips(w['pips'])}</b>")
        wr = f" · win rate {w['winRate']}%" if w["winRate"] is not None else ""
        be = f" · {w['breakeven']} BE" if w["breakeven"] else ""
        out.append(f"✅ {w['wins']} won · ❌ {w['losses']} lost{be}{wr}")
        if w["best"] and w["best"][1] > 0:
            out.append(f"🏆 Best: {w['best'][0]} {_pips(w['best'][1])}")
        if w["worst"]:
            out.append(f"🔻 Worst: {w['worst'][0]} {_pips(w['worst'][1])}")
    if w["running"]:
        out.append(f"⏳ Still running: {w['running']} trade{'s' if w['running'] > 1 else ''}")
    return "\n".join(out)


def results(limit: int = 200) -> dict:
    """The teams' real results from the trades they sent and followed since the history began: win rate, R, per pair
    (VERIFIED from the log)."""
    with SessionLocal() as db:
        since = history_since(db)
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state == "CLOSED", Signal.signal_time >= since)
                          .order_by(Signal.signal_time.desc()).limit(limit)).all()
        closed = [(r.symbol, r.outcome, r.r_multiple or 0.0) for r in rows]

    def agg(xs):
        n = len(xs)
        wins = sum(1 for _, o, _ in xs if o == "WIN")
        return {"trades": n, "wins": wins, "breakeven": sum(1 for _, o, _ in xs if o == "BREAKEVEN"),
                "losses": sum(1 for _, o, _ in xs if o == "LOSS"), "winRate": round(100 * wins / n) if n else None,
                "totalR": round(sum(r for _, _, r in xs), 2)}
    return {"all": agg(closed), "byPair": {p: agg([x for x in closed if x[0] == p]) for p in sorted({x[0] for x in closed})}}
