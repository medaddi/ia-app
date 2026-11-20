"""
Each pair's team, live, on the pair's latest closed candles with the pair's own config (configs/<PAIR>.json).
Every team runs FX Alex G Set & Forget (the owner's specification of 2026-11-20, package fxag/) with its 8 agents:
DataGuard, StructureEngine, ZoneArchitect, ConfluenceScorer, EntrySniper, RiskGovernor, SetupAuditor, OrderExecutor.
Each setup class (SYNC, RETRACE, COUNTER) says one of:
  SIGNAL    an approved trade (score >= 80 %, SoS + Engulfing, R:R >= 2.0, the auditor's APPROVE), locked Set & Forget
  BLOCKED   a recent two-step trigger that failed the gate (the failed lines are given)
  WATCHING  Tier 1 at the AOI with the SoS confirmed, the H1 / H2 / H4 engulfing awaited
  IDLE      nothing forming
Research, not advice: a SIGNAL is a setup the rules found, never a guarantee. The app places no order.
"""

import asyncio
import json
import time
from pathlib import Path

from ..market.data import fetch_candle_series, fetch_live_price, market_session_status
from ..market.pairs import PAIRS as FX_PAIRS
from . import playbook
from .fxag import engine as fx

CONFIGS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parent / "configs").glob("*.json"))}
BY_SYMBOL = {c["symbol"]: c for c in CONFIGS.values()}
PAIRS = ["XAU/USD", *FX_PAIRS]  # FXAlexG's watchlist: gold + the 28 forex pairs
M5_BARS, H1_BARS, D1_BARS = 2000, 6600, 1600  # H1 6600: 270+ NY-aligned D candles (250 for the D AOIs); D1 1600: the W memory (150 weeks)
TTL = 60
FRESH_SEC = 20 * 60  # CHOICE: a market entry is alerted only within 20 minutes of its trigger candle (never a stale price)
_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, asyncio.Lock] = {}
_cpu_gate: list = []


def _cpu() -> asyncio.Semaphore:
    """One strategy read at a time in its worker thread (several Python threads side by side starve the server more)."""
    if not _cpu_gate:
        _cpu_gate.append(asyncio.Semaphore(1))
    return _cpu_gate[0]
LIVE: dict[str, tuple] = {}  # pair → (closed M5 candles, cost, news times) of the last read: what the trade manager follows
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
    return max(0.0, int(lots * 100 + 1e-6) / 100)


def _setup_json(pair: str, cfg: dict, s: dict) -> dict:
    dec = cfg["decimals"]
    rd = lambda v: None if v is None else round(v, dec)  # noqa: E731
    rk = s.get("riskPct", 1.0)
    lots = {"1000": lots_for(cfg, s["entry"], s["sl"], 1000, rk), "10000": lots_for(cfg, s["entry"], s["sl"], 10000, rk)}
    g = s.get("geo") or {}
    zones = [{"label": "AOI", "top": g["aoi"][1], "bottom": g["aoi"][0], "from": g["aoi"][2]}] if g.get("aoi") else []
    zi = s.get("zoneInfo") or {}
    invalidation = (f"{'Below' if s['dir'] > 0 else 'Above'} {rd(s['sl'])}: price through the AOI ({rd(zi.get('low'))} – {rd(zi.get('high'))}) "
                    "and the last swing, plus a volatility buffer and the spread") if zi else None
    return {"id": setup_id(pair, s), "strategy": s["sid"], "name": playbook.NAMES[pair.replace("/", "")][s["sid"]],
            "direction": "BUY" if s["dir"] > 0 else "SELL", "time": s["time"], "entry": rd(s["entry"]), "sl": rd(s["sl"]), "tp": rd(s["tp"]),
            "tp1": rd(s["tp1"]), "part": s["part"], "market": s["market"], "zone": [rd(min(s["zone"])), rd(max(s["zone"]))],
            "rr": round(s["rr"], 2), "rrBest": round(s["rr"], 2), "validUntil": s["time"] + s["expiry"] * playbook.M5S, "liveUntil": s["holdUntil"],
            "expiry": s["expiry"], "holdUntil": s["holdUntil"], "beOff": s.get("beOff", 0.0), "newsMin": s.get("newsMin", playbook.NEWS_MIN),
            "state": s["result"]["state"], "pass": s["pass"], "checklist": [{"q": a, "ok": ok, "detail": det} for a, ok, det in s["checklist"]],
            "steps": [{"step": a, "ok": ok, "detail": det} for a, ok, det in s["steps"]], "lots": lots, "riskPct": rk,
            "grade": s.get("grade"), "gpa": s.get("gpa"), "consensus": s.get("consensus"), "setupType": s.get("setupType"), "etf": s.get("etf"),
            "family": "counter-trend" if s.get("setupType") == "COUNTER" else "trend-following", "invalidation": invalidation,
            "score": s.get("score"), "sos": s.get("sos"), "struct": s.get("struct"), "spreadPct": s.get("spreadPct"), "lots10k": s.get("lots10k"),
            "newsChecked": s.get("newsChecked"), "sosTf": s.get("sosTf"), "orderType": s.get("orderType"), "breakdown": s.get("breakdown"),
            "alignmentStrength": s.get("alignmentStrength"), "sosInfo": s.get("sosInfo"), "proposal": s.get("proposal"), "audit": s.get("audit"),
            "target": s.get("target"), "capped": s.get("capped"),
            "checklistGpa": s.get("checklistGpa"), "desk": s.get("desk"), "zoneInfo": s.get("zoneInfo"), "slPips": s.get("slPips"),
            "tpPips": s.get("tpPips"), "bePips": s.get("bePips"), "psychTp": s.get("psychTp"), "fridayExit": s.get("fridayExit"),
            "draw": {"entry": s["entry"], "sl": s["sl"], "tp": s["tp"], "zone": [min(s["zone"]), max(s["zone"])], "zones": zones, "from": s["time"]}}


def read_team(pair: str, cfg: dict, m5, h1, now: int, news: list[dict] | None = None, d1=None) -> dict:
    """The 8 agents' answer from closed candles (W / D / H4 / H2 / H1 / M30 / M15 decide; M5 follows the trades)."""
    key = pair.replace("/", "")
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    spread = cfg.get("live_spread") or None
    setups, _ = fx.scan(key, m5, h1, cost, news, d1, spread)
    LIVE[pair] = (m5, cost, fx.news_times(key, news) if news is not None else None)
    rep = fx.report(key, m5, h1, now, setups, news, d1, spread)
    for s in setups:  # only the trade the desk shows as running stays a signal
        if s["pass"] and rep["candidate"] is not s:
            s["pass"] = False
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE")]
    good = [s for s in live if s["pass"]]
    pr = (PLAY_RESULTS.get(key) or {}).get("strategies", {})
    r = rep["read"]
    rows = []
    for sid in playbook.STRATEGIES[key]:  # SYNC, RETRACE, COUNTER
        row = {"id": sid, "name": playbook.NAMES[key][sid], "status": "IDLE", "setup": None, "watch": None,
               "claimed": playbook.CLAIMED[(key, sid)], "measured": (pr.get(sid) or {}).get("all")}
        mine_good = [s for s in good if s["sid"] == sid]
        mine_live = [s for s in live if s["sid"] == sid]
        if mine_good:
            row.update(status="SIGNAL", setup=_setup_json(pair, cfg, mine_good[-1]))
        elif mine_live and now - mine_live[-1]["time"] <= 6 * 3600:
            row.update(status="BLOCKED", setup=_setup_json(pair, cfg, mine_live[-1]))
        elif r["aligned"] and fx.SID.get(r["align"]["kind"]) == sid and r["tier"] in ("TIER_1_SOS_CONFIRMED", "AWAIT_PULLBACK_LIMIT"):
            row.update(status="WATCHING", watch={"time": r["sos"]["time"], "direction": "BUY" if r["dir"] > 0 else "SELL", "steps": [
                {"step": r["align"]["label"], "ok": True, "detail": ""},
                {"step": f"At {r['zone']['kind']} AOI ({r['zone']['touches']} touches)", "ok": True, "detail": ""},
                {"step": f"{r['sos']['tf']} Shift of Structure", "ok": True, "detail": ""},
                {"step": "H1 / H2 / H4 Engulfing close", "ok": False, "detail": "awaited"}]})
        rows.append(row)
    shown = next((r_["setup"] for r_ in rows if r_["status"] == "SIGNAL"), None)
    b4 = r["bias"]["H4"]
    chart = {"trend": "BULLISH" if b4 > 0 else "BEARISH" if b4 < 0 else "UNDEFINED", "premium": False, "windows": [],
             **fx.draw_objects(key, m5, h1, now, lambda v: round(v, cfg["decimals"]), d1, spread, r.get("zone")), "trade": None}
    signals = []
    if shown:
        d = 1 if shown["direction"] == "BUY" else -1
        chart["trade"] = {"from": shown["time"], "to": max(shown["time"] + 24 * 3600, now + 6 * 3600), "entry": shown["entry"], "zone": shown["zone"],
                          "sl": shown["sl"], "tp": shown["tp"], "dir": d, "rr": shown["rr"], "tp1": None,
                          "label": f"{shown['direction']} · {shown['setupType']} · {shown.get('etf') or ''} · grade {shown['grade']} (signal)"}
        if now - shown["time"] <= FRESH_SEC:  # a market entry is alerted only while its price is fresh
            signals = [shown]
    c = rep["contract"]
    arrows = " ".join(f"{n} {'↑' if r['bias'][n] > 0 else '↓' if r['bias'][n] < 0 else '·'}" for n in ("W", "D", "H4"))
    return {"success": True, "symbol": pair, "at": now, "lastCandle": m5[-1].time if m5 else None, "strategies": rows, "signals": signals,
            "chart": chart, "playbook": {"name": playbook.STRATEGY_NAME, "source": (PLAY_RESULTS.get(key) or {}).get("source"),
                                         "from": (PLAY_RESULTS.get(key) or {}).get("from"), "to": (PLAY_RESULTS.get(key) or {}).get("to")},
            "badge": f"{arrows} · Score {c['gpa_score']}% ({c['grade']})", "grade": c["grade"], "gpa": c["gpa_score"], "consensus": c["consensus_score"],
            "decision": c["final_decision"], "direction": c["direction"], "setupType": c["setup_type"], "checklist": c["checklist"],
            "tier": rep["tier"], "alignment": c["alignment"], "radar": None, "news": news, "pairReport": c, "agents": rep["agents"]}


_ARROW = {"↑": 1, "↓": -1}


def summary(pair: str, t: dict) -> dict:
    """One pair's state in a few fields, for the dashboard's overview of all the pairs (saved by the notifier every minute):
    the verdict, the direction, the grade and its score, the W1 / D1 / H4 trend, the 5 agents' statuses, the setup being
    watched, the trade if there is one, and the last close."""
    trend = {}
    for tok in (t.get("badge") or "").split(" · ")[0].split():
        if tok in _ARROW and trend.get("_k"):
            trend[trend.pop("_k")] = _ARROW[tok]
        elif tok in ("W", "D", "H4", "W1", "D1"):
            trend["_k"] = {"W": "W1", "D": "D1"}.get(tok, tok)
    trend.pop("_k", None)
    # the pair's current trade: the setup row the desk executes (a trade still running, even once its alert is no longer fresh)
    sig = next((r["setup"] for r in t.get("strategies") or [] if r.get("status") == "SIGNAL" and r.get("setup")), None) or (t.get("signals") or [None])[0]
    watching = next((r["id"] for r in t.get("strategies") or [] if r.get("status") == "WATCHING"), None)
    live = LIVE.get(pair)
    return {"symbol": pair, "at": t.get("at"), "decision": t.get("decision"), "direction": t.get("direction"), "grade": t.get("grade"), "tier": t.get("tier"),
            "gpa": t.get("gpa"), "consensus": t.get("consensus"), "setupType": t.get("setupType"), "trend": trend,
            "agents": [a.get("status") for a in t.get("agents") or []], "watching": watching, "marketOpen": t.get("marketOpen"),
            "price": live[0][-1].close if live and live[0] else None, "decimals": BY_SYMBOL[pair]["decimals"],
            "signal": {k: sig.get(k) for k in ("id", "direction", "entry", "sl", "tp", "rr", "etf", "time", "grade", "setupType")} if sig else None}


def pair_currencies(pair: str) -> set[str]:
    """The currencies whose news moves the pair (gold: the dollar)."""
    a, b = pair.split("/")
    return {"USD"} if a == "XAU" else {a, b}


async def _pip_value(pair: str, cfg: dict) -> dict:
    """The live pip value per standard lot in dollars: pip × 100,000 units of the quote currency, converted at the live
    rate (USD/Q pairs divide, Q/USD pairs multiply; JPY: 1,000 yen per pip). Gold and USD-quoted pairs: the config's 10.
    The config's value when a price is missing."""
    q = pair.split("/")[1]
    if pair.startswith("XAU") or q == "USD":
        return cfg
    try:
        if q in ("EUR", "GBP", "AUD", "NZD"):
            rate = (await fetch_live_price(f"{q}/USD"))["price"]  # dollars per unit of Q
        else:
            rate = 1 / (await fetch_live_price(f"USD/{q}"))["price"]
        if rate > 0:
            return {**cfg, "pip_value_usd_per_lot": round(cfg["pip"] * 100000 * rate, 2)}
    except Exception:
        pass
    return cfg


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


async def team(pair: str, fresh: bool = False) -> dict:
    """The pair's team now (cached a minute: every screen and the notifier share one read). `fresh` skips this cache
    only: the candle caches (M5 60 s, H1 5 min, D1 30 min) always apply, so 29 pairs scan fast."""
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
        m5s, h1s, ds = await asyncio.gather(fetch_candle_series(pair, "5M", M5_BARS), fetch_candle_series(pair, "1H", H1_BARS),
                                            fetch_candle_series(pair, "1D", D1_BARS), return_exceptions=True)
        now = int(time.time())
        bad = lambda x: isinstance(x, BaseException) or x["isSynthetic"]  # noqa: E731
        out = {"success": False, "symbol": pair, "at": now, "error": "no live candles from the feed right now"}
        if not bad(m5s) and not bad(h1s):
            # only CLOSED candles: the forming one would change before its close
            m5 = [c for c in m5s["candles"] if c.time + 300 <= now]
            h1 = [c for c in h1s["candles"] if c.time + 3600 <= now]
            d1 = None if bad(ds) else [c for c in ds["candles"] if c.time + 86400 <= now]
            if len(m5) >= 300 and len(h1) >= 300:
                pv, news = await asyncio.gather(_pip_value(pair, cfg), _news(pair))
                # the strategy maths is CPU work (about a second cold): in a worker thread, one read at a time, so the server
                # keeps answering the chart's candles and the prices meanwhile instead of making them wait behind it
                async with _cpu():
                    out = await asyncio.to_thread(read_team, pair, {**pv, "live_spread": m5s.get("spread") or 0.0}, m5, h1, now, news, d1)
                out["marketOpen"] = market_session_status(pair)["isOpen"]
                out["source"] = m5s["source"]
                out["feed"] = {**(h1s.get("integrity") or {}), "spread": m5s.get("spread") or 0.0}  # the sanitizer's report on H1
        _cache[pair] = (time.time() + TTL, out)
        return out
