"""FXAlexG Set & Forget (the owner's md of 2026-11-19, applied to the letter): body-only Snake Trick elbows and the
structure, W1 / D1 / H4 sync, the 3-touch AOIs and the "every 500" level, the S_AlexG grading, the two-step trigger,
the SL / +1.5R / TP plan, the 5 agents, the 3-stage notifications and the +1.5R break-even trade management."""

import asyncio
import csv
import random
from pathlib import Path
from types import SimpleNamespace

from app.market.pairs import PAIRS, decimals_of
from app.market.sanitize import sanitize
from app.market.types import Candle
from app.smc import alexg, desk, manager, notify, playbook
from app.smc.playbook import _Bar
from app.smc.skill import portfolio

T0 = 1_790_000_000 - 1_790_000_000 % 86400
PIP = 0.0001
DATA = Path(__file__).resolve().parents[2] / "smc" / "pairs"


def stored(pair: str, tf: str) -> list[Candle]:
    p = DATA / pair / "data" / f"{tf}.csv"
    if not p.exists():
        p = DATA / pair / "data" / "dukascopy" / f"{tf}.csv"
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return [Candle(int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0))
                for r in csv.DictReader(f)]


def bars(oc: list[tuple[float, float]], step: int = 3600, t0: int = T0, wick: float = 2 * PIP) -> list:
    return [_Bar(t0 + i * step, o, max(o, c) + wick, min(o, c) - wick, c) for i, (o, c) in enumerate(oc)]


def path(closes: list[float]) -> list[tuple[float, float]]:
    """Candles from a close path: each opens at the previous close."""
    return [(closes[i - 1] if i else closes[0], c) for i, c in enumerate(closes)]


# ---------------------------------------------------------------- 3.1 Snake Trick elbows and the structure
def test_elbows_use_bodies_only_and_store_the_wick():
    c = bars(path([1.1000, 1.1010, 1.1020, 1.1050, 1.1030, 1.1020, 1.1010, 1.1015, 1.1030]), wick=0)
    c[3].high = 1.1090  # a long upper wick on the top candle: the elbow's P stays its body
    up, dn = alexg.find_elbows(c, 2)
    assert (3, 1.1050, 1.1090) in up  # P = B+ (the close), W = the highest wick of [t-1, t+1]
    assert any(q == 6 and p == 1.1010 for q, p, _ in dn)  # the lower body turn (B- of candle 6 = its close)
    flat = bars(path([1.1] * 9), wick=0)
    assert alexg.find_elbows(flat, 2)[0] == [] or all(min(x.close for x in flat[q + 1:q + 3]) < p for q, p, _ in alexg.find_elbows(flat, 2)[0])


def _trend_path():
    # up leg, pull back, break up (BOS), pull back to an HL, then down through that HL
    return [1.1000, 1.1010, 1.1020, 1.1030, 1.1040, 1.1030, 1.1020, 1.1015, 1.1012, 1.1020, 1.1035, 1.1045, 1.1060, 1.1070, 1.1080,
            1.1070, 1.1060, 1.1050, 1.1045, 1.1055, 1.1065, 1.1075, 1.1085, 1.1095, 1.1085, 1.1075, 1.1065, 1.1055, 1.1050]


def test_structure_shifts_only_beyond_hl_by_half_a_pip():
    cl = _trend_path()
    c = bars(path(cl), wick=0)
    up, dn = alexg.find_elbows(c, 3)
    s = alexg.trace_structure(c, up, dn, 3, PIP)
    i_bull = next(i for i, t in enumerate(s["trend"]) if t == 1)
    assert ("BOS", 1) in [(k, d) for _, k, d, _ in s["events"]] and s["trend"][-1] == 1
    hl = s["hl"][-1]
    assert hl[1] < s["hh"][-1][1] and i_bull < len(cl)  # HH always in front of HL
    just = cl + [hl[0] - 0.4 * PIP]  # 0.4 pip under HL: no shift
    c2 = bars(path(just), wick=0)
    s2 = alexg.trace_structure(c2, *alexg.find_elbows(c2, 3), 3, PIP)
    assert s2["trend"][-1] == 1
    below = cl + [hl[0] - 0.6 * PIP]  # 0.6 pip under HL: bearish
    c3 = bars(path(below), wick=0)
    s3 = alexg.trace_structure(c3, *alexg.find_elbows(c3, 3), 3, PIP)
    assert s3["trend"][-1] == -1 and s3["events"][-1][1:3] == ("SOS", -1) and abs(s3["events"][-1][3] - hl[0]) < 1e-12


def test_k_per_timeframe():
    assert alexg.K == {"W1": 2, "D1": 3, "H4": 3, "H1": 3, "M30": 3, "M15": 3}
    assert alexg.N_AOI == {"W1": 156, "D1": 300} and alexg.MIN_TOUCH == {"W1": 2, "D1": 3}


# ---------------------------------------------------------------- 3.2 AOIs and the "every 500" level
def _ranging_d1(n: int = 40):
    seq = []
    for _ in range(n):  # a floor near 1.2505 hit again and again, a ceiling near 1.2590
        seq += [(1.2580, 1.2545), (1.2545, 1.2505), (1.2505, 1.2555), (1.2555, 1.2590), (1.2590, 1.2580)]
    return bars(seq, 86400, T0 - 400 * 86400)


def test_aois_three_touches_four_bars_apart_min_width_and_psych_snap():
    d1 = _ranging_d1()
    tf = alexg.TF("D1", d1, PIP)
    zs = [alexg.snap_psych(z, PIP, 0.005) for z in alexg.build_aois(tf, len(d1) - 1, PIP, 60)]
    z = next(q for q in zs if q["lo"] <= 1.2505 <= q["hi"])
    assert z["touches"] >= 3 and all(b - a >= 4 for a, b in zip(z["hits"], z["hits"][1:]))
    assert z["width"] >= 12 - 1e-9 and z["width"] <= 60
    assert z["psych"] == 1.25 and z["lo"] <= 1.25  # 1.2500 within 8 pips: the zone widened to hold it
    far = alexg.snap_psych({"lo": 1.2520, "hi": 1.2532}, PIP, 0.005)
    assert far["psych"] is None and far["lo"] == 1.2520  # 1.2500 is 20 pips away, 1.2550 18 pips: no snap
    assert alexg.spaced([1, 2, 3, 5, 9, 10, 14]) == [1, 5, 9, 14]


def test_w1_and_d1_zones_merge():
    w = [{"lo": 1.2500, "hi": 1.2520, "touches": 2, "t_w1": 2, "tfs": {"W1"}, "roles": [], "t0": 5}]
    d = [{"lo": 1.2510, "hi": 1.2530, "touches": 4, "t_d1": 4, "tfs": {"D1"}, "roles": [], "t0": 3},
         {"lo": 1.2700, "hi": 1.2715, "touches": 3, "t_d1": 3, "tfs": {"D1"}, "roles": [], "t0": 9}]
    m = alexg.merge_zones(w, d)
    assert (m[0]["lo"], m[0]["hi"], m[0]["overlap"], m[0]["touches"], m[0]["t0"]) == (1.25, 1.253, True, 4, 3)
    assert m[1]["tfs"] == {"D1"} and not m[1]["overlap"]


# ---------------------------------------------------------------- 3.3 S_AlexG and the grades
def test_confluence_items_and_grades():
    pts = {k: p for k, p, _ in alexg.CONF}
    assert len(alexg.CONF) == 18 and sum(pts.values()) == 160
    assert (pts["sync"], pts["aoi_w1"], pts["aoi_d1"], pts["psych"], pts["sos"], pts["engulf"]) == (20, 10, 10, 5, 10, 10)
    assert (pts["ema_w1"], pts["ema_d1"], pts["ema_h4"], pts["elbow_w1"], pts["elbow_d1"], pts["elbow_h4"]) == (5, 5, 5, 10, 10, 5)
    assert (pts["candle_w1"], pts["candle_d1"], pts["candle_h4"], pts["pattern_w1"], pts["pattern_d1"], pts["pattern_h4"]) == (10, 10, 5, 10, 10, 10)
    assert [alexg.grade_of(s) for s in (130, 100, 99, 90, 89, 80, 79, 65)] == ["A+", "A+", "A", "A", "B", "B", "WAIT", "WAIT"]


def test_candle_rejections():
    p, x = _Bar(T0, 1.1000, 1.1005, 1.0948, 1.0950), _Bar(T0 + 1, 1.0950, 1.1012, 1.0948, 1.1010)
    assert alexg.engulf(p, x, 1) and not alexg.engulf(p, x, -1)  # C > O, C > B+(t-1), dB >= 0.85 dB(t-1)
    short = _Bar(T0 + 1, 1.0961, 1.1012, 1.0950, 1.1001)  # closes above, body 40 < 0.85 x 50
    assert not alexg.engulf(p, short, 1)
    assert alexg.pinbar(_Bar(T0, 1.1000, 1.1003, 1.0960, 1.1001), 1) and not alexg.pinbar(_Bar(T0, 1.1000, 1.1003, 1.0960, 1.1001), -1)
    a, b, c = _Bar(T0, 1.1050, 1.1052, 1.0998, 1.1000), _Bar(T0, 1.0998, 1.1003, 1.0990, 1.0995), _Bar(T0, 1.0996, 1.1035, 1.0994, 1.1030)
    assert alexg.star(a, b, c, 1) and not alexg.star(a, b, c, -1)  # morning star


def test_seasonal_risk():
    from datetime import datetime, timezone
    ts = lambda m: int(datetime(2026, m, 15, tzinfo=timezone.utc).timestamp())  # noqa: E731
    assert [alexg.season_risk(ts(m)) for m in range(1, 13)] == [1.0, 1.0, 1.0, 0.75, 0.75, 0.5, 0.5, 0.75, 0.75, 1.0, 1.0, 1.0]


# ---------------------------------------------------------------- 3.4 / 3.5 the trigger and the plan
def _fake_cx(levels_d1=(), adr=0.0080):
    class FakeTF:
        def __init__(self, lv):
            self.lv = lv

        def elbows(self, i, n):
            return [(0, p, 1) for p in self.lv]
    return SimpleNamespace(pip=PIP, spread=PIP, tf={"D1": FakeTF(levels_d1), "W1": FakeTF(())}, aois=lambda iw, id_: []), adr


def test_plan_market_limit_stop_buffer_cap_and_target():
    z = {"lo": 1.2500, "hi": 1.2512}
    sos = {"level": 1.2512, "swing": 1.2502}
    e = SimpleNamespace(c=[_Bar(T0, 1.2505, 1.2517, 1.2503, 1.2515)], at=[0.0020])
    cx, adr = _fake_cx()
    p = alexg._plan(cx, e, 0, z, 1, sos, adr, 0, 0)
    assert p["market"] and abs(p["sl"] - 1.2495) < 1e-9  # min(Z_low, L_swing) - max(5 pips, 2 x spread)
    assert abs(p["tp"] - (1.2515 + 3.5 * 0.0020)) < 1e-9 and abs(p["tp1"] - (1.2515 + 1.5 * 0.0020)) < 1e-9 and abs(p["rr"] - 3.5) < 1e-9
    cx, adr = _fake_cx([1.2560])  # an opposing D1 elbow: TP 5 pips before it; from the close 2.0R < 2.5 -> the 50 % limit
    q = alexg._plan(cx, e, 0, z, 1, sos, adr, 0, 0)
    assert not q["market"] and abs(q["entry"] - 1.2510) < 1e-9 and abs(q["tp"] - 1.2555) < 1e-9 and abs(q["rr"] - 3.0) < 1e-9
    assert q["band"] == (1.2510, 1.2512)  # the entry zone [min(N_SoS, P), max(N_SoS, P)]
    big = SimpleNamespace(c=[_Bar(T0, 1.2505, 1.2560, 1.2490, 1.2515)], at=[0.0020])  # range 70 pips > 1.8 ATR
    assert not alexg._plan(*_fake_cx()[:1], big, 0, z, 1, sos, 0.0080, 0, 0)["market"]
    cap = alexg._plan(_fake_cx()[0], e, 0, z, 1, sos, 0.0010, 0, 0)  # ADR 10 pips: the stop at most 1.2 ADR (12 pips) away
    assert abs((cap["entry"] - cap["sl"]) - 0.0012) < 1e-9
    inside = alexg._plan(_fake_cx([1.2514])[0], e, 0, z, 1, sos, 0.0080, 0, 0)  # an elbow of the zone itself is not opposing
    assert inside["struct"] is None


def _downtrend_then_sos():
    # a top, a lower high, two bearish breaks (BOS), down into the zone 1.2500 - 1.2512, then a close above the last LH (the SoS)
    return [1.2560, 1.2575, 1.2590, 1.2605, 1.2620, 1.2610, 1.2598, 1.2585, 1.2580, 1.2588, 1.2595, 1.2600, 1.2592, 1.2582, 1.2570, 1.2560,
            1.2552, 1.2545, 1.2550, 1.2556, 1.2560, 1.2553, 1.2540, 1.2530, 1.2520, 1.2512, 1.2506, 1.2510, 1.2518, 1.2526, 1.2534, 1.2545,
            1.2566, 1.2572, 1.2568, 1.2563]


def test_sos_after_a_swing_at_the_zone_then_the_engulfing():
    c = bars(path(_downtrend_then_sos()), wick=PIP)
    e = alexg.TF("H1", c, PIP)
    z = {"lo": 1.2500, "hi": 1.2512}
    shifts = [(i, lv) for i, k, d, lv in e.s["events"] if k == "SOS" and d == 1]
    assert shifts, e.s["events"]
    i_s, lv = shifts[-1]
    sos = alexg.find_sos(e, len(c) - 1, z, 1, 8 * PIP)
    assert sos and sos["index"] == i_s and sos["level"] == lv == 1.2560 and c[i_s].close > lv + 0.5 * PIP  # a body close above the LTF LH
    assert abs(sos["swing"] - min(x.low for x in c[max(i_s - 24, 0):i_s + 1])) < 1e-12  # L_swing, formed at the zone
    assert alexg.find_sos(e, len(c) - 1, {"lo": 1.2300, "hi": 1.2312}, 1, 8 * PIP) is None  # the swing was not at that zone


# ---------------------------------------------------------------- 4 the 5 agents
def _read(**over):
    z = {"lo": 1.2500, "hi": 1.2512, "tfs": {"W1", "D1"}, "touches": 4, "width": 12.0, "psych": 1.25, "overlap": True}
    items = {k: True for k, _, _ in alexg.CONF}
    r = {"dir": 1, "etf": "H1", "T": T0 + 9 * 3600, "Tx": T0 + 9 * 3600, "S": {"W1": 1, "D1": 1, "H4": 1}, "zone": z, "zones": [z], "near": z,
         "near_pips": 0.0, "broken": False, "prox": 9.6 * PIP, "price": 1.2515, "items": items, "score": 160, "grade": "A+", "setup": "SF_SWING",
         "sync_kind": "full", "w1_block": None, "c": {"sos": {"level": 1.2512, "time": T0, "index": 1, "swing": 1.2502}, "engulf_at": 5},
         "entry": 1.2515, "sl": 1.2495, "tp": 1.2585, "tp1": 1.2545, "rr": 3.5, "risk": 0.0020, "market": True, "news": [], "news_checked": True,
         "risk_pct": 1.0, "spread_ratio": 0.05}
    r.update(over)
    return r


def test_the_five_agents_weights_statuses_and_the_gate():
    sq = alexg.squad(_read(), PIP)
    assert list(sq["agents"]) == ["trend_director", "aoi_architect", "confluence_grader", "trigger_sniper", "risk_guardian"]
    assert [w for *_, w in alexg.ROLES] == [0.25, 0.25, 0.25, 0.15, 0.10]
    assert all(a["status"] == "ok" for a in sq["agents"].values()) and sq["execute"] and sq["consensus"] == 100 and sq["decision"] == "EXECUTE"
    st = lambda name, **o: alexg.squad(_read(**o), PIP)["agents"][name]["status"]  # noqa: E731
    # trend_director
    assert st("trend_director", sync_kind="day") == "ok" and st("trend_director", sync_kind="swing") == "warn"
    assert st("trend_director", sync_kind=None, setup=None) == "wait" and st("trend_director", w1_block="Opposing W1 AOI within 1.5R") == "veto"
    # aoi_architect
    assert st("aoi_architect", zone=None, near_pips=12.0) == "warn" and st("aoi_architect", zone=None, near_pips=40.0) == "wait"
    assert st("aoi_architect", zone=None, broken=True) == "veto"
    # confluence_grader
    assert st("confluence_grader", score=80, grade="B") == "ok" and st("confluence_grader", score=65, grade="WAIT") == "warn"
    assert st("confluence_grader", score=60, grade="WAIT") == "wait"
    # trigger_sniper
    assert st("trigger_sniper", c={"sos": {"level": 1.2512, "time": T0, "index": 1, "swing": 1.2502}, "engulf_at": None}) == "warn"
    assert st("trigger_sniper", c={"sos": None}) == "wait"
    # risk_guardian
    assert st("risk_guardian", rr=2.4) == "veto" and st("risk_guardian", spread_ratio=0.16) == "veto" and st("risk_guardian", news=[T0]) == "veto"
    assert st("risk_guardian", risk_pct=0.5) == "warn" and st("risk_guardian", risk_pct=0.75) == "ok"
    # the gate: sync, S >= 80, SoS + engulfing, R:R >= 2.5, no veto
    assert not alexg.squad(_read(score=79, grade="WAIT"), PIP)["execute"] and alexg.squad(_read(score=80, grade="B"), PIP)["execute"]
    assert not alexg.squad(_read(setup=None, sync_kind=None), PIP)["execute"] and not alexg.squad(_read(rr=2.49), PIP)["execute"]
    assert alexg.squad(_read(risk_pct=0.5), PIP)["execute"]  # the summer regime is a warning, not a veto


def test_the_radar_condition():
    radar = alexg.squad(_read(score=70, grade="WAIT", c={"sos": {"level": 1.2512, "time": T0, "index": 1, "swing": 1.2502}, "engulf_at": None}), PIP)
    assert radar["radar"] and not radar["execute"]  # trend ok, AOI ok, >= 65 %, SoS in, the engulfing awaited
    assert not alexg.squad(_read(score=60, grade="WAIT", c={"sos": {"level": 1.25, "time": T0, "index": 1, "swing": 1.25}, "engulf_at": None}), PIP)["radar"]
    assert not alexg.squad(_read(), PIP)["radar"]  # the engulfing is in: a signal, not a radar


def test_lots_per_10k_from_the_seasonal_risk():
    g = alexg.squad(_read(), PIP, 10.0)["agents"]["risk_guardian"]
    assert g["sl_pips"] == 20.0 and g["position_size_lots"] == 0.5  # $100 / (20 pips x $10)


# ---------------------------------------------------------------- the universe, the sanitizer, the portfolio
def test_the_29_instruments_and_the_two_setups():
    assert len(desk.PAIRS) == 29 and len(PAIRS) == 28
    assert all(v == ["SF_SWING", "SF_DAY"] for v in playbook.STRATEGIES.values()) and len(playbook.STRATEGIES) == 29
    for p in desk.PAIRS:
        cfg = desk.BY_SYMBOL[p]
        assert cfg["pip"] == (0.1 if p.startswith("XAU") else 0.01 if p.endswith("JPY") else 0.0001)
        assert cfg["psych_step"] == (25.0 if p.startswith("XAU") else 0.5 if p.endswith("JPY") else 0.005)
        assert decimals_of(p) == (2 if p.startswith("XAU") else 3 if p.endswith("JPY") else 5)
    wmax = {p: desk.BY_SYMBOL[p]["max_aoi_pips"] for p in desk.PAIRS}
    assert wmax["XAU/USD"] == 65 and wmax["EUR/GBP"] == 50 and wmax["EUR/CHF"] == 50 and wmax["GBP/JPY"] == 65 and wmax["AUD/NZD"] == 55
    import app.smc as pkg
    gone = ("gold", "fiber", "cable", "swissy", "aussie", "loonie", "simple", "engine", "engines", "agents", "chart")
    assert not any((Path(pkg.__file__).parent / f"{m}.py").exists() for m in gone)  # the legacy strategies are deleted


def test_the_sanitizer_never_vetoes_on_missing_volume():
    c = [Candle(T0 + 8 * 3600 + i * 300, 1.0, 1.0004, 0.9996, 1.0, 0.0) for i in range(30)]  # Yahoo forex: no volume
    out, rep = sanitize(c, 300)
    assert len(out) == 30 and rep["missing"] == [] and rep["artifacts"] == []


def test_every_pairs_trade_is_sent_one_live_trade_per_pair():
    now = T0 + 3600
    live = lambda s, d: {"symbol": s, "direction": d, "time": now - 60, "liveUntil": now + 9999}  # noqa: E731
    assert portfolio.check("EUR/USD", {"direction": "BUY"}, [live("EUR/USD", "SELL")], now)["verdict"] == "BLOCK"
    many = [live(p, "BUY") for p in ("USD/JPY", "EUR/JPY", "EUR/USD", "GBP/CHF", "AUD/NZD", "NZD/USD", "GBP/USD")]
    assert portfolio.check("GBP/JPY", {"direction": "BUY"}, many, now)["verdict"] == "PASS"


# ---------------------------------------------------------------- a full read and no look-ahead, on synthetic candles
def _walk(n: int, step: int, t_end: int, start: float, vol: float, seed: int) -> list:
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
    end = T0 + 7 * 86400 - (T0 + 7 * 86400) % 3600
    d1 = _walk(900, 86400, end - end % 86400, 1.2500, 0.0060, 1)
    last = d1[-1].close
    h1 = _walk(3000, 3600, end, last, 0.0012, 2)
    m5 = _walk(2000, 300, end, h1[-1].close, 0.0003, 3)
    return m5, h1, d1


def test_a_team_read_returns_the_5_agent_contract():
    m5, h1, d1 = _synthetic()
    t = desk.read_team("EUR/USD", desk.BY_SYMBOL["EUR/USD"], m5, h1, m5[-1].time + 300, None, d1)
    assert [a["id"] for a in t["agents"]] == ["trend_director", "aoi_architect", "confluence_grader", "trigger_sniper", "risk_guardian"]
    assert all(a["status"] in ("ok", "warn", "wait", "veto") and len(a["badge"]) <= 60 and 0 <= a["score"] <= 100 for a in t["agents"])
    rep = t["pairReport"]
    assert rep["grade"] in ("A+", "A", "B", "WAIT") and len(rep["checklist"]) == 18 and [s["id"] for s in t["strategies"]] == ["SF_SWING", "SF_DAY"]
    assert rep["final_decision"] in ("EXECUTE", "WAIT_FOR_TRIGGER", "WATCH_ONLY", "VETOED")
    ch = t["chart"]
    assert set(ch) >= {"boxes", "segments", "labels", "lines", "windows", "trade"}
    assert all("zone" in b["label"] and "touches" in b["label"] and len(b["label"]) <= 24 for b in ch["boxes"])
    assert sum(not b["detail"] for b in ch["boxes"]) <= 3 and all(o["detail"] for o in ch["labels"])


def test_no_look_ahead():
    m5, h1, d1 = _synthetic()
    cut = h1[-1].time - 40 * 86400
    a, _ = alexg.scan("EURUSD", h1, h1, 0.00012, None, d1, entry_tfs=("H1",))
    b, _ = alexg.scan("EURUSD", [x for x in h1 if x.time + 3600 <= cut], [x for x in h1 if x.time + 3600 <= cut], 0.00012, None,
                      [x for x in d1 if x.time + 86400 <= cut], entry_tfs=("H1",))
    key = lambda s: (s["time"], s["dir"], s["sid"], round(s["entry"], 6), round(s["sl"], 6), round(s["tp"], 6), s["score"])  # noqa: E731
    assert [key(s) for s in a if s["time"] <= cut - 86400] == [key(s) for s in b if s["time"] <= cut - 86400]


# ---------------------------------------------------------------- 5 the 3-stage notifications and the trade manager
def _sig(sid, t, **over):
    s = {"id": sid, "strategy": "SF_SWING", "setupType": "SF_SWING", "name": "S&F-SWING", "direction": "BUY", "time": t,
         "entry": 1.25120, "sl": 1.24780, "tp1": 1.25630, "tp": 1.26175, "part": 0.25, "market": True, "zone": [1.25000, 1.25150], "rr": 3.10,
         "validUntil": t, "expiry": 0, "holdUntil": t + 30 * 86400, "beOff": 0.0, "newsMin": 30, "fridayExit": False, "state": "ACTIVE",
         "pass": True, "checklist": [], "steps": [], "lots": {"1000": 0.02, "10000": 0.29}, "lots10k": 0.29, "riskPct": 1.0, "grade": "A", "gpa": 95,
         "score": 95, "consensus": 96, "slPips": 34.0, "tpPips": 105.5, "bePips": 51.0, "spreadPct": 3.5, "newsClear": True, "newsChecked": True,
         "struct": 1.26225, "zoneInfo": {"tfs": ["W1", "D1"], "overlap": True},
         "checklistGpa": [{"key": "sync", "label": "2+ consecutive TFs in sync", "pts": 20, "ok": True},
                          {"key": "pattern_h4", "label": "H4 chart pattern (H&S / double top-bottom)", "pts": 10, "ok": False}],
         "desk": [{"key": "trend", "role": "Trend & Structure Director", "status": "ok", "badge": "W1+D1+H4 Bullish Snake Sync", "score": 100},
                  {"key": "risk", "role": "Risk, RR & News Guardian", "status": "ok", "badge": "3.1R · Spread 3.5% of SL · Clear news", "score": 100}],
         "draw": {}}
    s.update(over)
    return s


def _clean():
    from app.db import SessionLocal, init_db
    from app.models import Signal, Watermark
    from app.store import set_setting
    init_db()
    with SessionLocal() as db:
        db.query(Signal).filter(Signal.id.like("SMC-%")).delete(synchronize_session=False)
        db.query(Watermark).filter(Watermark.ref == "RADAR").delete(synchronize_session=False)
        set_setting(db, "radar", {"items": []})
        set_setting(db, "history", {"since": 1})  # the test trades are dated in the past: count them
        db.commit()


def test_the_signal_message_follows_the_spec_example():
    t = notify.message(_sig(f"SMC-GBPUSD-SF_SWING-{T0}-B", T0), "GBP/USD", 5)
    lines = t.split("\n")
    assert lines[0] == "🎯 <b>FXAlexG SET &amp; FORGET — GBP/USD LONG (GRADE A · 95%)</b>"
    assert lines[2] == "📈 <b>Action:</b> BUY MARKET @ <code>1.25120</code>"
    assert lines[3] == "🛑 <b>Stop Loss:</b> <code>1.24780</code> <i>(-34.0 pips · below D1+W1 AOI)</i>"
    assert lines[4] == "🛡️ <b>Break-Even Trigger (+1.5R):</b> <code>1.25630</code> <i>(+51.0 pips)</i>"
    assert lines[5] == "💰 <b>Take Profit (+3.1R):</b> <code>1.26175</code> <i>(+105.5 pips · pre-structure)</i>"
    assert lines[6] == "⚖️ <b>Risk / Sizing:</b> <code>1%</code> (<code>0.29 Lots</code> per $10k) · <b>R:R:</b> <code>1 : 3.10</code>"
    assert "✅ 2+ consecutive TFs in sync (<code>+20%</code>)" in lines and not any("H4 chart pattern" in x for x in lines)  # the hits only
    assert "• <b>Trend Director:</b> <code>OK</code> W1+D1+H4 Bullish Snake Sync" in lines
    assert lines[-1].startswith("<i>Research software — does not place orders.")
    lim = notify.message(_sig("x", T0, market=False), "GBP/USD", 5).split("\n")[2]
    assert lim == "📈 <b>Action:</b> BUY LIMIT @ <code>1.25120</code> <i>(Entry Zone: <code>1.25000</code> – <code>1.25150</code>)</i>"


def _radar(T):
    return {"id": f"RADAR-GBPJPY-B-19240-{T}", "direction": "BUY", "tf": "W1+D1", "touches": 4, "low": 192.400, "high": 192.850, "psych": 192.5,
            "etf": "H1", "gpa": 70, "score": 70, "grade": "WAIT", "time": T, "setup": "SF_SWING", "sosLevel": 192.780, "trend": "W1+D1"}


def test_the_radar_message_follows_the_spec_example():
    t = notify.radar_message("GBP/JPY", _radar(T0), 3).split("\n")
    assert t[0] == "📡 <b>SET &amp; FORGET RADAR — GBP/JPY (BUY WATCH)</b>"
    assert t[1] == "• <b>Trend Sync:</b> W1 + D1 Bullish"
    assert t[2] == "• <b>Location:</b> Inside D1+W1 AOI (<code>192.400 – 192.850</code>) + Psych <code>192.500</code>"
    assert t[3] == ("• <b>Status:</b> H1 Shift of Structure (SoS) confirmed at <code>192.780</code> — Waiting for Retest &amp; "
                    "Bullish Engulfing trigger.")


def test_radar_once_per_aoi_visit_then_the_signal_once(monkeypatch):
    _clean()
    T = T0 + 9 * 3600
    state = {"sig": [], "radar": _radar(T)}

    async def fake_team(pair, fresh=False):
        if pair == "GBP/JPY":
            return {"success": True, "signals": [], "radar": state["radar"], "decision": "WAIT_FOR_TRIGGER"}
        if pair == "GBP/USD":
            return {"success": True, "signals": state["sig"], "radar": None, "decision": "EXECUTE"}
        return {"success": True, "signals": [], "radar": None, "decision": "WATCH_ONLY"}
    sent = []

    async def fake_broadcast(pair, text, title, body, tag, signal=None):
        sent.append((pair, text, title))
        return {"telegram": 1, "push": 1}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "broadcast", fake_broadcast)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    monkeypatch.setattr(notify.time, "time", lambda: T + 60)
    r1 = asyncio.run(notify.tick())
    asyncio.run(notify.tick())  # the same AOI visit: no second radar
    assert [p for p, *_ in sent] == ["GBP/JPY"] and sent[0][1].startswith("📡") and "radar BUY → telegram 1 · push 1" in r1["GBP/JPY"]
    state["radar"] = _radar(T + 3600 * 30)  # a new SoS wave (a new visit): a new radar
    asyncio.run(notify.tick())
    assert [p for p, *_ in sent] == ["GBP/JPY", "GBP/JPY"]
    state["sig"] = [_sig(f"SMC-GBPUSD-SF_SWING-{T}-B", T)]
    res = asyncio.run(notify.tick())
    asyncio.run(notify.tick())
    assert [p for p, *_ in sent].count("GBP/USD") == 1 and "SF_SWING grade A → telegram 1 · push 1" in res["GBP/USD"]
    from app.api import smc as smc_api
    feed = smc_api.smc_signals(None)
    assert [x["id"] for x in feed["radar"]] == [_radar(T + 3600 * 30)["id"], _radar(T)["id"]]  # the app's live feed: both radars
    assert any(x["id"] == state["sig"][0]["id"] for x in feed["signals"])


def test_the_manager_moves_the_stop_to_entry_at_1_5r_and_banks_25_percent(monkeypatch):
    _clean()
    T = T0 + 9 * 3600 - (T0 + 9 * 3600) % 300
    s = _sig(f"SMC-GBPUSD-SF_SWING-{T + 300}-B", T + 300)
    assert notify._claim("GBP/USD", s)

    def c(i, o, h, lo, cl):
        return Candle(T + i * 300, o, h, lo, cl, 0)
    m5 = [c(0, 1.2510, 1.2513, 1.2508, 1.2512), c(1, 1.2512, 1.2540, 1.2510, 1.2538), c(2, 1.2538, 1.2566, 1.2535, 1.2560)]
    desk.LIVE["GBP/USD"] = (m5, 0.0, None)
    sent = []

    async def send(pair, text, title, body, tag):
        sent.append((title, text, body))
    one = asyncio.run(manager.manage_all(send))
    assert one[s["id"]] == ["TP1"] and len(sent) == 1  # a market order: no FILLED line; +1.5R reached
    assert "BREAKEVEN (+1.5R)" in sent[0][0] and "SL moved to Break-Even <code>1.25120</code> · 25% banked" in sent[0][1] and "+0.375R" in sent[0][2]
    m5.append(c(3, 1.2560, 1.2562, 1.2509, 1.2511))  # back down to the entry
    two = asyncio.run(manager.manage_all(send))
    assert two[s["id"]] == ["BE_STOP"] and "BE_CLOSED" in sent[-1][0] and "(+0.37R)" in sent[-1][1]
    assert asyncio.run(manager.manage_all(send)) == {} and len(sent) == 2
    res = manager.results()
    assert res["all"]["trades"] == 1 and abs(res["all"]["totalR"] - 0.375) < 0.01  # 25 % banked at +1.5R, the rest at 0


def test_the_manager_tells_a_limit_fill_then_the_target(monkeypatch):
    _clean()
    T = T0 + 9 * 3600 - (T0 + 9 * 3600) % 300
    s = _sig(f"SMC-EURUSD-SF_DAY-{T + 300}-B", T + 300, market=False, expiry=50, entry=1.1000, sl=1.0980, tp1=1.1030, tp=1.1070, rr=3.5)
    assert notify._claim("EUR/USD", s)

    def c(i, o, h, lo, cl):
        return Candle(T + i * 300, o, h, lo, cl, 0)
    m5 = [c(0, 1.1005, 1.1006, 1.1003, 1.1005), c(1, 1.1005, 1.1006, 1.0999, 1.1002), c(2, 1.1002, 1.1072, 1.1001, 1.1068)]
    desk.LIVE["EUR/USD"] = (m5, 0.0, None)
    sent = []

    async def send(pair, text, title, body, tag):
        sent.append(title)
    out = asyncio.run(manager.manage_all(send))
    assert out[s["id"]] == ["FILLED", "TP"] and sent[0].startswith("🟢 FILLED") and sent[1].startswith("🏆 TP_HIT")
    res = manager.results()
    assert res["all"]["wins"] == 1 and abs(res["all"]["totalR"] - 3.5) < 1e-6


def test_the_history_counts_every_trade_from_its_start_with_the_win_rate():
    _clean()
    from app.db import SessionLocal
    from app.store import set_setting
    T = T0 + 9 * 3600 - (T0 + 9 * 3600) % 300
    old = _sig(f"SMC-EURUSD-SF_SWING-{T - 86400}-B", T - 86400)
    win = _sig(f"SMC-GBPUSD-SF_SWING-{T}-B", T)
    loss = _sig(f"SMC-USDJPY-SF_DAY-{T + 300}-S", T + 300, direction="SELL", entry=150.0, sl=150.5, tp=148.25, tp1=149.25)
    run_ = _sig(f"SMC-AUDUSD-SF_SWING-{T + 600}-B", T + 600)
    for p, s in (("EUR/USD", old), ("GBP/USD", win), ("USD/JPY", loss), ("AUD/USD", run_)):
        assert notify._claim(p, s)
    with SessionLocal() as db:
        set_setting(db, "history", {"since": T})  # the history starts after the first trade: that one is never counted
        from app.models import Signal
        for sid, out, r in ((win["id"], "WIN", 3.1), (loss["id"], "LOSS", -1.02)):
            row = db.get(Signal, sid)
            row.state, row.outcome, row.r_multiple, row.exit_time = "CLOSED", out, r, T + 3600
        db.get(Signal, run_["id"]).state = "OPEN"
        db.commit()
    h = manager.history()
    assert h["since"] == T and [x["symbol"] for x in h["items"]] == ["AUD/USD", "USD/JPY", "GBP/USD"]  # newest first, from the start only
    assert h["summary"] == {"given": 3, "running": 1, "closed": 2, "wins": 1, "breakeven": 0, "losses": 1, "notFilled": 0, "winRate": 50,
                            "totalR": 2.08}
    assert [c["winRate"] for c in h["curve"]] == [100, 50] or [c["winRate"] for c in h["curve"]] == [0, 50]
    assert manager.results()["all"]["trades"] == 2  # the dashboard's cards count from the same start
    from app.api import smc as smc_api
    assert smc_api.smc_history(None)["summary"]["winRate"] == 50


def test_the_history_starts_the_first_time_it_is_asked():
    from app.db import SessionLocal
    from app.store import set_setting
    import time as _t
    with SessionLocal() as db:
        set_setting(db, "history", {"since": 0})
        db.commit()
        t0 = _t.time()
        a = manager.history_since(db)
        assert abs(a - t0) < 5 and manager.history_since(db) == a  # set once, then the same

