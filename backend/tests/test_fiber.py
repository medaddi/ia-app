"""The EUR/USD spec (eur_usd_multi_agent_quantitative_strategy_claude_prompt.md): its math and its contract."""

from app.smc import fiber
from app.smc.playbook import _Bar

T0 = 1_790_000_000 - 1_790_000_000 % 86400


class B(_Bar):
    __slots__ = ("volume",)

    def __init__(self, t, o, h, lo, c, v):
        super().__init__(t, o, h, lo, c)
        self.volume = v


def test_the_session_vwap_and_its_volume_weighted_sigma():
    c = [B(T0 + 7 * 3600 + i * 300, 1, 1.0003, 0.9997, 1.0, 1.0) for i in range(2)] + [B(T0 + 7 * 3600 + 600, 1, 1.0063, 1.0057, 1.006, 2.0)]
    vw, sd = fiber.vwap_anchored(c, 0)
    tp = [1.0, 1.0, 1.006]
    w = [1.0, 1.0, 2.0]
    m = sum(a * b for a, b in zip(tp, w)) / sum(w)
    var = sum(b * (a - m) ** 2 for a, b in zip(tp, w)) / sum(w)
    assert abs(vw[-1] - m) < 1e-12 and abs(sd[-1] - var ** 0.5) < 1e-9
    vw12, _ = fiber.vwap_anchored(c, 12)
    assert vw12 == [None, None, None]  # the NY VWAP starts at 12:00 UTC


def test_the_risk_manager_widens_to_6_pips_rejects_over_28_and_asks_the_reward():
    sl, tp = fiber._risk(1.1000, 1.0997, 1, [("t", 1.1020)], 2.4)
    assert abs(sl - 1.0994) < 1e-9 and tp[0] == 1.1020
    assert fiber._risk(1.1000, 1.0970, 1, [("t", 1.1200)], 2.4)[0] is None
    assert fiber._risk(1.1000, 1.0990, 1, [("t", 1.1020)], 2.4)[0] is None


def test_scenario_c_events():
    ev = [{"time": 1, "currency": "EUR", "title": "Main Refinancing Rate"}, {"time": 2, "currency": "USD", "title": "Non-Farm Employment Change"},
          {"time": 3, "currency": "EUR", "title": "German Flash Services PMI"}]
    assert fiber.macro_times(ev) == [1, 2]


def test_the_json_contract_on_stored_candles():
    from tests.test_smc_live import candles
    m5, h1 = candles("EURUSD", "M5"), candles("EURUSD", "H1")
    if not m5:
        return
    s, w = fiber.scan(m5, h1, 0.00012, [], None, candles("GBPUSD", "M5"))
    c = fiber.report(m5, h1, m5[-1].time + 300, s, w, None, [], None, candles("GBPUSD", "M5"))["contract"]
    assert c["pair"] == "EUR/USD" and c["strategy_name"] == "London-NY Killzone VWAP Orderblock & SMT Divergence"
    assert set(c["agents"]) == {"lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager",
                                "backtest_engineer", "devils_advocate"}
    assert c["agents"]["devils_advocate"]["ui_badge_summary"].startswith("My worry:")
    assert all(len(a["ui_badge_summary"]) <= 55 for a in c["agents"].values())
