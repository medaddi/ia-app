"""The three pair agents (EUR/USD Asian sweep + FVG, GBP/USD London Judas + SMT, AUD/CHF range mean reversion) and the
global risk manager over them, on hand-built markets."""

import calendar
import math
import random
import time

from app.agent.risk_manager import daily_loss_check, day_start, usd_check
from app.agent.validator import validate_signal
from app.agent.trade_desk import review
from app.agent.explain import build_explanation
from app.strategies.engines import asian_sweep
from app.strategies.engines.engine import evaluate_agent
from app.strategies.engines.primitives import by_day, gaps, swing_flags
from app.strategies.pairs.config import PAIR_CONFIGS
from app.strategies.replay import replay
from app.strategies.service import STRATEGY_DEFS
from app.strategies.shared.lifecycle import simulate_lifecycle
from app.strategies.shared.types import Candle

M5, H1 = 300, 3600
T0 = calendar.timegm((2026, 11, 10, 0, 0, 0))  # a Tuesday in winter: London = UTC


def build(t0, closes, start, w=0.00005):
    c, p = [], start
    for k, x in enumerate(closes):
        o = p + (x - p) * 0.2
        c.append(Candle(t0 + k * M5, o, max(o, x) + w, min(o, x) - w, x))
        p = x
    return c


def inp(c, now=None, peer=None, events=None, tf="M5"):
    return {"candles": {tf: c}, "peer": {tf: peer} if peer else None, "nowSec": now or c[-1].time + (M5 if tf == "M5" else H1) + 5, "livePrice": 0,
            "spread": None, "isRealData": True, "dataSource": "test", "isMarketOpen": True, "day": {"trades": 0, "losses": 0},
            "news": {"events": events or [], "source": "test"}}


# ------------------------------------------------------------------ Agent 1 · EUR/USD
def eur_market(asia_amp=0.0015, sweep=(1.1019, 1.1021)):
    cl = [1.10025 + asia_amp * math.sin(k / 4) for k in range(84)]  # 00:00–07:00: the Asian box
    cl += [1.1005 + 0.0001 * math.sin(k) for k in range(12)]  # 07:00–08:00
    cl += [1.1006, 1.1004, 1.1002, 1.1005, 1.1008, 1.1012, 1.1016, *sweep,  # swing low 1.1002, then the Asian high is swept
           1.1018, 1.1009, 1.0999, 1.0996,  # displacement with an FVG, close under the swing low (MSS)
           1.1000, 1.1005, 1.1010, 1.1013, 1.1008, 1.1000, 1.0995, 1.0990, 1.0985, 1.0980]  # back into the FVG, then the target
    while len(cl) < 288:
        cl.append(1.0982 + 0.0001 * math.sin(len(cl)))
    prev = [1.1000 + 0.0003 * math.sin(k / 5) for k in range(288)]
    return build(T0 - 86400, prev + cl, 1.1)


def test_agent1_asian_sweep_fvg_sells_the_gap_back_to_the_asian_low():
    c = eur_market()
    cfg = PAIR_CONFIGS["EUR/USD"]
    r = evaluate_agent(inp(c), cfg)
    assert r["dataQuality"]["ok"] and len(r["history"]) == 1
    h = r["history"][0]
    assert h["direction"] == "SELL" and h["exitType"] == "TP3" and h["r"] >= 2
    # live, at the MSS close: a SELL LIMIT at the FVG's 50 %, SL beyond the sweep + 3 pips, TP the Asian low, 12 M5 to fill
    sig = h["signalTime"]
    live = evaluate_agent(inp(c, now=sig + 3), cfg)
    s = live["setup"]
    assert live["status"] == "SIGNAL" and live["canNotify"] and s["entryType"] == "LIMIT" and s["lifecycle"]["state"] == "PENDING"
    assert s["expiresAt"] - sig == 12 * M5 and s["params"]["cancelLevel"] == s["tp3"]
    asia_low = min(x.low for x in c[288:288 + 84])
    assert abs(s["tp3"] - asia_low) < 2e-5 and s["slPips"] <= 18 and s["rrTarget"] >= 2
    assert s["entry"] < s["tp1"] or s["tp3"] < s["tp1"] < s["entry"]  # break-even level between the entry and the target
    assert validate_signal(live)["approved"]
    desk = review({**live, "price": 1.0999})
    assert desk["approved"] and any(k["key"] == "limit" for k in desk["checks"])
    assert "LIMIT order" in build_explanation(live)
    # the replay (today's trade count) finds the same signal
    st = replay(STRATEGY_DEFS["EUR/USD"], {**inp(c), "candles": {"M5": c}}, c[0].time, c[-1].time + M5)
    assert [e["id"] for e in st.emitted] == [s["id"]]


def test_agent1_quality_filter_and_real_breakouts():
    cfg = PAIR_CONFIGS["EUR/USD"]
    # an Asian range of 6 pips: the market is dead, no trade today
    r = evaluate_agent(inp(eur_market(asia_amp=0.0003)), cfg)
    assert not r["history"] and "outside 12–45" in r["facts"]["progress"]
    # the Asian high taken by 25 pips (> 20): a real breakout, not a sweep
    r = evaluate_agent(inp(eur_market(sweep=(1.1030, 1.1044))), cfg)
    assert not r["history"]


def test_agent1_news_deletes_the_pending_limit_15_min_before():
    c = eur_market()
    cfg = PAIR_CONFIGS["EUR/USD"]
    sig = evaluate_agent(inp(c), cfg)["history"][0]["signalTime"]
    news = [{"time": sig + 40 * 60, "currency": "USD", "title": "CPI m/m", "impact": "High"}]
    s = evaluate_agent(inp(c, now=sig + 3, events=news), cfg)["setup"]
    assert s["expiresAt"] == sig + 25 * 60  # 15 min before the news, sooner than the 12-candle expiry
    # a red event 20 min after the MSS: no new trade inside ±30 min
    news = [{"time": sig + 20 * 60, "currency": "EUR", "title": "ECB rate", "impact": "High"}]
    assert evaluate_agent(inp(c, now=sig + 3, events=news), cfg)["status"] != "SIGNAL"


# ------------------------------------------------------------------ Agent 2 · GBP/USD
def judas_market(base, judas, eur_break=False):
    prev = [base + 0.0010 + 0.0020 * math.sin(k / 6) for k in range(288)]
    day = [base + 0.0005 + 0.0010 * math.sin(k / 4) for k in range(90)]  # 00:00–07:30
    day += [base + 0.0008 + 0.0001 * math.sin(k) for k in range(6)]
    if judas:  # GBP/USD takes the Asian high by 8 pips, then breaks the structure back down
        day += [base + x for x in (0.0004, 0.0006, 0.0010, 0.0016, 0.0020, 0.0023, 0.0015, 0.0005, -0.0002, 0.0005, 0.0012, 0.0022, 0.0016,
                                   0.0005, -0.0005, -0.0015, -0.0025, -0.0030, -0.0035)]
    else:  # EUR/USD stays under its Asian high (SMT) or takes it too
        top = 0.0019 if eur_break else 0.0012
        day += [base + x for x in (0.0004, 0.0006, 0.0008, 0.0010, 0.0011, top, 0.0008, 0.0004, 0.0, 0.0002, 0.0005, 0.0008, 0.0006, 0.0002,
                                   -0.0003, -0.0008)]
    while len(day) < 288:
        day.append(day[-1] + 0.00005 * math.sin(len(day)))
    return build(T0 - 86400, prev + day, base)


def test_agent2_london_judas_with_smt():
    cfg = PAIR_CONFIGS["GBP/USD"]
    g = judas_market(1.3000, True)
    r = evaluate_agent(inp(g, peer=judas_market(1.1000, False)), cfg)
    assert len(r["history"]) == 1
    h = r["history"][0]
    assert h["direction"] == "SELL" and h["exitType"] == "TP3" and abs(h["r"] - 3) < 0.05  # one target at 3R
    live = evaluate_agent(inp(g, now=h["signalTime"] + 3, peer=judas_market(1.1000, False)), cfg)
    s = live["setup"]
    assert s["entryType"] == "LIMIT" and 15 <= s["slPips"] <= 28 and abs(s["rrTarget"] - 3) < 0.02 and abs(s["rrTp2"] - 3) < 0.02
    assert abs(abs(s["tp1"] - s["entry"]) / abs(s["entry"] - s["sl"]) - 1.5) < 0.02  # break-even at 1.5R
    assert any("SMT" in w for w in s["anchors"]["pair"]["why"]) and validate_signal(live)["approved"]
    # EUR/USD took its own Asian high as well: no divergence, no trade
    assert not evaluate_agent(inp(g, peer=judas_market(1.1000, False, eur_break=True)), cfg)["history"]
    # no EUR/USD feed: the agent does not guess
    assert not evaluate_agent(inp(g), cfg)["dataQuality"]["ok"]


# ------------------------------------------------------------------ Agent 3 · AUD/CHF
def range_market(n=3000, seed=7):
    random.seed(seed)
    c, p = [], 0.5950
    t0 = 1_790_985_600
    for k in range(n):
        target = 0.5950 + 0.0045 * math.sin(2 * math.pi * k / 160) + 0.0012 * math.sin(2 * math.pi * k / 37)
        x = p + (target - p) * 0.35 + random.gauss(0, 0.0004)
        c.append(Candle(t0 + k * H1, p, max(p, x) + abs(random.gauss(0, 0.0002)), min(p, x) - abs(random.gauss(0, 0.0002)), x))
        p = x
    return c


def test_agent3_mean_reversion_range():
    cfg = PAIR_CONFIGS["AUD/CHF"]
    c = range_market()
    r = evaluate_agent(inp(c, tf="H1"), cfg)
    assert r["dataQuality"]["ok"] and r["history"]
    for h in r["history"]:
        lc_ok = h["exitType"] in ("SL", "BE_EXIT", "TP3", "TP2")
        assert lc_ok
    # every setup: market at the engulfing close, 50 % at the range's middle then BE, the rest at the opposite zone, R:R ≥ 1.8
    i = r["history"][0]["time"]
    idx = next(k for k, x in enumerate(c) if x.time == i)
    s = evaluate_agent(inp(c[:idx + 1], tf="H1"), cfg)["setup"]
    assert s["entryType"] == "MARKET" and s["params"]["partials"] == [0.5, 0, 0.5] and s["params"]["breakeven"]
    buy = s["direction"] == "BUY"
    assert (s["sl"] < s["entry"] < s["tp1"] < s["tp3"]) if buy else (s["sl"] > s["entry"] > s["tp1"] > s["tp3"])
    risk = abs(s["entry"] - s["sl"])
    assert 0.5 * abs(s["tp1"] - s["entry"]) / risk + 0.5 * abs(s["tp3"] - s["entry"]) / risk >= 1.8 - 1e-6
    assert any("RSI divergence" in w for w in s["anchors"]["pair"]["why"]) and any("engulfing" in w for w in s["anchors"]["pair"]["why"])


# ------------------------------------------------------------------ primitives, lifecycle, speed
def test_fractal_swings_and_fvg():
    c = build(T0, [1.0, 1.1, 1.2, 1.1, 1.0, 1.1, 1.4, 1.5], 1.0, w=0.0)
    hi, lo = swing_flags(c)
    assert hi[2] and lo[4] and not hi[3]
    g = gaps(c, 2, len(c) - 1, True, 0.01)
    assert g and g[-1].bottom == c[g[-1].index - 2].high and g[-1].top == c[g[-1].index].low


def test_limit_cancelled_when_the_target_comes_first():
    c = [Candle(0, 1.0, 1.001, 0.999, 1.0), Candle(300, 1.0, 1.0005, 0.990, 0.991)]
    p = {"side": "SELL", "entryType": "LIMIT", "entry": 1.002, "sl": 1.004, "tp1": 0.999, "tp2": 0.995, "tp3": 0.995, "expiryTime": 3600,
         "marketFillTime": None, "cancelIfTp1BeforeFill": True, "cancelLevel": 0.995, "partials": [0, 0, 1], "spread": 0, "slippage": 0}
    lc = simulate_lifecycle(c, p, 0)
    assert lc["state"] == "CANCELLED" and lc["events"][-1]["price"] == 0.995


def test_fast_execution_on_60_days_of_m5():
    """A new M5 close re-reads today only: finished days come from the day cache."""
    cfg = PAIR_CONFIGS["EUR/USD"]
    days = [eur_market()[288:] for _ in range(42)]
    c = [Candle(T0 + k * M5 - 41 * 86400, x.open, x.high, x.low, x.close) for k, x in enumerate(sum(days, []))]
    assert len(by_day(c)) == 42
    t = time.perf_counter()
    cold = evaluate_agent(inp(c), cfg)
    t_cold = time.perf_counter() - t
    t = time.perf_counter()
    evaluate_agent(inp(c), cfg)
    t_warm = time.perf_counter() - t
    assert cold["dataQuality"]["ok"] and len(cold["history"]) >= 20  # one trade a day (one at a time, two a day at most)
    assert t_warm < t_cold and t_warm < 0.5
    asian_sweep.PARAMS  # the plan's own numbers are the config's
    assert cfg["params"]["maxSweepPips"] == 20 and cfg["params"]["expiryBars"] == 12


# ------------------------------------------------------------------ global risk manager
def test_usd_correlation_and_daily_circuit_breaker():
    from app.db import SessionLocal, init_db
    from app.models import Signal

    init_db()
    now = int(time.time())
    with SessionLocal() as db:
        db.query(Signal).delete()
        db.add(Signal(id="EURUSD-A1-1", symbol="EUR/USD", setup="AGENT", direction="BUY", entry_type="LIMIT", entry=1.1, sl=1.099, tp1=1.101,
                      tp2=1.102, tp3=1.102, rr_tp2=2, score=100, signal_time=now, state="OPEN", params={}, payload={}))
        db.commit()
        gbp = {"spec": {"symbol": "GBPUSD", "displaySymbol": "GBP/USD"}, "setup": {"id": "GBPUSD-A2-1", "direction": "BUY"}}
        assert not usd_check(gbp, db)["passed"]  # both short USD, the first not at break-even yet: refused
        assert usd_check({**gbp, "setup": {"id": "x", "direction": "SELL"}}, db)["passed"]  # the other way: fine
        db.query(Signal).filter(Signal.id == "EURUSD-A1-1").update({"state": "TP1_HIT"})  # stop at break-even: USD risk gone
        db.commit()
        assert usd_check(gbp, db)["passed"]
        assert daily_loss_check(db, now)["passed"]
        for k, rm in enumerate((-1.0, -1.0, -0.6)):
            db.add(Signal(id=f"L{k}", symbol="AUD/CHF", setup="AGENT", direction="BUY", entry_type="MARKET", entry=1, sl=0.99, tp1=1.01, tp2=1.02,
                          tp3=1.02, rr_tp2=2, score=100, signal_time=now, state="CLOSED", outcome="LOSS", r_multiple=rm,
                          exit_time=max(day_start(now), now - 60), params={}, payload={}))
        db.commit()
        out = daily_loss_check(db, now)
        assert not out["passed"] and "LOCK_UNTIL_NEXT_DAY" in out["detail"]  # −2.6 %: every agent locked until 00:00
        db.query(Signal).delete()
        db.commit()
