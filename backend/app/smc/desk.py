"""
Each pair's team, live: the shared engine (engine.py) run on the pair's latest closed candles (M5 entry, H1 context) with
the pair's own config (configs/<PAIR>.json). The research project (smc/) runs the same engine on stored history.

For each strategy S1–S4 the team says one of:
  SIGNAL    a setup whose rules AND the 7 questions pass, its limit not yet expired or its trade still running
  BLOCKED   a live setup whose rules pass but the checklist says no (the failed questions are given)
  WATCHING  the last step reached by a setup forming (what is missing)
  IDLE      nothing forming
Research, not advice: a SIGNAL is a setup the rules found, never a guarantee.
"""

import asyncio
import json
import time
from pathlib import Path
from ..market.data import fetch_candle_series, market_session_status
from . import engine
from .agents import team_agents
from .chart import analysis

CONFIGS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parent / "configs").glob("*.json"))}
BY_SYMBOL = {c["symbol"]: c for c in CONFIGS.values()}
PAIRS = ["XAU/USD", "EUR/USD", "GBP/USD", "EUR/CHF", "AUD/CAD", "AUD/CHF"]
M5_BARS, H1_BARS = 2000, 1500  # about 7 days of M5, 2 months of H1
TTL = 60
_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, asyncio.Lock] = {}
WATCH_HOURS = 6


def setup_id(pair: str, s: dict) -> str:
    return f"SMC-{pair.replace('/', '')}-{s['sid']}-{s['time']}-{'B' if s['dir'] > 0 else 'S'}"


def lots_for(cfg: dict, entry: float, sl: float, equity: float, risk_pct: float = 1.0) -> float:
    """Lots for `risk_pct` % of `equity` with this stop: risk / (stop in pips × pip value per lot), down to 0.01."""
    pips = abs(entry - sl) / cfg["pip"]
    if pips <= 0:
        return 0.0
    lots = equity * risk_pct / 100 / (pips * cfg["pip_value_usd_per_lot"])
    return max(0.0, int(lots * 100 + 1e-6) / 100)  # rounded down to 0.01 (the tolerance absorbs float error: 20 pips, not 19.99999)


def _draw(s: dict) -> dict:
    """The setup on the chart: its zone (OB / FVG / Asian box) and its entry, stop and target."""
    g = s.get("geo") or {}
    zones = []
    if g.get("ob"):
        top, bot, t0 = g["ob"]
        zones.append({"label": "H1 OB", "top": top, "bottom": bot, "from": t0})
    if g.get("gap"):
        bot, top, t0 = g["gap"]
        zones.append({"label": "M5 FVG", "top": top, "bottom": bot, "from": t0})
    if g.get("box"):
        hi, lo, t0, _t1 = g["box"]
        zones.append({"label": "Asian range", "top": hi, "bottom": lo, "from": t0})
    if g.get("candle"):
        hi, lo, t0 = g["candle"]
        zones.append({"label": "H1 candle", "top": hi, "bottom": lo, "from": t0})
    return {"entry": s["entry"], "sl": s["sl"], "tp": s["tp"], "zones": zones, "from": s["time"]}


def _setup_json(pair: str, cfg: dict, s: dict) -> dict:
    r = s["result"]
    return {"id": setup_id(pair, s), "strategy": s["sid"], "name": engine.STRATEGY_NAMES[s["sid"]], "direction": "BUY" if s["dir"] > 0 else "SELL",
            "time": s["time"], "entry": round(s["entry"], cfg["decimals"]), "sl": round(s["sl"], cfg["decimals"]), "tp": round(s["tp"], cfg["decimals"]),
            "rr": round(s["rr"], 2), "validUntil": s["time"] + engine.EXPIRY[engine.STRATEGY_OF[s["sid"]]] * engine.M5S,
            "state": r["state"], "pass": s["pass"], "checklist": [{"q": a, "ok": ok, "detail": det} for a, ok, det in s["checklist"]],
            "steps": [{"step": a, "ok": ok, "detail": det} for a, ok, det in s["steps"]],
            "lots": {"1000": lots_for(cfg, s["entry"], s["sl"], 1000), "10000": lots_for(cfg, s["entry"], s["sl"], 10000)},
            "draw": _draw(s)}


def read_team(pair: str, cfg: dict, m5, h1, now: int) -> dict:
    """The team's answer from candles (sync: configure + scan run together, nothing else can change the engine's config)."""
    engine.configure(cfg, [])
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    res = engine.scan_all(m5, h1, cost, cfg["decimals"])
    strategies = []
    for sid in ("S1", "S2", "S3", "S4"):
        live = [s for s in res[sid]["setups"] if s["result"]["state"] in ("PENDING", "ACTIVE")]
        row = {"id": sid, "name": engine.STRATEGY_NAMES[sid], "status": "IDLE", "setup": None, "watch": None}
        good = [s for s in live if s["pass"] and abs(s["entry"] - s["sl"]) >= cfg["min_stop_cost_ratio"] * cost]
        if good:
            row.update(status="SIGNAL", setup=_setup_json(pair, cfg, good[-1]))
        elif live:
            row.update(status="BLOCKED", setup=_setup_json(pair, cfg, live[-1]))
        else:
            w = [x for x in res[sid]["watch"] if x["time"] >= now - WATCH_HOURS * 3600]
            if w:
                x = w[-1]
                row.update(status="WATCHING", watch={"time": x["time"], "direction": "BUY" if x["dir"] > 0 else "SELL",
                                                     "steps": [{"step": a, "ok": ok, "detail": det} for a, ok, det in x["steps"]]})
        strategies.append(row)
    chart = analysis(m5, res["_h1v"], cfg["decimals"], now,  # the team's read, drawn on its pair's chart
                     next((r["setup"] for r in reversed(strategies) if r["status"] == "SIGNAL"), None))
    return {"success": True, "symbol": pair, "at": now, "lastCandle": m5[-1].time if m5 else None, "strategies": strategies,
            "signals": [r["setup"] for r in strategies if r["status"] == "SIGNAL"], "chart": chart,
            "agents": team_agents(pair, cfg, m5, res["_h1v"], strategies, chart, now)}  # the team's seven role agents


async def team(pair: str, fresh: bool = False) -> dict:
    """The pair's team now (cached a minute: every screen and the notifier share one read)."""
    if pair not in BY_SYMBOL:
        return {"success": False, "symbol": pair, "error": "not a pair of the app"}
    hit = _cache.get(pair)
    if hit and not fresh and hit[0] > time.time():
        return hit[1]
    lock = _locks.setdefault(pair, asyncio.Lock())
    async with lock:
        hit = _cache.get(pair)
        if hit and not fresh and hit[0] > time.time():
            return hit[1]
        cfg = BY_SYMBOL[pair]
        m5s, h1s = await asyncio.gather(fetch_candle_series(pair, "5M", M5_BARS, fresh=fresh), fetch_candle_series(pair, "1H", H1_BARS, fresh=fresh))
        now = int(time.time())
        # only CLOSED candles: the forming one would change before its close
        m5 = [c for c in m5s["candles"] if c.time + 300 <= now]
        h1 = [c for c in h1s["candles"] if c.time + 3600 <= now]
        if m5s["isSynthetic"] or h1s["isSynthetic"] or len(m5) < 300 or len(h1) < 300:
            out = {"success": False, "symbol": pair, "at": now, "error": "no live candles from the feed right now"}
        else:
            out = read_team(pair, cfg, m5, h1, now)
            out["marketOpen"] = market_session_status(pair)["isOpen"]
            out["source"] = m5s["source"]
        _cache[pair] = (time.time() + TTL, out)
        return out

