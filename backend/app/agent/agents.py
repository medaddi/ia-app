"""
Three agents, one trade: a signal goes out only when all three agree.

1. Market Analysis agent: reads the market on its own (not the strategy's rules): the daily trend (EMA20 / EMA50 on daily
   candles), the volatility regime (ATR now vs its usual level) and the high-impact news ahead. It writes a trend report
   and objects to a trade against the daily trend, in a volatility spike, or with major news less than an hour away.
2. Strategy agent: takes the strategy's own decision (rules, score, a fresh setup it may notify) and the market report,
   and builds the plan (entry, stop, target, R:R). It agrees only with a valid signal that fits the report.
3. Risk & Execution agent: the AI trade desk (rules re-checked, live data, price drift, live R:R, market open, currency
   exposure) plus the book: at most MAX_OPEN signals open at once. It approves the final order.

Measured on each pair's past trades, the market agent's trend veto blocked 8 of 111 trades for about the same total result
(+0.3R): it mostly removes counter-trend trades, it is not a profit engine. Each agent can only block, never create a trade.
"""

import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal
from ..strategies.shared.types import Candle
from .trade_desk import OPEN_STATES, review

MAX_OPEN = 4  # signals open at the same time across every pair
NEWS_AHEAD_SEC = 3600  # major news of the pair's currencies less than an hour away: no new trade
SPIKE_ATR = 2.5  # ATR(14) above 2.5 × its usual level = volatility spike
DAILY_FAST, DAILY_SLOW = 20, 50


def _ema(vals: list[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    k, e = 2 / (n + 1), vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _daily(c: list[Candle]) -> list[tuple[float, float, float, float]]:
    days: dict[int, list[float]] = {}
    for x in c:
        k = x.time // 86400
        if k not in days:
            days[k] = [x.open, x.high, x.low, x.close]
        else:
            d = days[k]
            d[1], d[2], d[3] = max(d[1], x.high), min(d[2], x.low), x.close
    return [tuple(days[k]) for k in sorted(days)]


def _vote(key: str, name: str, agree: bool, summary: str, checks: list[dict], extra: Optional[dict] = None) -> dict:
    return {"key": key, "name": name, "agree": bool(agree), "summary": summary, "checks": checks, **(extra or {})}


def _check(label: str, passed: bool, detail: str) -> dict:
    return {"label": label, "passed": bool(passed), "detail": detail}


def market_agent(r: dict, candles: list[Candle], news_events: list[dict], now: Optional[int] = None) -> dict:
    """The market report (always), and the agent's vote on the strategy's trade when there is one."""
    now = now or int(time.time())
    s = r.get("setup")
    d = r["spec"]["decimals"]
    closed = [x for x in candles if x.time < now - 1]
    days = _daily(closed)[:-1]  # complete days only
    closes = [x[3] for x in days]
    fast, slow = _ema(closes, DAILY_FAST), _ema(closes, DAILY_SLOW)
    if fast is None or slow is None:
        trend, trend_txt = 0, "not enough daily history"
    else:
        trend = 1 if fast > slow and closes[-1] > slow else -1 if fast < slow and closes[-1] < slow else 0
        trend_txt = (f"EMA{DAILY_FAST} {fast:.{d}f} {'>' if fast > slow else '<'} EMA{DAILY_SLOW} {slow:.{d}f}, "
                     f"close {closes[-1]:.{d}f}")
    tr = [max(x.high, p.close) - min(x.low, p.close) for p, x in zip(closed[-501:-1], closed[-500:])]
    atr = sum(tr[-14:]) / 14 if len(tr) >= 14 else 0
    usual = sorted(tr)[len(tr) // 2] if tr else 0
    ratio = atr / usual if usual else 1
    regime = "spike" if ratio > SPIKE_ATR else "high" if ratio > 1.5 else "low" if ratio < 0.7 else "normal"
    ccys = set(r["spec"]["displaySymbol"].split("/"))
    ahead = sorted((e for e in news_events if e.get("impact") == "High" and e.get("currency") in ccys and 0 < e["time"] - now <= 6 * 3600),
                   key=lambda e: e["time"])
    soon = [e for e in ahead if e["time"] - now <= NEWS_AHEAD_SEC]
    word = {1: "bullish", -1: "bearish", 0: "neutral"}[trend]
    report = {"dailyTrend": word, "trendDetail": trend_txt, "volatility": regime, "atrRatio": round(ratio, 2),
              "newsAhead": [{"currency": e["currency"], "title": e["title"], "inMin": int((e["time"] - now) // 60)} for e in ahead[:3]]}
    checks = [_check("Daily trend", True, f"{word} ({trend_txt})"),
              _check("Volatility regime", regime != "spike", f"{regime}: ATR {ratio:.2f}× its usual level"),
              _check("No major news within 1 h", not soon, f"{soon[0]['currency']} {soon[0]['title']} in {int((soon[0]['time'] - now) // 60)} min" if soon else
                     (f"next: {ahead[0]['currency']} {ahead[0]['title']} in {int((ahead[0]['time'] - now) // 60)} min" if ahead else "none in the next 6 h"))]
    if s:
        side = 1 if s["direction"] == "BUY" else -1
        checks.insert(1, _check("Trade with the daily trend (or a neutral one)", trend != -side,
                                f"{s['direction']} vs a {word} daily trend"))
    agree = bool(s) and all(c["passed"] for c in checks)
    summary = (f"Daily trend {word}, volatility {regime}" + (f", {len(ahead)} major news in 6 h" if ahead else ", no major news ahead")
               + ("" if not s else " · agrees with the trade" if agree else " · objects: " + "; ".join(c["label"] for c in checks if not c["passed"])))
    return _vote("market", "Market analysis", agree, summary, checks, {"report": report, "bias": word})


def strategy_agent(r: dict, market: dict) -> dict:
    """The strategy's decision turned into a plan; agrees with a valid, fresh signal that fits the market report."""
    s = r.get("setup")
    if not s:
        return _vote("strategy", "Strategy", False, r.get("headline") or "No setup", [_check("A setup", False, r.get("rejection") or r.get("headline", ""))])
    risk = abs(s["entry"] - s["sl"])
    rr = abs(s["tp3"] - s["entry"]) / risk if risk else 0
    d = r["spec"]["decimals"]
    plan = {"direction": s["direction"], "entryType": s["entryType"], "entry": s["entry"], "sl": s["sl"], "tp": s["tp3"], "rr": round(rr, 2)}
    checks = [
        _check("Strategy rules: signal", r["status"] == "SIGNAL", f"{r['status']} · score {r['score']}"),
        _check("Fresh setup the strategy may send", bool(r.get("canNotify")) and s["lifecycle"]["state"] in ("PENDING", "OPEN"), s["lifecycle"]["state"]),
        _check("Fits the market report", market["bias"] == "neutral" or (market["bias"] == "bullish") == (s["direction"] == "BUY"),
               f"{s['direction']} with a {market['bias']} daily trend"),
    ]
    agree = all(c["passed"] for c in checks)
    summary = f"{s['direction']} {s['entryType']} {s['entry']:.{d}f} · SL {s['sl']:.{d}f} · TP {s['tp3']:.{d}f} (1:{rr:.1f})"
    return _vote("strategy", "Strategy", agree, summary, checks, {"plan": plan})


def risk_agent(r: dict, db: Optional[Session]) -> dict:
    """The AI trade desk plus the size of the book: approves the final order."""
    if not r.get("setup"):
        return _vote("risk", "Risk & execution", False, "Nothing to execute", [])
    desk = review(r, db)
    checks = [_check(c["label"], c["passed"], c["detail"]) for c in desk["checks"]]
    if db is not None:
        n = len(db.scalars(select(Signal.id).where(Signal.state.in_(OPEN_STATES), Signal.id != r["setup"]["id"])).all())
        checks.append(_check(f"At most {MAX_OPEN} signals open across every pair", n < MAX_OPEN, f"{n} open now"))
    agree = all(c["passed"] for c in checks)
    summary = "Order approved" if agree else "Blocked: " + "; ".join(c["label"] for c in checks if not c["passed"])
    return _vote("risk", "Risk & execution", agree, summary, checks, {"score": desk["score"]})


def consensus(r: dict, candles: list[Candle], news_events: list[dict], db: Optional[Session]) -> dict:
    """The three votes; `approved` only when all three agree."""
    market = market_agent(r, candles, news_events)
    strategy = strategy_agent(r, market)
    risk = risk_agent(r, db)
    agents = [market, strategy, risk]
    agreed = sum(a["agree"] for a in agents)
    approved = agreed == 3
    return {"approved": approved, "agreed": agreed, "agents": agents,
            "summary": "3/3 agents agree: the trade is sent" if approved else f"{agreed}/3 agents agree: no trade",
            "issues": [f"{a['name']}: {a['summary']}" for a in agents if not a["agree"]]}


def market_candles(bundle: dict) -> list[Candle]:
    """The candles the market agent reads: hourly where the strategy has them (gold, GPA), else H4 (RSI(2))."""
    c = bundle.get("candles") or {}
    return c.get("H1") or c.get("H4") or next(iter(c.values()), [])
