"""
XAUUSD (Gold) — "Liquidity Sweep + MSS + FVG"

Bias (H4 + H1): bullish if H1 close > EMA200(H1) AND the last H4 structure break is bullish;
bearish mirror; disagreement = no trade.
Kill zones: London 08:00–11:00 London time, New York 08:30–11:30 New York time.
Sequence (M5, all required, in order):
  1. Sweep of a key level against the bias (Asian low/PDL/PWL/EQL/round number for buys).
  2. Within 6 M5 candles: MSS/CHoCH in the bias direction with displacement (body > 1.5× avg body 20).
  3. The displacement leaves an FVG (else an OB).
  4. LIMIT entry at FVG 50% (or OB 50%).
Risk: SL beyond the sweep wick + 0.2 × ATR(14, M5) + spread, $2–$8. TP1 = 1R (50%, SL to BE),
TP2 = nearest opposing liquidity (min 1:2), TP3 = next H1 level or 3R. Pending order expires
after 45 minutes or when TP1 trades first.
"""

import math

from ..shared.common import active_window, is_untaken, item, nearest_swing_beyond, new_result, to_signal_json, volatility_ratio
from ..shared.drawings import (declutter_zones, fvg_drawings, level_drawings, ob_drawings, session_drawings, structure_drawings,
                               sweep_drawings, swing_drawings, trade_drawings)
from ..shared.indicators import atr_series, avg_body_series, ema_series, last_value
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_div, js_str, round_to, to_fixed
from ..shared.liquidity import Level, daily_weekly_levels, equal_levels, find_sweeps, round_number_levels
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, to_pips
from ..shared.sessions import local_date_key, session_range
from ..shared.structure import detect_structure, detect_swings
from ..shared.types import closed_only
from ..shared.zones import Fvg, detect_fvgs, detect_order_blocks
from .config import XAU_CONFIG

DAILY_KINDS = ("PDH", "PDL", "PWH", "PWL")


def evaluate_xauusd(inp: dict, cfg: dict = XAU_CONFIG) -> dict:
    spec = cfg["spec"]
    d = spec["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    now = inp["nowSec"]
    candles = inp["candles"]
    m5 = closed_only(candles.get("M5") or [], 300, now)[-600:]
    m15 = closed_only(candles.get("M15") or [], 900, now)[-900:]
    h1 = closed_only(candles.get("H1") or [], 3600, now)[-800:]
    h4 = closed_only(candles.get("H4") or [], 14400, now)[-300:]
    last = len(m5) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (m5[last].close if m5 else 0)
    spread = inp["spread"] if inp["spread"] is not None else cfg["filters"]["assumedSpread"]
    S = cfg["structure"]
    R = cfg["risk"]
    SET = cfg["setup"]
    FIL = cfg["filters"]

    result = new_result(spec, cfg, inp, price)

    # ---- Data quality ----
    stale = inp["isMarketOpen"] and len(m5) > 0 and now - (m5[last].time + 300) > 3 * 300
    if not inp["isRealData"] or len(m5) < 150 or len(h1) < cfg["bias"]["emaPeriod"] + 20 or len(h4) < 40 or stale:
        result["dataQuality"] = {
            "ok": False, "source": inp["dataSource"],
            "reason": "Live feed unavailable (synthetic candles): no analysis" if not inp["isRealData"]
            else "Last M5 candle is stale (feed paused)" if stale
            else f"Not enough history (M5 {len(m5)}, H1 {len(h1)}, H4 {len(h4)})",
        }
        return _finish(result, "Data not usable", "البيانات غير صالحة")

    # ---- Detectors ----
    atr5 = atr_series(m5, cfg["atrPeriod"])
    atr_now5 = last_value(atr5)
    swings5 = detect_swings(m5, S["swingN"])
    st5, _ = detect_structure(m5, swings5, avg_body_series(m5, S["avgBodyPeriod"]), S["displacementMult"])
    fvgs5 = detect_fvgs(m5, atr5, cfg["fvgMinAtr"], "M5")
    obs5 = detect_order_blocks(m5, st5, "M5")

    atr_h1 = atr_series(h1, cfg["atrPeriod"])
    swings_h1 = detect_swings(h1, S["htfSwingN"])
    st_h1, _ = detect_structure(h1, swings_h1, avg_body_series(h1, S["avgBodyPeriod"]), S["displacementMult"])
    fvgs_h1 = detect_fvgs(h1, atr_h1, cfg["fvgMinAtr"], "H1")
    obs_h1 = detect_order_blocks(h1, st_h1, "H1")
    swings_h4 = detect_swings(h4, S["htfSwingN"])
    st_h4, _ = detect_structure(h4, swings_h4, avg_body_series(h4, S["avgBodyPeriod"]), S["displacementMult"])

    # ---- Bias ----
    ema200 = last_value(ema_series([x.close for x in h1], cfg["bias"]["emaPeriod"]))
    h1_close = h1[-1].close
    h1_dir = "BULLISH" if h1_close > ema200 else "BEARISH"
    last_h4 = st_h4[-1] if st_h4 else None
    h4_dir = last_h4.direction if last_h4 else "NEUTRAL"
    bias = h1_dir if h1_dir == h4_dir else "NEUTRAL"
    h4_txt = f"{last_h4.type} {last_h4.direction.lower()} at {f(last_h4.level)}" if last_h4 else "break: none"
    bias_detail = f"H1 close {f(h1_close)} {'>' if h1_close > ema200 else '<'} EMA200 {f(ema200)} · H4 last {h4_txt}"
    result["bias"] = {"direction": bias, "detail": bias_detail}

    # ---- Levels ----
    asia_cfg = cfg["sessions"]["asia"]
    today_key = local_date_key(now, asia_cfg["tz"])
    asia = session_range(m5, 300, "Asia", today_key, asia_cfg["tz"], asia_cfg["start"], asia_cfg["end"], now)
    london_kz = cfg["sessions"]["killzones"][0]
    london_range = session_range(m5, 300, "London", today_key, london_kz["tz"], london_kz["start"], london_kz["end"], now)
    levels: list[Level] = list(daily_weekly_levels(m15))
    if asia and asia.complete:
        levels.append(Level(f"ASIA_H-{asia.dateKey}", "ASIA_H", "Asia H", asia.high, "HIGH", asia.startSec, asia.endSec, 0.9))
        levels.append(Level(f"ASIA_L-{asia.dateKey}", "ASIA_L", "Asia L", asia.low, "LOW", asia.startSec, asia.endSec, 0.9))
    if london_range and london_range.complete:
        lr = london_range
        levels.append(Level(f"PSH-{lr.dateKey}", "PSH", "London H", lr.high, "HIGH", lr.startSec, lr.endSec, 0.8))
        levels.append(Level(f"PSL-{lr.dateKey}", "PSL", "London L", lr.low, "LOW", lr.startSec, lr.endSec, 0.8))
    recent_start = m5[max(0, last - SET["sweepLookbackBars"] * 3)].time
    levels.extend(lv for lv in equal_levels(swings5, atr_now5, cfg["equalLevelTolAtr"], last) if lv.time >= recent_start)
    if cfg["roundNumbers"]["enabled"]:
        levels.extend(round_number_levels(price, cfg["roundNumbers"]["steps"], cfg["roundNumbers"]["count"], m5[0].time))

    # ---- Filters (evaluated for every state) ----
    vol = volatility_ratio(atr_h1, FIL["volatility"]["lookbackBars"])
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    result["news"] = {
        "blocked": news["blocked"],
        "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else "No high-impact USD news within ±30 min",
        "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None,
        "source": inp["news"]["source"],
    }
    win = active_window(now, cfg["sessions"]["killzones"])
    result["market"]["window"] = win["name"] if win else None

    # ---- Setup search ----
    W = cfg["scoring"]["weights"]
    checklist: list[dict] = [item("bias", "H4 and H1 bias agree", "توافق اتجاه H4 و H1", bias != "NEUTRAL", bias_detail, W["bias"], True)]

    setup = None
    progress = "H4 and H1 disagree: no trade" if bias == "NEUTRAL" else ""
    chosen = None

    if bias != "NEUTRAL":
        buy = bias == "BULLISH"
        sweepable = [lv for lv in levels if lv.side == ("LOW" if buy else "HIGH") and lv.kind in SET["sweepKinds"]]
        sweeps = find_sweeps(m5, sweepable, max(0, last - SET["sweepLookbackBars"]), last, atr_now5)[::-1]
        if not sweeps:
            progress = f"Waiting for a sweep of {'sell-side (Asia L / PDL / EQL)' if buy else 'buy-side (Asia H / PDH / EQH)'} liquidity"

        max_bars = SET["maxBarsSweepToMss"]
        for sw in sweeps:
            mss = next((e for e in st5 if e.direction == bias and sw.index < e.breakIndex <= sw.index + max_bars), None)
            if not mss:
                progress = progress or f"Sweep of {sw.level.label} {f(sw.level.price)} at {fmt_time(sw.time)}, waiting for an M5 MSS within {max_bars} candles"
                if last - sw.index <= max_bars:
                    break
                continue
            protected_ok = True
            for i in range(sw.index + 1, mss.breakIndex + 1):
                if (m5[i].low < sw.extreme) if buy else (m5[i].high > sw.extreme):
                    protected_ok = False
            if not protected_ok:
                progress = progress or f"Sweep low/high at {f(sw.extreme)} was broken before the MSS"
                continue
            if mss.displacementIndex is None or mss.displacementIndex <= sw.index:
                progress = progress or (f"MSS at {fmt_time(mss.breakTime)} has no displacement (body {to_fixed(mss.displacementMult, 2)}× avg "
                                        f"< {js_str(S['displacementMult'])}×)")
                continue

            break_time = m5[mss.breakIndex].time
            fvg_pool = [z for z in fvgs5 if z.direction == bias and sw.index < z.createdIndex <= mss.breakIndex + 2
                        and not (z.filledTime is not None and z.filledTime <= break_time)]
            fvg_pool.sort(key=lambda z: z.bottom if buy else -z.top)
            fvg = fvg_pool[0] if fvg_pool else None
            ob = next((o for o in obs5 if o.breakTime == mss.breakTime and o.state != "BROKEN"), None)
            if not fvg and not ob:
                progress = progress or f"MSS at {fmt_time(mss.breakTime)} left no FVG or order block"
                continue
            ready_idx = max(mss.breakIndex, fvg.createdIndex) if fvg else mss.breakIndex
            if ready_idx > last:
                progress = progress or "Waiting for the FVG candle to close"
                break
            chosen = (sw, mss, ("FVG", fvg) if fvg else ("OB", ob), ready_idx)
            break

        if chosen:
            sw, mss, (poi_kind, zone), ready_idx = chosen
            entry = round_to(zone.ce if poi_kind == "FVG" else zone.mid, d)
            atr_at = atr5[ready_idx]
            buffer = R["slAtrBuffer"] * (atr_at if atr_at and not math.isnan(atr_at) else atr_now5) + spread
            sl = round_to(sw.extreme - buffer if buy else sw.extreme + buffer, d)
            sl_dist = abs(entry - sl)
            tp1 = round_to(entry + R["tp1R"] * sl_dist if buy else entry - R["tp1R"] * sl_dist, d)
            targets = [lv for lv in levels if lv.side == ("HIGH" if buy else "LOW") and lv.kind in SET["targetKinds"]
                       and (lv.price > entry if buy else lv.price < entry) and is_untaken(lv, m5, ready_idx)]
            targets.sort(key=lambda lv: lv.price if buy else -lv.price)
            tgt = targets[0] if targets else None
            tp2 = round_to(tgt.price if tgt else (entry + R["minRrTp2"] * sl_dist if buy else entry - R["minRrTp2"] * sl_dist), d)
            rr_tp2 = rr(entry, sl, tp2)
            h1_next = nearest_swing_beyond(swings_h1, tp2, buy, len(h1) - 1)
            tp3 = round_to(h1_next.price if h1_next else (entry + R["tp3R"] * sl_dist if buy else entry - R["tp3R"] * sl_dist), d)
            if (tp3 <= tp2) if buy else (tp3 >= tp2):
                tp3 = round_to(tp2 + sl_dist if buy else tp2 - sl_dist, d)
            signal_time = m5[ready_idx].time + 300
            expires_at = signal_time + R["orderExpiryMin"] * 60
            params = {
                "side": "BUY" if buy else "SELL", "entryType": "LIMIT", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "expiryTime": expires_at, "cancelIfTp1BeforeFill": R["cancelIfTp1First"], "partials": R["partials"],
                "spread": spread, "slippage": FIL["slippage"],
            }
            lifecycle = simulate_lifecycle(m5, params, ready_idx + 1)
            min_rr_txt = js_str(R["minRrTp2"])
            setup = {
                "id": f"XAUUSD-{sw.time}-{mss.breakTime}",
                "setup": "GOLD",
                "direction": "BUY" if buy else "SELL",
                "entryType": "LIMIT",
                "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "tp2Source": f"{tgt.label} (opposing liquidity)" if tgt else f"{min_rr_txt}R (no opposing liquidity in range)",
                "tp3Source": "Next H1 swing level" if h1_next else f"{js_str(R['tp3R'])}R",
                "rrTp2": rr_tp2,
                "slDistance": round_to(sl_dist, d),
                "slPips": to_pips(spec, sl_dist),
                "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
                "signalTime": signal_time,
                "signalIndex": ready_idx,
                "expiresAt": expires_at,
                "invalidation": f"M5 close {'below' if buy else 'above'} {f(sl)} before entry, order not filled by {fmt_time(expires_at)}, or TP1 {f(tp1)} reached first",
                "isFresh": ready_idx == last,
                "lifecycle": lifecycle,
                "params": params,
                "anchors": {"sweep": sw.to_dict(), "mss": mss.to_dict(), "poi": {
                    "kind": poi_kind, "top": zone.top, "bottom": zone.bottom,
                    "time": zone.startTime if poi_kind == "FVG" else zone.time}},
            }

            # ---- Checklist (in rule order) ----
            sig_win = active_window(signal_time - 1, cfg["sessions"]["killzones"])
            checklist.append(item("killzone", "Inside a kill zone (London 08:00–11:00 / NY 08:30–11:30)", "داخل نافذة السيولة (لندن / نيويورك)", sig_win is not None,
                                  f"{sig_win['name']} at {fmt_time(signal_time)}" if sig_win else f"Setup completed at {fmt_time(signal_time)}, outside both kill zones",
                                  W["killzone"], True))
            depth_q = 0.6 if sw.depthAtr < 0.05 else 0.7 if sw.depthAtr > 1.5 else 1
            checklist.append(item("sweep", "Liquidity sweep against the bias", "سحب سيولة عكس الاتجاه", True,
                                  f"{sw.level.label} {f(sw.level.price)} swept at {fmt_time(sw.time)}, wick {f(sw.extreme)} ({to_fixed(sw.depthAtr, 2)}× ATR), closed back inside",
                                  W["sweep"], True, sw.level.weight * depth_q))
            checklist.append(item("mss", f"M5 MSS within {max_bars} candles with displacement > {js_str(S['displacementMult'])}× avg body", "كسر هيكلي M5 مع اندفاع", True,
                                  f"{'CHoCH' if mss.type == 'CHOCH' else 'BOS'} close beyond {f(mss.level)} at {fmt_time(mss.breakTime + 300)}, "
                                  f"{mss.breakIndex - sw.index} candles after the sweep, displacement {to_fixed(mss.displacementMult, 2)}× avg body",
                                  W["displacement"], True, 0.5 + (mss.displacementMult - S["displacementMult"]) / 3))
            checklist.append(item("poi", "Displacement left an FVG (else an OB)", "فجوة FVG أو بلوك أوامر", True,
                                  f"{poi_kind} {f(zone.bottom)}–{f(zone.top)}, limit at 50% {f(entry)}", W["poi"], True,
                                  (1 if zone.sizeAtr >= 0.5 else 0.8) if poi_kind == "FVG" else 0.7))
            checklist.append(item("sl", f"Stop ${js_str(R['minSl'])}–${js_str(R['maxSl'])} beyond the sweep wick", "وقف خسارة بين 2 و 8 دولار",
                                  R["minSl"] <= sl_dist <= R["maxSl"],
                                  f"SL {f(sl)} = ${to_fixed(sl_dist, 2)} (wick {f(sw.extreme)} + 0.2× ATR + spread)", 0, True))
            checklist.append(item("rr", f"R:R to TP2 >= 1:{min_rr_txt}", "عائد للهدف الثاني 1:2 على الأقل", rr_tp2 >= R["minRrTp2"],
                                  f"TP2 {f(tp2)} = {setup['tp2Source']}, 1:{to_fixed(rr_tp2, 2)}", W["rr"], True, 1 if rr_tp2 >= 3 else 0.7))
            htf = nearest_swing_beyond(swings_h1, entry, buy, len(h1) - 1)
            htf_r = js_div(abs(htf.price - entry), sl_dist) if htf else 99
            checklist.append(item("htf", "Room to the next H1 level", "مسافة كافية حتى مستوى H1", htf_r >= 1,
                                  f"Next H1 {'high' if buy else 'low'} {f(htf.price)} = {to_fixed(htf_r, 1)}R away" if htf else "No H1 level in the way",
                                  W["htfDistance"], False, 1 if htf_r >= 2 else 0.6 if htf_r >= 1 else 0.2))
        else:
            checklist.append(item("setup", "Sweep → MSS → FVG sequence", "تسلسل سحب السيولة ← كسر الهيكل ← FVG", False,
                                  progress or "No setup in the lookback window", 0, True))

    V = FIL["volatility"]
    vol_ok = V["min"] <= vol["ratio"] <= V["max"]
    checklist.append(item("volatility", f"ATR(14,H1) between {js_str(V['min'] * 100)}% and {js_str(V['max'] * 100)}% of its 20-day average", "التقلب في المجال الطبيعي", vol_ok,
                          f"ATR H1 {to_fixed(vol['now'], 2)} = {to_fixed(vol['ratio'] * 100, 0)}% of 20-day average {to_fixed(vol['avg'], 2)}",
                          W["volatility"], True, 1 if 0.8 <= vol["ratio"] <= 1.8 else 0.6))
    checklist.append(item("news", "No high-impact USD news ±30 min", "لا أخبار قوية للدولار ±30 دقيقة", not news["blocked"], result["news"]["detail"], 0, True))
    checklist.append(item("spread", f"Spread <= ${js_str(FIL['maxSpread'])}", "السبريد مقبول", spread <= FIL["maxSpread"],
                          f"Spread ${to_fixed(spread, 2)}{' (assumed, no live spread in feed)' if inp['spread'] is None else ''}", 0, True))
    day = inp["day"]
    day_ok = day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"]
    checklist.append(item("daily", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} losses per day", "حد الصفقات اليومي", day_ok,
                          f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True))

    result["checklist"] = checklist
    result["setup"] = setup
    result["score"] = score_checklist(checklist) if setup else 0
    failed = [c for c in checklist if c["required"] and not c["passed"]]
    result["rejection"] = f"{failed[0]['rule']}: {failed[0]['detail']}" if failed else None
    result["status"] = classify(result["score"], not failed, cfg["scoring"]["thresholds"]) if setup else "NO_TRADE"
    if setup and result["status"] == "SIGNAL":
        result["signal"] = to_signal_json(spec, cfg["strategy"], setup, result["score"], cfg["timeframes"], checklist)
    result["canNotify"] = bool(result["status"] == "SIGNAL" and setup and setup["isFresh"] and setup["lifecycle"]["state"] == "PENDING" and inp["isMarketOpen"])

    # ---- Drawings ----
    max_n = cfg["drawings"]["maxPerType"]
    sessions = []
    for day_offset in (1, 0):
        key = local_date_key(now - day_offset * 86400, asia_cfg["tz"])
        a = session_range(m5, 300, "Asia", key, asia_cfg["tz"], asia_cfg["start"], asia_cfg["end"], now)
        if a:
            sessions.append(a)
        for kz in cfg["sessions"]["killzones"]:
            r = session_range(m5, 300, "London" if kz["name"].startswith("London") else "NY", local_date_key(now - day_offset * 86400, kz["tz"]),
                              kz["tz"], kz["start"], kz["end"], now)
            if r:
                sessions.append(r)
    shown_levels = [lv for lv in levels if lv.kind != "ROUND" or abs(lv.price - price) <= 12]
    drawings = [
        *session_drawings(sessions),
        *level_drawings([lv for lv in shown_levels if is_untaken(lv, m5, last) or lv.kind in DAILY_KINDS]),
        *structure_drawings(st_h1, "H1", "M5", 3),
        *structure_drawings(st5, "M5", "M5", max_n),
        *swing_drawings(swings5, "M5", max_n),
        *fvg_drawings(fvgs_h1, "H1", "M5", 2),
        *fvg_drawings(fvgs5, "M5", "M5", 3),
        *ob_drawings(obs_h1, "H1", "M5", 2),
        *ob_drawings(obs5, "M5", "M5", 3),
        *sweep_drawings(find_sweeps(m5, levels, max(0, last - 200), last, atr_now5), "M5", max_n),
    ]
    if setup:
        drawings.extend(trade_drawings(setup, "M5", f"{js_str(setup['lots'].get('1000$', 0))} lot / $1k"))
    result["drawings"] = declutter_zones(drawings)

    # ---- Facts for the AI agent (detector output only) ----
    result["facts"] = {
        "price": price, "spread": spread, "atrM5": round_to(atr_now5, 2), "atrH1": round_to(vol["now"], 2), "volatilityRatio": round_to(vol["ratio"], 2),
        "bias": {"h1": h1_dir, "h1Close": h1_close, "ema200": round_to(ema200, d), "h4": h4_dir,
                 "h4LastBreak": {"type": last_h4.type, "direction": last_h4.direction, "level": last_h4.level, "time": last_h4.breakTime} if last_h4 else None},
        "killzone": win["name"] if win else "none",
        "asianRange": {"high": asia.high, "low": asia.low, "complete": asia.complete} if asia else None,
        "levels": [{"kind": lv.kind, "label": lv.label, "price": lv.price, "untaken": is_untaken(lv, m5, last)} for lv in shown_levels],
        "m5Structure": [{"type": e.type, "direction": e.direction, "level": e.level, "time": e.breakTime, "displacement": round_to(e.displacementMult, 2)} for e in st5[-5:]],
        "h1Structure": [{"type": e.type, "direction": e.direction, "level": e.level, "time": e.breakTime} for e in st_h1[-3:]],
        "fvgsM5": [{"direction": z.direction, "top": z.top, "bottom": z.bottom, "state": z.state} for z in [z for z in fvgs5 if z.state != "FILLED"][-max_n:]],
        "orderBlocksH1": [{"direction": o.direction, "top": o.top, "bottom": o.bottom, "state": o.state} for o in [o for o in obs_h1 if o.state != "BROKEN"][-3:]],
        "progress": progress,
    }

    side = setup["direction"] if setup else ""
    status = result["status"]
    if not setup:
        headline = progress or "No setup"
    elif status == "SIGNAL":
        headline = f"{side} limit {f(setup['entry'])} · score {result['score']}"
    elif status == "WATCH":
        headline = f"{side} watch · score {result['score']} (needs {cfg['scoring']['thresholds']['signal']})"
    elif status == "IGNORE":
        headline = f"{side} setup scored {result['score']}: ignored"
    else:
        headline = f"{side} setup rejected: {failed[0]['rule'] if failed else 'undefined'}"
    headline_ar = (f"إشارة {side} عند {f(setup['entry'])}" if status == "SIGNAL" else "إعداد موجود لكنه غير مكتمل الشروط") if setup else "لا توجد صفقة حالياً"
    return _finish(result, headline, headline_ar)


def _finish(r: dict, headline: str, headline_ar: str) -> dict:
    r["headline"] = headline
    r["headlineAr"] = headline_ar
    return r
