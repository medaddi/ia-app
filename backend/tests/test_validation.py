"""v2.4 (the owner's prompt of 2026-11-11): the testable parameters and their pre-registered grid, the H4 fallback zone,
the stricter counter-trend gate, causal touches, per-symbol units, what the chart draws against the API payload, the
validation maths and the evidence state."""

import json
import sys
from pathlib import Path

import pytest

from app.smc import alexg, desk, playbook
from app.smc.playbook import _Bar
from tests.test_alexg import T0, _read, stored

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from smc.tools import validate  # noqa: E402


@pytest.fixture(autouse=True)
def _default_params():
    alexg.use()
    yield
    alexg.use()


# ---------------------------------------------------------------- the parameters
def test_every_threshold_has_an_origin_and_a_finite_grid():
    ps = alexg.STRATEGY["params"]
    assert all(v["origin"] in ("source", "research", "baseline", "owner") and v["value"] in v["grid"] and len(v["grid"]) <= 4 for v in ps.values())
    assert ps["min_touches"] == {**ps["min_touches"], "value": 3, "origin": "source", "grid": [3]}  # the three-touch rule is never lowered
    assert alexg.P["h4_fallback"] is True and alexg.P["counter_min_gpa"] == 80 and alexg.P["min_rr"] == 2.0 and alexg.P["break_even"] is False
    assert alexg.use("baseline") == {**alexg.P, "h4_fallback": False, "counter_min_gpa": 70, "min_rr": 2.0, "break_even": True}
    assert alexg.use("candidate_rr3")["min_rr"] == 3.0 and alexg.use("candidate_rr4")["min_rr"] == 4.0
    with pytest.raises(ValueError):
        alexg.use(min_rr=2.5)  # not in the pre-registered grid: no tuning by hand
    with pytest.raises(ValueError):
        alexg.use(min_touches=2)


# ---------------------------------------------------------------- causal touches
def test_one_visit_is_one_touch_and_only_once_its_rejection_is_in():
    lo, hi, rev = 1.1000, 1.1010, 0.0030
    px = [1.1050, 1.1040, 1.1008, 1.1006, 1.1009, 1.1020, 1.1045]  # comes down into the zone, stays 3 candles, leaves by 35 pips
    c = [_Bar(T0 + i * 86400, p, p + 0.0002, p - 0.0002, p) for i, p in enumerate(px)]
    c[-1] = _Bar(c[-1].time, 1.1020, 1.1046, 1.1018, 1.1045)
    assert alexg.touches(c, 0, 4, lo, hi, rev)[0] == 0  # inside the zone, the rejection not there yet: not a touch
    n, roles = alexg.touches(c, 0, 6, lo, hi, rev)
    assert n == 1 and roles == [(2, 1)]  # three candles inside one visit count once, as support


# ---------------------------------------------------------------- the counter-trend gate and the R:R floor
def test_a_counter_trend_setup_needs_a_higher_grade():
    weekly_against = {"W1": -1, "D1": 1, "H4": 1}
    ok_trend = alexg.squad(_read(gpa=75, grade="B"), 0.0001)
    assert ok_trend["execute"]  # a trend-following B passes
    short = alexg.squad(_read(S=weekly_against, setup="SF_COUNTER", gpa=75, grade="B"), 0.0001)
    assert not short["execute"] and short["agents"]["confluence_grader"]["status"] == "wait" and "Counter-trend" in short["agents"]["confluence_grader"]["badge"]
    assert alexg.squad(_read(S=weekly_against, setup="SF_COUNTER", gpa=85, grade="A"), 0.0001)["execute"]
    alexg.use("baseline")
    assert alexg.squad(_read(S=weekly_against, setup="SF_COUNTER", gpa=75, grade="B"), 0.0001)["execute"]  # the old rule, kept as the baseline


def test_the_rr_floor_is_the_parameter_never_a_stretched_target():
    assert alexg.squad(_read(rr=2.4), 0.0001)["execute"]
    alexg.use("candidate_rr3")
    sq = alexg.squad(_read(rr=2.4), 0.0001)
    assert not sq["execute"] and sq["agents"]["risk_guardian"]["status"] == "veto" and "< 3.0" in sq["agents"]["risk_guardian"]["badge"]
    assert alexg.squad(_read(rr=3.1), 0.0001)["execute"]


# ---------------------------------------------------------------- the H4 fallback zone
def test_h4_fallback_only_when_w1_and_d1_have_no_zone_and_still_three_touches():
    m5, h1 = stored("GBPUSD", "M5"), stored("GBPUSD", "H1")
    if not m5:
        return
    m5, h1 = m5[-30000:], h1[-4000:]
    d1 = playbook.resample(h1, 86400)
    cand, _ = alexg.scan("GBPUSD", m5, h1, 0.00018, None, d1)
    on_h4 = [s for s in cand if s["zoneInfo"]["label"] == "4H"]
    assert all(s["zoneInfo"]["touches"] >= 3 and s["zoneInfo"]["tfs"] == ["H4"] for s in on_h4)
    alexg.use("baseline")
    base, _ = alexg.scan("GBPUSD", m5, h1, 0.00018, None, d1)
    assert not [s for s in base if s["zoneInfo"]["label"] == "4H"]
    key = lambda s: (s["time"], s["dir"], s["etf"])  # noqa: E731
    w1d1 = {key(s) for s in base}
    assert all(key(s) not in w1d1 for s in on_h4)  # a fallback setup never replaces one that had a W1 / D1 zone
    assert {key(s) for s in cand if s["zoneInfo"]["label"] != "4H"} == w1d1


# ---------------------------------------------------------------- units and the chart against the payload
def test_distances_use_each_instruments_own_pip():
    for key, pip in (("EURUSD", 0.0001), ("XAUUSD", 0.1)):
        m5, h1 = stored(key, "M5"), stored(key, "H1")
        if not m5:
            continue
        m5, h1 = m5[-20000:], h1[-3000:]
        ss, _ = alexg.scan(key, m5, h1, 3 * pip, None, playbook.resample(h1, 86400))
        assert alexg.config(key)["pip"] == pip
        for s in ss:
            assert s["slPips"] == round(abs(s["entry"] - s["sl"]) / pip, 1) and s["tpPips"] == round(abs(s["tp"] - s["entry"]) / pip, 1)
            assert abs(s["rr"] - abs(s["tp"] - s["entry"]) / abs(s["entry"] - s["sl"])) < 1e-9
            assert (s["sl"] < s["entry"] < s["tp"]) if s["dir"] > 0 else (s["tp"] < s["entry"] < s["sl"])
            assert s["family"] == ("counter-trend" if s["sid"] == "SF_COUNTER" else "trend-following")


def test_the_chart_draws_the_payloads_numbers_and_few_objects_by_default():
    for key, pair in (("GBPUSD", "GBP/USD"), ("XAUUSD", "XAU/USD")):
        m5, h1 = stored(key, "M5"), stored(key, "H1")
        if not m5:
            continue
        d1 = playbook.resample(h1, 86400)
        hit = None
        ends = [len(m5)] + [k + 1 for k in range(len(m5) - 1, 5000, -2000)]
        for end in ends:  # a moment with a live signal when the stored candles have one, else the last read
            a = m5[:end]
            now = a[-1].time + 300
            t = desk.read_team(pair, desk.BY_SYMBOL[pair], a, [x for x in h1 if x.time + 3600 <= now], now, None, [x for x in d1 if x.time + 86400 <= now])
            hit = hit or t
            if t["chart"]["trade"]:
                hit = t
                break
        ch = hit["chart"]
        assert all(isinstance(o.get("detail"), bool) for o in [*ch["boxes"], *ch["segments"], *ch["labels"]])
        assert sum(not b["detail"] for b in ch["boxes"]) <= 3 and all(o["detail"] for o in ch["labels"])  # a calm default view
        assert hit["evidence"]["state"] in ("insufficient data", "experimental", "validated for research") and hit["evidence"]["needed"] == 100
        tr = ch["trade"]
        if tr:
            s = next(r["setup"] for r in hit["strategies"] if r["status"] == "SIGNAL")
            assert (tr["entry"], tr["sl"], tr["tp"], tr["tp1"], tr["rr"]) == (s["entry"], s["sl"], s["tp"], s["tp1"], s["rr"])
            assert s["invalidation"] and s["etf"] in alexg.ENTRY_TFS and "research signal" in tr["label"]


# ---------------------------------------------------------------- the validation maths
def test_expectancy_profit_factor_drawdown_and_the_interval():
    tr = [{"time": i, "r": r, "cost": 0.1} for i, r in enumerate([3.0, -1.0, -1.0, 3.0, -1.0, -1.0, -1.0, 3.0])]
    m = validate.metrics(tr)
    assert m["trades"] == 8 and m["wins"] == 3 and m["winRate"] == 37.5 and m["avgWinR"] == 3.0 and m["avgLossR"] == 1.0 and m["avgCostR"] == 0.1
    assert m["expectancyR"] == round(0.375 * 3.0 - 0.625 * 1.0, 3) == 0.5 and m["pf"] == 1.8 and m["maxDrawdownR"] == 3.0 and m["totalR"] == 4.0
    assert m["ci95"] == validate.metrics(tr)["ci95"] and m["ci95"][0] < 0.5 < m["ci95"][1]  # seeded: reproducible
    assert validate.metrics([]) == {"trades": 0} and validate.metrics(tr[:1])["ci95"] is None


def test_no_pair_is_called_validated_without_the_sample():
    assert validate.MIN_OOS == 100
    assert validate.state_of({"trades": 12, "ci95": [0.5, 2.0]}) == "insufficient data"  # a good-looking handful proves nothing
    assert validate.state_of({"trades": 120, "ci95": [-0.1, 0.4]}) == "experimental"
    assert validate.state_of({"trades": 120, "ci95": [0.05, 0.4]}) == "validated for research"
    f = Path(desk.__file__).parent / "research" / "validation.json"
    if f.exists():
        for key, v in json.loads(f.read_text(encoding="utf-8"))["pairs"].items():
            assert v["state"] == validate.state_of({"trades": v["oosTrades"], "ci95": v.get("ci95")}) or v["oosTrades"] < 100
            assert v["state"] != "validated for research" or v["oosTrades"] >= 100
    assert desk.evidence("NOPAIR") == {"state": "insufficient data", "oosTrades": 0, "needed": 100, "trades": 0, "source": None}
