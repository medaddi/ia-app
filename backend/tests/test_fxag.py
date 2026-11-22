"""FX Alex G Set & Forget v2 (the owner's blueprint of 2026-11-20): the two agents, the 16 scenarios (S01-S16), the
anti-look-ahead protocol, the 29 pair configs, resilience and the notifications. Each scenario test is named after its id."""

import asyncio
import random
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.smc import desk, manager, notify, playbook
from app.smc.fxag import config as C
from app.smc.fxag.pair_actor import context, evaluate
from app.smc.fxag.risk.levels import lots, plan, rank_key, risk_mult, season_mult
from app.smc.fxag.risk.order import client_order_id
from app.smc.fxag.strategy import alignment, confluence, zones
from app.smc.fxag.strategy.checks import audit
from app.smc.fxag.strategy.data import Series
from app.smc.fxag.strategy.entry import order
from app.smc.fxag.strategy.structure import Structure, extreme
from app.smc.fxag.time_utils import blackout, news_block, ny_day_open
from app.smc.playbook import _Bar

PIP = 0.0001
T0 = 1_790_000_000 - 1_790_000_000 % 86400


def bars(closes, step=86400, t0=T0, wick=2 * PIP):
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(_Bar(t0 + i * step, o, max(o, c) + wick, min(o, c) - wick, c))
    return out


def series(name, c, step):
    return Series(name, c, [x.time + step for x in c])


def structure(name, closes, step, wick=2 * PIP, chop=False):
    return Structure(series(name, bars(closes, step, wick=wick), step), PIP, chop=chop)


def zone(lo, hi, tfs=("D",), kind="D", roles=(-1,), psych=None, flip=False, touches=3):
    return {"lo": lo, "hi": hi, "tfs": set(tfs), "kind": kind, "sl_lo": lo, "sl_hi": hi, "roles": set(roles), "flip": flip, "psych": psych,
            "touches": touches, "t0": T0, "id": f"{kind}-{round(lo / PIP)}", "overlap": len(tfs) > 1, "width_pips": round((hi - lo) / PIP, 1)}


def tue(h, m=0):
    return int(datetime(2026, 11, 17, h, m, tzinfo=timezone.utc).timestamp())  # a Tuesday


# ---------------------------------------------------------------- the 29 pairs (step 5.1, 5.3)
@pytest.mark.parametrize("key", C.UNIVERSE)
def test_pair_config_pip_lambda_psych_shard_and_lot(key):
    m = C.meta(key)
    assert m["pip"] == (0.10 if key == "XAUUSD" else 0.01 if key.endswith("JPY") else 0.0001)
    assert m["lam"] == {"G1": 1.0, "G2": 1.15, "G3": 1.15, "G4": 1.35, "G5": 2.5}[C.group_of(key)]
    assert m["step500"] == (25.0 if key == "XAUUSD" else 0.5 if key.endswith("JPY") else 0.005)
    assert key in C.SHARDS[C.shard_of(key)] and m["decimals"] == (2 if key == "XAUUSD" else 3 if key.endswith("JPY") else 5)
    assert m["pip_value_usd_per_lot"] > 0 and m["lot_step"] > 0 and len(m["currencies"]) >= 1
    n = lots(100.0, 30.0, m["pip_value_usd_per_lot"], m["min_lot"], m["max_lot"], m["lot_step"])
    assert 0 < n <= m["max_lot"] and abs(n / m["lot_step"] - round(n / m["lot_step"])) < 1e-6  # no division by zero, a whole lot step


def test_universe_groups_and_shards_cover_the_29_pairs_once():
    assert len(C.UNIVERSE) == 29 and len(set(C.UNIVERSE)) == 29 and set(C.UNIVERSE) == set(playbook.ALEXG_PAIRS)
    flat = [p for g in C.GROUPS.values() for p in g["pairs"]]
    assert sorted(flat) == sorted(C.UNIVERSE) and [len(v) for v in C.SHARDS.values()] == [7, 7, 8, 7]
    assert [len(g["pairs"]) for g in C.GROUPS.values()] == [5, 12, 6, 5, 1]


def test_old_engine_and_strategies_are_gone():
    from pathlib import Path
    import app.smc as pkg
    base = Path(pkg.__file__).parent
    assert not (base / "alexg.py").exists() and (base / "fxag" / "strategy").is_dir() and (base / "fxag" / "risk").is_dir()


# ---------------------------------------------------------------- 2.2 structure
def _trend():
    return [1.1000, 1.1010, 1.1020, 1.1035, 1.1050, 1.1040, 1.1030, 1.1025, 1.1030, 1.1045, 1.1060, 1.1075, 1.1090, 1.1080,
            1.1070, 1.1062, 1.1070, 1.1085, 1.1100, 1.1115, 1.1130]


def test_true_elbows_alternate_and_respect_alpha_atr():
    st = structure("D", _trend() * 2, 86400, wick=0)
    kinds = [e[1] for e in st.els]
    assert all(a != b for a, b in zip(kinds, kinds[1:])) and len(st.els) >= 3
    checked = 0
    for a, b in zip(st.els, st.els[1:]):
        if st.atr[b[0]]:  # before 14 candles the ATR is undefined and the first elbows are accepted
            assert abs(b[2] - a[2]) >= C.ALPHA["D"] * st.atr[b[0]] - 1e-12  # delta = alpha x ATR14
            checked += 1
    assert checked >= 1


def test_elbow_is_unknown_before_its_confirmation_candle():
    st = structure("D", _trend(), 86400, wick=0)
    for i in range(len(st.c)):
        assert all(e[0] + st.k <= i for e in st.elbows_at(i))  # an elbow at j is known only from j + w


def test_trend_shift_needs_a_body_close_half_a_pip_beyond_hl():
    c = _trend()
    st = structure("D", c, 86400, wick=0)
    assert st.bias[-1] == 1
    hl = st.hl[-1][0]
    assert structure("D", c + [hl - 0.4 * PIP], 86400, wick=0).bias[-1] == 1     # 0.4 pip beyond: no shift
    down = structure("D", c + [hl - 0.7 * PIP], 86400, wick=0)
    assert down.bias[-1] == -1 and down.events[-1][1] == "SHIFT"
    wick = bars(c, 86400, wick=0) + [_Bar(T0 + 99 * 86400, c[-1], c[-1], hl - 50 * PIP, hl + PIP)]  # a wick far below HL, the close above
    assert Structure(series("D", wick, 86400), PIP).bias[-1] == 1


def test_chop_filter_er_and_overlap():
    flat = structure("D", [1.1 + (0.0004 if i % 2 else 0) for i in range(60)], 86400, wick=PIP, chop=True)
    assert flat.chop[-1] and flat.biased(len(flat.c) - 1) == 0
    trend = structure("D", [1.0 + 0.004 * i for i in range(60)], 86400, wick=PIP, chop=True)
    assert not trend.chop[-1]


def test_extreme_filter_veto_beyond_the_weekly_extreme():  # S09
    w = structure("W", [1.0 + 0.01 * i for i in range(40)], 7 * 86400)
    assert extreme(w, 39, 1) and not extreme(w, 39, -1)
    w2 = structure("W", [1.0 + 0.01 * i for i in range(30)] + [1.2, 1.1, 1.0, 1.05, 1.0, 1.1, 1.0, 1.05, 1.0, 1.1], 7 * 86400)
    assert not extreme(w2, 39, 1)


# ---------------------------------------------------------------- 2.3 alignment
@pytest.mark.parametrize("bw,bd,b4,d,scenario,bonus", [
    (1, 1, 1, 1, "M1", 25), (-1, -1, -1, -1, "M1", 25), (1, 1, -1, 1, "M2", 20), (1, 1, 0, 1, "M2", 20), (-1, -1, 1, -1, "M2", 20),
    (-1, 1, 1, 1, "M3", 15), (0, 1, 1, 1, "M3", 15), (1, -1, -1, -1, "M3", 15), (1, -1, 1, 1, "M4", 0), (1, -1, 1, -1, "M4", 0),
    (0, 0, 1, 1, "M4", 0), (1, 0, 1, 1, "M4", 0)])
def test_alignment_matrix_m1_to_m4(bw, bd, b4, d, scenario, bonus):  # S01, S02, S03
    a = alignment.matrix(bw, bd, b4, d)
    assert (a["scenario"], a["bonus"]) == (scenario, bonus)


def test_direction_of_an_alignment():
    assert alignment.direction(1, 1, 1) == 1 and alignment.direction(-1, -1, 1) == -1 and alignment.direction(1, -1, 1) == 0


def test_where_are_we_in_the_move():
    assert alignment.chasing(1.0900, 1.0, 1.1, 1) == "CHASING_HIGH" and alignment.chasing(1.0500, 1.0, 1.1, 1) is None
    assert alignment.chasing(1.0100, 1.0, 1.1, -1) == "CHASING_LOW" and alignment.chasing(1.0500, 1.0, 1.1, -1) is None
    assert alignment.in_value(1.0600, 1.0, 1.1, 1) and not alignment.in_value(1.0800, 1.0, 1.1, 1)


# ---------------------------------------------------------------- 2.4 AOIs
def test_adaptive_zone_width():
    w = zones.wmax("D", 0.0065, PIP, 1.0)
    assert abs(w - 0.55 * 0.0065) < 1e-12 and 35 < w / PIP < 36  # EURUSD ATR 65 pips: ~36 pips
    assert zones.wmax("D", 0.0001, PIP, 1.0) == 20 * PIP and zones.wmax("D", 0.05, PIP, 1.0) == 60 * PIP  # the floor and the cap
    assert abs(zones.wmax("W", 0.0100, PIP, 1.0) - 0.40 * 0.0100) < 1e-12 and zones.wmax("W", 0.2, PIP, 1.35) == 80 * 1.35 * PIP
    assert zones.wmax("W", 0.0030, PIP, 1.0) == 30 * PIP  # the weekly floor: 30 lambda pips
    assert abs(zones.wmax("D", 35.0, 0.10, 2.5) - 15.0) < 1e-9  # gold: ATR(D) $35 = 350 pips: capped at 150 pips = $15


def _ranging(n=40):
    seq = []
    for _ in range(n):
        seq += [1.2580, 1.2545, 1.2505, 1.2555, 1.2590]
    return seq


def test_aoi_validity_touches_flip_and_polarity():
    st = structure("D", _ranging(), 86400)
    zs = zones.build(st, len(st.c) - 1, PIP, 1.0)
    assert zs and all(z["touches"] >= 2 and (z["hi"] - z["lo"]) <= zones.wmax("D", st.atr[-1], PIP, 1.0) + 1e-12 for z in zs)
    assert all(b - a >= C.TOUCH_GAP for z in zs for a, b in zip(z["hits"], z["hits"][1:]))
    assert zones.polarity_ok(zone(1, 2, roles=(-1,)), 1) and not zones.polarity_ok(zone(1, 2, roles=(1,)), 1)
    assert zones.polarity_ok(zone(1, 2, roles=(1,), flip=True), 1)


def test_w_and_d_zones_merge_or_nest():  # S08
    w = [{"lo": 1.1000, "hi": 1.1030, "touches": 3, "roles": {-1}, "flip": False, "t0": 1, "hits": [1], "tf": "W", "wicks": 0}]
    d = [{"lo": 1.1020, "hi": 1.1050, "touches": 4, "roles": {1}, "flip": False, "t0": 2, "hits": [2], "tf": "D", "wicks": 0}]
    m = zones.merge(w, d, PIP, 1.0, 0.0080)[0]
    assert m["kind"] == "W+D" and (m["lo"], m["hi"]) == (1.1000, 1.1050) and m["tfs"] == {"W", "D"} and m["overlap"]
    wide = zones.merge([{**w[0], "lo": 1.0960}], d, PIP, 1.0, 0.0080)[0]
    assert (wide["lo"], wide["hi"]) == (1.1020, 1.1050) and wide["sl_lo"] == 1.0960 and wide["kind"] == "W+D"
    near = zones.merge(w, [{**d[0], "lo": 1.1040, "hi": 1.1060}], PIP, 1.0, 0.0080)  # 10 pips apart (<= 15 lambda): still one zone
    assert near[0]["kind"] == "W+D"


def test_500_level_snap_and_single_count():  # S09 of the blueprint's list (3 pips outside the edge)
    z = zones.snap_500(zone(1.1503, 1.1530), PIP, 1.0, 0.005, 0.0060)
    assert z["psych"] == 1.15 and z["lo"] == 1.15
    far = zones.snap_500(zone(1.1512, 1.1530), PIP, 1.0, 0.005, 0.0060)
    assert far["psych"] is None and far["lo"] == 1.1512
    inside = zones.snap_500(zone(1.1490, 1.1520), PIP, 1.0, 0.005, 0.0060)
    assert inside["psych"] == 1.15 and (inside["lo"], inside["hi"]) == (1.1490, 1.1520)


def test_liquidity_sweep_keeps_the_aoi_valid_and_a_body_close_breaks_it():  # S04, S05
    z = zone(1.1000, 1.1020)
    base = [1.1050, 1.1040, 1.1030, 1.1025]
    d1 = structure("D", base, 86400, wick=0)
    d1.c[-1].low = 1.0980  # a wick 20 pips under the zone, the body closes inside
    h4 = structure("H4", [1.1030] * 40, 14400, wick=PIP)
    assert not zones.suspended(z, 1, d1, 3, h4, 39, PIP)
    broken = structure("D", base + [1.0970], 86400, wick=0)
    assert zones.suspended(z, 1, broken, 4, h4, 39, PIP)
    back = structure("D", base + [1.0970, 1.1030], 86400, wick=0)
    assert not zones.suspended(z, 1, back, 5, h4, 39, PIP)  # back above the zone: the retest is allowed
    two = structure("H4", [1.1030] * 30 + [1.0970, 1.0968], 14400, wick=PIP)
    assert zones.suspended(z, 1, d1, 3, two, 31, PIP)  # two consecutive H4 closes beyond


def test_weekly_runway_and_trap_s10():  # S10
    act, wz = zone(1.1000, 1.1020), zone(1.0950, 1.0970, tfs=("W",), kind="W")
    opp, runway = zones.opposing_weekly([act, wz], act, -1, 1.1000)
    assert opp is wz and abs(runway - 0.0030) < 1e-12
    assert zones.opposing_weekly([act], act, -1, 1.1000) == (None, None)


# ---------------------------------------------------------------- 2.5 confluence and grades
def _candles(spec):
    return [_Bar(T0 + i * 3600, *p) for i, p in enumerate(spec)]


def test_clean_engulfing_definition():
    c = _candles([(1.1030, 1.1032, 1.1018, 1.1020), (1.1020, 1.1022, 1.1009, 1.1010), (1.1008, 1.1052, 1.1006, 1.1050)])
    assert confluence.engulfing(c, 2, 1, 0.0040) and not confluence.engulfing(c, 2, -1, 0.0040)
    assert not confluence.engulfing(c, 2, 1, 0.0120)  # body 42 pips < 0.55 ATR (66 pips)
    wicked = _candles([(1.1030, 1.1032, 1.1018, 1.1020), (1.1020, 1.1022, 1.1009, 1.1010), (1.1008, 1.1090, 1.1006, 1.1050)])
    assert not confluence.engulfing(wicked, 2, 1, 0.0040)  # a 40-pip upper wick on a 84-pip range: > 30 %
    gap = _candles([(1.1030, 1.1032, 1.1018, 1.1020), (1.1020, 1.1022, 1.1009, 1.1010), (1.1030, 1.1074, 1.1028, 1.1070)])
    assert not confluence.engulfing(gap, 2, 1, 0.0040)  # it opens far above the previous body


def test_multi_bar_engulfing_of_a_pause():
    c = _candles([(1.1030, 1.1032, 1.1018, 1.1020), (1.1020, 1.1026, 1.1012, 1.1024), (1.1024, 1.1028, 1.1020, 1.1022), (1.1018, 1.1062, 1.1016, 1.1060)])
    assert confluence.engulfing(c, 3, 1, 0.0040)


def test_rejection_patterns():
    assert confluence.pin(_Bar(T0, 1.1000, 1.1003, 1.0960, 1.1002), 1) and not confluence.pin(_Bar(T0, 1.1000, 1.1003, 1.0960, 1.1002), -1)
    assert confluence.doji_rej(_Bar(T0, 1.1000, 1.1002, 1.0970, 1.1001), 1)


@pytest.mark.parametrize("total,scenario,rr,grade", [(100, "M1", 3.0, "A+"), (85, "M2", 2.0, "A+"), (84, "M2", 2.0, "A"), (75, "M3", 2.0, "A"),
                                                     (74, "M1", 2.5, "B+"), (68, "M1", 3.0, "B+"), (68, "M1", 2.2, "C"), (70, "M2", 3.0, "C"),
                                                     (67, "M1", 3.0, "C"), (40, "M1", 3.0, "D")])
def test_grade_scale(total, scenario, rr, grade):
    assert confluence.grade_of(total, scenario, rr) == grade


def test_weights_sum_to_100():
    assert max(C.W_C1.values()) + C.W_C2_MERGED + C.W_C3 + C.W_C4 + C.W_C5 + C.W_C6 + C.W_C7 + C.W_C8["E1"] == 100
    assert C.W_C1 == {"M1": 25, "M2": 20, "M3": 15} and C.W_C8 == {"E1": 10, "E2": 8, "E3": 8}


# ---------------------------------------------------------------- 2.6 the 3 models, the huge engulfing
def test_huge_engulfing_goes_to_the_50_percent_limit_s06():  # S06, S07
    candle = _Bar(T0, 1.1000, 1.1105, 1.0998, 1.1100)
    tr = {"candle": candle, "atr": 0.0040, "model": "E1"}
    plan_at = lambda e: {"entry": e, "rr": (1.1300 - e) / (e - 1.0960), "risk": e - 1.0960, "trap": False, "slWide": False, "tp": 1.13}  # noqa: E731
    o = order(tr, 1, plan_at, 0)
    assert o["orderType"] == "LIMIT_PULLBACK" and o["model"] == "E3" and abs(o["entry"] - 1.1050) < 1e-9 and o["rr"] >= 2.2 and o["huge"]
    normal = {"candle": _Bar(T0, 1.1000, 1.1030, 1.0998, 1.1028), "atr": 0.0040, "model": "E2"}
    m = order(normal, 1, plan_at, 0)
    assert m["orderType"] == "MARKET" and m["model"] == "E2" and m["entry"] == 1.1028
    low = lambda e: {"entry": e, "rr": 1.4, "risk": 0.003, "trap": False, "slWide": False, "tp": 1.12}  # noqa: E731
    assert order(tr, 1, low, 0)["reject"] == "RR_BELOW_MIN"


def test_market_with_rr_under_2_but_limit_over_2_2_becomes_e3():
    c = _Bar(T0, 1.1000, 1.1060, 1.0998, 1.1055)  # not huge (body 55 pips <= 1.6 x 50)
    tr = {"candle": c, "atr": 0.0050, "model": "E1"}
    plan_at = lambda e: {"entry": e, "rr": 1.8 if e > 1.1050 else 2.4, "risk": 0.003, "trap": False, "slWide": False, "tp": 1.12}  # noqa: E731
    o = order(tr, 1, plan_at, 0)
    assert o["orderType"] == "LIMIT_PULLBACK" and o["model"] == "E3"


def test_e3_takes_the_sos_neckline_when_it_is_inside_the_body_and_gives_more_rr():
    candle = _Bar(T0, 1.1000, 1.1105, 1.0998, 1.1100)  # huge: body 100 pips > 1.6 x 40
    plan_at = lambda e: {"entry": e, "rr": (1.1300 - e) / (e - 1.0960), "risk": e - 1.0960, "trap": False, "slWide": False, "tp": 1.13}  # noqa: E731
    deep = order({"candle": candle, "atr": 0.0040, "model": "E1", "sos": {"level": 1.1030}}, 1, plan_at, 0)
    assert deep["orderType"] == "LIMIT_PULLBACK" and abs(deep["entry"] - 1.1030) < 1e-9  # deeper than 50 %: higher R:R
    shallow = order({"candle": candle, "atr": 0.0040, "model": "E1", "sos": {"level": 1.1080}}, 1, plan_at, 0)
    assert abs(shallow["entry"] - 1.1050) < 1e-9  # the 50 % is better
    outside = order({"candle": candle, "atr": 0.0040, "model": "E1", "sos": {"level": 1.0990}}, 1, plan_at, 0)
    assert abs(outside["entry"] - 1.1050) < 1e-9  # a neckline outside the body is not used


def test_s13_a_short_hole_is_tolerated_more_than_3_missing_bars_is_unsafe():
    from app.smc.fxag.strategy.data import health
    t0 = 1_790_000_000 - 1_790_000_000 % 86400 + 86400 * 2  # a weekday
    while datetime.fromtimestamp(t0, timezone.utc).weekday() not in (1, 2):
        t0 += 86400
    mk = lambda skip: [_Bar(t0 + h * 3600, 1, 1, 1, 1) for h in range(20) if h not in skip]  # noqa: E731
    T = t0 + 20 * 3600
    assert health(mk(set()), [], T)["ok"]
    assert health(mk({8, 9, 10}), [], T)["ok"]          # 3 missing bars: tolerated
    assert not health(mk({8, 9, 10, 11}), [], T)["ok"]  # 4 missing bars: DATA_OR_SPREAD_UNSAFE


# ---------------------------------------------------------------- step 3 risk
def _sts(atr_h1=0.0010, atr_d=0.0100, atr_h4=0.0030, d_elbows=(), w_elbows=()):
    mk = lambda a, el: SimpleNamespace(atr=[a] * 5, elbows_at=lambda i, _e=list(el): _e)  # noqa: E731
    return {"H1": mk(atr_h1, ()), "D": mk(atr_d, [(0, 1, p) for p in d_elbows]), "H4": mk(atr_h4, ()), "W": mk(0.03, [(0, 1, p) for p in w_elbows])}


IDX = {"H1": 4, "D": 4, "H4": 4, "W": 4}


def test_stop_loss_anchor_buffer_and_floor():
    sts = _sts(d_elbows=[1.2700])
    p = plan(1.2520, 1, zone(1.2500, 1.2510), 1.2500, [], sts, IDX, PIP, 1.0, PIP, "M1")
    assert abs(p["sl"] - (1.2500 - (6 * PIP + PIP))) < 1e-12  # anchor - (max(6 pips, 0.30 ATR H1) + spread)
    tight = plan(1.2503, 1, zone(1.2500, 1.2510), 1.2500, [], sts, IDX, PIP, 1.0, PIP, "M1")
    assert abs((1.2503 - tight["sl"]) - 12 * PIP) < 1e-12  # the floor: max(12 lambda pips, 0.65 ATR H1) = 12 pips
    big = plan(1.2520, 1, zone(1.2500, 1.2510), 1.2500, [], _sts(atr_h1=0.0030, d_elbows=[1.2700]), IDX, PIP, 1.0, PIP, "M1")
    assert abs(big["sl"] - (1.2500 - (0.30 * 0.0030 + PIP))) < 1e-12  # the ATR share beats 6 pips


def test_sl_too_wide_veto():
    p = plan(1.2520, 1, zone(1.2500, 1.2510), 1.2200, [], _sts(atr_d=0.0100, d_elbows=[1.2900]), IDX, PIP, 1.0, PIP, "M1")
    assert p["slWide"]  # 3.3 > 1.8 ATR(D)


def test_take_profit_major_target_margin_and_cap():
    sts = _sts(d_elbows=[1.2540, 1.2640, 1.2700])
    p = plan(1.2520, 1, zone(1.2500, 1.2510), 1.2500, [], sts, IDX, PIP, 1.0, PIP, "M1")
    risk = 1.2520 - p["sl"]
    assert abs(p["tp"] - (1.2640 - max(4 * PIP, 0.15 * 0.0030))) < 1e-9 and p["rr"] >= 2.0  # 1.2540 is under 2 x the stop: skipped
    far = plan(1.2520, 1, zone(1.2500, 1.2510), 1.2500, [], _sts(d_elbows=[1.3000]), IDX, PIP, 1.0, PIP, "M1")
    assert abs(far["rr"] - 4.5) < 1e-9 and far["capped"] and abs(far["tp"] - (1.2520 + 4.5 * (1.2520 - far["sl"]))) < 1e-9
    assert risk > 0


def test_no_target_means_no_trade():
    p = plan(1.2520, 1, zone(1.2500, 1.2510), 1.2500, [], _sts(), IDX, PIP, 1.0, PIP, "M1")
    assert p["tp"] is None and p["rr"] == 0.0


def test_weekly_trap_185_and_m3_runway():  # S10, S03
    sts = _sts(d_elbows=[1.2800])
    z = zone(1.2500, 1.2510)
    near = plan(1.2520, 1, z, 1.2500, [zone(1.2565, 1.2600, tfs=("W",), kind="W")], sts, IDX, PIP, 1.0, PIP, "M1")
    assert near["trap"]  # runway 45 pips < 1.85 x the 27-pip stop
    far = plan(1.2520, 1, z, 1.2500, [zone(1.2800, 1.2850, tfs=("W",), kind="W")], sts, IDX, PIP, 1.0, PIP, "M1")
    assert not far["trap"]
    wz = [zone(1.2570, 1.2600, tfs=("W",), kind="W")]  # runway 50 pips: >= 1.85 x 27 (not a trap in M1) but < 2.2 x 27 = 59 (a trap in M3)
    assert not plan(1.2520, 1, z, 1.2500, wz, sts, IDX, PIP, 1.0, PIP, "M1")["trap"]
    assert plan(1.2520, 1, z, 1.2500, wz, sts, IDX, PIP, 1.0, PIP, "M3")["trap"]


@pytest.mark.parametrize("month,grade,mult", [(1, "A+", 1.0), (6, "A", 1.0), (11, "B+", 0.75), (12, "A", 0.5), (12, "B+", 0.375), (3, "C", 0.0)])
def test_risk_multiplier_grade_and_season(month, grade, mult):
    t = int(datetime(2026, month, 15, tzinfo=timezone.utc).timestamp())
    assert risk_mult(t, grade) == mult and season_mult(t) == (0.5 if month == 12 else 1.0)


def test_lot_formula_floors_and_never_divides_by_zero():  # S13
    assert lots(100, 25, 10.0) == 0.4 and lots(100, 30, 6.54) == 0.5 and lots(1, 30, 10.0) == 0.01
    assert lots(100, 0, 10.0) == 0.0 and lots(100, 30, 0) == 0.0
    assert lots(100, 33, 10.0) == 0.3  # 0.303 -> 0.30, never rounded up


def test_ranking_and_idempotent_id():  # S16
    sig = [{"symbol": "A", "score": 85, "alignmentStrength": 5, "rr": 2.5}, {"symbol": "B", "score": 100, "alignmentStrength": 4, "rr": 2.1},
           {"symbol": "C", "score": 85, "alignmentStrength": 5, "rr": 3.0}]
    assert [s["symbol"] for s in sorted(sig, key=rank_key, reverse=True)] == ["B", "C", "A"]
    assert client_order_id("EUR/USD", 1, "H4", T0) == client_order_id("EUR/USD", 1, "H4", T0) != client_order_id("EUR/USD", -1, "H4", T0)
    assert len(client_order_id("EUR/USD", 1, "H4", T0)) == 16


# ---------------------------------------------------------------- step 4 the final gates (S11-S16)
def _good(**o):
    p = {"grade": "A", "score": 80, "rr": 3.0, "model": "E1", "ext_atr": 0.5, "slWide": False, "trap": False, "side": "BUY", "side_of": {}}
    p.update(o)
    return p


OK = {"ok": True}


@pytest.mark.parametrize("override,code", [({"grade": "C"}, "SCORE_TOO_LOW"), ({"rr": 1.9}, "RR_BELOW_MIN"), ({"slWide": True}, "SL_TOO_WIDE"),
                                           ({"trap": True}, "WEEKLY_TRAP"), ({"model": "E2", "ext_atr": 1.5}, "EXTENDED_ENTRY"),
                                           ({"early": ["CHOP_MARKET"]}, "CHOP_MARKET")])
def test_each_veto_code(override, code):
    a = audit(_good(**override), tue(14), [], True, PIP, PIP, PIP, OK)
    assert a["verdict"] == "VETO" and code in a["reasons"]
    assert audit(_good(), tue(14), [], True, PIP, PIP, PIP, OK)["verdict"] == "APPROVE"


def test_news_blackout_on_both_currencies_s11():  # S11
    T = tue(14)
    assert "NEWS_BLACKOUT" in audit(_good(), T, [T + 40 * 60], True, PIP, PIP, PIP, OK)["reasons"]   # -45 min
    assert "NEWS_BLACKOUT" in audit(_good(), T, [T - 25 * 60], True, PIP, PIP, PIP, OK)["reasons"]   # +30 min
    assert news_block(T, [T + 46 * 60]) is None and news_block(T, [T - 31 * 60]) is None
    cal = [{"time": T + 10 * 60, "currency": "JPY", "title": "BoJ"}]
    from app.smc.fxag.engine import news_times
    assert news_times("EURJPY", cal) == [T + 600] and news_times("EURUSD", cal) == []  # the quote leg counts for EURJPY


@pytest.mark.parametrize("when,blocked", [(tue(14), False), (tue(20, 59), False), (tue(21, 0), True), (tue(23, 20), True), (tue(23, 30), False),
                                          (int(datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc).timestamp()), True),   # Friday 19:00
                                          (int(datetime(2026, 11, 20, 18, 30, tzinfo=timezone.utc).timestamp()), False),
                                          (int(datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc).timestamp()), True),   # Saturday
                                          (int(datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc).timestamp()), True)])  # Sunday
def test_session_and_rollover_blackouts_s12(when, blocked):  # S12
    assert (blackout(when) == "SESSION_BLACKOUT") is blocked


def test_spread_spike_and_data_gap_s13():  # S13 (blueprint numbering of the feed)
    assert "DATA_OR_SPREAD_UNSAFE" in audit(_good(), tue(14), [], True, 3.0 * PIP, 1.0 * PIP, PIP, OK)["reasons"]
    assert "DATA_OR_SPREAD_UNSAFE" in audit(_good(), tue(14), [], True, PIP, PIP, PIP, {"ok": False})["reasons"]
    assert "DATA_OR_SPREAD_UNSAFE" not in audit(_good(), tue(14), [], True, 2.4 * PIP, PIP, PIP, OK)["reasons"]


def test_pair_locked_s14():  # S14
    assert "PAIR_LOCKED" in audit(_good(), tue(14), [], True, PIP, PIP, PIP, OK, locked=True)["reasons"]
    from app.smc.skill import portfolio
    now = T0 + 3600
    live = {"symbol": "EUR/USD", "direction": "SELL", "time": now - 60, "liveUntil": now + 9999}
    assert portfolio.check("EUR/USD", {"direction": "BUY"}, [live], now)["verdict"] == "BLOCK"
    assert portfolio.check("EUR/USD", {"direction": "BUY"}, [{**live, "state": "CLOSED"}], now)["verdict"] == "PASS"


def test_currency_exposure_cap_s15():  # S15
    from app.smc.skill import portfolio
    now = T0 + 3600
    live = lambda s, d: {"symbol": s, "direction": d, "time": now - 60, "liveUntil": now + 9999}  # noqa: E731
    three_long_usd = [live("USD/JPY", "BUY"), live("USD/CAD", "BUY"), live("USD/CHF", "BUY")]
    blocked = portfolio.check("GBP/USD", {"direction": "SELL"}, three_long_usd, now)  # SELL GBP/USD = long USD: the 4th
    assert blocked["verdict"] == "BLOCK" and any("CURRENCY_EXPOSURE_CAP" in r for r in blocked["reasons"])
    assert portfolio.check("GBP/USD", {"direction": "BUY"}, three_long_usd, now)["verdict"] == "PASS"  # the other way: short USD
    assert portfolio.check("GBP/USD", {"direction": "SELL"}, three_long_usd[:2], now)["verdict"] == "PASS"  # only 2 open


def test_cron_double_call_is_idempotent_s16(monkeypatch):  # S16
    _clean()
    T = T0 + 9 * 3600 - (T0 + 9 * 3600) % 300
    state = {"sig": [_sig(f"SMC-GBPUSD-M1-{T + 300}-B", T + 300)]}

    async def fake_team(pair, fresh=False):
        return {"success": True, "signals": state["sig"] if pair == "GBP/USD" else [], "decision": "WATCH_ONLY"}
    sent = []

    async def fake_broadcast(pair, text, title, body, tag, signal=None):
        sent.append(pair)
        return {"telegram": 1, "push": 1}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "broadcast", fake_broadcast)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    asyncio.run(notify.tick())
    asyncio.run(notify.tick())
    assert sent.count("GBP/USD") == 1


# ---------------------------------------------------------------- time
def test_new_york_close_is_dst_aware():
    summer = int(datetime(2026, 7, 15, 12, tzinfo=timezone.utc).timestamp())
    winter = int(datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp())
    assert datetime.fromtimestamp(ny_day_open(summer), timezone.utc).hour == 21 and datetime.fromtimestamp(ny_day_open(winter), timezone.utc).hour == 22


# ---------------------------------------------------------------- the whole engine: anti-look-ahead, scan == live, resilience
def _walk(n, step, t_end, start, vol, seed):
    rnd = random.Random(seed)
    out, px = [], start
    t0 = t_end - n * step
    for i in range(n):
        o = px
        c = o + rnd.gauss(0, vol)
        out.append(_Bar(t0 + i * step, o, max(o, c) + abs(rnd.gauss(0, vol / 2)), min(o, c) - abs(rnd.gauss(0, vol / 2)), c))
        px = c
    return out


def _synthetic():
    end = T0 + 7 * 86400
    h1 = _walk(6600, 3600, end, 1.2500, 0.0011, 2)
    d1 = _walk(1600, 86400, end - 6600 * 3600, 1.2500, 0.0060, 1)
    m5 = _walk(2000, 300, end, h1[-1].close, 0.0003, 3)
    return m5, h1, d1


def test_no_look_ahead_the_read_at_t_ignores_every_later_candle():
    m5, h1, d1 = _synthetic()
    full = context("EURUSD", m5, h1, d1)
    for T in (h1[-1].time - 40 * 86400 + 3600, h1[-1].time - 20 * 86400 + 3600, h1[-1].time - 5 * 86400 + 3600):
        cut = [x for x in h1 if x.time + 3600 <= T]
        part = context("EURUSD", [], cut, [x for x in d1 if x.time + 86400 <= T])
        for d in (1, -1):
            a, b = evaluate(full, T, d, cut[-1].close), evaluate(part, T, d, cut[-1].close)
            assert (a["bias"], a["tier"], a["vetoes"], (a["zone"] or {}).get("id"), (a["conf"] or {}).get("total")) == \
                   (b["bias"], b["tier"], b["vetoes"], (b["zone"] or {}).get("id"), (b["conf"] or {}).get("total"))


def test_scan_equals_live_on_the_same_function():
    from app.smc.fxag import engine
    m5, h1, d1 = _synthetic()
    cx = context("EURUSD", [], h1, d1)
    s, _ = engine.scan("EURUSD", [], h1, 0.00012, None, d1, follow=h1)
    for x in s:  # every replayed trade equals a fresh evaluation at its close
        r = evaluate(cx, x["confirmedAt"], x["dir"], None, None)
        assert r["candidate"] and (r["candidate"]["entry"], r["candidate"]["sl"], r["candidate"]["tp"], r["candidate"]["score"]) == \
               (x["entry"], x["sl"], x["tp"], x["score"])
    assert all(x["proposal"] is None or x["proposal"]["set_and_forget_locked"] for x in s)
    assert engine.scan("EURUSD", [], h1[:200], 0.00012, None, d1, follow=h1[:200]) == ([], [])


def test_the_read_returns_the_2_agent_contract():
    m5, h1, d1 = _synthetic()
    t = desk.read_team("EUR/USD", desk.BY_SYMBOL["EUR/USD"], m5, h1, m5[-1].time + 300, None, d1)
    assert [a["id"] for a in t["agents"]] == ["StrategyAgent", "RiskAgent"] and len(t["agents"][0]["lines"]) == 7
    assert [r["id"] for r in t["strategies"]] == ["M1", "M2", "M3"] and t["grade"] in ("A+", "A", "B+", "C", "D") and t["tier"]
    assert all("zone" in b["label"] and len(b["label"]) <= 24 for b in t["chart"]["boxes"])


def test_one_pair_failing_never_stops_the_others(monkeypatch):
    _clean()

    async def fake_team(pair, fresh=False):
        if pair in ("EUR/USD", "GBP/JPY", "XAU/USD"):
            raise RuntimeError("429 from the feed")
        return {"success": True, "signals": [], "decision": "WATCH_ONLY"}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    res = asyncio.run(notify.tick())
    assert [p for p, v in res.items() if str(v).startswith("error")] == ["XAU/USD", "EUR/USD", "GBP/JPY"] or \
           sorted(p for p, v in res.items() if str(v).startswith("error")) == ["EUR/USD", "GBP/JPY", "XAU/USD"]
    assert sum(1 for p, v in res.items() if p in desk.PAIRS and not str(v).startswith("error")) == 26


# ---------------------------------------------------------------- notifications: the trade and its end
def _sig(sid, t, **o):
    s = {"id": sid, "strategy": "M1", "setupType": "M1", "name": "Full Sync (W + D + 4H)", "direction": "BUY", "time": t,
         "entry": 1.25120, "sl": 1.24780, "tp1": None, "tp": 1.26175, "part": 1.0, "market": True, "zone": [1.2512, 1.2512], "rr": 3.10,
         "validUntil": t, "expiry": 0, "holdUntil": t + 60 * 86400, "beOff": None, "newsMin": 30, "fridayExit": False, "state": "ACTIVE",
         "pass": True, "checklist": [], "steps": [], "lots": {"1000": 0.0, "10000": 0.0}, "riskPct": 1.0, "riskMult": 1.0, "grade": "A", "gpa": 85,
         "score": 85, "slPips": 34.0, "tpPips": 105.5, "sosTf": "M30", "etf": "H4", "orderType": "MARKET", "model": "E1",
         "breakdown": {"C1": 25, "C2": 15}, "proposal": {"client_order_id": "abc123"}, "draw": {}}
    s.update(o)
    return s


def _clean():
    from app.db import SessionLocal, init_db
    from app.models import Signal
    from app.store import set_setting
    init_db()
    with SessionLocal() as db:
        db.query(Signal).filter(Signal.id.like("SMC-%")).delete(synchronize_session=False)
        set_setting(db, "history", {"since": 1})
        db.commit()


def test_the_trade_message_is_short_and_no_radar():
    s = _sig("SMC-GBPUSD-M1-1-B", T0)
    t = notify.message(s, "GBP/USD", 5).split(chr(10))
    assert t == ["🟢 <b>GBP/USD · BUY</b>", "Entry <code>1.25120</code>", f"SL <code>{s['sl']:.5f}</code>", f"TP <code>{s['tp']:.5f}</code>"]
    one = notify.line(s, "GBP/USD", 5, "0.25")
    assert chr(10) not in one and one == f"🟢 GBP/USD BUY · Entry 1.25120 · SL {s['sl']:.5f} · TP {s['tp']:.5f} · Lot 0.25"
    assert notify.line({**s, "direction": "SELL", "orderType": "LIMIT_PULLBACK"}, "GBP/USD", 5).startswith("🔴 GBP/USD SELL LIMIT · Entry")
    assert notify.recent_radar() == [] and not hasattr(notify, "radar_message")


def test_telegram_trades_command_lists_the_running_trade_on_one_line():
    from app.telegram import bot
    _clean()
    assert bot._trades_text() == "📈 <b>Trades running</b>\nNone right now."
    assert notify._claim("GBP/USD", _sig("SMC-GBPUSD-M1-7-B", T0))
    t = bot._trades_text().split("\n")
    assert t == ["📈 <b>Trades running (1)</b>", "🟢 <b>GBP/USD BUY</b> · Entry 1.25120 · SL 1.24780 · TP 1.26175"]
    assert "Trades 1 · running 1" in bot._history_text()
    _clean()


def test_trade_followed_to_its_end_without_break_even(monkeypatch):
    _clean()
    T = T0 + 9 * 3600 - (T0 + 9 * 3600) % 300
    s = _sig(f"SMC-GBPUSD-M1-{T + 300}-B", T + 300)
    assert notify._claim("GBP/USD", s)

    def c(i, o, h, lo, cl):
        from app.market.types import Candle
        return Candle(T + i * 300, o, h, lo, cl, 0)
    m5 = [c(0, 1.2510, 1.2513, 1.2508, 1.2512), c(1, 1.2512, 1.2566, 1.2510, 1.2560), c(2, 1.2560, 1.2620, 1.2555, 1.2618)]
    desk.LIVE["GBP/USD"] = (m5, 0.0, None)
    msgs = []

    async def send(pair, text, title, body, tag):
        msgs.append(title)
    out = asyncio.run(manager.manage_all(send))
    assert out[s["id"]] == ["TP"] and msgs[0] == "GBP/USD BUY · 🏆 TP hit · +3.10R" and not any("BREAKEVEN" in m for m in msgs)
    assert abs(manager.results()["all"]["totalR"] - 3.1) < 0.01


def test_a_limit_missed_bus_is_cancelled_s07():  # S07
    from app.smc.playbook import run
    m5 = [_Bar(T0 + i * 300, *p) for i, p in enumerate([(1.1060, 1.1062, 1.1058, 1.1060), (1.1060, 1.1090, 1.1058, 1.1088), (1.1088, 1.1100, 1.1085, 1.1098)])]
    ev = []
    out = run(m5, 0, 1, 1.1050, 1.1000, None, 1.1150, 1.0, False, 96, T0 + 86400, 0.0, ev, None, None, None, 1.1100)  # miss_px: half way to the TP
    assert out["state"] == "MISSED" and [k for _, k, _ in ev] == ["MISSED"]


def test_pips_of_a_closed_trade_use_the_pair_pip_size():
    from app.smc.manager import trade_pips

    assert trade_pips("EUR/USD", 1.1000, 1.0980, 2.2) == 44.0     # 20-pip stop, +2.2R
    assert trade_pips("USD/JPY", 150.00, 150.30, -1.0) == -30.0   # JPY pip 0.01
    assert trade_pips("XAU/USD", 3500.0, 3510.0, 1.5) == 150.0    # gold pip 0.10
