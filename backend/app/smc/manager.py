"""
The trade manager: what a trader does after the order is in. Every minute it follows each setup the teams sent, on the
pair's latest closed M5 candles, with the SAME rules as the backtest (engine.simulate for the limit, manage.managed for the
trade), and tells you each step once, on Telegram and as a push:

  FILLED        the limit was reached: you are in
  PARTIAL_1_3   1:3 reached: close 50 %
  BE            an M5 BOS in your favour: move the stop to the entry
  TRAIL         a new M5 swing confirmed in your favour: move the stop under it
  TP / STOP / BE_STOP / TRAIL_STOP / TIME   the trade is over, with its result in R
  EXPIRED       the limit was not reached in time: cancel it
  MISSED        price reached the target before the entry: cancel it

Each step is saved with the setup (signals.params["events"]) so it is never sent twice, and the result (outcome, R) is
saved when the trade ends: the app's real results and win rate come from here. Research, not advice: it places nothing.
"""

import html
import time

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Signal
from . import engine, playbook
from .desk import BY_SYMBOL, LIVE
from .manage import managed

DONE = {"WIN", "LOSS", "BE", "TIME", "EXPIRED", "MISSED", "CLOSED"}
WORDS = {
    "FILLED": ("✅ Filled", "the limit was reached: the trade is on"),
    "PARTIAL_1_3": ("💰 1:3 reached", "close 50 % of the position now"),
    "RISK_OFF": ("🚨 Risk-off: close the buy", "VIX jumped or the S&P 500 fell: the guide closes the AUD/CHF long at once"),
    "TP1": ("💰 TP1 reached", "close the planned part now and move the stop to the entry"),
    "BE": ("🛡 Stop to break-even", "an M5 BOS in your favour: move the stop to the entry"),
    "TRAIL": ("📈 Trail the stop", "a new M5 swing confirmed in your favour: move the stop"),
    "TP": ("🎯 Target hit", "the trade is closed at the target"),
    "STOP": ("❌ Stop hit", "the trade is closed at the stop"),
    "TRAIL_STOP": ("✅ Trailing stop hit", "the rest is closed at the trailing stop"),
    "BE_STOP": ("➖ Closed at break-even", "the stop at the entry was hit: no loss on the rest"),
    "TIME": ("⏱ Time exit", "4 hours since the fill: close the rest at market"),
    "EXPIRED": ("⌛ Limit expired", "not reached in time: cancel the order"),
    "MISSED": ("⚪ Missed", "price reached the target before the entry: cancel the order"),
}


def _index_of(m5, t_close: int) -> int | None:
    """The M5 candle whose close is t_close (the signal's candle)."""
    for k in range(len(m5) - 1, -1, -1):
        if m5[k].time + engine.M5S == t_close:
            return k
        if m5[k].time + engine.M5S < t_close:
            return None
    return None


def follow(pair: str, p: dict, m5, st5, cost: float, news: list[int] | None = None, exits: list[int] | None = None) -> tuple[list[tuple], dict]:
    """The steps of one sent setup so far (index, kind, price) and its state, from the candles."""
    d = 1 if p["direction"] == "BUY" else -1
    k0 = _index_of(m5, p["time"])
    if k0 is None:
        return [], {"state": "UNKNOWN"}
    if str(p["strategy"]).startswith("P"):  # the pair's strategy from the guide: its own trade rules (TP1 part, break-even, close time)
        events: list[tuple] = []
        out = playbook.run(m5, k0, d, p["entry"], p["sl"], p.get("tp1"), p["tp"], p.get("part", 1.0), bool(p.get("market")),
                           int(p.get("expiry") or 0), int(p.get("holdUntil") or p["time"] + 86400), cost, events,
                           sorted(news) if news else None,  # the same news rule as the team: a pending limit pulled around a release
                           exits if pair == "AUD/CHF" else None,  # the macro risk-off close
                           (p["beOff"] if "beOff" in p else 0.0), p.get("missPx"), int(p.get("newsMin") or 0))  # BE offset (None: no BE), cancel price, news pull
        return events, out
    sid = engine.STRATEGY_OF.get(p["strategy"], "A")
    res = engine.simulate(m5, k0, d, p["entry"], p["sl"], p["tp"], engine.EXPIRY[sid], cost)
    events: list[tuple] = []
    if res["state"] in ("EXPIRED", "MISSED"):
        return [(len(m5) - 1, res["state"], p["entry"])], res
    if "fill" not in res:
        return [], res  # still pending
    events.append((res["fill"], "FILLED", p["entry"]))
    out = managed(m5, st5, {"dir": d, "entry": p["entry"], "sl": p["sl"], "tp": p["tp"], "result": res}, cost, trail=True, events=events)
    return events, out


def message(pair: str, p: dict, kind: str, price: float, out: dict) -> str:
    dec = BY_SYMBOL[pair]["decimals"]
    head, what = WORDS.get(kind, (kind, ""))
    line = f"{head} · <b>{p['direction']} {pair}</b> ({p['strategy']})\n{html.escape(what)}"
    if kind in ("TRAIL", "BE"):
        line += f"\nNew stop: <code>{price:.{dec}f}</code>"
    if kind == "TP1" and p.get("part"):
        line += f"\nClose {round(p['part'] * 100)} % at <code>{price:.{dec}f}</code>"
    if kind in ("TP", "STOP", "BE_STOP", "TRAIL_STOP", "TIME", "RISK_OFF") and "r" in out:
        line += f"\nResult: <b>{out['r']:+.2f}R</b> (after costs)"
    return line + "\n<i>Research, not advice.</i>"


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
        m5, st5, cost = live
        try:
            from .desk import _macro, _pause
            nl = await _pause(now)
            mv = await _macro() if pair == "AUD/CHF" else None
        except Exception:
            nl, mv = None, None
        events, out = follow(pair, p, m5, st5, cost, nl, (mv or {}).get("exits"))
        done = set(params.get("events") or [])
        new = []
        for j, kind, price in events:
            key = f"{kind}@{m5[j].time}"
            if key in done:
                continue
            done.add(key)
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
