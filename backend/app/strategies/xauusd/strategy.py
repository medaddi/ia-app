"""
XAUUSD (Gold) — "H1 Trend Breakout"

Trend (H1): BUY only if EMA50 > EMA200 and the close is above EMA200; SELL only on the mirror.
Entry: an H1 candle CLOSES beyond the highest high (buys) / lowest low (sells) of the previous 20 H1
candles with a body > 0.5 × ATR(14). MARKET entry at that close.
Stop: beyond the extreme of the last 4 candles ± 0.2 × ATR, at least 1 × ATR away; no trade above 3 × ATR.
Targets: TP1 = 1R (close 50%, stop to breakeven), TP2 = 2R (25%), TP3 = 3R (rest).
One trade at a time: the candles are replayed in order, and a new breakout only counts once the
previous trade has closed (exactly how the strategy was backtested).
"""

from typing import Optional

from ..shared.common import active_window, item, new_result, to_signal_json
from ..shared.drawings import level_drawings, trade_drawings
from ..shared.indicators import atr_series, ema_series
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.liquidity import daily_weekly_levels
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, to_pips
from ..shared.types import Candle, closed_only
from .config import XAU_CONFIG

H1_SEC = 3600


def _trend(c: list[Candle], i: int, ef: list[float], es: list[float]) -> int:
    if ef[i] > es[i] and c[i].close > es[i]:
        return 1
    if ef[i] < es[i] and c[i].close < es[i]:
        return -1
    return 0


def _breakout_at(c: list[Candle], i: int, atr: list[float], ef: list[float], es: list[float], cfg: dict) -> Optional[dict]:
    """The pure entry rules on candle i (closed). Returns the order levels, or None."""
    B, R = cfg["breakout"], cfg["risk"]
    a = atr[i]
    if not (a > 0):
        return None
    x = c[i]
    trend = _trend(c, i, ef, es)
    window = c[i - B["lookback"]:i]
    hi, lo = max(y.high for y in window), min(y.low for y in window)
    ref_bars = c[i - R["stopRefBars"] + 1:i + 1]
    if trend == 1 and x.close > hi and x.close - x.open > B["minBodyAtr"] * a:
        buy, level, ref = True, hi, min(y.low for y in ref_bars)
    elif trend == -1 and x.close < lo and x.open - x.close > B["minBodyAtr"] * a:
        buy, level, ref = False, lo, max(y.high for y in ref_bars)
    else:
        return None
    entry = x.close
    if buy:
        sl = min(ref - R["stopBufferAtr"] * a, entry - R["minSlAtr"] * a)
    else:
        sl = max(ref + R["stopBufferAtr"] * a, entry + R["minSlAtr"] * a)
    risk = abs(entry - sl)
    if risk > R["maxSlAtr"] * a:
        return None
    return {"buy": buy, "index": i, "entry": entry, "sl": sl, "risk": risk, "atr": a, "level": level, "rangeHigh": hi, "rangeLow": lo,
            "body": abs(x.close - x.open)}


def _build_setup(c: list[Candle], b: dict, spec: dict, cfg: dict, spread: float, last: int) -> dict:
    R, FIL = cfg["risk"], cfg["filters"]
    d = spec["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    buy, i, risk = b["buy"], b["index"], b["risk"]
    entry = round_to(b["entry"], d)
    sl = round_to(b["sl"], d)
    # Targets from the rounded entry and stop, so TP1/TP2/TP3 sit exactly 1R/2R/3R away as printed
    unit = abs(entry - sl)
    tp = lambda k: round_to(entry + k * unit if buy else entry - k * unit, d)  # noqa: E731
    tp1, tp2, tp3 = tp(R["tp1R"]), tp(R["tp2R"]), tp(R["tp3R"])
    signal_time = c[i].time + H1_SEC
    valid_until = signal_time + R["marketValidMin"] * 60
    params = {"side": "BUY" if buy else "SELL", "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": None, "marketFillTime": signal_time, "cancelIfTp1BeforeFill": False, "partials": R["partials"],
              "spread": spread, "slippage": FIL["slippage"]}
    lifecycle = simulate_lifecycle(c, params, i + 1)
    return {
        "id": f"XAUUSD-BO-{c[i].time}", "setup": "BREAKOUT", "direction": "BUY" if buy else "SELL", "entryType": "MARKET",
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "tp2Source": f"{js_str(R['tp2R'])}R", "tp3Source": f"{js_str(R['tp3R'])}R",
        "rrTp2": rr(entry, sl, tp2), "slDistance": round_to(abs(entry - sl), d), "slPips": to_pips(spec, abs(entry - sl)),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": valid_until,
        "invalidation": f"H1 close {'below' if buy else 'above'} {f(sl)}; do not enter after {fmt_time(valid_until)}",
        "isFresh": i == last, "lifecycle": lifecycle, "params": params,
        "anchors": {"breakout": {"direction": "BUY" if buy else "SELL", "level": b["level"], "lookback": cfg["breakout"]["lookback"],
                                 "rangeHigh": b["rangeHigh"], "rangeLow": b["rangeLow"], "atr": round_to(b["atr"], 2),
                                 "time": c[i].time, "close": entry}},
    }


def evaluate_xauusd(inp: dict, cfg: dict = XAU_CONFIG) -> dict:
    spec = cfg["spec"]
    d = spec["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    now = inp["nowSec"]
    h1 = closed_only(inp["candles"].get("H1") or [], H1_SEC, now)[-cfg["history"]:]
    last = len(h1) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (h1[last].close if h1 else 0)
    spread = inp["spread"] if inp["spread"] is not None else cfg["filters"]["assumedSpread"]
    T, B, R, FIL = cfg["trend"], cfg["breakout"], cfg["risk"], cfg["filters"]
    W = cfg["scoring"]["weights"]
    result = new_result(spec, cfg, inp, price)

    # ---- Data quality ----
    min_bars = T["emaSlow"] + B["lookback"] + 30
    stale = inp["isMarketOpen"] and len(h1) > 0 and now - (h1[last].time + H1_SEC) > 3 * H1_SEC
    if not inp["isRealData"] or len(h1) < min_bars or stale:
        result["dataQuality"] = {
            "ok": False, "source": inp["dataSource"],
            "reason": "Live feed unavailable (synthetic candles): no analysis" if not inp["isRealData"]
            else "Last H1 candle is stale (feed paused)" if stale else f"Not enough history (H1 {len(h1)}, needs {min_bars})",
        }
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    closes = [x.close for x in h1]
    atr = atr_series(h1, cfg["atrPeriod"])
    ef, es = ema_series(closes, T["emaFast"]), ema_series(closes, T["emaSlow"])

    # ---- Replay one trade at a time, exactly like the backtest ----
    latest: Optional[tuple[dict, dict]] = None
    i = max(T["emaSlow"] + 10, B["lookback"] + R["stopRefBars"])
    while i <= last:
        b = _breakout_at(h1, i, atr, ef, es, cfg)
        if not b:
            i += 1
            continue
        s = _build_setup(h1, b, spec, cfg, spread, last)
        latest = (b, s)
        lc = s["lifecycle"]
        if lc["state"] != "CLOSED":
            break  # still in this trade: no new breakout counts
        exit_idx = next((j for j in range(i + 1, last + 1) if h1[j].time == lc["exitTime"]), last)
        i = exit_idx + 1

    trend_now = _trend(h1, last, ef, es)
    trend_txt = {1: "bullish", -1: "bearish", 0: "flat"}[trend_now]
    trend_detail = (f"EMA{T['emaFast']} {f(ef[last])} {'>' if ef[last] > es[last] else '<'} EMA{T['emaSlow']} {f(es[last])}, "
                    f"close {f(h1[last].close)} {'>' if h1[last].close > es[last] else '<'} EMA{T['emaSlow']}")
    result["bias"] = {"direction": "BULLISH" if trend_now == 1 else "BEARISH" if trend_now == -1 else "NEUTRAL", "detail": trend_detail}
    window = h1[last - B["lookback"] + 1:last + 1]
    range_hi, range_lo = max(y.high for y in window), min(y.low for y in window)

    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    result["news"] = {
        "blocked": news["blocked"],
        "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else "No high-impact USD news within ±30 min",
        "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None,
        "source": inp["news"]["source"],
    }
    win = active_window(now, cfg["sessions"]["windows"])
    result["market"]["window"] = win["name"] if win else None

    setup = None
    if latest:
        b, s = latest
        recent = b["index"] >= last - R["showLastSetupBars"]
        if s["lifecycle"]["state"] != "CLOSED" or recent:
            setup = s

    checklist: list[dict]
    if setup:
        b = latest[0]
        buy = b["buy"]
        signal_time = setup["signalTime"]
        nb = news_block(signal_time, inp["news"]["events"], FIL["news"])
        day = inp["day"]
        checklist = [
            item("trend", f"H1 trend: EMA{T['emaFast']} {'>' if buy else '<'} EMA{T['emaSlow']} and close {'above' if buy else 'below'} EMA{T['emaSlow']}",
                 "اتجاه H1 واضح", True, trend_detail if setup["isFresh"] else f"{'Bullish' if buy else 'Bearish'} trend at the breakout", W["trend"], True),
            item("breakout", f"H1 close beyond the {B['lookback']}-hour {'high' if buy else 'low'}", f"إغلاق H1 فوق/تحت أعلى/أدنى {B['lookback']} ساعة", True,
                 f"Close {f(b['entry'])} {'>' if buy else '<'} {B['lookback']}h {'high' if buy else 'low'} {f(b['level'])} ({fmt_time(signal_time)})", W["breakout"], True),
            item("momentum", f"Breakout candle body > {js_str(B['minBodyAtr'])}× ATR(14, H1)", "شمعة اختراق قوية", True,
                 f"Body ${to_fixed(b['body'], 2)} = {to_fixed(b['body'] / b['atr'], 2)}× ATR ${to_fixed(b['atr'], 2)}", W["momentum"], True,
                 min(1.0, b["body"] / b["atr"])),
            item("stop", f"Stop {js_str(R['minSlAtr'])}–{js_str(R['maxSlAtr'])}× ATR beyond the last {R['stopRefBars']} candles", "وقف الخسارة حسب التقلب", True,
                 f"SL {f(setup['sl'])} = ${to_fixed(setup['slDistance'], 2)} ({to_fixed(b['risk'] / b['atr'], 2)}× ATR)", W["stop"], True),
            item("targets", f"TP1 {js_str(R['tp1R'])}R (50%, SL to entry) · TP2 {js_str(R['tp2R'])}R · TP3 {js_str(R['tp3R'])}R", "الأهداف 1R / 2R / 3R", True,
                 f"TP1 {f(setup['tp1'])} · TP2 {f(setup['tp2'])} · TP3 {f(setup['tp3'])}", W["targets"], True),
            item("oneTrade", "One trade at a time", "صفقة واحدة في نفس الوقت", True, "No other gold trade open at the breakout", 0, True),
            item("news", "No high-impact USD news ±30 min", "لا أخبار قوية للدولار ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
            item("spread", f"Spread <= ${js_str(FIL['maxSpread'])}", "السبريد مقبول", spread <= FIL["maxSpread"],
                 f"Spread ${to_fixed(spread, 2)}{' (assumed, no live spread in feed)' if inp['spread'] is None else ''}", 0, True),
            item("daily", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} losses per day", "حد الصفقات اليومي",
                 day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"],
                 f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
        ]
    else:
        if trend_now == 1:
            progress = f"Bullish trend: waiting for an H1 close above the {B['lookback']}-hour high {f(range_hi)}"
        elif trend_now == -1:
            progress = f"Bearish trend: waiting for an H1 close below the {B['lookback']}-hour low {f(range_lo)}"
        else:
            progress = f"No clear H1 trend (EMA{T['emaFast']} / EMA{T['emaSlow']}): no trade"
        checklist = [
            item("trend", f"H1 trend: EMA{T['emaFast']} vs EMA{T['emaSlow']} and close vs EMA{T['emaSlow']}", "اتجاه H1 واضح", trend_now != 0, trend_detail, W["trend"], True),
            item("breakout", f"H1 close beyond the {B['lookback']}-hour high (buys) / low (sells)", "إغلاق H1 خارج النطاق", False, progress, W["breakout"], True),
            item("news", "No high-impact USD news ±30 min", "لا أخبار قوية للدولار ±30 دقيقة", not news["blocked"], result["news"]["detail"], 0, True),
        ]
        result["facts"]["progress"] = progress

    result["checklist"] = checklist
    result["setup"] = setup
    failed = [c for c in checklist if c["required"] and not c["passed"]]
    result["score"] = score_checklist(checklist) if setup else 0
    result["rejection"] = f"{failed[0]['rule']}: {failed[0]['detail']}" if failed else None
    result["status"] = classify(result["score"], not failed, cfg["scoring"]["thresholds"]) if setup else "NO_TRADE"
    if setup and result["status"] == "SIGNAL":
        result["signal"] = to_signal_json(spec, cfg["strategy"], setup, result["score"], cfg["timeframes"], checklist)
    result["canNotify"] = bool(result["status"] == "SIGNAL" and setup and setup["isFresh"] and setup["lifecycle"]["state"] == "OPEN" and inp["isMarketOpen"])

    # ---- Drawings: the 20-hour range, daily/weekly levels, the breakout and the trade ----
    t_range = h1[last - B["lookback"] + 1].time
    drawings = [
        {"id": "XAU-RANGE-H", "layer": "levels", "kind": "hline", "tf": "H1", "t1": t_range, "t2": None, "p1": range_hi,
         "text": f"{B['lookback']}h high", "color": "bull" if trend_now == 1 else "muted", "style": "dashed"},
        {"id": "XAU-RANGE-L", "layer": "levels", "kind": "hline", "tf": "H1", "t1": t_range, "t2": None, "p1": range_lo,
         "text": f"{B['lookback']}h low", "color": "bear" if trend_now == -1 else "muted", "style": "dashed"},
        *level_drawings(daily_weekly_levels(h1)),
    ]
    if setup:
        bo = setup["anchors"]["breakout"]
        drawings.append({"id": f"XAU-BO-{bo['time']}", "layer": "structure", "kind": "hline", "tf": "H1",
                         "t1": bo["time"] - B["lookback"] * H1_SEC, "t2": bo["time"], "p1": bo["level"],
                         "text": f"Breakout {B['lookback']}h {'high' if bo['direction'] == 'BUY' else 'low'}",
                         "color": "bull" if bo["direction"] == "BUY" else "bear", "style": "solid"})
        drawings.extend(trade_drawings(setup, "H1", ""))
    result["drawings"] = drawings

    result["facts"].update({
        "price": price, "spread": spread, "atrH1": round_to(atr[last], 2), "ema50": round_to(ef[last], d), "ema200": round_to(es[last], d),
        "trend": trend_txt, "range20h": {"high": range_hi, "low": range_lo},
        "levels": [{"kind": lv.kind, "label": lv.label, "price": lv.price} for lv in daily_weekly_levels(h1)],
        "lastTrade": ({"id": latest[1]["id"], "state": latest[1]["lifecycle"]["state"], "outcome": latest[1]["lifecycle"]["outcome"],
                       "r": latest[1]["lifecycle"]["rMultiple"]} if latest else None),
    })

    side = setup["direction"] if setup else ""
    status = result["status"]
    if not setup:
        result["headline"] = result["facts"]["progress"]
    elif status == "SIGNAL" and setup["isFresh"]:
        result["headline"] = f"{side} market {f(setup['entry'])} · score {result['score']}"
    elif status == "SIGNAL":
        result["headline"] = f"{side} breakout {fmt_time(setup['signalTime'])} · {setup['lifecycle']['state']}"
    elif status in ("WATCH", "IGNORE"):
        result["headline"] = f"{side} breakout scored {result['score']}"
    else:
        result["headline"] = f"{side} breakout rejected: {failed[0]['rule']}"
    result["headlineAr"] = (f"إشارة {side} عند {f(setup['entry'])}" if status == "SIGNAL" else "إعداد موجود لكنه غير مكتمل الشروط") if setup else "لا توجد صفقة حالياً"
    return result
