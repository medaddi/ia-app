"""
"London breakout" on H1 (GBP/USD).

Asian range: the high and low of the H1 candles opening 00:00–06:00 GMT (at least 5 of them).
Breakout: the first H1 candle opening 07:00–10:00 GMT (closing by 11:00) that closes beyond the range with a strong body
(at least half its range) and in its outer third → MARKET at that close. A range wider than 3 × ATR(14) is skipped.
Stop: the opposite side of the Asian range. Target: 2R. Closed at market after 14 H1 candles (end of day) if neither is hit.
One trade a day, replayed in order like the backtest.
"""

from typing import Optional

from ..shared.common import HISTORY_MAX, item, new_result, target_hit_pct, to_signal_json, history_stats, tp_options, trade_record
from ..shared.drawings import trade_drawings
from ..shared.indicators import atr_series, ema_series
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, snap_sl, snap_tp, to_pips
from ..shared.types import Candle, closed_only

H1 = 3600


def _hour(t: int) -> int:
    return (t // 3600) % 24


def asian_ranges(c: list[Candle], cfg: dict) -> dict[int, dict]:
    """day (unix // 86400) → {hi, lo, n, t0}: the Asian range of each day."""
    S = cfg["session"]
    out: dict[int, dict] = {}
    for x in c:
        if S["asiaStartHour"] <= _hour(x.time) < S["asiaEndHour"]:
            r = out.setdefault(x.time // 86400, {"hi": x.high, "lo": x.low, "n": 0, "t0": x.time})
            r["hi"], r["lo"], r["n"] = max(r["hi"], x.high), min(r["lo"], x.low), r["n"] + 1
    return out


def _setup_at(c: list[Candle], i: int, atr: list[float], ranges: dict, cfg: dict) -> Optional[dict]:
    """The breakout at candle i, if it is one."""
    S, B = cfg["session"], cfg["breakout"]
    x = c[i]
    if not (S["asiaEndHour"] <= _hour(x.time) < S["breakoutEndHour"]) or not (atr[i] > 0):
        return None
    r = ranges.get(x.time // 86400)
    if not r or r["n"] < S["minAsiaCandles"] or r["hi"] <= r["lo"] or r["hi"] - r["lo"] > B["maxRangeAtr"] * atr[i]:
        return None
    span = x.high - x.low
    if span <= 0 or abs(x.close - x.open) < B["minBodyPct"] * span:
        return None
    if x.close > r["hi"] and (x.close - x.low) / span >= B["closeOuterThird"]:
        return {"buy": True, "index": i, "entry": x.close, "sl": r["lo"], "range": r, "atr": atr[i]}
    if x.close < r["lo"] and (x.high - x.close) / span >= B["closeOuterThird"]:
        return {"buy": False, "index": i, "entry": x.close, "sl": r["hi"], "range": r, "atr": atr[i]}
    return None


def _build(c: list[Candle], b: dict, cfg: dict, spread: float, last: int) -> dict:
    R, FIL, spec = cfg["risk"], cfg["filters"], cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    buy, i = b["buy"], b["index"]
    entry, sl = round_to(b["entry"], d), snap_sl(b["sl"], buy, d)
    unit = abs(entry - sl)
    mark = lambda k: snap_tp(entry + k * unit if buy else entry - k * unit, buy, d)  # noqa: E731
    tp1, tp2, tp3 = mark(R["tp1R"]), mark(R["tp2R"]), mark(R["capR"])
    signal_time = c[i].time + H1
    params = {"side": "BUY" if buy else "SELL", "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": None, "marketFillTime": signal_time, "cancelIfTp1BeforeFill": False, "partials": R["partials"],
              "breakeven": R["breakeven"], "maxBars": R["maxBars"], "spread": spread, "slippage": FIL["slippagePips"] * pip}
    f = lambda v: to_fixed(v, d)  # noqa: E731
    rg = b["range"]
    return {
        "id": f"{spec['symbol']}-LB-{c[i].time}", "setup": "LONDON", "direction": "BUY" if buy else "SELL", "entryType": "MARKET",
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "tp2Source": f"{js_str(R['tp2R'])}R mark", "tp3Source": f"{js_str(R['capR'])}R target",
        "rrTp2": rr(entry, sl, tp2), "rrTarget": rr(entry, sl, tp3), "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": signal_time + R["marketValidMin"] * 60,
        "invalidation": f"SL {f(sl)} (the {'low' if buy else 'high'} of the Asian range); closed at market after {R['maxBars']} H1 candles",
        "isFresh": i == last, "lifecycle": simulate_lifecycle(c, params, i + 1, None, None, None), "params": params,
        "anchors": {"london": {"direction": "BUY" if buy else "SELL", "rangeHigh": round_to(rg["hi"], d), "rangeLow": round_to(rg["lo"], d),
                               "rangeStart": rg["t0"], "time": c[i].time, "atr": round_to(b["atr"], d)}},
    }


def evaluate_london(inp: dict, cfg: dict) -> dict:
    spec = cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    now = inp["nowSec"]
    c = closed_only(inp["candles"].get("H1") or [], H1, now)[-cfg["history"]:]
    last = len(c) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (c[last].close if c else 0)
    S, B, T, R, FIL = cfg["session"], cfg["breakout"], cfg["trend"], cfg["risk"], cfg["filters"]
    W = cfg["scoring"]["weights"]
    spread = inp["spread"] if inp["spread"] is not None else FIL["assumedSpreadPips"] * pip
    result = new_result(spec, cfg, inp, price)

    stale = inp["isMarketOpen"] and len(c) > 0 and now - (c[last].time + H1) > 3 * 3600
    if not inp["isRealData"] or len(c) < T["emaSlow"] + 30 or stale:
        result["dataQuality"] = {"ok": False, "source": inp["dataSource"],
                                 "reason": "Live feed unavailable (synthetic candles): no analysis" if not inp["isRealData"]
                                 else "Last H1 candle is stale (feed paused)" if stale else f"Not enough history (H1 {len(c)})"}
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    closes = [x.close for x in c]
    atr = atr_series(c, cfg["atrPeriod"])
    ef, es = ema_series(closes, T["emaFast"]), ema_series(closes, T["emaSlow"])
    ranges = asian_ranges(c, cfg)

    latest = None
    past: list[dict] = []
    i = T["emaSlow"] + 10
    while i <= last:
        b = _setup_at(c, i, atr, ranges, cfg)
        if not b:
            i += 1
            continue
        s = _build(c, b, cfg, spread, last)
        latest = (b, s)
        lc = s["lifecycle"]
        if lc["state"] == "CLOSED":
            past.append(trade_record(s, H1, c, i))
        if lc["state"] != "CLOSED":
            break
        # one breakout a day: the next one is looked for from the next day's Asian session at the earliest
        exit_i = next((j for j in range(i + 1, last + 1) if c[j].time == lc["exitTime"]), last)
        next_day = (c[i].time // 86400 + 1) * 86400
        i = max(exit_i + 1, next((j for j in range(i + 1, last + 1) if c[j].time >= next_day), last + 1))

    result["history"] = past[-HISTORY_MAX:]
    result["historyStats"] = history_stats(past)

    trend_now = 1 if ef[last] > es[last] and c[last].close > es[last] else -1 if ef[last] < es[last] and c[last].close < es[last] else 0
    word = {1: "bullish", -1: "bearish", 0: "flat"}
    trend_detail = (f"EMA{T['emaFast']} {f(ef[last])} {'>' if ef[last] > es[last] else '<'} EMA{T['emaSlow']} {f(es[last])} (H1, context only)")
    result["bias"] = {"direction": "BULLISH" if trend_now == 1 else "BEARISH" if trend_now == -1 else "NEUTRAL", "detail": trend_detail}
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    ccys = "/".join(FIL["news"]["currencies"])
    result["news"] = {"blocked": news["blocked"], "source": inp["news"]["source"],
                      "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else f"No high-impact {ccys} news within ±30 min",
                      "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None}

    today = ranges.get(now // 86400) or ranges.get(c[last].time // 86400)
    setup = None
    if latest and (latest[1]["lifecycle"]["state"] != "CLOSED" or latest[0]["index"] >= last - R["showLastSetupBars"]):
        setup = latest[1]
    day = inp["day"]
    window = f"{S['asiaEndHour']:02d}:00–{S['breakoutEndHour']:02d}:00 GMT"
    if setup:
        b = latest[0]
        buy, rg = b["buy"], b["range"]
        x = c[b["index"]]
        span = x.high - x.low or 1
        nb = news_block(setup["signalTime"], inp["news"]["events"], FIL["news"])
        checklist = [
            item("range", f"Asian range {S['asiaStartHour']:02d}:00–{S['asiaEndHour']:02d}:00 GMT, no wider than {js_str(B['maxRangeAtr'])} × ATR(14)", "نطاق الجلسة الآسيوية", True,
                 f"{f(rg['lo'])} – {f(rg['hi'])} ({js_str(round(to_pips(spec, rg['hi'] - rg['lo']), 1))} pips)", W["range"], True),
            item("breakout", f"H1 close {'above' if buy else 'below'} the Asian range between {window}", "إغلاق خارج النطاق", True,
                 f"Close {f(x.close)} at {fmt_time(x.time + H1)}", W["breakout"], True),
            item("strength", "Strong breakout candle: body ≥ half its range, close in its outer third (no pin bar)", "شمعة اختراق قوية", True,
                 f"Body {abs(x.close - x.open) / span * 100:.0f}% of the candle", W["strength"], True),
            item("stop", f"Stop at the opposite side of the Asian range", "الستوب في الطرف الآخر", True, f"SL {f(setup['sl'])} ({js_str(setup['slPips'])} pips)", W["stop"], True),
            item("target", f"One target at {js_str(R['capR'])}R, closed at the end of the day", "هدف واحد", True, f"TP {f(setup['tp3'])}", W["target"], True),
            item("oneTrade", "One breakout a day", "صفقة واحدة في اليوم", True, "No other trade open on this pair", 0, True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
            item("spread", f"Spread <= {js_str(FIL['maxSpreadPips'])} pips", "السبريد مقبول", spread <= FIL["maxSpreadPips"] * pip,
                 f"Spread {to_fixed(spread / pip, 1)} pips{' (assumed)' if inp['spread'] is None else ''}", 0, True),
            item("daily", f"Max {FIL['maxTradesPerDay']} trade / stop after {FIL['maxLossesPerDay']} loss per day", "حد الصفقات اليومي",
                 day["trades"] < FIL["maxTradesPerDay"] + (1 if setup["isFresh"] else 0) and day["losses"] < FIL["maxLossesPerDay"],
                 f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
        ]
    else:
        h = _hour(now)
        if today and S["asiaStartHour"] <= h < S["asiaEndHour"]:
            progress = f"Asian range forming: {f(today['lo'])} – {f(today['hi'])} (breakout window {window})"
        elif today and S["asiaEndHour"] <= h < S["breakoutEndHour"]:
            progress = f"Waiting for a strong H1 close beyond the Asian range {f(today['lo'])} – {f(today['hi'])} before {S['breakoutEndHour']:02d}:00 GMT"
        else:
            progress = f"London window closed: the next Asian range builds from {S['asiaStartHour']:02d}:00 GMT, breakout {window}"
        result["facts"]["progress"] = progress
        checklist = [
            item("range", "Asian range defined", "نطاق الجلسة الآسيوية", bool(today), f"{f(today['lo'])} – {f(today['hi'])}" if today else "Not yet", W["range"], True),
            item("breakout", f"H1 close beyond the range between {window}", "إغلاق خارج النطاق", False, progress, W["breakout"], True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not news["blocked"], result["news"]["detail"], 0, True),
        ]
    result["checklist"] = checklist
    result["setup"] = setup
    result["tpReach"] = tp_options(past, setup, d)
    if result["tpReach"] is not None:
        result["tpReach"]["targetHit"] = target_hit_pct(past, setup)
    failed = [x for x in checklist if x["required"] and not x["passed"]]
    result["score"] = score_checklist(checklist) if setup else 0
    result["rejection"] = f"{failed[0]['rule']}: {failed[0]['detail']}" if failed else None
    result["status"] = classify(result["score"], not failed, cfg["scoring"]["thresholds"]) if setup else "NO_TRADE"
    if setup and result["status"] == "SIGNAL":
        result["signal"] = to_signal_json(spec, cfg["strategy"], setup, result["score"], cfg["timeframes"], checklist)
    result["canNotify"] = bool(result["status"] == "SIGNAL" and setup and setup["isFresh"] and setup["lifecycle"]["state"] == "OPEN" and inp["isMarketOpen"])

    sym = spec["symbol"]
    drawings = []
    shown = (setup["anchors"]["london"] if setup else None)
    rg_hi, rg_lo, rg_t0 = ((shown["rangeHigh"], shown["rangeLow"], shown["rangeStart"]) if shown else
                           (today["hi"], today["lo"], today["t0"]) if today else (None, None, None))
    if rg_hi is not None:
        drawings += [
            {"id": f"{sym}-AR-{rg_t0}", "layer": "levels", "kind": "box", "tf": "H1", "t1": rg_t0, "t2": None, "p1": rg_hi, "p2": rg_lo,
             "text": "Asian range", "color": "liquidity"},
            {"id": f"{sym}-AH-{rg_t0}", "layer": "levels", "kind": "hline", "tf": "H1", "t1": rg_t0, "t2": None, "p1": rg_hi, "text": "Asian high", "color": "muted", "style": "dashed"},
            {"id": f"{sym}-AL-{rg_t0}", "layer": "levels", "kind": "hline", "tf": "H1", "t1": rg_t0, "t2": None, "p1": rg_lo, "text": "Asian low", "color": "muted", "style": "dashed"},
        ]
    if setup:
        a = setup["anchors"]["london"]
        drawings.append({"id": f"{sym}-LB-M-{a['time']}", "layer": "structure", "kind": "marker", "tf": "H1", "t1": a["time"], "t2": None, "p1": setup["entry"],
                         "text": "London breakout", "color": "bull" if a["direction"] == "BUY" else "bear", "position": "below" if a["direction"] == "BUY" else "above"})
        drawings.extend(trade_drawings(setup, "H1", ""))
    result["drawings"] = drawings
    result["facts"].update({
        "price": price, "spread": spread, "trend": word[trend_now], "trendH1": word[trend_now], "atrH1": round_to(atr[last], d),
        "asianHigh": round_to(today["hi"], d) if today else None, "asianLow": round_to(today["lo"], d) if today else None,
        "ema50": round_to(ef[last], d), "ema200": round_to(es[last], d),
        "lastTrade": ({"id": latest[1]["id"], "state": latest[1]["lifecycle"]["state"], "outcome": latest[1]["lifecycle"]["outcome"],
                       "r": latest[1]["lifecycle"]["rMultiple"]} if latest else None),
    })
    st = result["status"]
    sd = setup["direction"] if setup else ""
    if not setup:
        result["headline"] = result["facts"]["progress"]
    elif st == "SIGNAL" and setup["isFresh"]:
        result["headline"] = f"{sd} market {f(setup['entry'])} · London breakout of the Asian range"
    elif st == "SIGNAL":
        result["headline"] = f"{sd} London breakout {fmt_time(setup['signalTime'])} · {setup['lifecycle']['state']}"
    else:
        result["headline"] = f"{sd} London breakout rejected: {failed[0]['rule']}" if failed else f"{sd} London breakout scored {result['score']}"
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])}" if st == "SIGNAL" else "إعداد غير مكتمل") if setup else "لا توجد صفقة حالياً"
    return result
