"""
Parity with the original TypeScript strategies: the fixtures were recorded by scripts/dump-parity.ts
on real candles (every kill-zone / window bar plus a sample outside) and on the hand-built
scenarios of the TS unit tests. Every status, score, level, checklist result and drawing must match.

PARITY_STEP=1 checks every recorded evaluation (default: every 3rd, plus all evaluations with a setup).
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

from app.strategies.eurusd.strategy import evaluate_eurusd
from app.strategies.shared.jsnum import js_str, round_to
from app.strategies.shared.types import candles_from_rows

FIXTURES = Path(__file__).parent / "fixtures"
# XAUUSD moved to the H1 Trend Breakout (tests/test_xau_breakout.py); EURUSD keeps its recorded TypeScript parity
RUN = {"eur": evaluate_eurusd, "EUR/USD": evaluate_eurusd}


def summary(r: dict) -> dict:
    s = r["setup"]
    lines = sorted(
        f"{d['id']}|{d['layer']}|{d['kind']}|{js_str(d['t1'])}|{js_str(d['t2'])}|{js_str(d['p1'])}|{js_str(d['p2']) if 'p2' in d else ''}|{d.get('text') or ''}"
        for d in r["drawings"]
    )
    return {
        "status": r["status"], "score": r["score"], "bias": r["bias"]["direction"], "rejection": r["rejection"], "headline": r["headline"],
        "canNotify": r["canNotify"], "checklist": [[c["key"], c["passed"]] for c in r["checklist"]],
        "setup": s and {
            "id": s["id"], "setup": s["setup"], "direction": s["direction"], "entryType": s["entryType"],
            "entry": s["entry"], "sl": s["sl"], "tp1": s["tp1"], "tp2": s["tp2"], "tp3": s["tp3"],
            "rrTp2": round_to(s["rrTp2"], 6), "state": s["lifecycle"]["state"], "lots": s["lots"],
        },
        "drawings": hashlib.sha1("\n".join(lines).encode("utf8")).hexdigest(),
        "drawingCount": len(r["drawings"]),
    }


def _input(raw: dict) -> dict:
    return {**raw, "candles": {tf: candles_from_rows(rows) for tf, rows in raw["candles"].items()}}


def _compare(got: dict, want: dict, label: str):
    for key in want:
        if key == "drawings" and got[key] != want[key]:
            pytest.fail(f"{label}: drawings differ (count {got['drawingCount']} vs {want['drawingCount']})")
        assert got[key] == want[key], f"{label}: {key}\n  python: {got[key]}\n  ts:     {want[key]}"


SCENARIOS = [s for s in json.loads((FIXTURES / "parity_scenarios.json").read_text("utf8")) if s["fn"] in RUN]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenarios(scenario):
    r = RUN[scenario["fn"]](_input(scenario["input"]))
    _compare(summary(r), scenario["result"], scenario["name"])


@pytest.mark.parametrize("symbol", ["EURUSD"])
def test_real_candles(symbol):
    fx = json.loads((FIXTURES / f"parity_{symbol}.json").read_text("utf8"))
    run = RUN[fx["symbol"]]
    candles = {tf: candles_from_rows(rows) for tf, rows in fx["candles"].items()}
    base = {"candles": candles, "livePrice": 0, "spread": None, "isRealData": True, "dataSource": fx["source"],
            "news": {"events": [], "source": "fixture"}, "isMarketOpen": True, "day": {"trades": 0, "losses": 0}}
    step = int(os.environ.get("PARITY_STEP", "3"))
    checked = 0
    for k, ev in enumerate(fx["evals"]):
        if k % step and not ev["result"]["setup"]:
            continue
        r = run({**base, "nowSec": ev["nowSec"]})
        _compare(summary(r), ev["result"], f"{symbol} @ {ev['nowSec']}")
        checked += 1
    assert checked > 0
