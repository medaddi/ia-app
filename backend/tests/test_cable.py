"""The Cable spec (gbp_usd_multi_agent_quantitative_strategy_claude_prompt.md): its rules and its contract."""

from app.smc import cable


def test_the_risk_manager_bounds_the_stop_and_asks_2_6_r():
    sl, tp = cable._risk(1.3000, 1.2995, 1, [("t", 1.3060)], 2.6)  # a 5-pip stop is widened to 8 pips
    assert abs(sl - 1.2992) < 1e-9 and tp[0] == 1.3060
    sl, why = cable._risk(1.3000, 1.2960, 1, [("t", 1.3200)], 2.6)  # a 40-pip stop is rejected
    assert sl is None and "32.0" in why
    sl, why = cable._risk(1.3000, 1.2990, 1, [("t", 1.3020)], 2.6)  # 2 R only: no TP2
    assert sl is None


def test_uk_lockout_events():
    ev = [{"time": 1, "currency": "GBP", "title": "CPI y/y"}, {"time": 2, "currency": "GBP", "title": "Official Bank Rate"},
          {"time": 3, "currency": "GBP", "title": "GDP m/m"}, {"time": 4, "currency": "USD", "title": "CPI y/y"}]
    assert cable.uk_lock(ev) == [1, 2]


def test_the_json_contract_on_stored_candles():
    from tests.test_smc_live import candles
    m5, h1 = candles("GBPUSD", "M5"), candles("GBPUSD", "H1")
    if not m5:
        return
    s, w = cable.scan(m5, h1, 0.00018, [], None, None)
    rep = cable.report(m5, h1, m5[-1].time + 300, s, w, None, [], None, None)
    c = rep["contract"]
    assert c["pair"] == "GBP/USD" and c["strategy_name"] == "London Judas Swing & Unicorn Breaker-FVG Strategy"
    assert set(c["agents"]) == {"lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager",
                                "backtest_engineer", "devils_advocate"}
    assert c["agents"]["devils_advocate"]["ui_badge_summary"].startswith("My worry:")
    assert all(len(a["ui_badge_summary"]) <= 55 for a in c["agents"].values())
    assert c["final_decision"] in ("NO_TRADE", "BUY_LIMIT", "SELL_LIMIT")
