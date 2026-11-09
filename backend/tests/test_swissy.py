"""The EUR/CHF spec (eur_chf_multi_agent_quantitative_strategy_claude_prompt.md): its math and its rules."""

import math
import random

from app.smc import swissy


def test_the_z_score_uses_the_sma_and_the_sample_std():
    c = [1.0, 2.0, 3.0, 4.0, 5.0]
    z, mu, sd = swissy.zscore_sma(c, 5)
    s = (sum((v - 3) ** 2 for v in c) / 4) ** 0.5  # N - 1
    assert mu[-1] == 3.0 and abs(sd[-1] - s) < 1e-12 and abs(z[-1] - 2 / s) < 1e-12 and z[3] is None


def test_hurst_separates_a_trend_from_a_mean_reverting_series():
    rnd = random.Random(7)
    trend, r = [1.0], 0.0
    for _ in range(200):  # persistent returns (AR 0.9): a trending, H > 0.5 series
        r = 0.9 * r + 0.001 * rnd.gauss(0, 1)
        trend.append(trend[-1] * math.exp(r))
    alt = [1.0 + (0.001 if i % 2 else -0.001) + 0.0001 * rnd.gauss(0, 1) for i in range(201)]
    ht, ha = swissy.hurst_rs(trend, 100)[-1], swissy.hurst_rs(alt, 100)[-1]
    assert ha < 0.46 < ht and swissy.hurst_rs(trend, 100)[50] is None


def test_the_half_life_of_an_ar1_series():
    rnd = random.Random(3)
    b = -0.1  # ΔC = -0.1 C_{t-1}: τ = -ln2 / ln 0.9 ≈ 6.6 bars
    c = [0.0]
    for _ in range(3000):
        c.append(c[-1] + b * c[-1] + rnd.gauss(0, 1))
    tau = swissy.half_life(c, len(c) - 1, 2500)
    assert abs(tau - (-math.log(2) / math.log(0.9))) < 1.5
    assert swissy.half_life(list(range(300)), 250) is None  # a trend has no half-life


def test_the_blended_reward_and_the_shock_events():
    s = {"entry": 1.0, "sl": 0.999, "tp1": 1.001, "tp": 1.003, "part": 0.6}
    assert abs(swissy.blended_r(s) - (0.6 * 1 + 0.4 * 3)) < 1e-9
    ev = [{"time": 1, "currency": "CHF", "title": "SNB Policy Rate"}, {"time": 2, "currency": "CHF", "title": "CPI m/m"},
          {"time": 3, "currency": "EUR", "title": "Main Refinancing Rate"}]
    assert swissy.shock_times(ev) == [1, 3]
    assert swissy._shock_on([(100, 1)], 100 + 23 * 3600) and not swissy._shock_on([(100, 1)], 100 + 25 * 3600)
