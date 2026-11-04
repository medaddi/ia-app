"""The 4 pair agents (each on its plan proven on 2 years of H1 / H4), the chart overlay each one emits, and the risk
coordinator and delivery, on hand-built markets."""

import calendar
import math
import time

from app.agent.validator import validate_signal
from app.agents.engine import evaluate_agent
from app.agents.registry import AGENT_CONFIGS, AGENTS
from app.core.instrument_specs import pips_to_price, price_to_pips, usd_direction
from app.core.quant_primitives import fvg_at, is_swing_high_now, is_swing_low_now, mt, order_block, ote
from app.core.risk_guard import coordinate, usd_exposure
from app.strategies.service import STRATEGY_DEFS
from app.strategies.shared.lifecycle import simulate_lifecycle
from app.strategies.shared.types import Candle

M5, H1, H4 = 300, 3600, 14400
DAY = calendar.timegm((2026, 11, 10, 0, 0, 0))  # a Tuesday 00:00 UTC


def build(t0, closes, start, w, step=M5):
    c, p = [], start
    for k, x in enumerate(closes):
        o = p + (x - p) * 0.2
        c.append(Candle(t0 + k * step, o, max(o, x) + w, min(o, x) - w, x))
        p = x
    return c


def inp(c, now=None, events=None, tf="H1", price=0):
    step = {"M5": M5, "H1": H1, "H4": H4}[tf]
    return {"candles": {tf: c}, "peer": None, "nowSec": now or c[-1].time + step + 5, "livePrice": price, "spread": None,
            "isRealData": True, "dataSource": "test", "isMarketOpen": True, "day": {"trades": 0, "losses": 0},
            "news": {"events": events or [], "source": "test"}}


def run(pair, c, **kw):
    return evaluate_agent(inp(c, tf=AGENTS[pair].tf, **kw), AGENTS[pair], AGENT_CONFIGS[pair])


def range_market(last_open, base, amp, step=H1, n=320):
    """A quiet zig-zag range, then a last candle (opening at `last_open`) closing well below the channel low."""
    t0 = last_open - (n - 1) * step
    c = build(t0, [base + amp * math.sin(k / 3) for k in range(n - 1)], base, amp / 10, step)
    low = min(x.low for x in c[-40:])
    c.append(Candle(last_open, c[-1].close, c[-1].close + amp / 10, low - 3.2 * amp, low - 3 * amp, 0))
    return c


def trend_market(base=3000.0):
    """Gold: an uptrend (EMA50 > EMA200), a flat zig-zag, then an H1 close well above the 20-hour high."""
    t0 = DAY + 14 * H1 - 319 * H1
    c = []
    for i in range(319):
        m = base + 0.5 * min(i, 250) + 3 * math.sin(i)
        c.append(Candle(t0 + i * H1, m - 1, m + 4, m - 4, m + 1, 0))
    top = max(x.high for x in c[-20:])
    c.append(Candle(t0 + 319 * H1, top - 1, top + 12, top - 2, top + 10, 0))
    return c


def gbp_market():
    return range_market(DAY + 8 * H4, 1.3000, 0.0020, step=H4, n=300)


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
    o = ote(2005.0, 1995.0)
    assert abs(o.ote_618 - 2001.18) < 1e-9 and abs(o.ote_786 - 2002.86) < 1e-9
    seq = [Candle(k, 1.0, 1.0 + k * 0.01, 0.99, 1.0 + (0.005 if k % 2 else -0.005)) for k in range(12)]
    ob = order_block(seq, 11, False, 10)
    assert ob and seq[ob.index].close > seq[ob.index].open


# ------------------------------------------------------------------ the 4 agents
def test_the_four_agents_and_their_plans():
    assert list(AGENTS) == list(STRATEGY_DEFS) == ["XAU/USD", "EUR/USD", "GBP/USD", "AUD/CHF"]
    for pair, ag in AGENTS.items():
        assert ag.target_range == (2.0, 2.0) and ag.test["unseen"]["totalR"] > 0 and ag.test["costsX2"] > 0  # held up on unseen history
        assert ag.tf in ("H1", "H4") and AGENT_CONFIGS[pair]["live"]
    assert AGENT_CONFIGS["XAU/USD"]["style"] == "trend" and AGENT_CONFIGS["EUR/USD"]["style"] == "reversal"
    # EUR/USD trades 00–06 GMT (01:00–07:00 Morocco): a candle opened 02:00 GMT may signal at its 03:00 close, 09:00 may not
    assert STRATEGY_DEFS["EUR/USD"].canSignalAt(DAY + 3 * H1) and not STRATEGY_DEFS["EUR/USD"].canSignalAt(DAY + 10 * H1)
    assert STRATEGY_DEFS["AUD/CHF"].canSignalAt(DAY + 24 * H1) and not STRATEGY_DEFS["AUD/CHF"].canSignalAt(DAY + 12 * H1)


def test_gold_breakout_in_the_trend_one_2r_target_and_its_chart():
    r = run("XAU/USD", trend_market())
    s = r["setup"]
    assert r["status"] == "SIGNAL" and r["canNotify"] and s["direction"] == "BUY" and s["entryType"] == "MARKET"
    assert abs(s["rrTarget"] - 2.0) < 0.05 and s["params"]["maxBars"] == 48 and s["params"]["partials"] == [0, 0, 1] and not s["params"]["breakeven"]
    assert any("Trend up" in w for w in s["anchors"]["pair"]["why"]) and validate_signal(r)["approved"]
    ov = r["overlay"]
    assert ov["agentId"] == "XAUUSD_TrendBreakout_Agent" and ov["fsmState"] == "IN_TRADE" and ov["tradeExecutionBox"]
    assert any(m["text"] == "BREAKOUT" for m in ov["markers"])


def test_eur_fade_only_in_the_asian_hours():
    r = run("EUR/USD", range_market(DAY + 2 * H1, 1.1000, 0.0008))  # the stretch opens at 02:00 GMT: faded
    s = r["setup"]
    assert r["status"] == "SIGNAL" and s["direction"] == "BUY" and abs(s["rrTarget"] - 2.0) < 0.05 and s["params"]["maxBars"] == 48
    assert any("00:00–06:00 GMT" in w for w in s["anchors"]["pair"]["why"])
    r2 = run("EUR/USD", range_market(DAY + 10 * H1, 1.1000, 0.0008))  # the same stretch at 10:00 GMT: no trade
    assert not (r2["setup"] and r2["setup"]["isFresh"]) and r2["overlay"]["fsmState"] in ("IDLE", "ARMED")


def test_audchf_fade_across_midnight():
    r = run("AUD/CHF", range_market(DAY + 23 * H1, 0.5700, 0.0010))  # 23:00 GMT: inside 22–05
    assert r["status"] == "SIGNAL" and r["setup"]["direction"] == "BUY" and r["setup"]["params"]["maxBars"] == 48


def test_gbp_fade_needs_no_strong_trend():
    r = run("GBP/USD", gbp_market())
    assert r["status"] == "SIGNAL" and r["setup"]["direction"] == "BUY" and r["setup"]["params"]["maxBars"] == 12
    up = build(DAY - 299 * H4, [1.2 + 0.002 * k for k in range(300)], 1.2, 0.0002, H4)  # a strong trend: ADX ≥ 35
    r2 = run("GBP/USD", up)
    assert not (r2["setup"] and r2["setup"]["isFresh"]) and r2["overlay"]["fsmState"] == "COOLDOWN"


def test_one_trade_at_a_time():
    """While a trade runs, the agent takes no other: two stretches in a row give one trade."""
    c = range_market(DAY + 2 * H1, 1.1000, 0.0008)
    low = c[-1].low
    c.append(Candle(c[-1].time + H1, c[-1].close, c[-1].close + 0.0001, low - 0.0010, low - 0.0008, 0))  # 03:00: a second, lower close
    setups = AGENTS["EUR/USD"].scan(c)["setups"]
    assert len([x for x in setups if x["time"] >= c[-2].time]) == 1


def test_news_is_a_note_never_a_block():
    c = range_market(DAY + 2 * H1, 1.1000, 0.0008)
    sig = run("EUR/USD", c)["setup"]["signalTime"]
    news = [{"time": sig + 20 * 60, "currency": "EUR", "title": "ECB rate", "impact": "High"}]
    r = run("EUR/USD", c, now=sig + 3, events=news)
    assert r["status"] == "SIGNAL" and r["canNotify"]
    note = next(x for x in r["checklist"] if x["key"] == "news")
    assert not note["passed"] and not note["required"] and "ECB" in note["detail"]


def test_fast_on_two_years_of_h1():
    c = range_market(DAY + 2 * H1, 1.1000, 0.0008, n=12500)
    run("EUR/USD", c)
    t = time.perf_counter()
    run("EUR/USD", c)
    assert time.perf_counter() - t < 2.0


def test_partial_and_break_even_plus_offset():
    c = [Candle(0, 100, 100.2, 99.9, 100), Candle(300, 100, 100.1, 98.4, 98.5), Candle(600, 98.5, 100.5, 98.4, 100.3)]
    p = {"side": "SELL", "entryType": "MARKET", "entry": 100, "sl": 101, "tp1": 98.5, "tp2": 96, "tp3": 96, "expiryTime": None,
         "marketFillTime": 0, "cancelIfTp1BeforeFill": False, "partials": [0.5, 0, 0.5], "breakeven": True, "beOffset": 0.2, "spread": 0, "slippage": 0}
    lc = simulate_lifecycle(c, p, 1)
    assert lc["state"] == "CLOSED" and lc["events"][-1]["price"] == 99.8 and abs(lc["rMultiple"] - (0.75 + 0.1)) < 1e-9


# ------------------------------------------------------------------ the risk coordinator
def test_risk_notes_never_block_and_the_trader_keeps_the_risk():
    from app.db import SessionLocal, init_db
    from app.models import Signal

    init_db()
    now = int(time.time())

    def add(id_, sym, side, state="OPEN"):
        db.add(Signal(id=id_, symbol=sym, setup="AGENT", direction=side, entry_type="MARKET", entry=1, sl=0.99, tp1=1.01, tp2=1.02, tp3=1.02,
                      rr_tp2=2, score=100, signal_time=now, state=state, params={}, payload={}))
        db.commit()

    with SessionLocal() as db:
        db.query(Signal).delete()
        db.commit()
        assert usd_exposure("GBP/USD", "BUY", db)["count"] == 0
        add("A", "EUR/USD", "BUY")
        add("B", "XAU/USD", "BUY")  # two short-USD trades not at break-even
        assert usd_exposure("GBP/USD", "BUY", db)["count"] == 2 and usd_exposure("GBP/USD", "SELL", db)["count"] == 0
        r = run("GBP/USD", gbp_market())
        sig = r["setup"]["signalTime"]
        news = {**r["news"], "blocked": True, "detail": "USD CPI at 13:30"}
        d = coordinate({**r, "news": news}, db, now=sig + 3)
        # still sent: the correlated USD trades and the news are notes, the lots are the full 1 % table
        assert d["approved"] and not d["issues"] and d["riskPct"] == 1.0
        assert any("USD" in n for n in d["notes"]) and any("news" in n.lower() for n in d["notes"])
        db.query(Signal).delete()
        db.commit()


# ------------------------------------------------------------------ delivery: recorded first, Telegram and the app independent
def _eur_signal():
    c = range_market(DAY + 2 * H1, 1.1000, 0.0008)
    sig = run("EUR/USD", c)["setup"]["signalTime"]
    return run("EUR/USD", c, now=sig + 3, price=c[-1].close)


def test_a_setup_is_recorded_then_sent_to_telegram_with_retry(monkeypatch):
    import asyncio

    from app.db import SessionLocal, init_db
    from app.models import Signal
    from app.store import set_setting
    from app.strategies.exunu import build_exunu_result
    from app.telegram import bot

    init_db()
    r = _eur_signal()
    res = build_exunu_result(r)
    res["consensus"] = coordinate(r, None)

    async def fake_run(symbol, *a, **k):
        return res

    calls = {"n": 0, "fail": True}

    async def fake_send(token, chat_id, text, markup=None, protect=True):
        calls["n"] += 1
        return {"success": False, "error": "network"} if calls["fail"] else {"success": True, "message_id": 1}

    monkeypatch.setattr(bot, "run_exunu", fake_run)
    monkeypatch.setattr(bot, "send_message", fake_send)
    with SessionLocal() as db:
        db.query(Signal).delete()
        db.commit()
        set_setting(db, "telegram", {"enabled": False})
    # Telegram off: the trade is still recorded (the trade-management agent and the app follow it)
    out = asyncio.run(bot.dispatch_setup("EUR/USD", manual=False))
    assert not out["success"] and out.get("recorded")
    with SessionLocal() as db:
        assert db.get(Signal, r["setup"]["id"]).recipients == 0
        set_setting(db, "telegram", {"enabled": True, "botToken": "x", "chatId": "123"})
    # Telegram on but failing: nothing lost, the claim is released and the next tick retries
    out = asyncio.run(bot.dispatch_setup("EUR/USD", manual=False))
    assert not out["success"] and calls["n"] == 1
    with SessionLocal() as db:
        assert db.get(Signal, r["setup"]["id"]).recipients == 0
    calls["fail"] = False
    out = asyncio.run(bot.dispatch_setup("EUR/USD", manual=False))
    assert out["success"] and out["recipients"] == 1
    assert asyncio.run(bot.dispatch_setup("EUR/USD", manual=False))["error"] == "This setup was already sent."
    with SessionLocal() as db:
        db.query(Signal).delete()
        db.commit()
        set_setting(db, "telegram", {"enabled": True, "botToken": "", "chatId": ""})


def test_the_notification_carries_the_whole_order():
    """A new order is placed straight from the notification: side + order type, entry, SL, TP1, TP2, lot."""
    from app.push import trade_message
    from app.strategies.exunu import build_exunu_result, to_ai_signal
    from app.telegram import bot

    r = _eur_signal()
    res = build_exunu_result(r)
    res["consensus"] = coordinate(r, None)
    s = r["setup"]
    signal = to_ai_signal(res)
    m = trade_message(signal, 0.25)
    assert m["title"] == "🟢 BUY MARKET · EUR/USD" and m["urgent"]
    assert m["body"] == f"Entry {s['entry']:.5f} | SL {s['sl']:.5f} | TP1 {s['tp1']:.5f} | TP2 {s['tp3']:.5f} | LOT 0.25"
    tg = bot.format_signal_message(signal, {"lots": 0.25}).split("\n")
    assert tg[0] == "🟢 <b>BUY | EUR/USD</b>" and not any("Valid until" in x for x in tg)
