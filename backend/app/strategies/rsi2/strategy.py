"""
"RSI(2) Connors pullback" on H4 (EUR/USD, GBP/USD).

Trend: BUY only if EMA50 > EMA200 and the H4 close is above EMA200 (mirror for SELL).
Entry: inside that trend, the H4 RSI(2) closes below the pair's extreme (EUR 10, GBP 5) for buys, above 100 − it for
sells → MARKET at that close (buying a sharp pullback in an uptrend).
Stop: entry ∓ slAtr × ATR(14, H4). Exit: the first H4 close back above EMA5 (buys) / below EMA5 (sells), at that
close; a 5R cap is only a safety target; closed at market after 48 H4 candles.
One trade at a time, replayed in order like the backtest.
"""

from typing import Optional

from ..shared.common import HISTORY_MAX, item, new_result, to_signal_json, history_stats, tp_options, trade_record
from ..shared.drawings import trade_drawings
from ..shared.indicators import atr_series, ema_series, rsi_series
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, snap_sl, snap_tp, to_pips
from ..shared.types import Candle, closed_only

H4 = 14400


def _trend(c: list[Candle], i: int, ef: list[float], es: list[float]) -> int:
    if ef[i] > es[i] and c[i].close > es[i]:
        return 1
    if ef[i] < es[i] and c[i].close < es[i]:
        return -1
    return 0


def exit_rule(c: list[Candle], side: str, period: int = 5):
    """The strategy exit used by the lifecycle (live tracking and backtests): close back over EMA5."""
    e5 = ema_series([x.close for x in c], period)
    buy = side == "BUY"
    return lambda i: e5[i] == e5[i] and ((c[i].close > e5[i]) if buy else (c[i].close < e5[i]))


def _setup_at(c, i, atr, ef, es, r2, cfg) -> Optional[dict]:
    if not (atr[i] > 0) or r2[i] != r2[i] or es[i] != es[i]:
        return None
    d = _trend(c, i, ef, es)
    lo = cfg["rsiBuyBelow"]
    if d == 1 and r2[i] < lo:
        return {"buy": True, "index": i, "entry": c[i].close, "sl": c[i].close - cfg["slAtr"] * atr[i], "atr": atr[i], "rsi": r2[i]}
    if d == -1 and r2[i] > 100 - lo:
        return {"buy": False, "index": i, "entry": c[i].close, "sl": c[i].close + cfg["slAtr"] * atr[i], "atr": atr[i], "rsi": r2[i]}
    return None


def _build(c, b, cfg, spread, last, e5) -> dict:
    R, FIL, spec = cfg["risk"], cfg["filters"], cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    buy, i = b["buy"], b["index"]
    entry, sl = round_to(b["entry"], d), snap_sl(b["sl"], buy, d)
    unit = abs(entry - sl)
    mark = lambda k: snap_tp(entry + k * unit if buy else entry - k * unit, buy, d)  # noqa: E731
    tp1, tp2, tp3 = mark(R["tp1R"]), mark(R["tp2R"]), mark(R["capR"])
    signal_time = c[i].time + H4
    valid_until = signal_time + R["marketValidMin"] * 60
    params = {"side": "BUY" if buy else "SELL", "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": None, "marketFillTime": signal_time, "cancelIfTp1BeforeFill": False, "partials": R["partials"],
              "breakeven": R["breakeven"], "maxBars": R["maxBars"], "spread": spread, "slippage": FIL["slippagePips"] * pip}
    rule = (lambda j: e5[j] == e5[j] and ((c[j].close > e5[j]) if buy else (c[j].close < e5[j]))) if cfg.get("exitAtEma", True) else None  # noqa: E731
    f = lambda v: to_fixed(v, d)  # noqa: E731
    return {
        "id": f"{spec['symbol']}-R2-{c[i].time}", "setup": "RSI2", "direction": "BUY" if buy else "SELL", "entryType": "MARKET",
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "tp2Source": f"{js_str(R['tp2R'])}R mark", "tp3Source": f"exit at the first H4 close {'above' if buy else 'below'} EMA{cfg['exitEma']} · {js_str(R['capR'])}R cap",
        "rrTp2": rr(entry, sl, tp2), "rrTarget": rr(entry, sl, tp3), "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": valid_until,
        "invalidation": f"SL {f(sl)}; exit at the first H4 close {'above' if buy else 'below'} EMA{cfg['exitEma']}; closed after {R['maxBars']} H4 candles",
        "isFresh": i == last, "lifecycle": simulate_lifecycle(c, params, i + 1, None, None, rule), "params": params,
        "exitRule": f"H4 close {'above' if buy else 'below'} EMA{cfg['exitEma']}",
        "anchors": {"rsi2": {"direction": "BUY" if buy else "SELL", "rsi": round(b["rsi"], 1), "level": cfg["rsiBuyBelow"] if buy else 100 - cfg["rsiBuyBelow"],
                             "ema5": round_to(e5[i], d), "atr": round_to(b["atr"], d), "time": c[i].time}},
    }


def evaluate_rsi2(inp: dict, cfg: dict) -> dict:
    spec = cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    now = inp["nowSec"]
    c = closed_only(inp["candles"].get("H4") or [], H4, now)[-cfg["history"]:]
    last = len(c) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (c[last].close if c else 0)
    T, R, FIL = cfg["trend"], cfg["risk"], cfg["filters"]
    W = cfg["scoring"]["weights"]
    spread = inp["spread"] if inp["spread"] is not None else FIL["assumedSpreadPips"] * pip
    result = new_result(spec, cfg, inp, price)

    stale = inp["isMarketOpen"] and len(c) > 0 and now - (c[last].time + H4) > max(3 * H4, 6 * 3600)
    if not inp["isRealData"] or len(c) < T["emaSlow"] + 30 or stale:
        result["dataQuality"] = {"ok": False, "source": inp["dataSource"],
                                 "reason": "Live feed unavailable (synthetic candles): no analysis" if not inp["isRealData"]
                                 else "Last H4 candle is stale (feed paused)" if stale else f"Not enough history (H4 {len(c)})"}
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    closes = [x.close for x in c]
    atr = atr_series(c, cfg["atrPeriod"])
    ef, es = ema_series(closes, T["emaFast"]), ema_series(closes, T["emaSlow"])
    e5 = ema_series(closes, cfg["exitEma"])
    r2 = rsi_series(closes, cfg["rsiPeriod"])

    latest = None
    past: list[dict] = []  # the trades the strategy closed (history list + target odds)
    i = T["emaSlow"] + 10
    while i <= last:
        b = _setup_at(c, i, atr, ef, es, r2, cfg)
        if not b:
            i += 1
            continue
        s = _build(c, b, cfg, spread, last, e5)
        latest = (b, s)
        lc = s["lifecycle"]
        if lc["state"] == "CLOSED":
            past.append(trade_record(s, H4, c, i))
        if lc["state"] != "CLOSED":
            break
        i = next((j for j in range(i + 1, last + 1) if c[j].time == lc["exitTime"]), last) + 1

    result["history"] = past[-HISTORY_MAX:]
    result["historyStats"] = history_stats(past)  # over every closed trade, not only the listed ones
    tp_past = past  # every closed trade feeds the target odds (the list above keeps only the recent ones)

    trend_now = _trend(c, last, ef, es)
    word = {1: "bullish", -1: "bearish", 0: "flat"}
    trend_detail = (f"EMA{T['emaFast']} {f(ef[last])} {'>' if ef[last] > es[last] else '<'} EMA{T['emaSlow']} {f(es[last])}, "
                    f"close {f(c[last].close)} {'>' if c[last].close > es[last] else '<'} EMA{T['emaSlow']}")
    result["bias"] = {"direction": "BULLISH" if trend_now == 1 else "BEARISH" if trend_now == -1 else "NEUTRAL", "detail": trend_detail}
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    ccys = "/".join(FIL["news"]["currencies"])
    result["news"] = {"blocked": news["blocked"], "source": inp["news"]["source"],
                      "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else f"No high-impact {ccys} news within ±30 min",
                      "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None}

    setup = None
    if latest and (latest[1]["lifecycle"]["state"] != "CLOSED" or latest[0]["index"] >= last - R["showLastSetupBars"]):
        setup = latest[1]
    lo = cfg["rsiBuyBelow"]
    day = inp["day"]
    if setup:
        b = latest[0]
        buy = b["buy"]
        nb = news_block(setup["signalTime"], inp["news"]["events"], FIL["news"])
        checklist = [
            item("trend", f"H4 trend: EMA{T['emaFast']} {'>' if buy else '<'} EMA{T['emaSlow']}, close {'above' if buy else 'below'} EMA{T['emaSlow']}", "اتجاه H4 واضح", True,
                 trend_detail if setup["isFresh"] else f"{'Bullish' if buy else 'Bearish'} trend at the entry", W["trend"], True),
            item("rsi", f"RSI(2) {'<' if buy else '>'} {js_str(lo if buy else 100 - lo)} (sharp pullback in the trend)", "RSI(2) متطرف", True,
                 f"RSI(2) {b['rsi']:.1f} at {fmt_time(c[b['index']].time + H4)}", W["rsi"], True),
            item("stop", f"Stop {js_str(cfg['slAtr'])} × ATR(14, H4)", "الستوب حسب ATR", True, f"SL {f(setup['sl'])} ({js_str(setup['slPips'])} pips)", W["stop"], True),
            item("exit", f"Exit at the first H4 close back {'above' if buy else 'below'} EMA{cfg['exitEma']}", "الخروج عند EMA5", True,
                 f"EMA{cfg['exitEma']} now {f(e5[last])}", W["exit"], True),
            item("oneTrade", "One trade at a time", "صفقة واحدة", True, "No other trade open on this pair", 0, True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
            item("spread", f"Spread <= {js_str(FIL['maxSpreadPips'])} pips", "السبريد مقبول", spread <= FIL["maxSpreadPips"] * pip,
                 f"Spread {to_fixed(spread / pip, 1)} pips{' (assumed)' if inp['spread'] is None else ''}", 0, True),
            item("daily", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} loss per day", "حد الصفقات اليومي",
                 day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"], f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
        ]
    else:
        progress = (f"Bullish H4 trend: waiting for RSI(2) < {js_str(lo)} (now {r2[last]:.1f})" if trend_now == 1
                    else f"Bearish H4 trend: waiting for RSI(2) > {js_str(100 - lo)} (now {r2[last]:.1f})" if trend_now == -1
                    else "No clear H4 trend (EMA50 / EMA200): no trade")
        result["facts"]["progress"] = progress
        checklist = [
            item("trend", "H4 trend: EMA50 vs EMA200 and close vs EMA200", "اتجاه H4 واضح", trend_now != 0, trend_detail, W["trend"], True),
            item("rsi", f"RSI(2) extreme in the trend direction", "RSI(2) متطرف", False, progress, W["rsi"], True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not news["blocked"], result["news"]["detail"], 0, True),
        ]
    result["checklist"] = checklist
    result["setup"] = setup
    result["tpReach"] = tp_options(tp_past, setup, cfg["spec"]["decimals"])
    failed = [x for x in checklist if x["required"] and not x["passed"]]
    result["score"] = score_checklist(checklist) if setup else 0
    result["rejection"] = f"{failed[0]['rule']}: {failed[0]['detail']}" if failed else None
    result["status"] = classify(result["score"], not failed, cfg["scoring"]["thresholds"]) if setup else "NO_TRADE"
    if setup and result["status"] == "SIGNAL":
        result["signal"] = to_signal_json(spec, cfg["strategy"], setup, result["score"], cfg["timeframes"], checklist)
    result["canNotify"] = bool(result["status"] == "SIGNAL" and setup and setup["isFresh"] and setup["lifecycle"]["state"] == "OPEN" and inp["isMarketOpen"])

    sym = spec["symbol"]
    drawings = [{"id": f"{sym}-E5", "layer": "levels", "kind": "hline", "tf": "H4", "t1": c[max(0, last - 12)].time, "t2": None, "p1": e5[last],
                 "text": f"EMA{cfg['exitEma']} (exit)", "color": "entry", "style": "dotted"}]
    if setup:
        a = setup["anchors"]["rsi2"]
        drawings.append({"id": f"{sym}-R2-{a['time']}", "layer": "structure", "kind": "marker", "tf": "H4", "t1": a["time"], "t2": None, "p1": setup["entry"],
                         "text": f"RSI(2) {a['rsi']}", "color": "bull" if a["direction"] == "BUY" else "bear", "position": "below" if a["direction"] == "BUY" else "above"})
        drawings.extend(trade_drawings(setup, "H4", ""))
    result["drawings"] = drawings
    result["facts"].update({
        "price": price, "spread": spread, "trend": word[trend_now], "trendH4": word[trend_now], "rsi2": round(r2[last], 1),
        "ema5": round_to(e5[last], d), "ema50": round_to(ef[last], d), "ema200": round_to(es[last], d), "atrH4": round_to(atr[last], d),
        "rsiLevel": lo,
        "lastTrade": ({"id": latest[1]["id"], "state": latest[1]["lifecycle"]["state"], "outcome": latest[1]["lifecycle"]["outcome"],
                       "r": latest[1]["lifecycle"]["rMultiple"]} if latest else None),
    })
    st = result["status"]
    sd = setup["direction"] if setup else ""
    if not setup:
        result["headline"] = result["facts"]["progress"]
    elif st == "SIGNAL" and setup["isFresh"]:
        result["headline"] = f"{sd} market {f(setup['entry'])} · RSI(2) {setup['anchors']['rsi2']['rsi']} · exit at EMA5"
    elif st == "SIGNAL":
        lcs = setup["lifecycle"]["state"]
        lcs = {"TP1_HIT": "running, 1R reached", "TP2_HIT": "running, 2R reached"}.get(lcs, lcs)
        result["headline"] = f"{sd} RSI(2) {fmt_time(setup['signalTime'])} · {lcs}"
    else:
        result["headline"] = f"{sd} RSI(2) setup rejected: {failed[0]['rule']}" if failed else f"{sd} RSI(2) setup scored {result['score']}"
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])}" if st == "SIGNAL" else "إعداد غير مكتمل") if setup else "لا توجد صفقة حالياً"
    return result
