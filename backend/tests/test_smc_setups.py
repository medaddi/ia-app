"""The SMC button's rule engine: fractal swings, a body close is a break and a wick is a sweep, FVGs, and a full
session-sweep setup (Asian high swept in London → M5 CHoCH with an FVG → a sell limit at the gap)."""

import calendar
import math

from app.analysis.smc_setups import Structure, fvgs, scan_all, simulate, smc_now, swings
from app.strategies.shared.types import Candle

DAY = calendar.timegm((2026, 11, 10, 0, 0, 0))  # a Tuesday
M5, H1 = 300, 3600
SPEC = {"decimals": 5, "pipSize": 0.0001}
COST = 0.00012


def seq(t0, closes, start, w=0.00005, step=M5):
    c, p = [], start
    for k, x in enumerate(closes):
        o = p + (x - p) * 0.2
        c.append(Candle(t0 + k * step, o, max(o, x) + w, min(o, x) - w, x))
        p = x
    return c


def test_swings_breaks_sweeps_and_gaps():
    c = seq(0, [1.0, 1.1, 1.2, 1.1, 1.0, 1.05, 1.0], 1.0, 0.0)
    sh, sl = swings(c)
    assert sh[2] == c[2].high and sl[4] is None  # a fractal needs 2 lower highs on each side
    st = Structure(c + [Candle(7 * M5, 1.0, 1.25, 0.99, 1.15)])  # a wick above the swing high, close back below
    assert st.swept(7, 1) and not st.breaks(7, 1)
    st = Structure(c + [Candle(7 * M5, 1.0, 1.25, 0.99, 1.22)])  # a body close above it
    assert st.breaks(7, 1) and not st.swept(7, 1)
    g = fvgs([Candle(0, 1.0, 1.01, 0.99, 1.0), Candle(1, 1.0, 1.05, 1.0, 1.05), Candle(2, 1.05, 1.06, 1.02, 1.055)])
    assert g[2] == (1, 1.01, 1.02)  # candle 1's high to candle 3's low


def asian_sweep_market(base=1.0990, amp=0.0030, h1fn=lambda k: 1.0970 + 0.0070 * math.sin(k / 5)):
    """An Asian range, a London rally that sweeps the Asian high, a pullback low, then a displacement down."""
    asia = [base + amp * math.sin(k / 4) for k in range(72)]
    pre = [1.1000 + 0.0001 * k for k in range(12)]
    london = [1.1012, 1.1016, 1.1020, 1.1024, 1.1026, 1.1022, 1.1019, 1.1023, 1.1027, 1.1030, 1.1028]
    m5 = seq(DAY, asia + pre + london, asia[0])
    t = m5[-1].time
    m5 += [Candle(t + M5, 1.1028, 1.1029, 1.1020, 1.1024), Candle(t + 2 * M5, 1.1024, 1.1025, 1.1005, 1.1006),
           Candle(t + 3 * M5, 1.1006, 1.1008, 1.1002, 1.1004), Candle(t + 4 * M5, 1.1004, 1.1005, 1.1000, 1.1002)]
    h1 = seq(DAY + 6 * H1 - 299 * H1, [h1fn(k) for k in range(300)], h1fn(0), 0.0002, H1)
    return m5, h1


def test_session_sweep_rules_met_but_the_checklist_says_no():
    m5, h1 = asian_sweep_market()  # a narrow Asian range: the other side is < 3R away, and no bearish H1 bias
    res = scan_all(m5, h1, COST, 5)
    d = res["D"]["setups"]
    assert len(d) == 1 and d[0]["dir"] == -1 and d[0]["result"]["state"] == "PENDING"
    s = d[0]
    assert abs(s["entry"] - 1.1008) < 1e-9 and s["sl"] > 1.1030 and abs(s["tp"] - min(x.low for x in m5[:72])) < 1e-9 and s["rr"] >= 1.5
    assert all(ok for _, ok, _ in s["steps"]) and any("London killzone" in a for a, _, _ in s["steps"])
    assert not s["pass"] and not s["checklist"][6][1]  # question 7: reward < 3R
    now = smc_now(m5, h1, COST, SPEC, m5[-1].close, lambda e, sl: {"1000$": 0.1})
    top = next(r for r in now["strategies"] if r["id"] == "D")
    assert top["status"] == "BLOCKED" and "checklist says no" in top["reason"] and now["verdict"].startswith("No confirmed")


def test_session_sweep_confirmed_when_the_7_questions_pass():
    m5, h1 = asian_sweep_market(1.0960, 0.0060, lambda k: 1.1280 - 0.0001 * k + 0.0010 * math.sin(k / 3))  # wide Asia, H1 falling
    s = scan_all(m5, h1, COST, 5)["D"]["setups"][0]
    assert s["pass"] and s["rr"] >= 3 and len(s["checklist"]) == 7
    news = []
    now = smc_now(m5, h1, COST, SPEC, m5[-1].close, lambda e, sl: {"1000$": 0.1}, lambda t: news[0] if news else None)
    top = now["strategies"][0]
    assert top["id"] == "D" and top["status"] == "CONFIRMED" and top["setup"]["direction"] == "SELL" and top["setup"]["entryType"] == "LIMIT"
    assert all(c["ok"] for c in top["checklist"]) and "confirmed" in now["verdict"]
    news.append("USD CPI 08:30")  # a red-folder release within 15 minutes: question 6 says no
    top = next(r for r in smc_now(m5, h1, COST, SPEC, m5[-1].close, lambda e, sl: {}, lambda t: news[0])["strategies"] if r["id"] == "D")
    assert top["status"] == "BLOCKED" and "CPI" in top["checklist"][5]["detail"]


def test_pullback_swings_ignore_inside_bars():
    from app.analysis.smc_setups import pullback_swings
    c = [Candle(0, 1.00, 1.02, 0.99, 1.01), Candle(1, 1.01, 1.05, 1.00, 1.04),  # the mother candle: high 1.05, low 1.00
         Candle(2, 1.04, 1.045, 1.01, 1.02),  # an inside bar: no pullback
         Candle(3, 1.02, 1.03, 0.995, 1.00)]  # trades below the mother's low: the pullback, 1.05 is a swing high
    sh, sl, at = pullback_swings(c)
    assert sh[1] == 1.05 and at == {3: [("H", 1)]}


def test_the_limit_order_life():
    c = [Candle(k * M5, 1.0, 1.001, 0.999, 1.0) for k in range(5)]
    assert simulate(c, 0, 1, 0.99, 0.98, 1.01, 12, 0)["state"] == "PENDING"  # not reached yet, still valid
    c2 = c + [Candle(5 * M5, 1.0, 1.0, 0.975, 0.98)]  # fills and hits the stop in the same candle: the stop counts
    assert simulate(c2, 0, 1, 0.99, 0.98, 1.01, 12, 0)["state"] == "LOSS"
    c3 = c + [Candle(5 * M5, 1.0, 1.0, 0.989, 0.99), Candle(6 * M5, 0.99, 1.012, 0.99, 1.011)]
    r = simulate(c3, 0, 1, 0.99, 0.98, 1.01, 12, 0)
    assert r["state"] == "WIN" and abs(r["r"] - 2.0) < 1e-9
    c4 = c + [Candle(5 * M5, 1.0, 1.02, 1.0, 1.015)]  # the target is reached before the limit fills: missed
    assert simulate(c4, 0, 1, 0.99, 0.98, 1.01, 12, 0)["state"] == "MISSED"


def test_the_analyse_drawing_of_a_confirmed_smc_setup():
    from app.analysis.drawing import plan_drawing, smc_drawing
    m5, h1 = asian_sweep_market(1.0960, 0.0060, lambda k: 1.1280 - 0.0001 * k + 0.0010 * math.sin(k / 3))
    now = smc_now(m5, h1, COST, SPEC, m5[-1].close, lambda e, sl: {"1000$": 0.1})
    row = now["strategies"][0]
    d = smc_drawing("EURUSD", row, m5[-1].close, 0.0001)
    assert {z["category"] for z in d["zones"]} == {"ASIAN_BOX", "FVG_BEAR"} and {l["category"] for l in d["priceLines"]} >= {"BSL", "EQUILIBRIUM"}
    box = d["tradeExecutionBox"]
    assert box["direction"] == "SHORT" and box["orderType"] == "LIMIT" and box["status"] == "PENDING" and box["entryPrice"] == row["setup"]["entry"]
    plan = {"id": "P", "name": "plan", "timeframe": "H1", "status": "SETUP",
            "setup": {"direction": "BUY", "entry": 1.1, "sl": 1.09, "tp": 1.12, "rr": 2, "since": DAY, "geo": {"level": 1.098, "side": -1, "n": 10, "t0": DAY - 36000}}}
    p = plan_drawing("EURUSD", plan, 1.101, 0.0001)
    assert p["priceLines"][0]["startPrice"] == 1.098 and p["tradeExecutionBox"]["orderType"] == "MARKET" and p["tradeExecutionBox"]["floatingPips"] == 10.0
