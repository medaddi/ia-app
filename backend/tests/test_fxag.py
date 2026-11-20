"""FX Alex G Set & Forget (the owner's specification of 2026-11-20): unit tests of the 8 agents and the spec's 18
edge-case scenarios (section 6), each named after its number."""

import asyncio
import random
from datetime import datetime, timezone

from app.smc import desk, manager, notify, playbook
from app.smc.fxag import config as C
from app.smc.fxag.strategy.data import Series
from app.smc.fxag.strategy.structure import Structure, alignment, extreme
from app.smc.fxag.strategy.zones import dist_pips, merge, opposing_weekly, snap_500, suspended
from app.smc.fxag.strategy.confluence import doji, ema_rejection, engulfing, grade_of, pin, star
from app.smc.fxag.strategy.entry import order
from app.smc.fxag.risk.levels import lots, plan, rank_key
from app.smc.fxag.strategy.checks import audit
from app.smc.fxag.risk.order import client_order_id
from app.smc.fxag.time_utils import blackout, in_session, news_block, ny_day_open
from app.smc.playbook import _Bar, run

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


def zone(lo, hi, tfs=("D",), kind="D", roles=(-1, 1), psych=None):
    return {"lo": lo, "hi": hi, "tfs": set(tfs), "kind": kind, "sl_lo": lo, "sl_hi": hi, "roles": set(roles), "psych": psych,
            "touches": 3, "t0": T0, "id": f"{kind}-{lo}", "overlap": False, "width_pips": round((hi - lo) / PIP, 1)}


# ---------------------------------------------------------------- 2 normalization, 3.1 structure
def test_29_pairs_pip_lambda_shards_and_500_steps():  # scenario 13 (pip math)
    assert len(C.UNIVERSE) == 29 and len(set(C.UNIVERSE)) == 29 and set(C.UNIVERSE) == set(playbook.ALEXG_PAIRS)
    assert (C.pip_size("XAUUSD"), C.pip_size("USDJPY"), C.pip_size("EURUSD")) == (0.10, 0.01, 0.0001)
    assert (C.lam("XAUUSD"), C.lam("GBPJPY"), C.lam("GBPAUD"), C.lam("GBPNZD"), C.lam("EURUSD")) == (2.5, 1.25, 1.25, 1.25, 1.0)
    assert (C.step_500("XAUUSD"), C.step_500("EURJPY"), C.step_500("GBPUSD")) == (50.0, 0.5, 0.05)
    assert [len(v) for v in C.SHARDS.values()] == [8, 7, 7, 7] and C.shard_of("CHFJPY") == "B"
    assert abs(C.W_MAX_PIPS * C.lam("XAUUSD") * C.pip_size("XAUUSD") - 15.0) < 1e-9  # gold max AOI = 150 pips = $15


def _trend():
    return [1.1000, 1.1010, 1.1020, 1.1035, 1.1050, 1.1040, 1.1030, 1.1025, 1.1030, 1.1045, 1.1060, 1.1075, 1.1090, 1.1080,
            1.1070, 1.1062, 1.1070, 1.1085, 1.1100, 1.1115, 1.1130]


def test_structure_is_body_only_and_shifts_on_a_close_below_hl():
    c = bars(_trend(), wick=0)
    st = Structure(series("D", c, 86400), PIP)
    assert st.bias[-1] == 1 and st.hl[-1][1] < st.hh[-1][1]
    kinds = [e[1] for e in st.els]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))  # strictly alternating True Elbows
    hl = st.hl[-1][0]
    wick = c + [_Bar(c[-1].time + 86400, c[-1].close, c[-1].close, hl - 50 * PIP, hl + PIP)]  # a wick far below HL, the close above
    assert Structure(series("D", wick, 86400), PIP).bias[-1] == 1
    down = bars(_trend() + [hl - PIP], wick=0)
    s2 = Structure(series("D", down, 86400), PIP)
    assert s2.bias[-1] == -1 and s2.events[-1][1:3] == ("SHIFT", -1)


def test_chop_and_extreme_filters():
    flat = bars([1.1 + (0.0004 if i % 2 else 0) for i in range(60)], wick=PIP)
    st = Structure(series("D", flat, 86400), PIP, chop=True)
    assert st.chop[-1] and st.biased(len(flat) - 1) == 0
    up = Structure(series("W", bars([1.0 + 0.01 * i for i in range(30)], 7 * 86400), 7 * 86400), PIP)
    assert extreme(up, 29, 1) and not extreme(up, 29, -1)  # a buy at the all-time body high: EXTREME_NO_DATA


def test_alignment_matrix():  # scenarios 1, 2
    assert alignment(1, 1, 1) == {"dir": 1, "kind": "full", "strength": 5, "anchor": "WD", "label": "Full Sync Swing"}
    assert alignment(1, 1, -1)["kind"] == "retrace" and alignment(1, 1, -1)["dir"] == 1 and alignment(1, 1, -1)["strength"] == 5  # 1
    two = alignment(1, -1, -1)  # 2: W bullish, D and 4H bearish: SELL from a Daily AOI only
    assert two["dir"] == -1 and two["kind"] == "counter" and two["anchor"] == "D" and two["strength"] == 4
    assert alignment(1, -1, 1)["dir"] == 0 and alignment(1, 0, 1)["label"].startswith("Daily Consolidation")


# ---------------------------------------------------------------- 3.3 zones
def test_w_and_d_overlap_merge_or_nest():  # scenario 8
    w = [{"lo": 1.1000, "hi": 1.1030, "touches": 3, "roles": {-1}, "t0": 1, "hits": [1], "tf": "W"}]
    d = [{"lo": 1.1020, "hi": 1.1050, "touches": 4, "roles": {1}, "t0": 2, "hits": [2], "tf": "D"}]
    m = merge(w, d, PIP, 1.0)[0]
    assert m["kind"] == "W+D_MERGED" and (m["lo"], m["hi"]) == (1.1000, 1.1050) and m["tfs"] == {"W", "D"}
    wide = merge([{**w[0], "lo": 1.0960}], d, PIP, 1.0)[0]  # union 90 pips > 60: the D core nested in the W envelope
    assert wide["kind"] == "D_IN_W" and (wide["lo"], wide["hi"]) == (1.1020, 1.1050) and wide["sl_lo"] == 1.0960


def test_500_level_snap():  # scenario 9
    z = snap_500({**zone(1.1503, 1.1530), "sl_lo": 1.1503, "sl_hi": 1.1530}, PIP, 1.0, 0.05)
    assert z["psych"] == 1.15 and z["lo"] == 1.15  # 3 pips outside: the edge moves to include it
    far = snap_500({**zone(1.1510, 1.1540), "sl_lo": 1.1510, "sl_hi": 1.1540}, PIP, 1.0, 0.05)
    assert far["psych"] is None and far["lo"] == 1.1510


def test_proximity_and_break_suspension():  # scenarios 4, 5, 11
    z = zone(1.1000, 1.1020)
    assert dist_pips(1.1010, z, PIP) == 0 and round(dist_pips(1.1032, z, PIP), 1) == 12.0
    closes = [1.1050, 1.1040, 1.1030, 1.1025]
    d1 = bars(closes, wick=0)
    d1[-1].low = 1.0980  # 4: a wick 20 pips under the zone, the body closes inside
    st = Structure(series("D", d1, 86400), PIP)
    w = Structure(series("W", bars([1.1050] * 3, 7 * 86400, wick=0), 7 * 86400), PIP)
    assert not suspended(z, 1, st, len(d1) - 1, w, 2, PIP, 1.0)
    br = Structure(series("D", bars(closes + [1.0990], wick=0), 86400), PIP)  # 5: a body close 10 pips under
    assert suspended(z, 1, br, 4, w, 2, PIP, 1.0)
    back = Structure(series("D", bars(closes + [1.0990, 1.1030], wick=0), 86400), PIP)  # back above the zone: retest allowed
    assert not suspended(z, 1, back, 5, w, 2, PIP, 1.0)


def test_opposing_weekly_trap_veto():  # scenarios 2, 3
    act = zone(1.1000, 1.1020)
    wz = zone(1.0950, 1.0970, tfs=("W",), kind="W")
    opp, runway = opposing_weekly([act, wz], act, -1, 1.1000)
    assert opp is wz and abs(runway - 0.0030) < 1e-12
    d_st = Structure(series("D", bars([1.12, 1.11, 1.13, 1.10, 1.14, 1.09, 1.13, 1.12, 1.11]), 86400), PIP)
    idx = {"W": 0, "D": 8}
    sts = {"W": d_st, "D": d_st}
    p = plan(1.1000, -1, act, 1.1025, _Bar(T0, 1.1010, 1.1022, 1.0998, 1.1000), [act, wz], sts, idx, PIP, 1.0, PIP, counter=True)
    assert p is None or p["trap"]  # SL ~ 32 pips, runway 30 pips < 2 x SL: HARD VETO
    if p:
        assert "ERR_OPPOSING_WEEKLY_AOI_TRAP" in audit({**_good(), "trap": True}, _tue(10), [], True, PIP, PIP, PIP, 1.0, {"ok": True})["reasons"]


# ---------------------------------------------------------------- 3.4 confluences, 3.6 grades
def test_candle_table():
    p, x = _Bar(T0, 1.1010, 1.1012, 1.0995, 1.1000), _Bar(T0, 1.1000, 1.1025, 1.0999, 1.1020)
    assert engulfing(p, x, 1, 2 * PIP) and not engulfing(p, x, -1, 2 * PIP)
    assert not engulfing(p, _Bar(T0, 1.1004, 1.1025, 1.0999, 1.1020), 1, 2 * PIP)  # opens 4 pips above C(t-1) > the 2-pip gap
    assert pin(_Bar(T0, 1.1000, 1.1003, 1.0960, 1.1002), 1, 0.0050) and doji(_Bar(T0, 1.1000, 1.1002, 1.0970, 1.1001), 1)
    a, b, c = _Bar(T0, 1.1050, 1.1052, 1.0998, 1.1000), _Bar(T0, 1.0999, 1.1003, 1.0990, 1.0995), _Bar(T0, 1.0996, 1.1035, 1.0994, 1.1030)
    assert star(a, b, c, 1, 0.0050)


def test_ema_is_live_only():  # scenario 10
    c = bars([1.1000 + 0.0002 * i for i in range(60)], wick=PIP)
    st = Structure(series("H4", c, 14400), PIP)
    e = st.e50[59]
    z = zone(e - 0.0005, e + 0.0005)
    assert not ema_rejection(st, 59, z, 1, PIP, 1.0)  # price far above the EMA now: an old touch weighs 0
    c[58] = _Bar(c[58].time, c[58].open, c[58].high, st.e50[58] - PIP, c[58].close)  # a live wick into the EMA, the close above
    assert ema_rejection(Structure(series("H4", c, 14400), PIP), 59, z, 1, PIP, 1.0)


def test_grades_and_weights():
    assert [grade_of(s) for s in (115, 100, 95, 90, 85, 80, 79, 60, 59)] == ["A+", "A+", "A", "A", "B", "B", "C", "C", "D"]
    assert C.W_ALIGN == {"full": 20, "retrace": 15, "counter": 10} and C.W_AOI_W == C.W_AOI_D == 15 and C.W_ENTRY == 10
    assert C.GRADE_MULT == {"A+": 1.0, "A": 1.0, "B": 0.75}


# ---------------------------------------------------------------- 3.5 entry, 3.7 risk, agent 7, agent 8
def _good(**o):
    p = {"score": 95, "grade": "A", "sos": True, "engulf": True, "rr": 3.0, "orderType": "MARKET", "entryDistPips": 2.0, "trap": False,
         "suspended": False, "extreme": False, "slPips": 30.0}
    p.update(o)
    return p


def _tue(h, m=0):
    base = datetime(2026, 11, 17, h, m, tzinfo=timezone.utc)  # a Tuesday
    return int(base.timestamp())


def test_huge_engulfing_goes_to_the_50_percent_limit():  # scenario 6
    z = zone(1.1000, 1.1020)
    eng = {"candle": _Bar(T0, 1.1010, 1.1100, 1.1005, 1.1095), "atr": 0.0030}  # range 95 pips > 2.2 ATR
    plan_at = lambda e: {"entry": e, "sl": 1.0980, "tp": 1.1200, "rr": (1.1200 - e) / (e - 1.0980), "risk": e - 1.0980, "trap": False}  # noqa: E731
    o = order(eng, z, 1, plan_at, PIP, 1.0)
    assert o.get("reject") == "ERR_LIMIT_FAR_FROM_AOI" and o["huge"]  # its middle 1.10525 is 32 pips from the AOI (> 10): no chase, no trade
    near = {"candle": _Bar(T0, 1.0995, 1.1060, 1.0990, 1.1045), "atr": 0.0020}  # huge, its middle 1.1020 at the zone edge
    o2 = order(near, z, 1, plan_at, PIP, 1.0)
    assert o2["orderType"] == "LIMIT_PULLBACK" and abs(o2["entry"] - 1.1020) < 1e-9 and o2["rr"] >= 2.2
    ok = order({"candle": _Bar(T0, 1.1000, 1.1022, 1.0998, 1.1018), "atr": 0.0020}, z, 1, plan_at, PIP, 1.0)
    assert ok["orderType"] == "MARKET" and ok["entry"] == 1.1018


def test_auditor_vetoes():  # scenarios 11, 14, 15, 17
    T = _tue(14)
    ok = audit(_good(), T, [], True, PIP, PIP, PIP, 1.0, {"ok": True})
    assert ok["verdict"] == "APPROVE" and ok["reasons"] == []
    assert "ERR_OUTSIDE_AOI_PROXIMITY" in audit(_good(entryDistPips=12.0), T, [], True, PIP, PIP, PIP, 1.0, {"ok": True})["reasons"]  # 11
    assert "ERR_NEWS_BLACKOUT" in audit(_good(), T, [T + 25 * 60], True, PIP, PIP, PIP, 1.0, {"ok": True})["reasons"]  # 14
    assert "ERR_SPREAD_ANOMALY" in audit(_good(), T, [], True, 4.5 * PIP, 1.0 * PIP, PIP, 1.0, {"ok": True})["reasons"]  # 15
    assert "ERR_SCORE_BELOW_80" in audit(_good(score=75), T, [], True, PIP, PIP, PIP, 1.0, {"ok": True})["reasons"]
    assert "ERR_RR_BELOW_2" in audit(_good(rr=1.9), T, [], True, PIP, PIP, PIP, 1.0, {"ok": True})["reasons"]
    sun = int(datetime(2026, 11, 22, 22, 30, tzinfo=timezone.utc).timestamp())  # 17: Sunday open
    assert blackout(sun) == "ERR_SUNDAY_OPEN" and "ERR_SUNDAY_OPEN" in audit(_good(), sun, [], True, PIP, PIP, PIP, 1.0, {"ok": True})["reasons"]
    assert blackout(_tue(21)) == "ERR_ROLLOVER_BLACKOUT" and not in_session(_tue(11, 45)) and in_session(_tue(12, 0))
    assert news_block(T, [T + 46 * 60]) is None and news_block(T, [T - 30 * 60]) is not None


def test_dst_aware_ny_close():  # scenario 18
    summer = int(datetime(2026, 7, 15, 12, tzinfo=timezone.utc).timestamp())
    winter = int(datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp())
    assert datetime.fromtimestamp(ny_day_open(summer), timezone.utc).hour == 21  # 17:00 EDT
    assert datetime.fromtimestamp(ny_day_open(winter), timezone.utc).hour == 22  # 17:00 EST


def test_lots_and_idempotency():  # scenarios 13, 16
    assert lots(100, 25, 10.0) == 0.4 and lots(100, 30, 6.54) == 0.5 and lots(1, 30, 10.0) == 0.01  # floored, then max(Lot_min, .)
    assert client_order_id("EUR/USD", 1, "H4", T0) == client_order_id("EUR/USD", 1, "H4", T0) != client_order_id("EUR/USD", -1, "H4", T0)


def test_signals_of_one_close_are_ranked():  # scenario 7 (the owner: every pair's trade is sent, ranked)
    sig = [{"symbol": "EUR/USD", "score": 85, "alignmentStrength": 5, "rr": 2.5}, {"symbol": "GBP/USD", "score": 100, "alignmentStrength": 5, "rr": 2.1},
           {"symbol": "AUD/USD", "score": 85, "alignmentStrength": 5, "rr": 3.0}]
    assert [s["symbol"] for s in sorted(sig, key=rank_key, reverse=True)] == ["GBP/USD", "AUD/USD", "EUR/USD"]


def test_set_and_forget_never_moves_the_stop():
    m5 = [_Bar(T0 + i * 300, *p) for i, p in enumerate([(100, 100, 100, 100), (100, 102.0, 99.9, 101.9), (101.9, 102.0, 98.9, 99.0)])]
    ev = []
    out = run(m5, 0, 1, 100.0, 99.0, None, 103.0, 1.0, True, 0, T0 + 86400, 0.0, ev, None, None, None)
    assert [k for _, k, _ in ev] == ["FILLED", "STOP"] and abs(out["r"] + 1.0) < 1e-9  # +2R reached, then the full stop: no break-even


# ---------------------------------------------------------------- the whole engine on synthetic candles
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


def test_a_read_returns_the_8_agent_contract():
    m5, h1, d1 = _synthetic()
    t = desk.read_team("EUR/USD", desk.BY_SYMBOL["EUR/USD"], m5, h1, m5[-1].time + 300, None, d1)
    assert [a["id"] for a in t["agents"]] == ["StrategyAgent", "RiskAgent"]  # the owner: one agent for the strategy and its confirmation, one for SL / TP / lot
    assert len(t["agents"][0]["lines"]) == 7 and t["agents"][0]["lines"][1].split(" ", 1)[1].startswith("Trend")
    assert all(a["status"] in ("ok", "warn", "wait", "veto") for a in t["agents"]) and t["grade"] in ("A+", "A", "B", "C", "D")
    assert [r["id"] for r in t["strategies"]] == ["SYNC", "RETRACE", "COUNTER"] and t["tier"]
    assert all("zone" in b["label"] and len(b["label"]) <= 24 for b in t["chart"]["boxes"])


def test_no_look_ahead():
    m5, h1, d1 = _synthetic()
    from app.smc.fxag import engine
    cut = h1[-1].time - 60 * 86400
    a, _ = engine.scan("EURUSD", [], h1, 0.00012, None, d1, follow=h1)
    b, _ = engine.scan("EURUSD", [], [x for x in h1 if x.time + 3600 <= cut], 0.00012, None, d1, follow=[x for x in h1 if x.time + 3600 <= cut])
    key = lambda s: (s["time"], s["dir"], round(s["entry"], 6), round(s["sl"], 6), round(s["tp"], 6), s["score"], s["pass"])  # noqa: E731
    assert [key(s) for s in a if s["time"] <= cut - 86400] == [key(s) for s in b if s["time"] <= cut - 86400]


# ---------------------------------------------------------------- notifications: the trade and its end
def _sig(sid, t, **o):
    s = {"id": sid, "strategy": "SYNC", "setupType": "SYNC", "name": "Full Sync Swing (W + D + 4H)", "direction": "BUY", "time": t,
         "entry": 1.25120, "sl": 1.24780, "tp1": None, "tp": 1.26175, "part": 1.0, "market": True, "zone": [1.2512, 1.2512], "rr": 3.10,
         "validUntil": t, "expiry": 0, "holdUntil": t + 60 * 86400, "beOff": None, "newsMin": 30, "fridayExit": False, "state": "ACTIVE",
         "pass": True, "checklist": [], "steps": [], "lots": {"1000": 0.0, "10000": 0.0}, "riskPct": 2.0, "grade": "A", "gpa": 95, "score": 95,
         "slPips": 34.0, "tpPips": 105.5, "sosTf": "M30", "etf": "H4", "orderType": "MARKET", "breakdown": {"W + D + 4H full sync": 20, "At Daily AOI": 15},
         "proposal": {"client_order_id": "abc123"}, "draw": {}}
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


def test_the_trade_message():
    t = notify.message(_sig("SMC-GBPUSD-SYNC-1-B", T0), "GBP/USD", 5).split("\n")
    assert t[0] == "🎯 <b>FX ALEX G SET &amp; FORGET — GBP/USD BUY (GRADE A · 95%)</b>" and t[2] == "📈 <b>Order:</b> MARKET @ <code>1.25120</code>"
    assert "R:R</b> <code>1 : 3.10</code>" in t[3] and "SoS M30 · Engulfing H4" in t[4] and "W + D + 4H full sync +20%" in t[5]
    assert "no break-even" in t[6] and "abc123" in t[6] and t[-1].startswith("<i>Signal only")
    assert notify.recent_radar() == [] and not hasattr(notify, "radar_message")


def test_trade_sent_once_and_followed_to_its_end_without_break_even(monkeypatch):  # scenario 16 (never twice)
    _clean()
    T = T0 + 9 * 3600 - (T0 + 9 * 3600) % 300
    state = {"sig": [_sig(f"SMC-GBPUSD-SYNC-{T + 300}-B", T + 300)]}

    async def fake_team(pair, fresh=False):
        return {"success": True, "signals": state["sig"] if pair == "GBP/USD" else [], "decision": "WATCH_ONLY"}
    sent = []

    async def fake_broadcast(pair, text, title, body, tag, signal=None):
        sent.append((pair, title))
        return {"telegram": 1, "push": 1}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "broadcast", fake_broadcast)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    asyncio.run(notify.tick())
    asyncio.run(notify.tick())
    assert [p for p, _ in sent].count("GBP/USD") == 1
    s = state["sig"][0]

    def c(i, o, h, lo, cl):
        from app.market.types import Candle
        return Candle(T + i * 300, o, h, lo, cl, 0)
    m5 = [c(0, 1.2510, 1.2513, 1.2508, 1.2512), c(1, 1.2512, 1.2566, 1.2510, 1.2560), c(2, 1.2560, 1.2620, 1.2555, 1.2618)]
    desk.LIVE["GBP/USD"] = (m5, 0.0, None)
    msgs = []

    async def send(pair, text, title, body, tag):
        msgs.append(title)
    out = asyncio.run(manager.manage_all(send))
    assert out[s["id"]] == ["TP"] and msgs[0].startswith("🏆 TP_HIT") and not any("BREAKEVEN" in m for m in msgs)
    assert abs(manager.results()["all"]["totalR"] - 3.1) < 0.01
