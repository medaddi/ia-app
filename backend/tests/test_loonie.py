"""The AUD/CAD spec (aud_cad_multi_agent_quantitative_strategy_claude_prompt.md): its math and its rules."""

import random

from app.smc import loonie
from app.smc.playbook import _Bar

T0 = 1_790_000_000 - 1_790_000_000 % 86400


class B(_Bar):
    __slots__ = ("volume",)

    def __init__(self, t, o, h, lo, c, v):
        super().__init__(t, o, h, lo, c)
        self.volume = v


def test_the_regression_channel_on_a_line_with_noise():
    rnd = random.Random(1)
    c = [1.0 + 0.001 * k + 0.0002 * rnd.gauss(0, 1) for k in range(100)]
    ch = loonie.channel(c, 99)
    assert abs(ch["beta"] - 0.001) < 0.0001 and ch["r2"] > 0.99
    res = [v - (ch["alpha"] + ch["beta"] * k) for k, v in zip(range(1, 101), c)]
    assert abs(ch["se"] - (sum(r * r for r in res) / 98) ** 0.5) < 1e-12  # N - 2
    assert abs(ch["z"] - res[-1] / ch["se"]) < 1e-9 and loonie.channel(c, 50) is None


def test_the_volume_profile_poc_and_value_area():
    h1 = [B(T0 + i * 3600, 1.0, 1.0 + 0.0001 * (i % 40) + 0.00005, 1.0 + 0.0001 * (i % 40), 1.0 + 0.0001 * (i % 40) + 0.00002, 100.0 if i % 40 == 20 else 1.0)
          for i in range(100)]
    p = loonie.profile(h1, 99)
    assert p["val"] <= p["vpoc"] <= p["vah"] and p["low"] <= p["val"] and p["vah"] <= p["high"]
    assert abs(p["vpoc"] - (1.0 + 0.002)) < 0.0002  # the heavy candle's bin
    assert p["vah"] - p["val"] < p["high"] - p["low"]


def test_scenario_c_events_and_the_rollover():
    ev = [{"time": 1, "currency": "CAD", "title": "Overnight Rate"}, {"time": 2, "currency": "CAD", "title": "GDP m/m"},
          {"time": 3, "currency": "AUD", "title": "CPI y/y"}, {"time": 4, "currency": "CAD", "title": "Employment Change"}]
    assert loonie.news_times(ev) == [1, 3, 4]
    assert loonie.rollover(T0 + 21 * 3600) and not loonie.rollover(T0 + 22 * 3600 + 1800)


def test_the_devil_counts_the_spec_traps():
    p, w = loonie.devil(None, {"time": T0 + 20 * 3600, "dir": 1, "slope": -1.8, "zoneTests": 2})
    assert p == 100 and len(w) == 3
    assert loonie.devil(None, {"time": T0 + 10 * 3600, "dir": 1, "slope": 1.8, "zoneTests": 0}) == (0.0, [])  # with the trend: fine
