"""FXAlexG Set & Forget (the 2026-11-11 spec): No-Gap candles, line-chart structure, AOIs, GPA, the 5 agents, the trade
follower, the sanitizer, the portfolio check, the 3-stage notifications."""

import asyncio
import csv
from pathlib import Path

from app.market.pairs import PAIRS, decimals_of
from app.market.sanitize import sanitize
from app.market.types import Candle
from app.smc import alexg, desk, manager, notify, playbook
from app.smc.playbook import _Bar, run
from app.smc.skill import portfolio

T0 = 1_790_000_000 - 1_790_000_000 % 86400
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


# ---------------------------------------------------------------- 3.1 - 3.3
def test_no_gap_candles():
    c = [_Bar(T0, 1.00, 1.02, 0.99, 1.01), _Bar(T0 + 60, 1.05, 1.06, 1.04, 1.055)]  # a gap up from 1.01 to 1.05
    g = alexg.nogap(c)
    assert (g[0].open, g[0].close) == (1.00, 1.01)
    assert g[1].open == 1.01 and g[1].low == 1.01 and g[1].high == 1.06 and g[1].close == 1.055  # O' = C(t-1), L' = min(L, O', C)


def test_ema_tap_and_the_candle_patterns():
    p, x = _Bar(T0, 1.1000, 1.1005, 1.0948, 1.0950), _Bar(T0 + 1, 1.0950, 1.1012, 1.0948, 1.1010)
    assert alexg.engulf(p, x, 1) and not alexg.engulf(p, x, -1)  # body >= 80 % of the previous one and >= 50 % of its range
    weak = _Bar(T0 + 1, 1.0950, 1.1060, 1.0900, 1.1001)  # closes above, but its body is under 50 % of its range
    assert not alexg.engulf(p, weak, 1)
    pin = _Bar(T0, 1.1000, 1.1003, 1.0960, 1.1001)  # body 2.5 %, lower wick 93 %
    assert alexg.doji(pin, 1) and not alexg.doji(pin, -1) and not alexg.doji(pin, 1, {"lo": 1.1002, "hi": 1.1010})  # must close above Z_low
    e = alexg.TF("H1", [_Bar(T0 + i * 3600, 1.0, 1.001, 0.999, 1.0) for i in range(60)])
    assert e.e50[-1] is not None and e.tap(59, 1) is False  # close equal to the EMA: not respected


def test_line_chart_structure_uses_closes_and_hh_is_in_front_of_hl():
    closes = [1.00, 1.02, 1.04, 1.06, 1.03, 1.01, 1.00, 1.02, 1.05, 1.08, 1.10, 1.07, 1.05, 1.08, 1.09, 1.04, 0.99, 0.97]
    s = alexg.structure(closes, 2)
    ev = [(k, d) for _, k, d, _ in s["events"]]
    i_bull = closes.index(1.08)  # the close above the 1.06 pivot
    assert s["trend"][i_bull] == 1 and ("BOS", 1) in ev
    hl, hh = s["hl"][i_bull], s["hh"][i_bull]
    assert hl[1] < hh[1] and hl[0] == 1.00  # HL = the lowest close between the break origin and the new HH, strictly behind it
    assert ev[-1] == ("SOS", -1) and s["trend"][-1] == -1  # a close strictly below HL turns it bearish
    eq = closes[:i_bull + 3] + [hl[0]]  # a close EQUAL to HL is not a shift
    assert alexg.structure(eq, 2)["trend"][-1] == 1


# ---------------------------------------------------------------- 3.4 AOIs
def _ranging_d1():
    seq, t = [], T0 - 400 * 86400
    for _ in range(40):  # a floor near 1.2500 hit again and again, each time bouncing ~80 pips
        for o, h, lo, c in ((1.2580, 1.2590, 1.2540, 1.2545), (1.2545, 1.2550, 1.2498, 1.2505), (1.2505, 1.2560, 1.2500, 1.2555),
                            (1.2555, 1.2600, 1.2550, 1.2590), (1.2590, 1.2610, 1.2575, 1.2580)):
            seq.append(_Bar(t, o, h, lo, c))
            t += 86400
    return seq


def test_aoi_touches_reversals_and_psych():
    d1 = _ranging_d1()
    tf = alexg.TF("D1", d1)
    i = len(d1) - 1
    atr_d = tf.at[i]
    zs = alexg.build_zones(tf, i, atr_d, 0.0001, 0.005)
    z = next(q for q in zs if q["lo"] <= 1.2505 <= q["hi"] + 0.0005)
    assert z["touches"] >= 3 and (z["hi"] - z["lo"]) <= 0.35 * atr_d + 1e-12  # >= 3 touches, <= 0.35 ATR thick
    assert z["psych"] == 1.25  # 1.2500 within 10 pips
    assert all(role == 1 for _, role in z["roles"])  # support touches (from above, bounced up)
    n, _ = alexg.touches(d1, 0, i, 1.2700, 1.2710, 0.75 * atr_d)
    assert n == 0  # price never reached that level


def test_a_buy_aoi_must_sit_inside_hl_hh():
    z = {"lo": 1.2500, "hi": 1.2510, "tfs": {"D1"}}
    assert alexg.bounded(z, 1, {"D1": (1.2400, 1.2800), "W1": None})
    assert not alexg.bounded(z, 1, {"D1": (1.2505, 1.2800), "W1": None})  # partly below HL
    assert not alexg.bounded(z, 1, {"D1": None, "W1": None})  # D1 not bullish


# ---------------------------------------------------------------- 3.6 GPA and the 5 agents
def test_gpa_items_and_grades():
    assert sum(p for _, p, _ in alexg.GPA) == 100 and len(alexg.GPA) == 9
    assert [alexg.grade_of(s) for s in (100, 90, 85, 80, 77, 75, 72, 70, 69)] == ["A+", "A+", "A", "A", "B", "B", "C+", "C+", "F"]
    assert alexg.RISK_BY_GRADE == {"A+": 1.0, "A": 1.0, "B": 0.75, "C+": 0.5}


def _read(**over):
    z = {"lo": 1.25, "hi": 1.2510, "tfs": {"W1", "D1"}, "touches": 5, "width": 10.0, "psych": 1.25, "overlap": True, "strong": True, "roles": [(1, 1)]}
    items = {k: True for k, _, _ in alexg.GPA}
    r = {"dir": 1, "etf": "H1", "T": T0 + 9 * 3600, "Tx": T0 + 9 * 3600, "S": {"W1": 1, "D1": 1, "H4": 1}, "zone": z, "zones": [z], "usable": [z],
         "near": z, "near_atr": 0.0, "price": 1.2512, "items": items, "gpa": 100, "grade": "A+", "setup": "SF_BOUNCE",
         "c": {"engulf": True, "doji": False, "doji_before": True, "sos": {"level": 1.2515, "time": T0, "index": 1}, "pattern": None, "ltf_ema": True},
         "entry": 1.2512, "sl": 1.2478, "tp": 1.2617, "tp1": 1.2563, "rr": 3.1, "news": [], "news_checked": True, "rollover": False,
         "spread_ratio": 0.04, "weekday": 1, "exec_session": True, "target_adr": 0.9}
    r.update(over)
    return r


def test_the_five_agents_and_the_execution_rule():
    sq = alexg.squad(_read(), 0.0001)
    assert list(sq["agents"]) == ["trend_director", "aoi_architect", "confluence_grader", "trigger_sniper", "risk_guardian"]
    assert all(a["status"] == "ok" and len(a["badge"]) <= 55 for a in sq["agents"].values())
    assert sq["agents"]["trend_director"]["score"] == 100 and sq["agents"]["aoi_architect"]["score"] == 100
    assert sq["agents"]["trigger_sniper"]["score"] == 100 and sq["execute"] and sq["consensus"] >= 90
    assert abs(sum(w for *_, w in alexg.ROLES) - 1.0) < 1e-9  # 0.25 + 0.25 + 0.20 + 0.20 + 0.10
    pull = alexg.squad(_read(S={"W1": 1, "D1": 1, "H4": -1}), 0.0001)
    assert pull["agents"]["trend_director"]["score"] == 80 and pull["agents"]["trend_director"]["status"] == "ok"
    counter = alexg.squad(_read(S={"W1": -1, "D1": 1, "H4": 1}, setup="SF_COUNTER"), 0.0001)
    assert counter["agents"]["trend_director"]["status"] == "warn" and counter["agents"]["trend_director"]["score"] == 70
    assert alexg.squad(_read(S={"W1": 1, "D1": -1, "H4": 1}), 0.0001)["agents"]["trend_director"]["status"] == "veto"
    low = alexg.squad(_read(gpa=60, grade="F"), 0.0001)
    assert low["agents"]["confluence_grader"]["status"] == "wait" and not low["execute"]
    assert alexg.squad(_read(gpa=50, grade="F"), 0.0001)["agents"]["confluence_grader"]["status"] == "veto"
    no_trig = alexg.squad(_read(c={"engulf": False, "doji": False, "sos": {"level": 1.25, "time": T0, "index": 1}, "pattern": None}), 0.0001)
    assert no_trig["agents"]["trigger_sniper"]["score"] == 65 and no_trig["radar"] and not no_trig["execute"]  # the radar stage
    away = alexg.squad(_read(zone=None, near_atr=0.8), 0.0001)
    assert away["agents"]["aoi_architect"]["status"] == "wait" and away["agents"]["aoi_architect"]["score"] == 60


def test_the_guardian_rules():
    g = lambda **o: alexg.squad(_read(**o), 0.0001)["agents"]["risk_guardian"]  # noqa: E731
    assert g(rr=1.9)["status"] == "veto"
    assert g(news=[T0])["status"] == "veto" and g(rollover=True)["status"] == "veto" and g(spread_ratio=0.3)["status"] == "veto"
    assert g(weekday=4)["status"] == "veto" and "Friday" in g(weekday=4)["badge"]
    assert g(weekday=3)["status"] == "ok" and g(weekday=3, gpa=75, grade="B")["status"] == "veto"  # Thursday asks A / A+
    assert g(weekday=3, target_adr=1.5)["status"] == "veto"
    assert g(exec_session=False)["status"] == "wait" and "06:00" in g(exec_session=False)["badge"]


# ---------------------------------------------------------------- 3.7 the trade follower
def test_break_even_plus_two_pips_at_one_and_a_half_r():
    m5 = [_Bar(T0 + i * 300, *p) for i, p in enumerate([(100, 100, 100, 100), (100, 101.6, 99.9, 101.4), (101.4, 101.5, 100.0, 100.1)])]
    ev = []
    out = run(m5, 0, 1, 100.0, 99.0, 101.5, 103.0, 0.0, True, 0, T0 + 86400, 0.0, ev, None, None, 0.02)
    assert [k for _, k, _ in ev] == ["FILLED", "TP1", "BE", "BE_STOP"]
    assert abs(out["r"] - 0.02) < 1e-9  # the stop at entry + 2 pips (0.02 here): a small win, never a loss
    ev2 = []
    run(m5[:2] + [_Bar(T0 + 600, 101.4, 101.7, 101.2, 101.6)], 0, 1, 100.0, 99.0, 101.5, 103.0, 0.0, True, 0, T0 + 86400, 0.0, ev2, None, None, 0.02)
    assert [k for _, k, _ in ev2].count("TP1") == 1  # locked once


def test_the_friday_exit_closes_only_a_trade_not_in_profit():
    fri = T0 - ((T0 // 86400 + 3) % 7) * 86400 + 4 * 86400 + 20 * 3600  # a Friday 20:00 UTC
    m5 = [_Bar(fri - 600, 100, 100, 100, 100), _Bar(fri - 300, 100, 100.2, 99.8, 99.9), _Bar(fri, 99.9, 100, 99.7, 99.8)]
    out = run(m5, 0, 1, 100.0, 99.0, None, 103.0, 0.0, True, 0, fri + 86400 * 7, 0.0, None, None, None, 0.0, None, 0, True)
    assert out["state"] == "LOSS" and out.get("fridayExit")
    up = [m5[0], _Bar(fri - 300, 100, 100.6, 99.9, 100.5), _Bar(fri, 100.5, 100.7, 100.4, 100.6)]
    assert run(up, 0, 1, 100.0, 99.0, None, 103.0, 0.0, True, 0, fri + 86400 * 7, 0.0, None, None, None, 0.0, None, 0, True)["state"] == "ACTIVE"


# ---------------------------------------------------------------- the universe, the sanitizer, the portfolio
def test_the_29_instruments_and_the_three_setups():
    assert len(desk.PAIRS) == 29 and len(PAIRS) == 28
    assert all(v == ["SF_BR", "SF_BOUNCE", "SF_COUNTER"] for v in playbook.STRATEGIES.values()) and len(playbook.STRATEGIES) == 29
    assert PAIRS["USD/JPY"][1] == "USDJPY=X" and PAIRS["USD/CHF"][1] == "USDCHF=X" and PAIRS["USD/CAD"][1] == "USDCAD=X"
    for p in desk.PAIRS:
        cfg = desk.BY_SYMBOL[p]
        assert cfg["pip"] == (0.1 if p.startswith("XAU") else 0.01 if p.endswith("JPY") else 0.0001)
        assert decimals_of(p) == (2 if p.startswith("XAU") else 3 if p.endswith("JPY") else 5)
    import app.smc as pkg
    gone = ("gold", "fiber", "cable", "swissy", "aussie", "loonie", "simple", "engine", "engines", "agents", "chart")
    assert not any((Path(pkg.__file__).parent / f"{m}.py").exists() for m in gone)  # the legacy strategies are deleted


def test_the_sanitizer_never_vetoes_on_missing_volume():
    c = [Candle(T0 + 8 * 3600 + i * 300, 1.0, 1.0004, 0.9996, 1.0, 0.0) for i in range(30)]  # Yahoo forex: no volume
    out, rep = sanitize(c, 300)
    assert len(out) == 30 and rep["missing"] == [] and rep["artifacts"] == []


def test_the_portfolio_caps():
    now = T0 + 3600
    live = lambda s, d: {"symbol": s, "direction": d, "time": now - 60, "liveUntil": now + 9999}  # noqa: E731
    assert portfolio.check("EUR/USD", {"direction": "BUY"}, [live("EUR/USD", "SELL")], now)["verdict"] == "BLOCK"  # one per pair
    two_jpy = [live("USD/JPY", "BUY"), live("EUR/JPY", "BUY")]  # already 2 short-JPY bets
    v = portfolio.check("GBP/JPY", {"direction": "BUY"}, two_jpy, now)
    assert v["verdict"] == "BLOCK" and any(r.startswith("JPY:") for r in v["reasons"])
    three = [live("EUR/USD", "BUY"), live("GBP/CHF", "SELL"), live("AUD/NZD", "BUY")]
    assert any(r.startswith("total risk") for r in portfolio.check("CAD/JPY", {"direction": "SELL"}, three, now)["reasons"])


# ---------------------------------------------------------------- a team on stored candles
def test_a_team_read_returns_the_5_agent_contract():
    for key, pair in (("EURUSD", "EUR/USD"), ("XAUUSD", "XAU/USD")):
        m5, h1 = stored(key, "M5"), stored(key, "H1")
        if not m5:
            continue
        d1 = playbook.resample(h1, 86400)
        t = desk.read_team(pair, desk.BY_SYMBOL[pair], m5, h1, m5[-1].time + 300, None, d1)
        assert [a["id"] for a in t["agents"]] == ["trend_director", "aoi_architect", "confluence_grader", "trigger_sniper", "risk_guardian"]
        assert all(a["status"] in ("ok", "warn", "wait", "veto") and len(a["badge"]) <= 55 and 0 <= a["score"] <= 100 for a in t["agents"])
        rep = t["pairReport"]
        assert rep["grade"] in ("A+", "A", "B", "C+", "F") and len(rep["checklist"]) == 9 and [s["id"] for s in t["strategies"]] == playbook.STRATEGIES[key]
        assert rep["final_decision"] in ("EXECUTE", "WAIT_FOR_TRIGGER", "WATCH_ONLY", "VETOED")
        ch = t["chart"]
        assert set(ch) >= {"boxes", "segments", "labels", "lines", "windows", "trade"}
        assert all("AOI" in b["label"] and "Touches" in b["label"] for b in ch["boxes"])
        assert {x["text"] for x in ch["labels"]} <= {"HH", "HL", "LH", "LL"}


def test_no_look_ahead_on_stored_candles():
    m5, h1 = stored("GBPUSD", "M5"), stored("GBPUSD", "H1")
    if not m5:
        return
    m5, h1 = m5[-20000:], h1[-3000:]  # the last ~10 weeks keep the test quick
    d1 = playbook.resample(h1, 86400)
    cut = m5[-1].time - 3 * 86400
    a, _ = alexg.scan("GBPUSD", m5, h1, 0.00018, None, d1)
    b, _ = alexg.scan("GBPUSD", [x for x in m5 if x.time < cut], [x for x in h1 if x.time + 3600 <= cut], 0.00018, None, [x for x in d1 if x.time + 86400 <= cut])
    key = lambda s: (s["time"], s["dir"], s["sid"], round(s["entry"], 6), round(s["sl"], 6), round(s["tp"], 6))  # noqa: E731
    assert [key(s) for s in a if s["time"] <= cut - 86400] == [key(s) for s in b if s["time"] <= cut - 86400]


# ---------------------------------------------------------------- the 3-stage notifications
def _sig(sid, t):
    return {"id": sid, "strategy": "SF_BR", "setupType": "SF_BR", "name": "Set & Forget — Break & Retest Continuation", "direction": "BUY", "time": t,
            "entry": 1.2512, "sl": 1.2478, "tp1": 1.2563, "tp": 1.26175, "part": 0.0, "market": True, "zone": [1.2505, 1.2519], "rr": 3.1,
            "validUntil": t, "expiry": 0, "holdUntil": t + 30 * 86400, "beOff": 0.0002, "newsMin": 30, "fridayExit": False, "state": "ACTIVE",
            "pass": True, "checklist": [], "steps": [], "lots": {"1000": 0.02, "10000": 0.29}, "riskPct": 1.0, "grade": "A", "gpa": 85,
            "consensus": 88, "slPips": 34.0, "tpPips": 105.5, "bePips": 51.0, "psychTp": 1.2625, "zoneInfo": {"tfs": ["D1"], "overlap": False},
            "desk": [{"key": "trend", "role": "HTF Trend Director", "status": "ok", "badge": "1W/1D/4H Bullish in sync · Pro-trend BUY", "score": 100}],
            "draw": {}}


def _clean():
    from app.db import SessionLocal, init_db
    from app.models import Signal
    init_db()
    with SessionLocal() as db:
        db.query(Signal).filter(Signal.id.like("SMC-%")).delete(synchronize_session=False)
        db.commit()


def test_the_signal_message():
    sid = f"SMC-GBPUSD-SF_BR-{T0}-B"
    t = notify.message({**_sig(sid, T0), "etf": "M15"}, "GBP/USD", 5)
    for part in ("GBP/USD — BUY</b> · Grade A", "Entry <code>1.25120</code>", "SL <code>1.24780</code>", "TP <code>1.26175</code>", "R:R 1:3.1",
                 "M15 | ", " UTC", f"ID <code>{sid}</code>", "not an order", "Stop fixed"):
        assert part in t, part
    assert "lot" not in t.lower() and "$" not in t and "risk" not in t.lower()  # market data only: nobody's risk or lot
    assert f"LD|v=1|id={sid}|symbol=GBPUSD|side=BUY|entry=1.25120|sl=1.24780|tp=1.26175|tf=M15|time=" in t
    mk = notify.copy_markup({**_sig(sid, T0), "etf": "M15"}, "GBP/USD", None)
    assert mk["inline_keyboard"][0][0]["copy_text"]["text"].startswith("LD|v=1|") and len(mk["inline_keyboard"][0][0]["copy_text"]["text"]) <= 256
    assert not hasattr(notify, "radar_message")  # the radar is no longer a notification


def test_no_radar_notification_and_the_signal_once(monkeypatch):
    _clean()
    T = T0 + 9 * 3600
    rad = {"id": f"RADAR-GBPJPY-B-1-{T}", "direction": "BUY", "tf": "1D", "touches": 4, "low": 192.4, "high": 192.85, "psych": 192.5, "etf": "H1",
           "gpa": 72, "grade": "C+", "time": T, "setup": "SF_BOUNCE"}
    state = {"sig": []}

    async def fake_team(pair, fresh=False):
        if pair == "GBP/JPY":
            return {"success": True, "signals": [], "radar": rad, "decision": "WAIT_FOR_TRIGGER"}
        if pair == "GBP/USD":
            return {"success": True, "signals": state["sig"], "radar": None, "decision": "EXECUTE"}
        return {"success": True, "signals": [], "radar": None, "decision": "WATCH_ONLY"}
    sent = []

    async def fake_broadcast(pair, text, title, body, tag, signal=None):
        sent.append((pair, text))
        return {"telegram": 1, "push": 1}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "broadcast", fake_broadcast)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    monkeypatch.setattr(notify.time, "time", lambda: T + 60)
    asyncio.run(notify.tick())
    asyncio.run(notify.tick())
    assert sent == []  # a radar read sends nothing: no Telegram, no push, nothing in the feed
    state["sig"] = [_sig(f"SMC-GBPUSD-SF_BR-{T}-B", T)]
    res = asyncio.run(notify.tick())
    asyncio.run(notify.tick())
    assert [p for p, _ in sent].count("GBP/USD") == 1 and "SF_BR grade A → telegram 1 · push 1" in res["GBP/USD"]
    assert all("RADAR" not in txt for _, txt in sent) and any(x["id"] == state["sig"][0]["id"] for x in notify.recent())
    from app.api import smc as smc_api
    assert "radar" not in smc_api.smc_signals(None)  # the app's feed carries the sent setups only


def test_the_manager_keeps_the_stop_fixed_and_tells_the_close(monkeypatch):
    _clean()
    T = T0 + 9 * 3600 - (T0 + 9 * 3600) % 300
    s = _sig(f"SMC-GBPUSD-SF_BR-{T + 300}-B", T + 300)
    assert notify._claim("GBP/USD", s)

    def c(i, o, h, lo, cl):
        return Candle(T + i * 300, o, h, lo, cl, 0)
    m5 = [c(0, 1.2510, 1.2513, 1.2508, 1.2512), c(1, 1.2512, 1.2540, 1.2510, 1.2538), c(2, 1.2538, 1.2566, 1.2535, 1.2560)]
    desk.LIVE["GBP/USD"] = (m5, 0.0, None)
    sent = []

    async def send(pair, text, title, body, tag):
        sent.append((title, text))
    one = asyncio.run(manager.manage_all(send))
    assert one[s["id"]] == ["FILLED"]  # past +1.5R: no break-even step any more, the stop stays where the signal put it
    m5.append(c(3, 1.2560, 1.2562, 1.2509, 1.2511))  # back down through the entry: the stop (1.24780) is still far away
    assert asyncio.run(manager.manage_all(send)) == {}
    m5.append(c(4, 1.2511, 1.2512, 1.2470, 1.2475))  # down through the saved stop
    two = asyncio.run(manager.manage_all(send))
    assert two[s["id"]] == ["STOP"] and "STOP LOSS HIT" in sent[-1][0] and len(sent) == 2
    from app.db import SessionLocal
    from app.models import Signal
    with SessionLocal() as db:
        row = db.get(Signal, s["id"])
        assert row.sl == s["sl"] == 1.2478 and row.outcome == "LOSS"  # the saved stop never changed
    res = manager.results()
    assert res["all"]["trades"] == 1 and abs(res["all"]["totalR"] + 1.0) < 0.01
