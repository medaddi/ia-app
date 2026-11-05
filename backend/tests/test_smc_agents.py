"""The six SMC agents: their report is complete, isolated on its pair and anchored to times and prices."""

import math

from app.analysis.smc_agents import report_drawing, smc_report
from app.analysis.smc_setups import smc_now
from app.strategies.shared.types import Candle
from tests.test_smc_setups import COST, SPEC, asian_sweep_market, seq

SPEC_EU = {**SPEC, "symbol": "EURUSD"}


def history(m5, n=620):
    """The days before: quiet candles around the same price, so the guard sees enough M5 history."""
    t0 = m5[0].time - n * 300
    return seq(t0, [1.0990 + 0.0004 * math.sin(k / 7) for k in range(n)], 1.0990) + m5


def build():
    m5, h1 = asian_sweep_market(1.0960, 0.0060, lambda k: 1.1280 - 0.0001 * k + 0.0010 * math.sin(k / 3))
    m5 = history(m5)
    now = m5[-1].time + 300
    rows = smc_now(m5, h1, COST, SPEC_EU, m5[-1].close, lambda e, s: {"1000$": 0.1})["strategies"]
    return smc_report("EUR/USD", SPEC_EU, m5, h1, m5[-1].close, now, True, rows), m5


def test_the_report_has_the_six_agents_on_one_pair():
    rep, m5 = build()
    assert set(rep) >= {"meta", "agent1_structure", "agent2_liquidity", "agent3_pdArrays", "agent4_strategy", "agent5_riskAndTrade", "summaryDarija"}
    assert rep["meta"]["symbol"] == "EURUSD" and rep["meta"]["pricePrecision"] == 5 and rep["meta"]["guard"]["ok"]
    assert rep["agent1_structure"]["htfBias"] == "BEARISH" and all(z["symbol"] == "EURUSD" and z["timeframe"] == "1h" for z in rep["agent3_pdArrays"]["zones"])
    a4, a5 = rep["agent4_strategy"], rep["agent5_riskAndTrade"]
    assert a4["selectedStrategy"] == "STRATEGY_3_SESSION_KILLZONE_SWEEP" and a4["ltfConfirmationStatus"] == "CONFIRMED"
    assert a5["status"] == "READY_TO_EXECUTE" and a5["direction"] == "SELL" and a5["riskRewardRatio"] >= 3 and a5["checklistScore"] == "7/7"
    assert a5["tp2_finalRunner"] < a5["tp1_partial50"] < a5["entryPrice"] < a5["stopLoss"]  # a sell: TP1 at 1:3 before the runner
    assert "بيع" in rep["summaryDarija"] and any(s.startswith("✓") for s in a4["executionStepsDarija"])


def test_the_drawing_is_anchored_and_belongs_to_the_pair():
    rep, m5 = build()
    d = report_drawing(rep)
    assert all(z["id"].startswith("SMC-") for z in d["zones"]) and all(l["id"].startswith("SMC-") for l in d["priceLines"])
    px = m5[-1].close
    for z in d["zones"]:
        assert z["startTime"] > 10 ** 9 and abs(z["topPrice"] - px) / px < 0.2
    assert any(l["label"].startswith("EQ") for l in d["priceLines"])


def test_a_price_from_another_pair_fails_the_guard():
    m5, h1 = asian_sweep_market()
    m5 = history(m5)
    rep = smc_report("EUR/USD", SPEC_EU, m5, h1, 4000.0, m5[-1].time + 300, True, [])  # a gold price on EUR/USD candles
    assert not rep["meta"]["guard"]["ok"] and rep["agent5_riskAndTrade"]["status"] == "NO_TRADE"
