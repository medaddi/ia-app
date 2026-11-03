"""The 4 autonomous pair agents, the chart overlay each one emits for its own chart, and the Multi-Agent Risk Coordinator,
on hand-built markets. Sessions are UTC+1 (Morocco time)."""

import calendar
import math
import random
import time

from app.agent.validator import validate_signal
from app.agents.engine import evaluate_agent
from app.agents.registry import AGENT_CONFIGS, AGENTS
from app.core.instrument_specs import pips_to_price, price_to_pips, usd_direction
from app.core.quant_primitives import fvg_at, is_swing_high_now, is_swing_low_now, mt, order_block, ote
from app.core.risk_guard import coordinate, usd_exposure
from app.strategies.replay import replay
from app.strategies.service import STRATEGY_DEFS
from app.strategies.shared.lifecycle import simulate_lifecycle
from app.strategies.shared.types import Candle

M5, H1 = 300, 3600
T0 = calendar.timegm((2026, 11, 10, 0, 0, 0)) - 3600  # Tuesday 00:00 UTC+1


def build(t0, closes, start, w):
    c, p = [], start
    for k, x in enumerate(closes):
        o = p + (x - p) * 0.2
        c.append(Candle(t0 + k * M5, o, max(o, x) + w, min(o, x) - w, x))
        p = x
    return c


def inp(c, now=None, peer=None, events=None, tf="M5", price=0):
    return {"candles": {tf: c}, "peer": {tf: peer} if peer else None, "nowSec": now or c[-1].time + (M5 if tf == "M5" else H1) + 5, "livePrice": price,
            "spread": None, "isRealData": True, "dataSource": "test", "isMarketOpen": True, "day": {"trades": 0, "losses": 0},
            "news": {"events": events or [], "source": "test"}}


def run(pair, c, **kw):
    return evaluate_agent(inp(c, **kw), AGENTS[pair], AGENT_CONFIGS[pair])


def cats(ov, key):
    return {x["category"] for x in ov[key]}


# ------------------------------------------------------------------ instruments and primitives
def test_instrument_normalisation_and_primitives():
    assert abs(pips_to_price("XAUUSD", 10) - 1.0) < 1e-12 and abs(price_to_pips("EURUSD", 0.0025) - 25) < 1e-9
    assert usd_direction("XAU/USD", "BUY") == usd_direction("EURUSD", "BUY") == -1 and usd_direction("AUD/CHF", "BUY") == 0
    assert mt(calendar.timegm((2026, 11, 10, 7, 0, 0)))[1] == 8 * 60  # 07:00 UTC = 08:00 UTC+1
    c = build(0, [1.0, 1.1, 1.2, 1.1, 1.0], 1.0, 0.0)
    assert is_swing_high_now(c) and not is_swing_low_now(c)
    up = build(0, [1.0, 1.0, 1.3, 1.5], 1.0, 0.0)
    g = fvg_at(up, 3, True, 0.01)
    assert g and g.bottom == up[1].high and g.top == up[3].low and g.ce_50 == (g.top + g.bottom) / 2
    o = ote(2005.0, 1995.0)  # a bearish leg of $10
    assert abs(o.ote_618 - 2001.18) < 1e-9 and abs(o.ote_786 - 2002.86) < 1e-9 and abs(o.ote_705 - 2002.05) < 1e-9
    seq = [Candle(k, 1.0, 1.0 + k * 0.01, 0.99, 1.0 + (0.005 if k % 2 else -0.005)) for k in range(12)]
    ob = order_block(seq, 11, False, 10)  # bearish MSS → the highest bullish candle
    assert ob and seq[ob.index].close > seq[ob.index].open and ob.mean == (seq[ob.index].open + seq[ob.index].close) / 2


# ------------------------------------------------------------------ Agent 1 · EUR/USD
def eur_market(asia_amp=0.0015, sweep=(1.1019, 1.1021)):
    cl = [1.10025 + asia_amp * math.sin(k / 4) for k in range(84)]  # 00:00–07:00 UTC+1
    cl += [1.1005 + 0.0001 * math.sin(k) for k in range(12)]
    cl += [1.1006, 1.1004, 1.1002, 1.1005, 1.1008, 1.1012, 1.1016, *sweep, 1.1018, 1.1009, 1.0999, 1.0996,
           1.1000, 1.1005, 1.1010, 1.1013, 1.1008, 1.1000, 1.0995, 1.0990, 1.0985, 1.0980]
    while len(cl) < 288:
        cl.append(1.0982 + 0.0001 * math.sin(len(cl)))
    prev = [1.1000 + 0.0003 * math.sin(k / 5) for k in range(288)]
    return build(T0 - 86400, prev + cl, 1.1, 0.00005)


def test_agent1_eurusd_asian_sweep_fvg_and_its_chart():
    c = eur_market()
    r = run("EUR/USD", c)
    assert r["dataQuality"]["ok"] and len(r["history"]) == 1
    h = r["history"][0]
    assert h["direction"] == "SELL" and h["exitType"] == "TP3" and h["r"] >= 2
    live = run("EUR/USD", c, now=h["signalTime"] + 3, price=1.0999)
    s, ov = live["setup"], live["overlay"]
    assert live["status"] == "SIGNAL" and live["canNotify"] and s["entryType"] == "LIMIT" and s["expiresAt"] - h["signalTime"] == 12 * M5
    assert 6 <= s["slPips"] <= 18 and s["rrTarget"] >= 2 and validate_signal(live)["approved"]
    # its own chart: Asian box + lines, sweep marker, MSS line, FVG with its 50 % CE, the live projection
    assert ov["symbol"] == "EURUSD" and ov["agentId"] == "EURUSD_AsianSweep_FVG_Agent" and ov["fsmState"] == "PENDING_ORDER"
    assert {"ASIAN_BOX", "FVG_BEAR"} <= cats(ov, "zones") and {"SESSION_HIGH", "SESSION_LOW", "EQUILIBRIUM", "MSS_BREAK"} <= cats(ov, "priceLines")
    fvg = next(z for z in ov["zones"] if z["category"] == "FVG_BEAR")
    assert fvg["label"] == "50% CE ENTRY" and abs(fvg["midPrice"] - s["entry"]) < 1e-5
    assert any(m["text"] == "ASIAN HIGH SWEPT" and m["position"] == "aboveBar" for m in ov["markers"])
    box = ov["tradeExecutionBox"]
    assert box["direction"] == "SHORT" and box["orderType"] == "LIMIT" and box["status"] == "PENDING" and box["tp2Price"] == s["tp3"]
    assert ov["metrics"]["confluenceTag"] == "ASIAN SWEEP + FVG" and ov["statusBannerText"].startswith("EURUSD · PENDING_ORDER")
    st = replay(STRATEGY_DEFS["EUR/USD"], {**inp(c), "candles": {"M5": c}}, c[0].time, c[-1].time + M5)
    assert [e["id"] for e in st.emitted] == [s["id"]]


def test_agent1_filters():
    r = run("EUR/USD", eur_market(asia_amp=0.0003))  # a 6-pip night: COOLDOWN
    assert not r["history"] and r["overlay"]["fsmState"] == "COOLDOWN"
    assert not run("EUR/USD", eur_market(sweep=(1.1030, 1.1044)))["history"]  # taken by 25 pips: a real breakout


def test_news_blackout_cuts_the_pending_limit_30_min_before():
    c = eur_market()
    sig = run("EUR/USD", c)["history"][0]["signalTime"]
    news = [{"time": sig + 50 * 60, "currency": "USD", "title": "CPI m/m", "impact": "High"}]
    assert run("EUR/USD", c, now=sig + 3, events=news)["setup"]["expiresAt"] == sig + 20 * 60
    news = [{"time": sig + 20 * 60, "currency": "EUR", "title": "ECB rate", "impact": "High"}]
    r = run("EUR/USD", c, now=sig + 3, events=news)
    assert r["status"] != "SIGNAL"


# ------------------------------------------------------------------ Agent 2 · GBP/USD
def judas_market(base, judas, eur_break=False):
    prev = [base + 0.0010 + 0.0020 * math.sin(k / 6) for k in range(288)]
    day = [base + 0.0005 + 0.0010 * math.sin(k / 4) for k in range(90)]  # 00:00–07:30
    day += [base + 0.0008 + 0.0001 * math.sin(k) for k in range(6)]
    if judas:
        day += [base + x for x in (0.0004, 0.0006, 0.0010, 0.0016, 0.0020, 0.0023, 0.0015, 0.0005, -0.0002, -0.0010, -0.0004, 0.0004, 0.0012,
                                   0.0024, 0.0012, 0.0002, -0.0010, -0.0025, -0.0040, -0.0055, -0.0065, -0.0075)]
    else:
        top = 0.0019 if eur_break else 0.0012
        day += [base + x for x in (0.0004, 0.0006, 0.0008, 0.0010, 0.0011, top, 0.0008, 0.0004, 0.0, -0.0004, 0.0, 0.0004, 0.0006, 0.0002)]
    while len(day) < 288:
        day.append(day[-1] + 0.00005 * math.sin(len(day)))
    return build(T0 - 86400, prev + day, base, 0.00005)


def test_agent2_gbpusd_judas_smt_order_block_and_its_chart():
    g, e = judas_market(1.3000, True), judas_market(1.1000, False)
    r = run("GBP/USD", g, peer=e)
    assert len(r["history"]) == 1, r["overlay"]["statusBannerText"]
    h = r["history"][0]
    assert h["direction"] == "SELL" and abs(h["r"] - 3) < 0.05
    live = run("GBP/USD", g, now=h["signalTime"] + 3, peer=e, price=1.2995)
    s, ov = live["setup"], live["overlay"]
    assert 15 <= s["slPips"] <= 28 and abs(s["rrTarget"] - 3) < 0.02 and abs(abs(s["tp1"] - s["entry"]) / abs(s["entry"] - s["sl"]) - 1.5) < 0.02
    assert s["expiresAt"] - h["signalTime"] == 90 * 60
    assert {"PDH", "PDL", "SESSION_HIGH", "SESSION_LOW", "MSS_BREAK"} <= cats(ov, "priceLines") and "OB_BEAR" in cats(ov, "zones")
    ob = next(z for z in ov["zones"] if z["category"] == "OB_BEAR")
    assert ob["label"] == "OB 50% ENTRY" and abs(ob["midPrice"] - s["entry"]) < 1e-5
    assert any(m["text"] == "JUDAS TRAP + SMT vs EURUSD" for m in ov["markers"]) and ov["metrics"]["confluenceTag"] == "SMT CONFIRMED"
    # EUR/USD took its own Asian high too: no SMT, no trade; no EUR/USD feed: the agent does not guess
    assert not [t for t in run("GBP/USD", g, peer=judas_market(1.1000, False, eur_break=True))["history"] if t["direction"] == "SELL"]
    assert not run("GBP/USD", g)["dataQuality"]["ok"]


# ------------------------------------------------------------------ Agent 3 · AUD/CHF
def range_market(n=3000, seed=7):
    random.seed(seed)
    c, p = [], 0.5950
    for k in range(n):
        target = 0.5950 + 0.0045 * math.sin(2 * math.pi * k / 160) + 0.0012 * math.sin(2 * math.pi * k / 37)
        x = p + (target - p) * 0.35 + random.gauss(0, 0.0004)
        c.append(Candle(1_790_985_600 + k * H1, p, max(p, x) + abs(random.gauss(0, 0.0002)), min(p, x) - abs(random.gauss(0, 0.0002)), x))
        p = x
    return c


def test_agent3_audchf_mean_reversion_and_its_chart():
    c = range_market()
    r = run("AUD/CHF", c, tf="H1")
    assert r["dataQuality"]["ok"] and r["history"]
    t = r["history"][0]["time"]
    idx = next(k for k, x in enumerate(c) if x.time == t)
    live = run("AUD/CHF", c[:idx + 1], tf="H1")
    s, ov = live["setup"], live["overlay"]
    buy = s["direction"] == "BUY"
    assert s["entryType"] == "MARKET" and s["params"]["partials"] == [0.5, 0, 0.5] and 20 <= s["slPips"] <= 35
    assert (s["sl"] < s["entry"] < s["tp1"] < s["tp3"]) if buy else (s["sl"] > s["entry"] > s["tp1"] > s["tp3"])
    assert {"SUPPLY_BAND", "DEMAND_BAND"} <= cats(ov, "zones") and {"EQUILIBRIUM", "DIVERGENCE_LINE"} <= cats(ov, "priceLines")
    div = next(x for x in ov["priceLines"] if x["category"] == "DIVERGENCE_LINE")
    assert div["label"] == "H1 RSI DIVERGENCE" and div["startTime"] < div["endTime"]
    assert any(m["text"] == "ENGULFING TRIGGER" for m in ov["markers"]) and ov["fsmState"] == "IN_TRADE"
    assert ov["tradeExecutionBox"]["orderType"] == "MARKET"


# ------------------------------------------------------------------ Agent 4 · XAU/USD
def gold_market(sweep_top=2007.4):
    cl = [2000 + 6 * math.sin(k / 4) for k in range(90)]  # 00:00–07:30 UTC+1: Asia ≈ $12
    cl += [2003.0 + 0.1 * math.sin(k) for k in range(6)]
    cl += [2003.0, 2002.4, 2001.8, 2003.0, 2004.2, 2005.4, 2006.4, sweep_top,  # protected low 2001.8, the Asian high swept
           2005.2, 2003.0, 1999.8,  # rejection, displacement with a bearish FVG, MSS
           2001.0, 2003.0, 2005.3, 2003.0, 2000.0, 1997.0, 1994.0, 1991.0, 1989.0, 1988.0]
    while len(cl) < 288:
        cl.append(1989.5 + 0.2 * math.sin(len(cl)))
    prev = [2000 + 3 * math.sin(k / 7) for k in range(288)]
    return build(T0 - 86400, prev + cl, 2000.0, 0.3)


def test_agent4_xauusd_sweep_rejection_ote_and_its_chart():
    c = gold_market()
    r = run("XAU/USD", c)
    assert len(r["history"]) == 1, r["overlay"]["statusBannerText"]
    h = r["history"][0]
    assert h["direction"] == "SELL" and h["r"] > 0
    live = run("XAU/USD", c, now=h["signalTime"] + 3, price=2000.0)
    s, ov = live["setup"], live["overlay"]
    assert s["entryType"] == "LIMIT" and 25 <= s["slPips"] <= 65 and s["params"]["partials"] == [0.5, 0, 0.5]
    assert abs(s["params"]["beOffset"] - 0.2) < 1e-9  # TP1: stop to entry + 2 pips ($0.20)
    assert abs(s["tp1"] - s["entry"]) / abs(s["entry"] - s["sl"]) >= 1.3 - 1e-6
    assert {"ASIAN_BOX", "LONDON_BOX", "OTE_GOLD_ZONE"} <= cats(ov, "zones") and "FVG_BEAR" in cats(ov, "zones")
    zone = next(z for z in ov["zones"] if z["category"] == "OTE_GOLD_ZONE")
    assert zone["label"] == "OTE GOLDEN ZONE (61.8% - 78.6%)" and zone["bottomPrice"] <= s["entry"] <= zone["topPrice"] + 1e-6
    assert next(z for z in ov["zones"] if z["category"] == "ASIAN_BOX")["fillColor"] == "rgba(212, 175, 55, 0.10)"
    assert any(m["text"] == "XAU LIQUIDITY SWEEP + REJECTION" for m in ov["markers"]) and "MSS_BREAK" in cats(ov, "priceLines")
    assert {"PDH", "PDL", "SESSION_HIGH"} <= cats(ov, "priceLines") and ov["metrics"]["confluenceTag"] in ("OTE + FVG", "FVG CE", "OTE + OB")
    assert validate_signal(live)["approved"]
    # swept by $7 (70 pips > 65): a real breakout, no trade
    assert not run("XAU/USD", gold_market(sweep_top=2014.0))["history"]


def test_partial_and_break_even_plus_offset():
    c = [Candle(0, 100, 100.2, 99.9, 100), Candle(300, 100, 100.1, 98.4, 98.5), Candle(600, 98.5, 100.5, 98.4, 100.3)]
    p = {"side": "SELL", "entryType": "MARKET", "entry": 100, "sl": 101, "tp1": 98.5, "tp2": 96, "tp3": 96, "expiryTime": None,
         "marketFillTime": 0, "cancelIfTp1BeforeFill": False, "partials": [0.5, 0, 0.5], "breakeven": True, "beOffset": 0.2, "spread": 0, "slippage": 0}
    lc = simulate_lifecycle(c, p, 1)
    assert lc["state"] == "CLOSED" and lc["events"][-1]["price"] == 99.8 and abs(lc["rMultiple"] - (0.75 + 0.1)) < 1e-9


def test_fast_on_60_days_of_m5():
    days = [eur_market()[288:] for _ in range(42)]
    c = [Candle(T0 + k * M5 - 41 * 86400, x.open, x.high, x.low, x.close) for k, x in enumerate(sum(days, []))]
    run("EUR/USD", c)
    t = time.perf_counter()
    r = run("EUR/USD", c)
    assert time.perf_counter() - t < 0.5 and len(r["history"]) >= 20


# ------------------------------------------------------------------ the risk coordinator
def test_usd_correlation_cap_and_coordinator():
    from app.db import SessionLocal, init_db
    from app.models import Signal

    init_db()
    now = int(time.time())

    def add(id_, sym, side, state="OPEN"):
        db.add(Signal(id=id_, symbol=sym, setup="AGENT", direction=side, entry_type="LIMIT", entry=1, sl=0.99, tp1=1.01, tp2=1.02, tp3=1.02,
                      rr_tp2=2, score=100, signal_time=now, state=state, params={}, payload={}))
        db.commit()

    with SessionLocal() as db:
        db.query(Signal).delete()
        db.commit()
        assert usd_exposure("GBP/USD", "BUY", db)["riskPct"] == 1.0
        add("A", "EUR/USD", "BUY")  # short USD, not at break-even
        e = usd_exposure("GBP/USD", "BUY", db)
        assert e["riskPct"] == 0.5 and not e["blocked"]
        assert usd_exposure("GBP/USD", "SELL", db)["riskPct"] == 1.0  # the other dollar direction
        add("B", "XAU/USD", "BUY")
        assert usd_exposure("GBP/USD", "BUY", db)["blocked"]  # a third correlated short-USD trade
        db.query(Signal).filter(Signal.id == "B").update({"state": "TP1_HIT"})  # at break-even: no longer counts
        db.commit()
        assert not usd_exposure("GBP/USD", "BUY", db)["blocked"]
        # the coordinator on a real agent order: approved at 0.5 % with halved lots next to the open EUR/USD trade
        g, eu = judas_market(1.3000, True), judas_market(1.1000, False)
        sig = run("GBP/USD", g, peer=eu)["history"][0]["signalTime"]
        r = run("GBP/USD", g, now=sig + 3, peer=eu, price=1.2995)
        r["market"]["isOpen"] = True
        d = coordinate(r, db, now=sig + 3)
        assert d["riskPct"] == 1.0  # GBP/USD SELL is long USD: EUR/USD BUY is the other way
        add("C", "EUR/USD", "SELL")
        d = coordinate(r, db, now=sig + 3)
        assert d["approved"], d["issues"]
        assert d["riskPct"] == 0.5 and all(d["lots"][k] <= r["setup"]["lots"][k] / 2 + 1e-9 for k in d["lots"])
        add("D", "XAU/USD", "SELL")
        d = coordinate(r, db, now=sig + 3)
        assert not d["approved"] and any("USD" in i for i in d["issues"])
        db.query(Signal).delete()
        db.commit()
