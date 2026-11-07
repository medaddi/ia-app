"""
Each pair's team, live, on the pair's latest closed candles with the pair's own config (configs/<PAIR>.json).
The team trades ONLY its pair's strategies from the user's guide (playbook.py: gold ICT Silver Bullet, EUR/USD Judas
swing + SnapBack 3σ, GBP/USD overlap sweep + EMA pullback, EUR/CHF and AUD/CAD time-filtered 3σ mean reversion, AUD/CHF
risk-on carry swing). The pair's chart shows that strategy's own levels, windows and lines. The shared SMC engine
(engine.py) only gives the agents the H1 / H4 structure they describe.

For the pair's strategy the team says one of:
  SIGNAL    a setup whose rules AND the guide's checklist pass, its limit not yet expired or its trade still running
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
from . import engine, playbook
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
LIVE: dict[str, tuple] = {}  # pair → (closed M5 candles, their structure, cost) of the last read
_PLAY_FILE = Path(__file__).parent / "research" / "playbook.json"
PLAY_RESULTS = json.loads(_PLAY_FILE.read_text(encoding="utf-8")) if _PLAY_FILE.exists() else {}  # smc/tools/playbook_test.py


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
    return {"entry": s["entry"], "sl": s["sl"], "tp": s["tp"], "zone": [min(s["zone"]), max(s["zone"])], "zones": zones, "from": s["time"]}


def _setup_json(pair: str, cfg: dict, s: dict) -> dict:
    r = s["result"]
    return {"id": setup_id(pair, s), "strategy": s["sid"], "name": engine.STRATEGY_NAMES[s["sid"]], "direction": "BUY" if s["dir"] > 0 else "SELL",
            "time": s["time"], "entry": round(s["entry"], cfg["decimals"]), "sl": round(s["sl"], cfg["decimals"]), "tp": round(s["tp"], cfg["decimals"]),
            # the entry is a ZONE, not one price: the limit sits at its near edge, so price only has to come into it
            "zone": [round(min(s["zone"]), cfg["decimals"]), round(max(s["zone"]), cfg["decimals"])],
            "rrBest": round(abs(s["tp"] - (2 * s["ideal"] - s["entry"])) / abs(2 * s["ideal"] - s["entry"] - s["sl"]), 2),
            "rr": round(s["rr"], 2), "validUntil": s["time"] + engine.EXPIRY[engine.STRATEGY_OF[s["sid"]]] * engine.M5S,
            "state": r["state"], "pass": s["pass"], "checklist": [{"q": a, "ok": ok, "detail": det} for a, ok, det in s["checklist"]],
            "steps": [{"step": a, "ok": ok, "detail": det} for a, ok, det in s["steps"]],
            "lots": {"1000": lots_for(cfg, s["entry"], s["sl"], 1000), "10000": lots_for(cfg, s["entry"], s["sl"], 10000)},
            "draw": _draw(s)}


def _play_draw(s: dict) -> dict:
    """The playbook setup on the chart: its zones (Asian range, FVG, OB, S&D zone, Fib zone) and its levels."""
    g = s.get("geo") or {}
    zones = []
    if g.get("asia"):
        hi, lo, t0, _t1 = g["asia"]
        zones.append({"label": "Asian range", "top": hi, "bottom": lo, "from": t0})
    if g.get("fvg"):
        a, b, t0 = g["fvg"]
        zones.append({"label": "M5 FVG", "top": max(a, b), "bottom": min(a, b), "from": t0})
    if g.get("ob"):
        top, bot, t0 = g["ob"]
        zones.append({"label": "M15 Order Block", "top": top, "bottom": bot, "from": t0})
    if g.get("zone"):
        a, b, t0 = g["zone"]
        zones.append({"label": "H1 supply / demand", "top": max(a, b), "bottom": min(a, b), "from": t0})
    if g.get("fib"):
        f50, f618, _f786, _b, _a, t0 = g["fib"]
        zones.append({"label": "Fib 50-61.8 %", "top": max(f50, f618), "bottom": min(f50, f618), "from": t0})
    return {"entry": s["entry"], "sl": s["sl"], "tp": s["tp"], "zone": [min(s["zone"]), max(s["zone"])], "zones": zones, "from": s["time"]}


def _play_json(pair: str, cfg: dict, s: dict) -> dict:
    dec = cfg["decimals"]
    rd = lambda v: None if v is None else round(v, dec)  # noqa: E731
    lots = {"1000": lots_for(cfg, s["entry"], s["sl"], 1000), "10000": lots_for(cfg, s["entry"], s["sl"], 10000)}
    chk = [(q, ok, f"{lots['1000']} lot / $1,000 · {lots['10000']} / $10,000" if q.startswith("4 ·") else det) for q, ok, det in s["checklist"]]
    return {"id": setup_id(pair, s), "strategy": s["sid"], "name": playbook.NAMES[pair.replace("/", "")][s["sid"]], "direction": "BUY" if s["dir"] > 0 else "SELL",
            "time": s["time"], "entry": rd(s["entry"]), "sl": rd(s["sl"]), "tp": rd(s["tp"]), "tp1": rd(s["tp1"]), "part": s["part"],
            "market": s["market"], "zone": [rd(min(s["zone"])), rd(max(s["zone"]))], "rr": round(s["rr"], 2), "rrBest": round(s["rr"], 2),
            "validUntil": s["time"] + s["expiry"] * engine.M5S, "liveUntil": s["holdUntil"], "expiry": s["expiry"], "holdUntil": s["holdUntil"],
            "state": s["result"]["state"], "pass": s["pass"], "checklist": [{"q": a, "ok": ok, "detail": det} for a, ok, det in chk],
            "steps": [{"step": a, "ok": ok, "detail": det} for a, ok, det in s["steps"]], "lots": lots, "draw": _play_draw(s)}


def read_team(pair: str, cfg: dict, m5, h1, now: int, cot: dict | None = None, sent: list[dict] | None = None,
              news: list[dict] | None = None, d1=None) -> dict:
    """The team's answer from candles (sync: configure + scan run together, nothing else can change the engine's config)."""
    engine.configure(cfg, [e["time"] for e in (news or [])])  # question 6: no entry 15 min around this pair's high-impact news
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    res = engine.scan_all(m5, h1, cost, cfg["decimals"])
    LIVE[pair] = (m5, res["_st5"], cost)  # the candles and the M5 structure the trade manager follows the sent setups with
    key = pair.replace("/", "")
    setups, watch = playbook.scan(key, m5, h1, cfg["pip"], cost, None if news is None else [e["time"] for e in news], None, d1)
    pr = (PLAY_RESULTS.get(key) or {}).get("strategies", {})
    strategies, raw_shown = [], None
    for sid in playbook.STRATEGIES[key]:
        mine = [s for s in setups if s["sid"] == sid]
        live = [s for s in mine if s["result"]["state"] in ("PENDING", "ACTIVE")]
        row = {"id": sid, "name": playbook.NAMES[key][sid], "status": "IDLE", "setup": None, "watch": None,
               "claimed": playbook.CLAIMED[(key, sid)], "measured": (pr.get(sid) or {}).get("all")}
        good = [s for s in live if s["pass"] and abs(s["entry"] - s["sl"]) >= cfg["min_stop_cost_ratio"] * cost]
        if good:
            row.update(status="SIGNAL", setup=_play_json(pair, cfg, good[-1]))
            raw_shown = raw_shown or good[-1]
        elif live:
            row.update(status="BLOCKED", setup=_play_json(pair, cfg, live[-1]))
        else:
            w = [x for x in watch if x.get("sid", sid) == sid and x["time"] >= now - WATCH_HOURS * 3600]
            if w:
                x = w[-1]
                row.update(status="WATCHING", watch={"time": x["time"], "direction": "BUY" if x["dir"] > 0 else "SELL",
                                                     "steps": [{"step": a, "ok": ok, "detail": det} for a, ok, det in x["steps"]]})
        strategies.append(row)
    shown = next((r["setup"] for r in strategies if r["status"] == "SIGNAL"), None)
    ctx = analysis(m5, res["_h1v"], cfg["decimals"], now, shown)  # the SMC read the agents describe (not drawn)
    chart = {"trend": ctx["trend"], "premium": ctx["premium"],  # the chart: the pair's strategy, nothing else
             **playbook.draw(key, m5, h1, now, raw_shown or next((s for s in reversed(setups) if s["result"]["state"] in ("PENDING", "ACTIVE")), None),
                             cfg["decimals"], d1)}
    chart["trade"] = None
    if shown:
        d = 1 if shown["direction"] == "BUY" else -1
        chart["trade"] = {"from": shown["time"], "to": max(shown.get("liveUntil") or shown["validUntil"], shown["time"] + 4 * 3600), "entry": shown["entry"],
                          "zone": shown.get("zone"), "sl": shown["sl"], "tp": shown["tp"], "dir": d, "label": f"{shown['name']} {shown['direction']} · 1:{shown['rr']}"}
        if shown.get("tp1") is not None:
            chart["segments"].append({"from": shown["time"], "to": chart["trade"]["to"], "price": shown["tp1"], "kind": "liquidity", "dir": d,
                                      "label": f"TP1 ({round(shown['part'] * 100)} %, stop to entry)"})
    return {"success": True, "symbol": pair, "at": now, "lastCandle": m5[-1].time if m5 else None, "strategies": strategies,
            "signals": [r["setup"] for r in strategies if r["status"] == "SIGNAL"], "chart": chart,
            "playbook": {"name": playbook.team_name(key), "source": (PLAY_RESULTS.get(key) or {}).get("source"),
                         "from": (PLAY_RESULTS.get(key) or {}).get("from"), "to": (PLAY_RESULTS.get(key) or {}).get("to")},
            "cot": cot, "news": news, "agents": team_agents(pair, cfg, m5, res["_h1v"], strategies, ctx, now, cot, sent or [], news)}  # the team's seven role agents


def pair_currencies(pair: str) -> set[str]:
    """The currencies whose news moves the pair (gold: the dollar)."""
    a, b = pair.split("/")
    return {"USD"} if a == "XAU" else {a, b}


async def _news(pair: str) -> list[dict] | None:
    """This pair's high-impact releases this week (the app's ForexFactory calendar, cached an hour); None when unavailable."""
    from ..market.news import load_news_calendar
    try:
        cal = await asyncio.wait_for(load_news_calendar(), 6)
    except Exception:
        return None
    if cal.get("source") == "none":
        return None
    cur = pair_currencies(pair)
    return sorted(({"time": e["time"], "currency": e["currency"], "title": e["title"]} for e in cal["events"]
                   if e.get("impact") == "High" and e.get("currency") in cur), key=lambda e: e["time"])


async def _cot(pair: str) -> dict | None:
    """The pair's COT view from the trader-skill (CFTC, cached 6 h); None when the report cannot be read within 4 s."""
    from .skill.cot import cot_all
    try:
        rows = await asyncio.wait_for(cot_all(), 4)
    except Exception:
        return None
    row = next((r for r in rows if r["symbol"] == pair), None)
    return {k: v for k, v in row.items() if k != "legs"} if row else None


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
        try:  # daily candles for the ADR (5, 20 and 250 days) the strategies and the regime check use
            ds = await fetch_candle_series(pair, "1D", 300, fresh=fresh)
            d1 = None if ds["isSynthetic"] else [c for c in ds["candles"] if c.time + 86400 <= now]
        except Exception:
            d1 = None
        # only CLOSED candles: the forming one would change before its close
        m5 = [c for c in m5s["candles"] if c.time + 300 <= now]
        h1 = [c for c in h1s["candles"] if c.time + 3600 <= now]
        if m5s["isSynthetic"] or h1s["isSynthetic"] or len(m5) < 300 or len(h1) < 300:
            out = {"success": False, "symbol": pair, "at": now, "error": "no live candles from the feed right now"}
        else:
            cot = await _cot(pair)  # the trader-skill's positioning (context only), never blocking the read
            try:
                from .notify import sent_setups
                sent = sent_setups()
            except Exception:  # no database (tests, a cold start): the risk check counts nothing live
                sent = []
            out = read_team(pair, cfg, m5, h1, now, cot, sent, await _news(pair), d1)
            out["marketOpen"] = market_session_status(pair)["isOpen"]
            out["source"] = m5s["source"]
        _cache[pair] = (time.time() + TTL, out)
        return out

