"""The AUD/CHF spec (aud_chf_multi_agent_quantitative_strategy_claude_prompt.md): its math and its rules."""

from app.smc import aussie
from app.smc.engines import efficiency
from app.smc.playbook import _Bar

T0 = 1_790_000_000 - 1_790_000_000 % 86400


def test_the_efficiency_ratio_20():
    c = [1.0 + 0.001 * i for i in range(21)]
    assert abs(efficiency(c, 20)[-1] - 1.0) < 1e-12  # a straight line is perfectly efficient
    z = [1.0 + (0.001 if i % 2 else 0.0) for i in range(21)]
    assert efficiency(z, 20)[-1] == 0.0  # back where it started: pure noise


def test_the_bandwidth_ratio_bb_over_keltner():
    c = [_Bar(T0 + i * 900, 1.0, 1.001, 0.999, 1.0 + (0.0001 if i % 2 else -0.0001)) for i in range(40)]
    b = aussie.bwr(c, 20)[-1]
    assert b is not None and b < 0.85  # closes barely move while the candles' ranges stay wide: the squeeze


def test_the_rollover_lockout_and_the_news():
    assert aussie.rollover(T0 + 20 * 3600 + 45 * 60) and aussie.rollover(T0 + 22 * 3600 + 29 * 60)
    assert not aussie.rollover(T0 + 22 * 3600 + 30 * 60) and not aussie.rollover(T0 + 20 * 3600 + 44 * 60)
    ev = [{"time": 1, "currency": "AUD", "title": "RBA Rate Statement"}, {"time": 2, "currency": "USD", "title": "CPI m/m"}, {"time": 3, "currency": "CHF", "title": "SNB Policy Rate"}]
    assert aussie.news_times(ev) == [1, 3]


def test_the_cross_currency_shock_sides():
    h = [_Bar(T0 + i * 3600, 1.0, 1.0005, 0.9995, 1.0) for i in range(20)] + [_Bar(T0 + 20 * 3600, 1.0, 1.0, 0.990, 0.991)]
    from app.smc.playbook import atr
    tw = (h, atr(h, 14), [x.time for x in h], "AUD/CAD")
    t = T0 + 21 * 3600
    assert aussie._shock(tw, t, 1, False)  # AUD/CAD drops: bad for an AUD/CHF long
    assert not aussie._shock(tw, t, -1, False)
    ec = (h, atr(h, 14), [x.time for x in h], "EUR/CHF")
    assert aussie._shock(ec, t, 1, False) and not aussie._shock(ec, t, -1, False)  # EUR/CHF drops = CHF strong: bad for a long only
