"""
EURUSD — "Trend Pullback + London Breakout Filter"

Bias (H4, Daily filter): bullish if H4 close > EMA200, EMA50 > EMA200 and H4 swings are HH/HL;
bearish mirror. No buys within 15 pips of daily resistance / PWH (mirror for sells).
Windows: London 07:00–10:30 and London/NY overlap 13:00–16:00 (London time); none Friday after 14:00.

Setup A (trend pullback, M15 entry): pullback into >= 2 of {H1 OB, Fib 50–61.8% of the last H1
impulse, M15 EMA50}; RSI(14, M15) at the pullback 40–50 (buys) / 50–60 (sells); confirmation
candle = engulfing, pin bar (wick >= 2× body) or M15 CHoCH; MARKET entry at its close.
Setup B (Asian false breakout): Asian range 12–40 pips; in the London window a candle trades
beyond one side and closes back inside; trade toward the other side only with the H4 bias.
Risk: SL beyond zone/swing + 3 pips or 1.5 × ATR(14, M15), whichever is wider, 8–25 pips.
TP1 = 1R (50%, SL to BE), TP2 = next H1 level (>= 2R) or 2R, TP3 trails behind M15 swings.
"""

import math
from typing import Optional

from ..shared.common import active_window, item, nearest_swing_beyond, new_result, to_signal_json, volatility_ratio
from ..shared.drawings import (declutter_zones, fvg_drawings, level_drawings, ob_drawings, session_drawings, structure_drawings,
                               sweep_drawings, swing_drawings, trade_drawings)
from ..shared.indicators import atr_series, avg_body_series, body, ema_series, last_value, rsi_series
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_div, js_str, round_to, to_fixed
from ..shared.liquidity import Level, daily_weekly_levels, find_sweeps
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, to_pips
from ..shared.sessions import in_local_window, local_date_key, session_range, zoned_parts
from ..shared.structure import Swing, detect_structure, detect_swings, structure_from_labels
from ..shared.types import closed_only
from ..shared.zones import detect_fvgs, detect_order_blocks
from .config import EUR_CONFIG

INF = math.inf


def _mark(ok: bool) -> str:
    return "✓" if ok else "✗"


def evaluate_eurusd(inp: dict, cfg: dict = EUR_CONFIG) -> dict:
    spec = cfg["spec"]
    d = spec["decimals"]
    pip = spec["pipSize"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    pips = lambda v: to_pips(spec, v)  # noqa: E731
    now = inp["nowSec"]
    candles = inp["candles"]
    m15 = closed_only(candles.get("M15") or [], 900, now)[-700:]
    h1 = closed_only(candles.get("H1") or [], 3600, now)[-800:]
    h4 = closed_only(candles.get("H4") or [], 14400, now)[-500:]
    d1 = closed_only(candles.get("D1") or [], 86400, now)[-300:]
    last = len(m15) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (m15[last].close if m15 else 0)
    FIL = cfg["filters"]
    R = cfg["risk"]
    A = cfg["setupA"]
    B = cfg["setupB"]
    spread = inp["spread"] if inp["spread"] is not None else FIL["assumedSpreadPips"] * pip
    slippage = FIL["slippagePips"] * pip
    S = cfg["structure"]
    W = cfg["scoring"]["weights"]
    SES = cfg["sessions"]
    day = inp["day"]

    result = new_result(spec, cfg, inp, price)

    stale = inp["isMarketOpen"] and len(m15) > 0 and now - (m15[last].time + 900) > 3 * 900
    if not inp["isRealData"] or len(m15) < 150 or len(h1) < 150 or len(h4) < cfg["bias"]["emaSlow"] + 10 or len(d1) < 30 or stale:
        result["dataQuality"] = {
            "ok": False, "source": inp["dataSource"],
            "reason": "Live feed unavailable (synthetic candles): no analysis" if not inp["isRealData"]
            else "Last M15 candle is stale (feed paused)" if stale
            else f"Not enough history (M15 {len(m15)}, H1 {len(h1)}, H4 {len(h4)}, D1 {len(d1)})",
        }
        result["headline"] = "Data not usable"
        result["headlineAr"] = "البيانات غير صالحة"
        return result

    # ---- Detectors ----
    atr15 = atr_series(m15, cfg["atrPeriod"])
    swings15 = detect_swings(m15, S["swingN"])
    st15, _ = detect_structure(m15, swings15, avg_body_series(m15, S["avgBodyPeriod"]), S["displacementMult"])
    closes15 = [x.close for x in m15]
    ema50m15 = ema_series(closes15, A["emaPeriod"])
    rsi15 = rsi_series(closes15, A["rsiPeriod"])
    atr_h1 = atr_series(h1, cfg["atrPeriod"])
    swings_h1 = detect_swings(h1, S["swingN"])
    st_h1, _ = detect_structure(h1, swings_h1, avg_body_series(h1, S["avgBodyPeriod"]), S["displacementMult"])
    obs_h1 = detect_order_blocks(h1, st_h1, "H1")
    fvgs_h1 = detect_fvgs(h1, atr_h1, cfg["fvgMinAtr"], "H1")
    swings_h4 = detect_swings(h4, S["htfSwingN"])
    swings_d1 = detect_swings(d1, S["dailySwingN"])
    levels: list[Level] = daily_weekly_levels(h1)

    # ---- Bias ----
    h4_close = h4[-1].close
    closes_h4 = [x.close for x in h4]
    e50 = last_value(ema_series(closes_h4, cfg["bias"]["emaFast"]))
    e200 = last_value(ema_series(closes_h4, cfg["bias"]["emaSlow"]))
    h4_struct = structure_from_labels(swings_h4)
    bias = "NEUTRAL"
    if h4_close > e200 and e50 > e200 and h4_struct == "BULLISH":
        bias = "BULLISH"
    elif h4_close < e200 and e50 < e200 and h4_struct == "BEARISH":
        bias = "BEARISH"
    struct_txt = "HH/HL" if h4_struct == "BULLISH" else "LH/LL" if h4_struct == "BEARISH" else "mixed"
    bias_detail = (f"H4 close {f(h4_close)} {'>' if h4_close > e200 else '<'} EMA200 {f(e200)}, "
                   f"EMA50 {f(e50)} {'>' if e50 > e200 else '<'} EMA200, H4 swings {struct_txt}")
    result["bias"] = {"direction": bias, "detail": bias_detail}

    # ---- Shared filters ----
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    result["news"] = {
        "blocked": news["blocked"],
        "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else "No high-impact EUR/USD news within ±30 min",
        "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None,
        "source": inp["news"]["source"],
    }
    vol = volatility_ratio(atr_h1, FIL["volatility"]["lookbackBars"])
    win_now = active_window(now, SES["windows"])
    result["market"]["window"] = win_now["name"] if win_now else None

    asia_cfg = SES["asia"]
    today_key = local_date_key(now, asia_cfg["tz"])
    asia = session_range(m15, 900, "Asia", today_key, asia_cfg["tz"], asia_cfg["start"], asia_cfg["end"], now)

    # Filters evaluated at the signal time of a candidate
    def common_checks(signal_time: int, direction: str, entry: float, sl: float, tp2: float, sl_dist: float) -> list[dict]:
        buy = direction == "BUY"
        win = active_window(signal_time - 1, SES["windows"])
        fc = SES["fridayCutoff"]
        friday = zoned_parts(signal_time - 1, fc["tz"]).weekday == 5 and not in_local_window(signal_time - 1, fc["tz"], "00:00", fc["time"])
        daily_res = _nearest_daily_barrier(swings_d1, levels, entry, buy, len(d1) - 1)
        room = pips(abs(daily_res["price"] - entry)) if daily_res else 999
        rr_tp2 = rr(entry, sl, tp2)
        sl_pips = pips(sl_dist)
        nb = news_block(signal_time, inp["news"]["events"], FIL["news"])
        spread_pips = spread / pip
        day_ok = day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"]
        htf = nearest_swing_beyond(swings_h1, entry, buy, len(h1) - 1)
        htf_r = js_div(abs(htf.price - entry), sl_dist) if htf else 99
        nev = nb["event"]
        return [
            item("window", "London 07:00–10:30 or overlap 13:00–16:00 (London time), not Friday after 14:00", "نافذة لندن أو التداخل مع نيويورك", bool(win) and not friday,
                 "Friday after 14:00 London: no new trades" if friday else f"{win['name']} at {fmt_time(signal_time)}" if win else f"{fmt_time(signal_time)} is outside both windows",
                 W["window"], True),
            item("daily", f"Daily room >= {cfg['dailyRoomPips']} pips", "مسافة كافية عن مستوى يومي", room >= cfg["dailyRoomPips"],
                 f"{daily_res['label']} {f(daily_res['price'])} is {js_str(room)} pips away" if daily_res else "No daily barrier in the way", 0, True),
            item("sl", f"Stop {R['minSlPips']}–{R['maxSlPips']} pips", "وقف الخسارة بين 8 و 25 نقطة", R["minSlPips"] <= sl_pips <= R["maxSlPips"],
                 f"SL {f(sl)} = {js_str(sl_pips)} pips", 0, True),
            item("rr", f"R:R to TP2 >= 1:{R['minRr']}", "عائد 1:2 على الأقل", rr_tp2 >= R["minRr"] - 1e-9, f"TP2 {f(tp2)} = 1:{to_fixed(rr_tp2, 2)}",
                 W["rr"], True, 1 if rr_tp2 >= 3 else 0.7),
            item("htf", "Room to the next H1 level", "مسافة حتى مستوى H1", htf_r >= 1,
                 f"Next H1 {'high' if buy else 'low'} {f(htf.price)} = {to_fixed(htf_r, 1)}R away" if htf else "No H1 level in the way",
                 W["htfDistance"], False, 1 if htf_r >= 2 else 0.6 if htf_r >= 1 else 0.2),
            item("volatility", "Normal volatility (ATR H1 vs 20-day average)", "تقلب طبيعي", 0.5 <= vol["ratio"] <= 2.5,
                 f"ATR H1 {js_str(pips(vol['now']))} pips = {to_fixed(vol['ratio'] * 100, 0)}% of average", W["volatility"], False,
                 1 if 0.8 <= vol["ratio"] <= 1.8 else 0.5),
            item("news", "No high-impact EUR/USD news ±30 min", "لا أخبار قوية لليورو أو الدولار", not nb["blocked"],
                 f"{nev['currency']} {nev['title']} at {fmt_time(nev['time'])}" if nev else "Clear", 0, True),
            item("spread", f"Spread <= {js_str(FIL['maxSpreadPips'])} pips", "السبريد مقبول", spread_pips <= FIL["maxSpreadPips"],
                 f"Spread {to_fixed(spread_pips, 1)} pips{' (assumed, no live spread in feed)' if inp['spread'] is None else ''}", 0, True),
            item("dailyLimit", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} losses per day", "حد الصفقات اليومي", day_ok,
                 f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
        ]

    def build_setup(sid: str, kind: str, direction: str, idx: int, entry: float, structural_sl: float, tp2_hint: Optional[dict], anchors: dict) -> dict:
        buy = direction == "BUY"
        atr_sl = entry - R["slAtrMult"] * atr15[idx] if buy else entry + R["slAtrMult"] * atr15[idx]
        sl = round_to(_js_min(structural_sl, atr_sl) if buy else _js_max(structural_sl, atr_sl), d)
        sl_dist = abs(entry - sl)
        tp1 = round_to(entry + sl_dist * R["tp1R"] if buy else entry - sl_dist * R["tp1R"], d)
        if tp2_hint:
            tp2, tp2_source = round_to(tp2_hint["price"], d), tp2_hint["label"]
        else:
            lvl = _nearest_h1_target(swings_h1, levels, entry, buy, len(h1) - 1, entry + (1 if buy else -1) * sl_dist * R["minRr"])
            tp2 = round_to(lvl["price"] if lvl else (entry + sl_dist * R["tp2R"] if buy else entry - sl_dist * R["tp2R"]), d)
            tp2_source = f"{lvl['label']} (next H1 level)" if lvl else f"{R['tp2R']}R"
        tp3 = round_to(entry + sl_dist * R["tp3RefR"] if buy else entry - sl_dist * R["tp3RefR"], d)
        signal_time = m15[idx].time + 900
        trail_kind = "LOW" if buy else "HIGH"
        buf = R["slBufferPips"] * pip

        def trail(i: int):
            sw = next((s for s in reversed(swings15) if s.kind == trail_kind and s.confirmedIndex <= i), None)
            return (sw.price - buf if buy else sw.price + buf) if sw else None

        params = {"side": direction, "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": None, "expiryTime": None,
                  "marketFillTime": signal_time, "cancelIfTp1BeforeFill": False, "partials": R["partials"], "spread": spread, "slippage": slippage}
        lifecycle = simulate_lifecycle(m15, params, idx + 1, trail)
        valid_until = signal_time + R["marketOrderValidMin"] * 60
        return {
            "id": sid, "setup": kind, "direction": direction, "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "tp2Source": tp2_source, "tp3Source": "Trail behind M15 swings (3R shown as reference)", "rrTp2": rr(entry, sl, tp2),
            "slDistance": round_to(sl_dist, d), "slPips": pips(sl_dist), "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
            "signalTime": signal_time, "signalIndex": idx, "expiresAt": valid_until,
            "invalidation": f"M15 close {'below' if buy else 'above'} {f(sl)}; do not enter after {fmt_time(valid_until)}",
            "isFresh": idx == last, "lifecycle": lifecycle, "params": params, "anchors": anchors,
        }

    candidates: list[dict] = []
    progress_a = ""
    progress_b = ""
    fib_drawing: list[dict] = []

    # ---- Setup A: trend pullback ----
    if bias != "NEUTRAL":
        buy = bias == "BULLISH"
        leg = next((e for e in reversed(st_h1) if e.direction == bias), None)
        if not leg:
            progress_a = "No H1 impulse leg in the bias direction"
        else:
            leg_start = h1[leg.legStartIndex].low if buy else h1[leg.legStartIndex].high
            leg_end, leg_end_time = (-INF if buy else INF), 0
            for i in range(leg.legStartIndex, len(h1)):
                if (h1[i].high > leg_end) if buy else (h1[i].low < leg_end):
                    leg_end, leg_end_time = (h1[i].high if buy else h1[i].low), h1[i].time
            rng = abs(leg_end - leg_start)
            f50, f618 = (leg_end - r * rng if buy else leg_end + r * rng for r in A["fib"])
            fib_top, fib_bot = max(f50, f618), min(f50, f618)
            t_leg = h1[leg.legStartIndex].time
            fib_drawing.extend([
                {"id": f"FIB-50-{leg.breakTime}", "layer": "fib", "kind": "hline", "tf": "H1", "t1": t_leg, "t2": None, "p1": f50, "text": "0.5", "color": "gold", "style": "dotted"},
                {"id": f"FIB-618-{leg.breakTime}", "layer": "fib", "kind": "hline", "tf": "H1", "t1": t_leg, "t2": None, "p1": f618, "text": "0.618", "color": "gold", "style": "dotted"},
                {"id": f"FIB-Z-{leg.breakTime}", "layer": "fib", "kind": "box", "tf": "H1", "t1": leg_end_time, "t2": None, "p1": fib_top, "p2": fib_bot, "text": "Fib 50–61.8", "color": "gold", "faded": True},
            ])
            ob = next((o for o in reversed(obs_h1) if o.direction == bias and o.state != "BROKEN"), None)
            leg_pips = pips(rng)
            if leg_pips < A["minLegPips"]:
                progress_a = f"H1 impulse leg only {js_str(leg_pips)} pips"

            idx = last
            lower = max(A["pullbackBars"], last - A["lookbackBars"])
            while idx >= lower and leg_pips >= A["minLegPips"]:
                c, p = m15[idx], m15[idx - 1]
                if c.time < leg_end_time:
                    break  # pullback must come after the impulse high/low
                pb_idx = idx
                for i in range(idx - A["pullbackBars"] + 1, idx + 1):
                    if (m15[i].low < m15[pb_idx].low) if buy else (m15[i].high > m15[pb_idx].high):
                        pb_idx = i
                pb_extreme = m15[pb_idx].low if buy else m15[pb_idx].high
                tol = A["fibTolerance"] * rng
                fib_hit = (fib_bot - tol <= pb_extreme <= fib_top) if buy else (fib_bot <= pb_extreme <= fib_top + tol)
                ob_hit = ob is not None and ((pb_extreme <= ob.top and c.close >= ob.bottom) if buy else (pb_extreme >= ob.bottom and c.close <= ob.top))
                ema_hit = False
                for i in range(idx - A["pullbackBars"] + 1, idx + 1):
                    if m15[i].low <= ema50m15[i] and m15[i].high >= ema50m15[i]:
                        ema_hit = True
                confl = int(fib_hit) + int(ob_hit) + int(ema_hit)
                if confl < A["minConfluence"]:
                    if idx == last:
                        progress_a = f"Pullback touches {confl}/3 zones (Fib {_mark(fib_hit)}, H1 OB {_mark(ob_hit)}, EMA50 {_mark(ema_hit)})"
                    idx -= 1
                    continue

                if buy:
                    engulf = p.close < p.open and c.close > c.open and c.close >= p.open and c.open <= p.close
                else:
                    engulf = p.close > p.open and c.close < c.open and c.close <= p.open and c.open >= p.close
                b = max(body(c), pip * 0.1)
                lower_wick = min(c.open, c.close) - c.low
                upper_wick = c.high - max(c.open, c.close)
                mid = (c.high + c.low) / 2
                pin = (lower_wick >= A["pinWickBody"] * b and c.close >= mid) if buy else (upper_wick >= A["pinWickBody"] * b and c.close <= mid)
                choch = any(e.breakIndex == idx and e.direction == bias and e.type == "CHOCH" for e in st15)
                if not engulf and not pin and not choch:
                    if idx == last:
                        progress_a = f"In zone ({confl}/3), waiting for an engulfing / pin bar / M15 CHoCH"
                    idx -= 1
                    continue

                rsi_v = rsi15[pb_idx]
                r_lo, r_hi = A["rsiBuy"] if buy else A["rsiSell"]
                entry = round_to(c.close, d)
                if buy:
                    zone_edge = _js_min(pb_extreme, ob.bottom if ob_hit and ob else INF, fib_bot if fib_hit else INF)
                    structural_sl = zone_edge - R["slBufferPips"] * pip
                else:
                    zone_edge = _js_max(pb_extreme, ob.top if ob_hit and ob else -INF, fib_top if fib_hit else -INF)
                    structural_sl = zone_edge + R["slBufferPips"] * pip
                direction = "BUY" if buy else "SELL"
                trigger = "Engulfing" if engulf else "Pin bar" if pin else "M15 CHoCH"
                setup = build_setup(f"EURUSD-A-{c.time}", "A", direction, idx, entry, structural_sl, None, {
                    "leg": {"start": leg_start, "end": leg_end, "fib50": f50, "fib618": f618},
                    "ob": {"top": ob.top, "bottom": ob.bottom} if ob else None,
                    "ema50": ema50m15[idx], "pullback": pb_extreme, "trigger": trigger,
                })
                ob_txt = f" ({f(ob.bottom)}–{f(ob.top)})" if ob else ""
                checklist = [
                    item("bias", "H4 trend: close vs EMA200, EMA50 vs EMA200, HH/HL structure", "اتجاه H4 واضح", True, bias_detail, W["bias"], True),
                    item("zone", f"Pullback into >= {A['minConfluence']} of: H1 OB, Fib 50–61.8%, EMA50 M15", "رجوع لمنطقة توافق", True,
                         f"Fib {_mark(fib_hit)} ({f(fib_bot)}–{f(fib_top)}), H1 OB {_mark(ob_hit)}{ob_txt}, EMA50 {_mark(ema_hit)}; pullback {f(pb_extreme)}",
                         W["zone"], True, confl / 3),
                    item("momentum", f"RSI(14, M15) at the pullback {r_lo}–{r_hi}", "RSI في المجال المطلوب", r_lo <= rsi_v <= r_hi, f"RSI {to_fixed(rsi_v, 1)}",
                         W["momentum"], True),
                    item("trigger", "Confirmation: engulfing, pin bar or M15 CHoCH", "شمعة تأكيد", True,
                         f"{trigger} closed at {f(c.close)} ({fmt_time(c.time + 900)})", W["trigger"], True, 1 if choch else 0.9 if engulf else 0.8),
                    *common_checks(setup["signalTime"], direction, entry, setup["sl"], setup["tp2"], setup["slDistance"]),
                ]
                candidates.append({"setup": setup, "checklist": checklist, "score": score_checklist(checklist),
                                   "requiredOk": all(x["passed"] or not x["required"] for x in checklist)})
                break
            if not candidates and not progress_a:
                progress_a = "Waiting for a pullback into the confluence zone"
    else:
        progress_a = "H4 trend not clear: no trade"

    # ---- Setup B: Asian range false breakout ----
    if asia and asia.complete:
        range_pips = pips(asia.high - asia.low)
        asia_levels = _asia_levels(asia)
        london = SES["windows"][0]
        sweeps = [s for s in find_sweeps(m15, asia_levels, 0, last, last_value(atr15)) if in_local_window(s.time, london["tz"], london["start"], london["end"])]
        range_ok = B["minRangePips"] <= range_pips <= B["maxRangePips"]
        if not range_ok:
            progress_b = f"Asian range {js_str(range_pips)} pips (needs {B['minRangePips']}–{B['maxRangePips']})"
        elif not sweeps:
            progress_b = f"Asian range {js_str(range_pips)} pips, waiting for a false breakout in the London window"
        for sw in (sweeps[::-1] if range_ok else []):
            direction = "SELL" if sw.level.side == "HIGH" else "BUY"
            need_bias = "BULLISH" if direction == "BUY" else "BEARISH"
            c = m15[sw.index]
            entry = round_to(c.close, d)
            structural_sl = sw.extreme - R["slBufferPips"] * pip if direction == "BUY" else sw.extreme + R["slBufferPips"] * pip
            opposite = asia.high if direction == "BUY" else asia.low
            setup = build_setup(f"EURUSD-B-{c.time}", "B", direction, sw.index, entry, structural_sl,
                                {"price": opposite, "label": f"Asian range {'high' if direction == 'BUY' else 'low'}"},
                                {"sweep": sw.to_dict(), "asia": {"high": asia.high, "low": asia.low}})
            checklist = [
                item("bias", f"H4 bias {need_bias.lower()} (trade only with the trend)", "توافق مع اتجاه H4", bias == need_bias, bias_detail, W["bias"], True),
                item("zone", f"Asian range {B['minRangePips']}–{B['maxRangePips']} pips", "نطاق آسيا مناسب", True,
                     f"Asian range {f(asia.low)}–{f(asia.high)} = {js_str(range_pips)} pips", W["zone"], True, 1),
                item("trigger", "False breakout: wick beyond the Asian range, close back inside", "اختراق كاذب لنطاق آسيا", True,
                     f"{sw.level.label} {f(sw.level.price)} taken to {f(sw.extreme)}, closed back inside at {f(c.close)} ({fmt_time(c.time + 900)})",
                     W["trigger"], True, 1 if sw.depthAtr <= 1.5 else 0.7),
                item("momentum", "Breakout failed on the first candle that took the level", "فشل الاختراق من أول شمعة", True,
                     f"{js_str(pips(abs(sw.extreme - sw.level.price)))} pips beyond the range", W["momentum"], False, 1),
                *common_checks(setup["signalTime"], direction, entry, setup["sl"], setup["tp2"], setup["slDistance"]),
            ]
            candidates.append({"setup": setup, "checklist": checklist, "score": score_checklist(checklist),
                               "requiredOk": all(x["passed"] or not x["required"] for x in checklist)})
            break
    else:
        progress_b = "Asian range not complete yet"

    # ---- Pick: valid candidates first, then the higher score, then the newer one ----
    candidates.sort(key=lambda c: (-int(c["requiredOk"]), -c["score"], -c["setup"]["signalTime"]))
    best = candidates[0] if candidates else None
    if best:
        result["setup"] = best["setup"]
        result["checklist"] = best["checklist"]
        result["score"] = best["score"]
        failed_items = [c for c in best["checklist"] if c["required"] and not c["passed"]]
        result["rejection"] = f"{failed_items[0]['rule']}: {failed_items[0]['detail']}" if failed_items else None
        result["status"] = classify(best["score"], best["requiredOk"], cfg["scoring"]["thresholds"])
        if result["status"] == "SIGNAL":
            result["signal"] = to_signal_json(spec, cfg["strategy"], best["setup"], best["score"], cfg["timeframes"], best["checklist"])
        result["canNotify"] = bool(result["status"] == "SIGNAL" and best["setup"]["isFresh"] and inp["isMarketOpen"])
    else:
        result["checklist"] = [
            item("bias", "H4 trend: close vs EMA200, EMA50 vs EMA200, HH/HL structure", "اتجاه H4 واضح", bias != "NEUTRAL", bias_detail, W["bias"], True),
            item("setupA", "Setup A: pullback into confluence + confirmation", "الإعداد A", False, progress_a or "Not found", 0, True),
            item("setupB", "Setup B: Asian range false breakout", "الإعداد B", False, progress_b or "Not found", 0, False),
        ]
        result["rejection"] = "H4 trend not clear" if bias == "NEUTRAL" else (progress_a or progress_b)

    # ---- Drawings ----
    max_n = cfg["drawings"]["maxPerType"]
    sessions = []
    for off in (1, 0):
        key = local_date_key(now - off * 86400, asia_cfg["tz"])
        a = session_range(m15, 900, "Asia", key, asia_cfg["tz"], asia_cfg["start"], asia_cfg["end"], now)
        if a:
            sessions.append(a)
        for i, w in enumerate(SES["windows"]):
            r = session_range(m15, 900, "London" if i == 0 else "NY", key, w["tz"], w["start"], w["end"], now)
            if r:
                sessions.append(r)
    drawings = [
        *session_drawings(sessions),
        *level_drawings(levels),
        *fib_drawing,
        *structure_drawings(st_h1, "H1", "M15", 3),
        *structure_drawings(st15, "M15", "M15", max_n),
        *swing_drawings(swings15, "M15", max_n),
        *ob_drawings(obs_h1, "H1", "M15", 3),
        *fvg_drawings(fvgs_h1, "H1", "M15", 3),
    ]
    if asia and asia.complete:
        drawings.extend(sweep_drawings(find_sweeps(m15, _asia_levels(asia), 0, last, last_value(atr15)), "M15", max_n))
    s = result["setup"]
    if s:
        drawings.extend(trade_drawings(s, "M15", f"{js_str(s['lots'].get('1000$', 0))} lot / $1k"))
    result["drawings"] = declutter_zones(drawings)

    result["facts"] = {
        "price": price, "spreadPips": round_to(spread / pip, 1), "atrM15Pips": pips(last_value(atr15)), "atrH1Pips": pips(vol["now"]),
        "volatilityRatio": round_to(vol["ratio"], 2),
        "bias": {"h4Close": h4_close, "ema50": round_to(e50, d), "ema200": round_to(e200, d), "h4Structure": h4_struct, "direction": bias},
        "window": result["market"]["window"] or "none",
        "asianRange": {"high": asia.high, "low": asia.low, "pips": pips(asia.high - asia.low), "complete": asia.complete} if asia else None,
        "levels": [{"kind": lv.kind, "price": lv.price} for lv in levels],
        "h1Structure": [{"type": e.type, "direction": e.direction, "level": e.level, "time": e.breakTime} for e in st_h1[-3:]],
        "m15Structure": [{"type": e.type, "direction": e.direction, "level": e.level, "time": e.breakTime} for e in st15[-4:]],
        "orderBlocksH1": [{"direction": o.direction, "top": o.top, "bottom": o.bottom, "state": o.state} for o in [o for o in obs_h1 if o.state != "BROKEN"][-3:]],
        "ema50M15": round_to(last_value(ema50m15), d),
        "rsiM15": round_to(last_value(rsi15), 1),
        "progress": {"setupA": progress_a, "setupB": progress_b},
    }

    status = result["status"]
    if not s:
        result["headline"] = "H4 trend not clear: no trade" if bias == "NEUTRAL" else (progress_a or progress_b or "No setup")
    elif status == "SIGNAL":
        result["headline"] = f"{s['direction']} (Setup {s['setup']}) at {f(s['entry'])} · score {result['score']}"
    elif status == "WATCH":
        result["headline"] = f"{s['direction']} Setup {s['setup']} watch · score {result['score']}"
    elif status == "IGNORE":
        result["headline"] = f"Setup {s['setup']} scored {result['score']}: ignored"
    else:
        first_failed = next((c for c in result["checklist"] if c["required"] and not c["passed"]), None)
        result["headline"] = f"Setup {s['setup']} rejected: {first_failed['rule'] if first_failed else 'undefined'}"
    result["headlineAr"] = (f"إشارة {s['direction']} (الإعداد {s['setup']})" if status == "SIGNAL" else "إعداد موجود لكنه غير مكتمل الشروط") if s else "لا توجد صفقة حالياً"
    return result


def _asia_levels(asia) -> list[Level]:
    return [
        Level(f"ASIA_H-{asia.dateKey}", "ASIA_H", "Asia H", asia.high, "HIGH", asia.startSec, asia.endSec, 1),
        Level(f"ASIA_L-{asia.dateKey}", "ASIA_L", "Asia L", asia.low, "LOW", asia.startSec, asia.endSec, 1),
    ]


def _js_min(*xs: float) -> float:
    return math.nan if any(math.isnan(x) for x in xs) else min(xs)


def _js_max(*xs: float) -> float:
    return math.nan if any(math.isnan(x) for x in xs) else max(xs)


def _nearest_daily_barrier(swings_d1: list[Swing], levels: list[Level], entry: float, buy: bool, upto_index: int) -> Optional[dict]:
    """Nearest daily barrier in the trade direction: untaken daily swing or PWH/PWL."""
    pool = []
    sw = nearest_swing_beyond(swings_d1, entry, buy, upto_index)
    if sw:
        pool.append({"price": sw.price, "label": "Daily resistance" if buy else "Daily support"})
    for lv in levels:
        if (lv.kind == "PWH" and lv.price > entry) if buy else (lv.kind == "PWL" and lv.price < entry):
            pool.append({"price": lv.price, "label": lv.label})
    pool.sort(key=lambda x: x["price"] if buy else -x["price"])
    return pool[0] if pool else None


def _nearest_h1_target(swings_h1: list[Swing], levels: list[Level], entry: float, buy: bool, upto_index: int, min_price: float) -> Optional[dict]:
    """Nearest H1 target beyond `min_price` (untaken H1 swing, PDH/PDL, PWH/PWL)."""
    pool = []
    kind = "HIGH" if buy else "LOW"
    for s in swings_h1:
        if s.kind != kind or s.confirmedIndex > upto_index or (s.takenIndex is not None and s.takenIndex <= upto_index):
            continue
        pool.append({"price": s.price, "label": "H1 swing high" if buy else "H1 swing low"})
    for lv in levels:
        if lv.side == ("HIGH" if buy else "LOW"):
            pool.append({"price": lv.price, "label": lv.label})
    pool = [x for x in pool if (x["price"] >= min_price if buy else x["price"] <= min_price)]
    pool.sort(key=lambda x: x["price"] if buy else -x["price"])
    return pool[0] if pool else None
