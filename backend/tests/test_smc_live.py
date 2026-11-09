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


def test_each_team_trades_only_its_pair_strategies_from_the_guide():
    from app.smc import playbook
    for pair in ("XAU/USD", "EUR/USD", "EUR/CHF", "AUD/CAD"):
        k = pair.replace("/", "")
        m5, h1 = candles(k, "M5"), candles(k, "H1")
        if not m5:
            continue
        t = desk.read_team(pair, desk.BY_SYMBOL[pair], m5, h1, m5[-1].time + 300)
        assert t["success"] and [s["id"] for s in t["strategies"]] == playbook.STRATEGIES[k]
        for row in t["strategies"]:
            assert row["name"] == playbook.NAMES[k][row["id"]] and row["claimed"] == playbook.CLAIMED[(k, row["id"])]
            assert row["status"] in ("SIGNAL", "BLOCKED", "WATCHING", "IDLE", "OFF") and (row["status"] == "OFF") == ((k, row["id"]) in playbook.DISABLED)
        for s in t["signals"]:  # a signal passed its rules AND the guide's checklist
            assert s["pass"] and len(s["checklist"]) == 6 and all(q["ok"] for q in s["checklist"])  # a 7th (busy) only on a skipped one
        ch = t["chart"]  # the chart shows the pair's strategy: its lines and windows, never the old S1-S4 boxes
        assert set(ch) >= {"boxes", "segments", "labels", "lines", "windows", "trade", "trend", "premium"}
        assert not any(b["label"].endswith("Order Block") for b in ch["boxes"])


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


def test_gold_team_follows_its_spec():
    m5, h1 = candles("XAUUSD", "M5"), candles("XAUUSD", "H1")
    if not m5:
        return
    t = desk.read_team("XAU/USD", desk.BY_SYMBOL["XAU/USD"], m5, h1, m5[-1].time + 300)
    assert [a["key"] for a in t["agents"]] == ["lead", "structure", "liquidity", "entry", "risk", "backtest", "devil"]
    assert all(a["status"] in ("ok", "warn", "wait", "veto") and len(a["finding"]) <= 55 for a in t["agents"])
    rep = t["goldReport"]
    assert rep["strategy_name"].startswith("London-NY Fix") and (rep["final_decision"] != "NO_TRADE") == bool(t["signals"])


def test_eur_chf_team_follows_its_spec():
    m5, h1 = candles("EURCHF", "M5"), candles("EURCHF", "H1")
    if not m5:
        return
    t = desk.read_team("EUR/CHF", desk.BY_SYMBOL["EUR/CHF"], m5, h1, m5[-1].time + 300)
    assert [a["key"] for a in t["agents"]] == ["lead", "structure", "liquidity", "entry", "risk", "backtest", "devil"]
    assert all(a["status"] in ("ok", "warn", "wait", "veto") and len(a["finding"]) <= 55 for a in t["agents"])
    rep = t["pairReport"]
    assert rep["strategy_name"] == "Ornstein-Uhlenbeck Z-Score & Range Sweep Mean Reversion"
    assert (rep["final_decision"] != "NO_TRADE") == bool(t["signals"])
    assert rep["agents"]["devils_advocate"]["ui_badge_summary"].startswith("My worry: ")
    assert "hurst_exponent" in rep["agents"]["structure_analyst"] and "half_life_bars" in rep["agents"]["backtest_engineer"]


def test_aud_chf_team_follows_its_spec():
    m5, h1 = candles("AUDCHF", "M5"), candles("AUDCHF", "H1")
    if not m5:
        return
    t = desk.read_team("AUD/CHF", desk.BY_SYMBOL["AUD/CHF"], m5, h1, m5[-1].time + 300)
    assert [a["key"] for a in t["agents"]] == ["lead", "structure", "liquidity", "entry", "risk", "backtest", "devil"]
    assert all(a["status"] in ("ok", "warn", "wait", "veto") and len(a["finding"]) <= 55 for a in t["agents"])
    rep = t["pairReport"]
    assert rep["strategy_name"] == "Risk-Regime Trend Efficiency & Cross-Session Inducement Pullback"
    assert (rep["final_decision"] != "NO_TRADE") == bool(t["signals"])
    assert "efficiency_ratio_20" in rep["agents"]["structure_analyst"] and rep["agents"]["devils_advocate"]["ui_badge_summary"].startswith("My worry: ")


def test_aud_cad_team_follows_its_spec():
    m5, h1 = candles("AUDCAD", "M5"), candles("AUDCAD", "H1")
    if not m5:
        return
    t = desk.read_team("AUD/CAD", desk.BY_SYMBOL["AUD/CAD"], m5, h1, m5[-1].time + 300)
    assert [a["key"] for a in t["agents"]] == ["lead", "structure", "liquidity", "entry", "risk", "backtest", "devil"]
    assert all(a["status"] in ("ok", "warn", "wait", "veto") and len(a["finding"]) <= 55 for a in t["agents"])
    rep = t["pairReport"]
    assert rep["strategy_name"] == "Cointegrated Regression Channel & VPOC Supply/Demand Reversion"
    assert (rep["final_decision"] != "NO_TRADE") == bool(t["signals"])
    s = rep["agents"]["structure_analyst"]
    assert "channel_z_score" in s and "vpoc" in s and rep["agents"]["devils_advocate"]["ui_badge_summary"].startswith("My worry: ")


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
    assert "BUY EUR/USD" in text and "Buy zone <code>1.10000" in text and "limit at <code>1.10000</code>" in text and "not financial advice" in text
