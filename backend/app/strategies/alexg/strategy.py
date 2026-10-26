"""
Forex — "FXAlexG · Set & Forget Break & Retest" (EUR/USD, GBP/USD and the pairs FXAlexG trades).

1. Top-down (rule 1): weekly bias = last closed weekly close vs EMA20 (weekly); the last closed daily
   close vs EMA20 (daily) must agree. Pro-trend only (rule 4): buys in a bullish week, sells in a bearish one.
2. Look left (rule 2): areas of interest are H4 swing highs / lows of the last ~4 weeks that price
   touched at least twice.
3. Break and retest (rule 3, no anticipation): an H4 candle CLOSES beyond the level in the trend
   direction, price moves ≥ 1.5 × ATR away without closing back through it, then an H4 candle comes back
   to the level (± 0.5 × ATR), closes on the right side and is a bullish / bearish engulfing or a pin bar.
4. Set & forget (rule 5): MARKET entry at that close, stop beyond the confirmation and previous candle
   ± 0.5 × ATR (15–120 pips), one target at 3R. No partials, no breakeven, no management.
D1 / W1 are built from H1 with the 22:00 UTC rollover. One trade at a time, replayed in order like the backtest.
"""

import bisect
from datetime import datetime, timezone
from typing import Optional

from ..shared.common import active_window, item, new_result, to_signal_json
from ..shared.drawings import level_drawings, trade_drawings
from ..shared.indicators import atr_series, ema_series
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.liquidity import daily_weekly_levels
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, to_pips
from ..shared.structure import detect_swings
from ..shared.types import Candle, closed_only

H1_SEC, H4_SEC = 3600, 14400
ROLLOVER = 2 * 3600  # the forex day starts at 22:00 UTC


def _resample(c: list[Candle], key) -> list[Candle]:
    out: list[Candle] = []
    k0 = None
    for x in c:
        k = key(x.time)
        if out and k == k0:
            y = out[-1]
            y.high, y.low, y.close = max(y.high, x.high), min(y.low, x.low), x.close
        else:
            out.append(Candle(x.time, x.open, x.high, x.low, x.close))
            k0 = k
    return out


def _day_key(t: int):
    return datetime.fromtimestamp(t + ROLLOVER, timezone.utc).date()


def _week_key(t: int):
    return datetime.fromtimestamp(t + ROLLOVER, timezone.utc).isocalendar()[:2]


def _engulfing(p: Candle, x: Candle, buy: bool) -> bool:
    if buy:
        return x.close > x.open and p.close < p.open and x.close >= p.open and x.open <= p.close
    return x.close < x.open and p.close > p.open and x.close <= p.open and x.open >= p.close


def _pin(x: Candle, buy: bool, cfg: dict) -> bool:
    rng = x.high - x.low
    if rng <= 0:
        return False
    b = abs(x.close - x.open)
    wick = (min(x.open, x.close) - x.low) if buy else (x.high - max(x.open, x.close))
    return wick >= cfg["pinWickBody"] * b and wick >= cfg["pinWickRange"] * rng


class _Ctx:
    """Everything the entry rules read, computed once per evaluation."""

    def __init__(self, h4: list[Candle], h1: list[Candle], cfg: dict):
        T, A = cfg["trend"], cfg["aoi"]
        self.h4 = h4
        self.atr = atr_series(h4, cfg["atrPeriod"])
        self.d1 = _resample(h1, _day_key)
        self.w1 = _resample(h1, _week_key)
        self.d_ema = ema_series([x.close for x in self.d1], T["dailyEma"])
        self.w_ema = ema_series([x.close for x in self.w1], T["weeklyEma"])
        self.d_t = [x.time for x in self.d1]
        self.w_t = [x.time for x in self.w1]
        # (confirmed index, swing) sorted by confirmation: the levels a trader sees when looking left
        self.swings = sorted(((s.confirmedIndex, s) for s in detect_swings(h4, A["swingN"])), key=lambda z: z[0])
        self.conf_idx = [z[0] for z in self.swings]

    def trend_at(self, t: int, cfg: dict) -> tuple[int, int, int, int]:
        """(weekly, daily, weekly index, daily index) from the candles CLOSED before time t."""
        wi = bisect.bisect_right(self.w_t, t) - 2
        di = bisect.bisect_right(self.d_t, t) - 2
        if wi < cfg["trend"]["weeklyEma"] or di < cfg["trend"]["dailyEma"]:
            return 0, 0, wi, di
        w = 1 if self.w1[wi].close > self.w_ema[wi] else -1
        d = 1 if self.d1[di].close > self.d_ema[di] else -1
        return w, d, wi, di


def _setup_at(ctx: _Ctx, i: int, cfg: dict) -> Optional[dict]:
    """The pure entry rules on H4 candle i (closed). Returns the order levels, or None."""
    A, BR, R = cfg["aoi"], cfg["breakRetest"], cfg["risk"]
    c, atr = ctx.h4, ctx.atr
    a = atr[i]
    if not (a > 0) or i < 1:
        return None
    x = c[i]
    w, d, _, _ = ctx.trend_at(x.time, cfg)
    if w == 0 or w != d:
        return None
    buy = w == 1
    prev = i - 1  # levels and breaks only use candles closed before the retest candle
    hi = bisect.bisect_right(ctx.conf_idx, prev)
    for k in range(hi - 1, -1, -1):
        ci, s = ctx.swings[k]
        if prev - s.index > A["lookbackBars"]:
            break
        if s.kind != ("HIGH" if buy else "LOW"):
            continue
        lv = s.price
        if A["minTouches"] > 1:
            z = A["touchAtr"] * atr[s.index] if atr[s.index] > 0 else 0
            touches = 1 + sum(1 for j in range(max(0, s.index - A["lookbackBars"]), s.index)
                              if abs((c[j].high if buy else c[j].low) - lv) <= z)
            if touches < A["minTouches"]:
                continue
        else:
            touches = 1
        bk = next((j for j in range(ci + 1, prev + 1) if (c[j].close > lv if buy else c[j].close < lv)), None)
        if bk is None or prev - bk > BR["maxBarsSinceBreak"] or prev - bk < 1:
            continue
        if any((c[j].close < lv - BR["invalidAtr"] * atr[j]) if buy else (c[j].close > lv + BR["invalidAtr"] * atr[j]) for j in range(bk + 1, prev + 1)):
            continue
        ext = max(c[j].high for j in range(bk, prev + 1)) if buy else min(c[j].low for j in range(bk, prev + 1))
        if abs(ext - lv) < BR["minMoveAtr"] * atr[bk]:
            continue
        tol = BR["retestTolAtr"] * a
        if not ((x.low <= lv + tol and x.close > lv) if buy else (x.high >= lv - tol and x.close < lv)):
            continue
        engulf = BR["engulfing"] and _engulfing(c[i - 1], x, buy)
        pin = BR["pinBar"] and _pin(x, buy, BR)
        if not (engulf or pin):
            continue
        pip = cfg["spec"]["pipSize"]
        entry = x.close
        ref = min(x.low, c[i - 1].low) if buy else max(x.high, c[i - 1].high)
        sl = ref - R["slBufferAtr"] * a if buy else ref + R["slBufferAtr"] * a
        if abs(entry - sl) < R["minSlPips"] * pip:
            sl = entry - R["minSlPips"] * pip if buy else entry + R["minSlPips"] * pip
        if abs(entry - sl) > R["maxSlPips"] * pip:
            return None  # the most recent area of interest is the one traded: too wide = no trade
        return {"buy": buy, "index": i, "entry": entry, "sl": sl, "atr": a, "level": lv, "levelIndex": s.index, "touches": touches,
                "breakIndex": bk, "extreme": ext, "pattern": "engulfing" if engulf else "pin bar"}
    return None


def _build_setup(c: list[Candle], b: dict, cfg: dict, spread: float, last: int) -> dict:
    R, FIL, spec = cfg["risk"], cfg["filters"], cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    buy, i = b["buy"], b["index"]
    entry, sl = round_to(b["entry"], d), round_to(b["sl"], d)
    unit = abs(entry - sl)
    tp = lambda k: round_to(entry + k * unit if buy else entry - k * unit, d)  # noqa: E731
    tp1, tp2, tp3 = tp(R["tp1R"]), tp(R["tp2R"]), tp(R["targetR"])
    signal_time = c[i].time + H4_SEC
    valid_until = signal_time + R["marketValidMin"] * 60
    params = {"side": "BUY" if buy else "SELL", "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": None, "marketFillTime": signal_time, "cancelIfTp1BeforeFill": False, "partials": R["partials"],
              "breakeven": R["breakeven"], "spread": spread, "slippage": FIL["slippagePips"] * pip}
    lifecycle = simulate_lifecycle(c, params, i + 1)
    return {
        "id": f"{spec['symbol']}-BR-{c[i].time}", "setup": "BREAK_RETEST", "direction": "BUY" if buy else "SELL", "entryType": "MARKET",
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "tp2Source": f"{js_str(R['tp2R'])}R mark", "tp3Source": f"{js_str(R['targetR'])}R target (set & forget)",
        "rrTp2": rr(entry, sl, tp2), "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": valid_until,
        "invalidation": f"Stop {f(sl)}, target {f(tp3)}: set & forget, no partials, no breakeven; do not enter after {fmt_time(valid_until)}",
        "isFresh": i == last, "lifecycle": lifecycle, "params": params,
        "anchors": {"breakRetest": {"direction": "BUY" if buy else "SELL", "level": b["level"], "levelTime": c[b["levelIndex"]].time,
                                    "touches": b["touches"], "breakTime": c[b["breakIndex"]].time, "extreme": b["extreme"],
                                    "retestTime": c[i].time, "pattern": b["pattern"], "atr": round_to(b["atr"], d)}},
    }


def evaluate_alexg(inp: dict, cfg: dict) -> dict:
    spec = cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    now = inp["nowSec"]
    h4 = closed_only(inp["candles"].get("H4") or [], H4_SEC, now)[-cfg["history"]:]
    h1 = closed_only(inp["candles"].get("H1") or [], H1_SEC, now)
    last = len(h4) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (h4[last].close if h4 else 0)
    FIL, R, A, BR, T = cfg["filters"], cfg["risk"], cfg["aoi"], cfg["breakRetest"], cfg["trend"]
    spread = inp["spread"] if inp["spread"] is not None else FIL["assumedSpreadPips"] * pip
    W = cfg["scoring"]["weights"]
    result = new_result(spec, cfg, inp, price)

    # ---- Data quality ----
    min_h4, min_h1 = A["lookbackBars"] + 60, (T["weeklyEma"] + 3) * 120
    stale = inp["isMarketOpen"] and len(h4) > 0 and now - (h4[last].time + H4_SEC) > 3 * H4_SEC
    if not inp["isRealData"] or len(h4) < min_h4 or len(h1) < min_h1 or stale:
        result["dataQuality"] = {
            "ok": False, "source": inp["dataSource"],
            "reason": "Live feed unavailable (synthetic candles): no analysis" if not inp["isRealData"]
            else "Last H4 candle is stale (feed paused)" if stale else f"Not enough history (H4 {len(h4)}/{min_h4}, H1 {len(h1)}/{min_h1})",
        }
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    ctx = _Ctx(h4, h1, cfg)

    # ---- Replay one trade at a time, exactly like the backtest ----
    latest: Optional[tuple[dict, dict]] = None
    i = A["lookbackBars"] + 30
    while i <= last:
        b = _setup_at(ctx, i, cfg)
        if not b:
            i += 1
            continue
        s = _build_setup(h4, b, cfg, spread, last)
        latest = (b, s)
        lc = s["lifecycle"]
        if lc["state"] != "CLOSED":
            break
        i = next((j for j in range(i + 1, last + 1) if h4[j].time == lc["exitTime"]), last) + 1

    # ---- Top-down read now ----
    w, dtr, wi, di = ctx.trend_at(h4[last].time + H4_SEC, cfg)
    word = {1: "bullish", -1: "bearish", 0: "unknown"}
    trend_detail = (f"Weekly close {f(ctx.w1[wi].close)} {'>' if w == 1 else '<'} EMA{T['weeklyEma']} {f(ctx.w_ema[wi])} ({word[w]}); "
                    f"daily close {f(ctx.d1[di].close)} {'>' if dtr == 1 else '<'} EMA{T['dailyEma']} {f(ctx.d_ema[di])} ({word[dtr]})") if w else "Not enough weekly history"
    aligned = w != 0 and w == dtr
    result["bias"] = {"direction": ("BULLISH" if w == 1 else "BEARISH") if aligned else "NEUTRAL", "detail": trend_detail}

    # Areas of interest visible now (looking left from the last closed candle)
    aoi = []
    for ci, s in reversed(ctx.swings):
        if ci > last:
            continue
        if last - s.index > A["lookbackBars"]:
            break
        if aligned and s.kind != ("HIGH" if w == 1 else "LOW"):
            continue
        aoi.append(s)
        if len(aoi) >= 3:
            break

    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    ccys = "/".join(FIL["news"]["currencies"])
    result["news"] = {
        "blocked": news["blocked"],
        "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else f"No high-impact {ccys} news within ±30 min",
        "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None,
        "source": inp["news"]["source"],
    }
    win = active_window(now, cfg["sessions"]["windows"])
    result["market"]["window"] = win["name"] if win else None

    setup = None
    if latest:
        b, s = latest
        if s["lifecycle"]["state"] != "CLOSED" or b["index"] >= last - R["showLastSetupBars"]:
            setup = s

    if setup:
        b = latest[0]
        buy = b["buy"]
        side = "high" if buy else "low"
        nb = news_block(setup["signalTime"], inp["news"]["events"], FIL["news"])
        day = inp["day"]
        sl_pips = setup["slPips"]
        checklist = [
            item("trend", "Top-down: weekly and daily trend agree (pro-trend only)", "الاتجاه الأسبوعي واليومي متوافق", True,
                 trend_detail if setup["isFresh"] else f"{'Bullish' if buy else 'Bearish'} weekly and daily at the retest", W["trend"], True),
            item("aoi", f"Look left: H4 swing {side} touched ≥ {A['minTouches']} times", "منطقة اهتمام على اليسار", True,
                 f"Level {f(b['level'])} ({fmt_time(h4[b['levelIndex']].time)}), {b['touches']} touches", W["aoi"], True),
            item("break", f"Break: H4 close {'above' if buy else 'below'} the level, then ≥ {js_str(BR['minMoveAtr'])}× ATR away", "كسر المستوى بإغلاق H4", True,
                 f"Break {fmt_time(h4[b['breakIndex']].time)}, extreme {f(b['extreme'])}", W["break"], True),
            item("retest", "Retest: back to the level with an engulfing or pin-bar close (no anticipation)", "إعادة الاختبار مع شمعة تأكيد", True,
                 f"{b['pattern'].capitalize()} closed {f(setup['entry'])} at {fmt_time(setup['signalTime'])}", W["retest"], True),
            item("stop", f"Stop beyond the confirmation candles ± {js_str(R['slBufferAtr'])}× ATR, {R['minSlPips']}–{R['maxSlPips']} pips", "وقف الخسارة خلف الشمعة", True,
                 f"SL {f(setup['sl'])} ({js_str(sl_pips)} pips)", W["stop"], True),
            item("target", f"Set & forget: one target at {js_str(R['targetR'])}R, no partials, no breakeven", "هدف واحد 3R بدون تدخل", True,
                 f"TP {f(setup['tp3'])}", W["target"], True),
            item("oneTrade", "One trade at a time", "صفقة واحدة في نفس الوقت", True, "No other trade open on this pair", 0, True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
            item("spread", f"Spread <= {js_str(FIL['maxSpreadPips'])} pips", "السبريد مقبول", spread <= FIL["maxSpreadPips"] * pip,
                 f"Spread {to_fixed(spread / pip, 1)} pips{' (assumed, no live spread in feed)' if inp['spread'] is None else ''}", 0, True),
            item("daily", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} loss per day", "حد الصفقات اليومي",
                 day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"],
                 f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
        ]
    else:
        if not aligned:
            progress = "Weekly and daily disagree: FXAlexG waits (no counter-trend, no anticipation)"
        elif aoi:
            lv = aoi[0]
            dirw = "above" if w == 1 else "below"
            progress = f"{'Bullish' if w == 1 else 'Bearish'} top-down: waiting for an H4 close {dirw} {f(lv.price)}, then a retest with an engulfing / pin bar"
        else:
            progress = "Trend clear, no area of interest on the left yet: patience"
        checklist = [
            item("trend", "Top-down: weekly and daily trend agree (pro-trend only)", "الاتجاه الأسبوعي واليومي متوافق", aligned, trend_detail, W["trend"], True),
            item("retest", "Break and retest with an engulfing / pin-bar close", "كسر وإعادة اختبار", False, progress, W["retest"], True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not news["blocked"], result["news"]["detail"], 0, True),
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

    # ---- Drawings: areas of interest, daily/weekly levels, the break & retest and the trade ----
    sym = spec["symbol"]
    drawings = [
        {"id": f"{sym}-AOI-{s.time}", "layer": "levels", "kind": "hline", "tf": "H4", "t1": s.time, "t2": None, "p1": s.price,
         "text": f"AOI {'resistance' if s.kind == 'HIGH' else 'support'}", "color": "bear" if s.kind == "HIGH" else "bull", "style": "dashed"}
        for s in aoi
    ]
    drawings.extend(level_drawings(daily_weekly_levels(h1[-2000:])))
    if setup:
        br = setup["anchors"]["breakRetest"]
        bull = br["direction"] == "BUY"
        drawings.append({"id": f"{sym}-BRL-{br['retestTime']}", "layer": "structure", "kind": "hline", "tf": "H4", "t1": br["levelTime"],
                         "t2": br["retestTime"] + H4_SEC, "p1": br["level"], "text": f"Break & retest {f(br['level'])}",
                         "color": "bull" if bull else "bear", "style": "solid"})
        drawings.append({"id": f"{sym}-BRK-{br['breakTime']}", "layer": "structure", "kind": "marker", "tf": "H4", "t1": br["breakTime"], "t2": None,
                         "p1": br["level"], "text": "Break", "color": "bull" if bull else "bear", "position": "above" if bull else "below"})
        drawings.append({"id": f"{sym}-RT-{br['retestTime']}", "layer": "structure", "kind": "marker", "tf": "H4", "t1": br["retestTime"], "t2": None,
                         "p1": setup["entry"], "text": f"Retest · {br['pattern']}", "color": "entry", "position": "below" if bull else "above"})
        drawings.extend(trade_drawings(setup, "H4", ""))
    result["drawings"] = drawings

    result["facts"].update({
        "price": price, "spread": spread, "atrH4": round_to(ctx.atr[last], d), "weeklyTrend": word[w], "dailyTrend": word[dtr],
        "areasOfInterest": [{"price": s.price, "kind": "resistance" if s.kind == "HIGH" else "support", "time": s.time} for s in aoi],
        "levels": [{"kind": lv.kind, "label": lv.label, "price": lv.price} for lv in daily_weekly_levels(h1[-2000:])],
        "lastTrade": ({"id": latest[1]["id"], "state": latest[1]["lifecycle"]["state"], "outcome": latest[1]["lifecycle"]["outcome"],
                       "r": latest[1]["lifecycle"]["rMultiple"]} if latest else None),
    })

    status = result["status"]
    sd = setup["direction"] if setup else ""
    if not setup:
        result["headline"] = result["facts"]["progress"]
    elif status == "SIGNAL" and setup["isFresh"]:
        result["headline"] = f"{sd} market {f(setup['entry'])} · break & retest · score {result['score']}"
    elif status == "SIGNAL":
        result["headline"] = f"{sd} break & retest {fmt_time(setup['signalTime'])} · {setup['lifecycle']['state']}"
    elif status in ("WATCH", "IGNORE"):
        result["headline"] = f"{sd} break & retest scored {result['score']}"
    else:
        result["headline"] = f"{sd} break & retest rejected: {failed[0]['rule']}"
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])}" if status == "SIGNAL" else "إعداد موجود لكنه غير مكتمل الشروط") if setup else "لا توجد صفقة حالياً"
    return result
