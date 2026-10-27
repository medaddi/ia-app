"""Dashboard: my results (profit / loss days, week, month), the strategies' own track record, the live
analysis of every instrument and the next high-impact news, in one request. Numbers only come from
the trades users logged, the signals the app sent and the strategies' current output."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Signal, Trade, User
from ..strategies.service import STRATEGY_DEFS, all_results
from ..trading import effective_risk, signal_days, signal_json, stats, today_status, trade_days, trade_json
from .market import news_items

router = APIRouter(prefix="/api")


def _market_row(sym: str, r: dict) -> dict:
    s = r["setup"]
    single = bool(s) and s["params"].get("breakeven", True) is False  # set & forget: one target (TP3)
    target = (s["tp3"] if single else s["tp2"]) if s else None
    facts = r["facts"] or {}
    return {
        "symbol": sym, "strategy": r["strategyName"], "entryTf": STRATEGY_DEFS[sym].entryTf, "price": r["price"],
        "decimals": r["spec"]["decimals"], "status": r["status"], "score": r["score"], "bias": r["bias"]["direction"],
        "biasDetail": r["bias"]["detail"], "headline": r["headline"], "isOpen": r["market"]["isOpen"], "dataOk": r["dataQuality"]["ok"],
        "dataReason": r["dataQuality"]["reason"], "newsBlocked": r["news"]["blocked"], "nextNews": r["news"]["next"],
        "setup": {"direction": s["direction"], "entryType": s["entryType"], "entry": s["entry"], "sl": s["sl"], "target": target,
                  "rr": round(abs(target - s["entry"]) / abs(s["entry"] - s["sl"]), 2) if s["entry"] != s["sl"] else None,
                  "state": s["lifecycle"]["state"], "outcome": s["lifecycle"]["outcome"], "r": s["lifecycle"]["rMultiple"],
                  "isFresh": s["isFresh"], "signalTime": s["signalTime"]} if s else None,
        "lastTrade": facts.get("lastTrade"),
        "trend": {"weekly": facts.get("weeklyTrend"), "daily": facts.get("dailyTrend"), "h4": facts.get("trendH4"), "h1": facts.get("trend")},
        "grade": r.get("grade"), "liveGrade": r.get("liveGrade"),
    }


def _edge(trades: list[Trade]) -> dict:
    """Average win / loss, expectancy and result per pair of the closed trades (in $ from the lots taken)."""
    closed = [t for t in trades if t.status == "CLOSED" and t.result != "CANCELLED"]
    wins = [t.pnl or 0 for t in closed if (t.pnl or 0) > 0]
    losses = [t.pnl or 0 for t in closed if (t.pnl or 0) < 0]
    by_pair: dict[str, dict] = {}
    for t in closed:
        b = by_pair.setdefault(t.symbol, {"pnl": 0.0, "trades": 0, "wins": 0})
        b["pnl"] = round(b["pnl"] + (t.pnl or 0), 2)
        b["trades"] += 1
        b["wins"] += (t.pnl or 0) > 0
    r = [t.r_multiple or 0 for t in closed]
    return {
        "avgWin": round(sum(wins) / len(wins), 2) if wins else None, "avgLoss": round(sum(losses) / len(losses), 2) if losses else None,
        "expectancy": round(sum(t.pnl or 0 for t in closed) / len(closed), 2) if closed else None,
        "expectancyR": round(sum(r) / len(r), 2) if r else None,
        "payoff": round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 2) if wins and losses else None,
        "byPair": dict(sorted(by_pair.items(), key=lambda kv: -kv[1]["pnl"])),
    }


@router.get("/dashboard")
async def dashboard(u: User = Depends(current_user), db: Session = Depends(get_db)):
    trades = db.scalars(select(Trade).where(Trade.user_id == u.id).order_by(Trade.opened_at.desc())).all()
    signals = db.scalars(select(Signal).order_by(Signal.sent_at.desc())).all()
    results = await all_results()
    now = int(time.time())
    news = [n for n in await news_items() if n["importance"] == "HIGH" and datetime.fromisoformat(n["publishedAt"]).timestamp() > now - 1800]
    news.sort(key=lambda n: n["publishedAt"])
    return {
        "success": True, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "me": {
            "username": u.username, "riskUsd": effective_risk(u.risk_usd, u.capital, u.risk_pct), "capital": u.capital or None,
            "stats": stats(trades, "trade"), "today": today_status(trades, u.daily_loss_limit), "days": trade_days(trades), "edge": _edge(trades),
            "openTrades": [trade_json(t) for t in trades if t.status == "OPEN"],
        },
        "strategy": {
            "stats": stats(signals, "signal"), "days": signal_days(signals),
            "recent": [signal_json(s) for s in signals[:12]],
        },
        "markets": [_market_row(sym, r) for sym, r in zip(STRATEGY_DEFS, results)],
        "news": news[:8],
    }
