"""The gold spec (xau_usd_gold_multi_agent_quantitative_strategy_claude_prompt.md): its formulas and its contract."""

from app.smc import gold
from app.smc.playbook import _Bar

T0 = 1_790_000_000 - 1_790_000_000 % 86400


def bars(prices, step=900):
    return [_Bar(T0 + i * step, *p) for i, p in enumerate(prices)]


def test_bos_needs_the_close_beyond_the_swing_plus_a_tenth_of_atr():
    c = bars([(100, 101, 99, 100), (100, 102, 99.5, 101), (101, 105, 100, 104), (104, 104.5, 101, 102), (102, 103, 100.5, 101),
              (101, 105.05, 100.8, 105.05), (105, 106, 104, 105.6)])
    at = [1.0] * len(c)
    hi, lo = gold.fractals(c)
    s = gold.structure(c, at, hi, lo)
    assert s["event"][5] is None  # 105.05 is not > 105 + 0.10 ATR
    assert s["event"][6] == ("CHOCH", 1)  # 105.6 > 105.10 with no prior trend: a change of character


def test_the_sweep_rules_depth_rejection_and_wick_dominance():
    class Gx:
        pass
    g = Gx()
    g.m15 = bars([(100.5, 100.8, 98.8, 100.4)])
    g.at15 = [2.0]
    assert gold.sweep(g, 0, 99.5, 1) == 0  # 0.7 below (0.35 ATR), closes back above, wick 80 % of the range
    g.m15 = bars([(100.5, 100.8, 96.0, 100.4)])
    assert gold.sweep(g, 0, 99.5, 1) is None  # 3.5 below = 1.75 ATR: too deep, a breakdown
    g.m15 = bars([(100.5, 100.8, 98.0, 99.4), (99.4, 99.8, 99.2, 99.7)])  # closes under the pool, wick 50 % of the range
    assert gold.sweep(g, 0, 99.5, 1) == 1  # the 2-bar sweep: the next close is back inside


def test_displacement_needs_1_35_times_the_average_body_and_68_percent_of_range():
    flat = [(100 + 0.1 * k, 100.3 + 0.1 * k, 99.9 + 0.1 * k, 100.2 + 0.1 * k) for k in range(22)]
    c = bars(flat + [(102.2, 102.4, 102.1, 102.3), (102.3, 104.1, 102.25, 104.0), (104.0, 105.0, 103.6, 104.8)])
    f = gold.displacement_fvg(c, len(c) - 1, 1, 1.0, 103.0)
    assert f is not None and f[0] == c[-3].high and f[1] == c[-1].low and abs(f[2] - (f[0] + f[1]) / 2) < 1e-9
    assert gold.displacement_fvg(c, len(c) - 1, 1, 1.0, 104.5) is None  # no MSS: the close stays under the internal swing


def test_the_consensus_formula_and_the_badge_length():
    sc = gold.scores({"sid": "A", "ote": (1, 3), "fvgCe": 2, "entry": 2}, {}, False, 20)
    assert sc["score"] == 0.25 * 100 + 0.25 * 100 + 0.20 * 100 + 0.15 * 0 + 0.15 * 80
    assert len(gold.badge("x" * 80)) == 55


def test_the_json_contract_on_stored_candles():
    from tests.test_smc_live import candles
    m5, h1 = candles("XAUUSD", "M5"), candles("XAUUSD", "H1")
    if not m5:
        return
    s, w = gold.scan(m5, h1, 0.3, [], None, None, None)
    rep = gold.report(m5, h1, m5[-1].time + 300, s, w, None, [], None)
    c = rep["contract"]
    assert set(c) == {"pair", "strategy_name", "timestamp_utc", "scenario_active", "consensus_score", "final_decision", "agents"}
    assert set(c["agents"]) == {"lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager",
                                "backtest_engineer", "devils_advocate"}
    assert all(len(a["ui_badge_summary"]) <= 55 for a in c["agents"].values())
    assert c["agents"]["devils_advocate"]["ui_badge_summary"].startswith("My worry:")
    assert c["final_decision"] in ("NO_TRADE", "BUY_LIMIT", "SELL_LIMIT", "BUY_MARKET", "SELL_MARKET")
