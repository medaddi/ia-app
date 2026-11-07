"""The trade manager replayed on real candles: each step is sent once, in order, and the result matches the backtest's."""

import asyncio
import csv
import json
from pathlib import Path

from app.market.types import Candle
from app.smc import desk, engine, manager
from app.smc.manage import managed

DATA = Path(__file__).resolve().parents[2] / "smc" / "pairs" / "XAUUSD"


def candles(tf):
    with open(DATA / "data" / f"{tf}.csv", newline="") as f:
        return [Candle(int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0))
                for r in csv.DictReader(f)]


def test_the_manager_follows_a_trade_to_its_end_once(monkeypatch):
    if not (DATA / "data" / "M5.csv").exists():
        return
    from app.db import SessionLocal, init_db
    from app.models import Signal

    init_db()
    cfg = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
    m5, h1 = candles("M5"), candles("H1")
    engine.configure(cfg, [])
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    res = engine.scan_all(m5, h1, cost, cfg["decimals"])
    filled = [s for sid in ("S1", "S2", "S3", "S4") for s in res[sid]["setups"] if "fill" in s["result"] and "r" in s["result"]]
    assert filled, "the data gives at least one filled setup"
    s = filled[-1]
    sig = desk._setup_json("XAU/USD", cfg, s)
    with SessionLocal() as db:
        db.merge(Signal(id=sig["id"], symbol="XAU/USD", setup=sig["strategy"], direction=sig["direction"], entry_type="LIMIT", entry=sig["entry"],
                        sl=sig["sl"], tp1=sig["tp"], tp2=sig["tp"], tp3=sig["tp"], rr_tp2=sig["rr"], score=7, signal_time=sig["time"],
                        state="PENDING", params={}, payload={**sig, "entry": s["entry"], "sl": s["sl"], "tp": s["tp"]}))
        db.commit()
    sent = []

    async def fake_send(pair, text, title, body, tag):
        sent.append(tag.rsplit("-", 1)[1])
    k0 = next(k for k, x in enumerate(m5) if x.time + 300 == s["time"])
    for cut in range(k0 + 1, min(len(m5), k0 + 1 + engine.HOLD + 20), 3):  # every 15 minutes, as the live loop would see it
        part = m5[:cut + 1]
        desk.LIVE["XAU/USD"] = (part, engine.Structure(part), cost)
        asyncio.run(manager.manage_all(fake_send))
    ends = [x for x in sent if x in ("TP", "STOP", "BE_STOP", "TRAIL_STOP", "TIME")]
    assert sent[0] == "FILLED" and sent.count("FILLED") == 1  # each step once, the fill first
    assert len(ends) == 1 and sent[-1] == ends[0] and sent.count("PARTIAL_1_3") <= 1, sent  # one end, last
    print("steps:", sent)
    expect = managed(m5, engine.Structure(m5), s, cost, trail=True)
    with SessionLocal() as db:
        row = db.get(Signal, sig["id"])
        assert row.state == "CLOSED" and abs(row.r_multiple - expect["r"]) < 1e-3  # the same result as the backtest
    r = manager.results()
    assert r["all"]["trades"] >= 1
