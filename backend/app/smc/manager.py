"""
The trade manager (the FXAlexG spec, 5.3): every minute it follows each setup the teams sent, on the pair's latest
closed M5 candles, with the SAME function as the backtest (playbook.run), and tells each step once, on Telegram, as a
web push and in the app:

  ✅ FILLED                    the entry is on
  🎯 TAKE PROFIT HIT (+X R)    the front-run target
  🛑 STOP LOSS HIT (-1 R)      the structural stop, saved with the signal and never moved (the owner, 2026-11-11)
  ⏱️ CLOSED / EXPIRED          the Friday 20:00 UTC exit when not in profit, or a cancelled order

Each step is saved with the setup (signals.params["events"]) so it is never sent twice; the result (outcome, R) is saved
when the trade ends: the app's real results and win rate (/api/smc/results) come from here. It places nothing.
"""

import html
import time

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Signal
from . import playbook
from .desk import BY_SYMBOL, LIVE

DONE = {"WIN", "LOSS", "BE", "TIME", "EXPIRED", "MISSED", "CLOSED"}
WORDS = {
    "FILLED": ("✅ FILLED", "price tapped the entry zone: the trade is on"),
    "TP1": ("🛡️ BREAKEVEN LOCKED (+1.5R)", "price reached +1.5R: the stop moved to the entry + 2 pips (risk-free Set & Forget)"),
    "TP": ("🎯 TAKE PROFIT HIT", "the full target is reached"),
    "STOP": ("🛑 STOP LOSS HIT", "the structural stop is hit"),
    "BE_STOP": ("⏱️ CLOSED at break-even", "the locked stop (entry + 2 pips) is hit"),
    "TIME": ("⏱️ CLOSED (Friday 20:00 UTC)", "not in profit before the weekend: closed at market"),
    "EXPIRED": ("⏱️ EXPIRED", "the order is cancelled"),
    "MISSED": ("⏱️ EXPIRED", "price reached the target before the entry: the order is cancelled"),
}
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
    # the stop saved with the signal never moves (the owner, 2026-11-11): no break-even step, also for signals sent before
    out = playbook.run(m5, k0, d, p["entry"], p["sl"], None, p["tp"], 1.0, bool(p.get("market")),
                       int(p.get("expiry") or 0), int(p.get("holdUntil") or p["time"] + 30 * 86400), cost, events,
                       sorted(news) if news else None, None, (p["beOff"] if "beOff" in p else 0.0), None, int(p.get("newsMin") or 0),
                       bool(p.get("fridayExit")))
    return events, out


def message(pair: str, p: dict, kind: str, price: float, out: dict) -> str:
    dec = BY_SYMBOL[pair]["decimals"]
    head, what = WORDS.get(kind, (kind, ""))
    line = f"{head} · <b>{p['direction']} {pair}</b> (Grade {p.get('grade', '?')})\n{html.escape(what)}"
    if kind == "FILLED":
        line += f"\nEntry <code>{price:.{dec}f}</code> · SL <code>{p['sl']:.{dec}f}</code> · TP <code>{p['tp']:.{dec}f}</code>"
    if kind == "TP1":
        d = 1 if p["direction"] == "BUY" else -1
        line += f"\nNew stop: <code>{p['entry'] + d * p.get('beOff', 0.0):.{dec}f}</code> (entry + 2 pips)"
    if kind in ("TP", "STOP", "BE_STOP", "TIME") and "r" in out:
        line = line.replace(head, f"{head} ({out['r']:+.2f} R)", 1)
        line += f"\nResult: <b>{out['r']:+.2f}R</b> (after costs)"
    return line + "\n<i>Research software — does not place orders.</i>"


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
            if kind in SILENT:
                continue
            new.append(kind)
            await send(pair, message(pair, p, kind, price, out), f"{WORDS.get(kind, (kind, ''))[0]} · {p['direction']} {pair}",
                       WORDS.get(kind, ("", kind))[1], f"ld-{sid}-{kind}")
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


def results(limit: int = 200) -> dict:
    """The teams' real results from the trades they sent and followed: win rate, R, per pair (VERIFIED from the log)."""
    with SessionLocal() as db:
        rows = db.scalars(select(Signal).where(Signal.id.like("SMC-%"), Signal.state == "CLOSED").order_by(Signal.signal_time.desc()).limit(limit)).all()
        closed = [(r.symbol, r.outcome, r.r_multiple or 0.0) for r in rows]

    def agg(xs):
        n = len(xs)
        wins = sum(1 for _, o, _ in xs if o == "WIN")
        return {"trades": n, "wins": wins, "breakeven": sum(1 for _, o, _ in xs if o == "BREAKEVEN"),
                "losses": sum(1 for _, o, _ in xs if o == "LOSS"), "winRate": round(100 * wins / n) if n else None,
                "totalR": round(sum(r for _, _, r in xs), 2)}
    return {"all": agg(closed), "byPair": {p: agg([x for x in closed if x[0] == p]) for p in sorted({x[0] for x in closed})}}
