"""The pair teams live: the desk reads a pair with the shared engine, and the notifier sends a new setup once only."""

import asyncio
import csv
from pathlib import Path

from app.market.types import Candle
from app.smc import desk, notify

DATA = Path(__file__).resolve().parents[2] / "smc" / "pairs"


def candles(pair: str, tf: str) -> list[Candle]:
    with open(DATA / pair / "data" / f"{tf}.csv", newline="") as f:
        return [Candle(int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0))
                for r in csv.DictReader(f)]


def test_the_desk_reads_every_strategy_of_a_pair():
    m5, h1 = candles("XAUUSD", "M5"), candles("XAUUSD", "H1")
    if not m5:
        return
    t = desk.read_team("XAU/USD", desk.BY_SYMBOL["XAU/USD"], m5, h1, m5[-1].time + 300)
    assert t["success"] and [s["id"] for s in t["strategies"]] == ["S1", "S2", "S3", "S4"]
    assert all(s["status"] in ("SIGNAL", "BLOCKED", "WATCHING", "IDLE") for s in t["strategies"])
    for s in t["signals"]:  # a signal passed its rules AND the 7 questions
        assert s["pass"] and len(s["checklist"]) == 7 and all(q["ok"] for q in s["checklist"])


def test_the_chart_analysis_uses_only_closed_candles_and_stays_still():
    from app.smc import engine
    from app.smc.chart import analysis

    m5, h1 = candles("EURUSD", "M5"), candles("EURUSD", "H1")
    if not m5:
        return
    a = analysis(m5, engine.H1View(h1), 5, m5[-1].time + 300)
    b = analysis(m5, engine.H1View(h1), 5, m5[-1].time + 300 + 240)  # the same candles read 4 minutes later
    assert a == b and a["trend"] in ("BULLISH", "BEARISH", "UNDEFINED")
    last = max(m5[-1].time, h1[-1].time)
    edge = last + 3600
    assert all(x["from"] <= x["to"] <= edge for x in a["boxes"] + a["segments"])  # each object starts and ends on candles that exist
    assert all(x["time"] <= last for x in a["labels"])
    assert all(z["bottom"] <= z["top"] for z in a["boxes"]) and len([z for z in a["boxes"] if z["kind"] == "ob"]) <= 2
    assert {s["label"] for s in a["segments"] if s["kind"] in ("bos", "choch")} <= {"BOS", "CHoCH"}


def test_each_team_has_its_seven_agents_and_the_lead_follows_the_gate():
    m5, h1 = candles("XAUUSD", "M5"), candles("XAUUSD", "H1")
    if not m5:
        return
    t = desk.read_team("XAU/USD", desk.BY_SYMBOL["XAU/USD"], m5, h1, m5[-1].time + 300)
    keys = [a["key"] for a in t["agents"]]
    assert keys == ["lead", "structure", "liquidity", "entry", "risk", "backtest", "devil"]
    assert all(a["status"] in ("ok", "warn", "wait") and a["finding"] for a in t["agents"])
    lead = t["agents"][0]
    assert lead["finding"].startswith("SETUP") == bool(t["signals"])  # the lead publishes a setup only when one passed the 7 questions
    assert any("not advice" in x for x in lead["lines"])
    devil = next(a for a in t["agents"] if a["key"] == "devil")
    assert any("100" in x for x in devil["lines"])  # the small sample is always raised


def test_lots_follow_the_risk_formula():
    cfg = desk.BY_SYMBOL["EUR/USD"]  # $10 a pip per lot
    assert desk.lots_for(cfg, 1.1000, 1.0980, 10000) == 0.5  # $100 / (20 pips × $10)
    assert desk.lots_for(desk.BY_SYMBOL["XAU/USD"], 4000.0, 3995.0, 10000) == 0.2  # $100 / (50 pips × $10)


def test_a_new_setup_is_sent_once(monkeypatch):
    from app.db import init_db

    init_db()
    sig = {"id": "SMC-EURUSD-S3-1790000000-B", "strategy": "S3", "name": "Asian range sweep", "direction": "BUY", "time": 1790000000,
           "entry": 1.1, "sl": 1.098, "tp": 1.108, "rr": 4.0, "validUntil": 1790003600, "state": "PENDING", "pass": True, "checklist": [],
           "steps": [], "lots": {"1000": 0.05, "10000": 0.5}, "draw": {}}

    async def fake_team(pair, fresh=False):
        return {"success": True, "signals": [sig] if pair == "EUR/USD" else []}
    sent = []

    async def fake_send(pair, s):
        sent.append((pair, s["id"]))
        return {"telegram": 1, "push": 0}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "_send", fake_send)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    first = asyncio.run(notify.tick())
    second = asyncio.run(notify.tick())
    assert sent == [("EUR/USD", sig["id"])] and "telegram 1" in first["EUR/USD"] and second["EUR/USD"] == "signal already sent"
    assert any(x["id"] == sig["id"] for x in notify.recent())
    text = notify.message(sig, "EUR/USD", 5)
    assert "BUY EUR/USD" in text and "Limit <code>1.10000</code>" in text and "not financial advice" in text
