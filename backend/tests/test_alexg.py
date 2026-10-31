"""FXAlexG Set & Forget GPA: structure trend, W1/D1 AOI with 3 touches, H&S, grade, TP before the round level, 1:2 minimum."""

import copy
import gzip
import json
from pathlib import Path

from app.agent.validator import validate_signal
from app.strategies.alexg import strategy as S
from app.strategies.alexg.config import ALEXG_CONFIGS, grade_of
from app.strategies.service import STRATEGY_DEFS, normalize_symbol
from app.strategies.shared.types import Candle, candles_from_rows
from app.telegram.bot import format_signal_message

CFG = ALEXG_CONFIGS["USD/CAD"]
FIX = json.loads(gzip.open(Path(__file__).parent / "fixtures" / "gpa_USDCAD.json.gz", "rt", encoding="utf8").read())


def _input(now: int, market_open: bool = True) -> dict:
    return {"candles": {tf: candles_from_rows(rows) for tf, rows in FIX["candles"].items()}, "nowSec": now, "livePrice": 0, "spread": None,
            "isRealData": True, "dataSource": "fixture", "news": {"events": [], "source": "test"}, "isMarketOpen": market_open,
            "day": {"trades": 0, "losses": 0}}


def test_grading_scale():
    assert [grade_of(s, CFG) for s in (100, 80, 79, 70, 69, 60, 59, 0)] == ["A+", "A+", "B", "B", "C+", "C+", "NO TRADE", "NO TRADE"]


def test_real_signal_from_the_rules():
    """USD/CAD BUY recorded from the live feed: the 30m engulfing at the open after the AOI touch and the H4 rejection."""
    r = S.evaluate_alexg(_input(FIX["nowSec"]), CFG)
    s = r["setup"]
    assert r["status"] == "SIGNAL" and r["canNotify"] and s["id"] == FIX["setup"]["id"], r["headline"]
    assert (s["direction"], s["entry"]) == (FIX["setup"]["direction"], FIX["setup"]["entry"])
    # App rule: the target is the next zone capped at 2R (the recorded zone target was further), never below 1.5R
    assert s["tp3"] < FIX["setup"]["tp3"] and 1.5 <= s["rrTarget"] <= 2 and "2R" in s["tp3Source"]
    # The stop is snapped to the tick AWAY from the entry (recorded nearest-rounded: at most 1 tick wider, never tighter)
    assert 0 <= FIX["setup"]["sl"] - s["sl"] <= 0.00001 + 1e-12
    g = s["anchors"]["gpa"]
    assert g["grade"] == r["grade"] == FIX["grade"] and r["score"] == FIX["score"] >= 60
    assert g["aoi"]["touches"] >= 3 and g["aoi"]["tfs"] in ("D1", "W1", "D1+W1") and g["session"] in ("London open", "New York open")
    assert s["rrTarget"] >= 1.5 and s["params"]["partials"] == [0, 0, 1] and s["params"]["breakeven"] is False
    # Exactly the 10 confluences, 10% each, plus the required rules
    conf = [c for c in r["checklist"] if c["weight"] == 10]
    assert len(conf) == 10 and sum(c["passed"] for c in conf) * 10 == r["score"]
    assert next(c for c in conf if c["key"] == "engulf")["passed"] and next(c for c in conf if c["key"] == "aoi")["passed"]
    assert validate_signal(r)["approved"]


def test_no_signal_one_candle_earlier():
    """Before the engulfing closes there is no trade (no anticipation)."""
    r = S.evaluate_alexg(_input(FIX["nowSec"] - 1800), CFG)
    assert not (r["setup"] and r["setup"]["id"] == FIX["setup"]["id"])


def test_minimum_risk_reward_blocks_the_trade():
    cfg = copy.deepcopy(CFG)
    cfg["risk"]["minRr"] = 50  # the next zone can never give 1:50
    r = S.evaluate_alexg(_input(FIX["nowSec"]), cfg)
    assert not (r["setup"] and r["setup"]["id"] == FIX["setup"]["id"])


def _bar(t, o, h, lo, c):
    return Candle(t, o, h, lo, c)


def test_structure_trend_flips_only_on_a_body_close():
    from app.strategies.shared.indicators import avg_body_series
    from app.strategies.shared.structure import detect_structure, detect_swings

    # Up, a swing high at 1.10, pullback, a WICK above 1.10 (no flip), then a BODY close above (bullish)
    closes = [1.05, 1.06, 1.07, 1.08, 1.09, 1.10, 1.09, 1.08, 1.07, 1.06, 1.07, 1.08]
    c = [_bar(k * 3600, x - 0.002, x + 0.001, x - 0.003, x) for k, x in enumerate(closes)]
    c[5] = _bar(5 * 3600, 1.098, 1.105, 1.095, 1.100)  # swing high 1.105
    c.append(_bar(12 * 3600, 1.08, 1.108, 1.079, 1.099))  # wick above, close below → still no break
    _, trend = detect_structure(c, detect_swings(c, 2), avg_body_series(c, 3), 1e9)
    assert trend != "BULLISH"
    c.append(_bar(13 * 3600, 1.099, 1.112, 1.098, 1.110))  # body close above 1.105
    _, trend = detect_structure(c, detect_swings(c, 2), avg_body_series(c, 3), 1e9)
    assert trend == "BULLISH"


def test_pairs_and_message():
    assert list(STRATEGY_DEFS) == ["XAU/USD", "EUR/USD", "GBP/USD", "USD/CAD", "NZD/USD", "EUR/CHF", "NZD/CAD", "AUD/CAD", "AUD/CHF"]
    gpa = [p for p in ALEXG_CONFIGS if p not in ("EUR/USD", "GBP/USD")]
    assert all(STRATEGY_DEFS[p].entryTf == "M30" and STRATEGY_DEFS[p].tfs == ["M30", "H1", "H4"] for p in gpa)
    assert all(STRATEGY_DEFS[p].entryTf == "H4" and STRATEGY_DEFS[p].exit_rule for p in ("EUR/USD", "GBP/USD"))  # RSI(2) H4
    d = STRATEGY_DEFS["USD/CAD"]
    london_open_close = 1792738800 + 1800  # Tue 2026-10-27 08:00 London (07:00 UTC) candle closes
    assert d.canSignalAt(london_open_close + 1800) and not d.canSignalAt(1792738800 + 12 * 3600)  # 19:00 London: no signal
    assert normalize_symbol("eurchf") == "EUR/CHF" and normalize_symbol("EUR") == "EUR/USD" and normalize_symbol("nzd") == "NZD/USD"
    msg = format_signal_message({"symbol": "GBP/USD", "signalType": "BUY", "entryPrice": 1.3, "stopLoss": 1.298, "target1": 1.302, "target2": 1.304,
                                 "target3": 1.30697, "confidence": 80, "grade": "A+", "signalJson": {"setup": "GPA", "entry_type": "MARKET"}})
    assert "TP <code>1.30697</code> · 1:3.5" in msg and "TP1" not in msg and "Grade <b>A+</b> · 80%" in msg


def test_agent_answers_in_the_five_parts():
    from app.agent.agent import deterministic_answer

    r = S.evaluate_alexg(_input(FIX["nowSec"]), CFG)
    text = deterministic_answer([r], "en")
    for part in ("1. Trend Sync Check", "2. AOI Validation", "3. Confluence Checklist & Final Grade", "4. Final Verdict", "5. Trade Parameters"):
        assert part in text
    assert "TAKE TRADE" in text and "60% → C+" in text and f"SL {r['setup']['sl']:.5f}" in text


def test_trade_desk_blocks_late_entries_and_crowded_currencies():
    from app.agent.trade_desk import legs, review
    from app.db import SessionLocal, init_db
    from app.models import Signal

    r = S.evaluate_alexg(_input(FIX["nowSec"]), CFG)
    s = r["setup"]
    assert legs("USD/CAD", "BUY") == {"USD": 1, "CAD": -1} and legs("XAU/USD", "SELL") == {"XAU": -1, "USD": 1}
    assert review(r)["approved"]  # at the candle close, price = entry
    risk = s["entry"] - s["sl"]
    late = {**r, "price": s["entry"] + 0.6 * risk}  # the market ran 0.6R away before the send
    out = review(late)
    assert not out["approved"] and any(c["key"] == "drift" and not c["passed"] for c in out["checks"])
    stale = {**r, "dataQuality": {**r["dataQuality"], "stale": True, "reason": "last good"}}
    assert not review(stale)["approved"]

    init_db()
    with SessionLocal() as db:  # two open USD-long signals already: a third one is blocked
        for k, (sym, side) in enumerate((("EUR/USD", "SELL"), ("GBP/USD", "SELL"))):
            db.merge(Signal(id=f"T-EXPO-{k}", symbol=sym, setup="GPA", direction=side, entry_type="MARKET", entry=1, sl=1.01, tp1=0.99, tp2=0.98,
                            tp3=0.97, rr_tp2=2, score=70, signal_time=1, state="OPEN", params={}, payload={}))
        db.commit()
        out = review(r, db)
        assert not out["approved"] and any(c["key"] == "exposure" and not c["passed"] for c in out["checks"])
        for k in range(2):
            db.delete(db.get(Signal, f"T-EXPO-{k}"))
        db.commit()
        assert review(r, db)["approved"]
