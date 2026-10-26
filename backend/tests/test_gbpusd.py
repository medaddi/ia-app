"""GBP/USD runs the EURUSD rules unchanged: same candles → same decision, its own instrument, news and ids."""

import json
from pathlib import Path

from app.strategies.eurusd.strategy import evaluate_eurusd
from app.strategies.gbpusd.config import GBP_CONFIG
from app.strategies.service import STRATEGY_DEFS, normalize_symbol
from app.strategies.shared.types import candles_from_rows

SCENARIOS = [s for s in json.loads((Path(__file__).parent / "fixtures" / "parity_scenarios.json").read_text("utf8")) if s["fn"] == "eur"]


def _input(raw):
    return {**raw, "candles": {tf: candles_from_rows(rows) for tf, rows in raw["candles"].items()}}


def test_symbol_and_service():
    assert normalize_symbol("gbpusd") == normalize_symbol("GBP/USD") == "GBP/USD"
    assert normalize_symbol("EURUSD") == "EUR/USD" and normalize_symbol("XAUUSD") == "XAU/USD"
    assert list(STRATEGY_DEFS) == ["XAU/USD", "EUR/USD", "GBP/USD"] and STRATEGY_DEFS["GBP/USD"].entryTf == "M15"


def test_same_rules_as_eurusd():
    for sc in SCENARIOS:
        eur = evaluate_eurusd(_input(sc["input"]))
        gbp = evaluate_eurusd(_input(sc["input"]), GBP_CONFIG)
        assert (gbp["status"], gbp["score"], gbp["bias"]["direction"]) == (eur["status"], eur["score"], eur["bias"]["direction"]), sc["name"]
        assert gbp["symbol"] == "GBPUSD" and gbp["displaySymbol"] == "GBP/USD"
        if gbp["setup"]:
            assert gbp["setup"]["id"].startswith("GBPUSD-") and gbp["setup"]["id"][6:] == eur["setup"]["id"][6:]
            assert (gbp["setup"]["entry"], gbp["setup"]["sl"], gbp["setup"]["tp2"]) == (eur["setup"]["entry"], eur["setup"]["sl"], eur["setup"]["tp2"])


def test_gbp_news_filter():
    sc = next(s for s in SCENARIOS if s["result"]["status"] == "SIGNAL")
    inp = _input(sc["input"])
    boe = {"time": inp["nowSec"] + 600, "currency": "GBP", "title": "BoE Official Bank Rate", "impact": "High"}
    assert evaluate_eurusd({**inp, "news": {"events": [boe], "source": "t"}}, GBP_CONFIG)["status"] == "NO_TRADE"
    assert evaluate_eurusd({**inp, "news": {"events": [boe], "source": "t"}})["status"] == "SIGNAL"  # GBP news does not block EURUSD
