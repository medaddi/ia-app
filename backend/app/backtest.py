"""
Backtester. Runs the SAME strategy code as the live app (via replay): bar by bar, closed
candles only, spread + slippage from each strategy's config, the same order lifecycle
(limit fill / expiry / TP1 cancel, partials, breakeven, trailing runner).
Run from the command line: python -m app.backtest XAUUSD
"""

import asyncio
import sys
from datetime import datetime, timezone

from .strategies.eurusd.config import EUR_CONFIG
from .strategies.replay import outcome, replay
from .strategies.service import STRATEGY_DEFS, load_strategy_candles, normalize_symbol
from .strategies.shared.common import active_window
from .strategies.shared.jsnum import fmt_utc_minute, iso, round_to
from .strategies.shared.news import load_news_calendar
from .strategies.shared.types import TF_SEC
from .strategies.xauusd.config import XAU_CONFIG

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def backtest_on(sym: str, candles: dict, source: str, news: dict) -> dict:
    d = STRATEGY_DEFS[sym]
    entry = candles.get(d.entryTf) or []
    tf_sec = TF_SEC[d.entryTf]
    warmup = min(len(entry) - 1, 700)
    frm, to = entry[warmup].time, entry[-1].time + tf_sec
    base = {"candles": candles, "livePrice": 0, "spread": None, "isRealData": True, "dataSource": source, "news": news}
    state = replay(d, base, frm, to)
    index_of = {c.time: i for i, c in enumerate(entry)}
    windows = XAU_CONFIG["sessions"]["killzones"] if sym == "XAU/USD" else EUR_CONFIG["sessions"]["windows"]

    trades = []
    for e in state.emitted:
        lc = outcome(d, entry, index_of, e["setup"])
        t = e["signalTime"]
        win = active_window(t - 1, windows)
        s = e["setup"]
        trades.append({
            "id": e["id"], "setup": s["setup"], "direction": s["direction"], "signalTime": fmt_utc_minute(t),
            "session": win["name"] if win else "other", "weekday": WEEKDAYS[datetime.fromtimestamp(t, timezone.utc).weekday()],
            "score": e["score"], "entry": s["entry"], "sl": s["sl"], "tp1": s["tp1"], "tp2": s["tp2"], "plannedRr": round_to(s["rrTp2"], 2),
            "state": lc["state"], "outcome": lc["outcome"], "r": lc["rMultiple"],
            "events": " ".join(f"{ev['type']}@{iso(ev['time'])[5:16].replace('T', ' ')}" for ev in lc["events"]),
        })

    closed = [t for t in trades if t["state"] == "CLOSED"]
    wins = sum(t["outcome"] == "WIN" for t in closed)
    losses = sum(t["outcome"] == "LOSS" for t in closed)
    pos = sum(max(0, t["r"] or 0) for t in closed)
    neg = sum(min(0, t["r"] or 0) for t in closed)
    total_r = round_to(pos + neg, 2)
    eq = peak = max_dd = 0.0
    curve = []
    for t in closed:
        eq += t["r"] or 0
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
        curve.append({"time": t["signalTime"], "equityR": round_to(eq, 2)})

    def group(key):
        out: dict[str, dict] = {}
        for t in closed:
            g = out.setdefault(key(t), {"trades": 0, "totalR": 0.0, "wins": 0, "losses": 0})
            g["trades"] += 1
            g["totalR"] = round_to(g["totalR"] + (t["r"] or 0), 2)
            g["wins"] += t["outcome"] == "WIN"
            g["losses"] += t["outcome"] == "LOSS"
        return out

    days = (to - frm) / 86400
    warnings = []
    if len(closed) < 30:
        warnings.append(f"Only {len(closed)} closed trades: far too few to judge the strategy. Treat every number below as anecdotal.")
    if days < 180:
        warnings.append(f"History is only {days:.0f} days (Yahoo limits 5m/15m data to ~60 days). A 2–3 year test needs broker (MT5) history.")
    warnings.append("News filter uses the current ForexFactory week only: past news events are not filtered in this backtest.")
    warnings.append("Spread is a fixed config value (feed has no live spread); real spreads widen around news and rollover.")
    if len(closed) >= 10 and total_r <= 0:
        warnings.append("Net result is negative or flat over this sample.")
    costs = ({"spread": f"${XAU_CONFIG['filters']['assumedSpread']}", "slippage": f"${XAU_CONFIG['filters']['slippage']}"} if sym == "XAU/USD"
             else {"spread": f"{EUR_CONFIG['filters']['assumedSpreadPips']} pips", "slippage": f"{EUR_CONFIG['filters']['slippagePips']} pips"})
    return {
        "symbol": sym, "strategy": (XAU_CONFIG if sym == "XAU/USD" else EUR_CONFIG)["name"],
        "period": {"from": iso(frm)[:10], "to": iso(to)[:10], "days": round_to(days, 1)}, "dataSource": source, "costs": costs,
        "signals": len(trades), "filled": sum(t["state"] not in ("CANCELLED", "EXPIRED", "PENDING") for t in trades),
        "cancelledOrExpired": sum(t["state"] in ("CANCELLED", "EXPIRED") for t in trades), "closed": len(closed),
        "open": sum(t["state"] in ("OPEN", "TP1_HIT", "TP2_HIT", "PENDING") for t in trades),
        "wins": wins, "losses": losses, "breakevens": sum(t["outcome"] == "BREAKEVEN" for t in closed),
        "winRate": round_to(wins / (wins + losses) * 100, 1) if wins + losses else None,
        "profitFactor": round_to(pos / -neg, 2) if neg < 0 else None,
        "expectancyR": round_to(total_r / len(closed), 3) if closed else None, "totalR": total_r,
        "avgPlannedRr": round_to(sum(t["plannedRr"] for t in trades) / len(trades), 2) if trades else None,
        "maxDrawdownR": round_to(max_dd, 2), "tradesPerMonth": round_to(len(trades) / (days / 30.4), 1) if days > 0 else 0,
        "bySession": group(lambda t: t["session"]), "bySetup": group(lambda t: t["setup"]),
        "byWeekday": {k: {"trades": v["trades"], "totalR": v["totalR"]} for k, v in group(lambda t: t["weekday"]).items()},
        "equityCurve": curve, "trades": trades, "warnings": warnings,
    }


async def run_backtest(raw_symbol: str) -> dict:
    sym = normalize_symbol(raw_symbol)
    loaded, news = await asyncio.gather(load_strategy_candles(sym), load_news_calendar())
    if not loaded["isReal"]:
        raise RuntimeError(f"Live feed unavailable for {sym}: cannot backtest on synthetic candles")
    return await asyncio.to_thread(backtest_on, sym, loaded["candles"], loaded["source"], news)


if __name__ == "__main__":
    import json

    report = asyncio.run(run_backtest(sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"))
    print(json.dumps({k: v for k, v in report.items() if k not in ("trades", "equityCurve")}, indent=1, ensure_ascii=False))
