"""
The SMC multi-agent pipeline of each pair: six agents in sequence, coded as mechanical rules (no discretion, no
lookahead, the same candles give the same report), filling the SMCAnalysisReport the chart and the panels read.

  AGENT_0  Pair isolation & context guard     the locked symbol / timeframes, price scale sanity, candle order, data age
  AGENT_1  Structure & pullback architect      H1 / M15 / M5 bias by the valid-pullback rule (mother candle, inside bars
                                               ignored), the last body-close BOS / CHoCH or wick sweep, the dealing range
                                               (confirmed swing low → high), its 50 % and the OTE band (61.8–78.6 %)
  AGENT_2  Liquidity & inducement hunter        the IDM (first internal pullback after the break) swept or not, BSL / SSL:
                                               PDH / PDL, PWH / PWL, Asian high / low, equal highs / lows, swept or not,
                                               the draw on liquidity, the retail trap of the moment
  AGENT_3  PD array & valuation inspector       H1 order blocks with their 4-point audit (FVG after it, caused a break,
                                               unmitigated, IDM in front), decisional vs extreme, FVG / inversion FVG,
                                               breaker blocks, supply-demand flip zones
  AGENT_4  Strategy & LTF execution sniper      the pair matched to the 4 strategies (1 trend continuation, 2 external sweep
                                               reversal, 3 session killzone sweep, 4 flip / single candle) and the state of
                                               its M5 trigger
  AGENT_5  Risk & trade manager                 RR ≥ 3 to the final target, TP1 at 1:3 (50 % partial), TP2 the external
                                               liquidity, break-even after the first M5 internal BOS, the 7 questions, lots

Every price and time in the report belongs to the locked symbol, at its precision; every zone carries its symbol and
timeframe and is anchored to times and prices, never to candle indexes.
"""

from typing import Optional

from .smc_setups import DAY, H1S, M5S, H1View, Structure, _h1_pois, fvgs

STRATEGY_ID = {"A": "STRATEGY_1_TREND_CONTINUATION", "B": "STRATEGY_2_EXTERNAL_SWEEP_REVERSAL", "D": "STRATEGY_3_SESSION_KILLZONE_SWEEP",
               "C": "STRATEGY_4_FLIP_OR_SINGLE_CANDLE", "E": "STRATEGY_4_FLIP_OR_SINGLE_CANDLE"}
STRATEGY_DARIJA = {
    "A": "الاستراتيجية 1: الاستمرار مع الاتجاه العام بعد سحب الـ IDM",
    "B": "الاستراتيجية 2: صيد السيولة الخارجية والانعكاس (PDH / PDL)",
    "D": "الاستراتيجية 3: سحب نطاق آسيا فـ killzone ديال لندن ولا نيويورك",
    "C": "الاستراتيجية 4: انقلاب المنطقة (S2D / D2S)",
    "E": "الاستراتيجية 4: الشمعة الواحدة القناصة (50% ديال شمعة الساعة)",
}
STATE_ORDER = {"CONFIRMED": 0, "RUNNING": 1, "FORMING": 2, "BLOCKED": 3, "WAITING": 4}


def _aggregate(c, step: int):
    out = []
    for x in c:
        t = x.time - x.time % step
        if out and out[-1]["time"] == t:
            o = out[-1]
            o["high"], o["low"], o["close"] = max(o["high"], x.high), min(o["low"], x.low), x.close
        else:
            out.append({"time": t, "open": x.open, "high": x.high, "low": x.low, "close": x.close})

    class K:
        __slots__ = ("time", "open", "high", "low", "close")

        def __init__(s, d):
            s.time, s.open, s.high, s.low, s.close = d["time"], d["open"], d["high"], d["low"], d["close"]
    return [K(d) for d in out]


def _bias(trend: int) -> str:
    return "BULLISH" if trend > 0 else "BEARISH" if trend < 0 else "RANGING"


def _last_event(st: Structure, upto: int, kinds=("BOS", "CHOCH")) -> Optional[tuple[int, tuple]]:
    for i in range(upto, max(-1, upto - 400), -1):
        for e in st.ev[i]:
            if e[0] in kinds:
                return i, e
    return None


def agent0(symbol: str, spec: dict, m5, h1, price: float, now: int, market_open: bool) -> dict:
    checks = []
    def asc(c) -> bool:
        tail = c[-500:]
        return all(a.time < b.time for a, b in zip(tail, tail[1:]))
    checks.append(("candles ascending, one per time", asc(m5) and asc(h1)))
    ref = m5[-1].close if m5 else 0
    checks.append(("live price on this pair's scale (within 20 % of its last close)", bool(ref) and abs(price - ref) / ref <= 0.2))
    checks.append(("enough history (H1 ≥ 260, M5 ≥ 600)", len(h1) >= 260 and len(m5) >= 600))
    age = now - (m5[-1].time + M5S) if m5 else 10 ** 9
    checks.append(("fresh data (last M5 close under 20 min old)" if market_open else "market closed: last data kept", age <= 1200 or not market_open))
    return {"symbol": spec["symbol"], "pair": symbol, "htfTimeframe": "1h", "itfTimeframe": "15m", "ltfTimeframe": "5m", "timestampUTC": now,
            "currentPrice": round(price, spec["decimals"]), "pricePrecision": spec["decimals"], "pipSize": spec["pipSize"],
            "guard": {"ok": all(ok for _, ok in checks), "checks": [{"label": a, "ok": ok} for a, ok in checks]}}


def agent1(h1v: H1View, m5, price: float, dec: int) -> dict:
    st, c = h1v.st, h1v.c
    i = len(c) - 1
    htf = _bias(st.trend[i])
    m15 = _aggregate(m5[-1200:], 900)
    st15, st5 = Structure(m15), Structure(m5[-600:])
    itf_t, ltf_t = _bias(st15.trend[-1]), _bias(st5.trend[-1])
    itf = itf_t if itf_t == htf or htf == "RANGING" else f"{itf_t}_PULLBACK"
    ltf_ev = _last_event(st5, len(st5.c) - 1)
    ltf = ltf_t
    if ltf_ev and len(st5.c) - 1 - ltf_ev[0] <= 12:
        ltf = f"{'BULLISH' if ltf_ev[1][1] > 0 else 'BEARISH'}_{ltf_ev[1][0]}_FRESH"
    ev = _last_event(st, i)
    sweep = _last_event(st, i, ("SWEEP",))
    last_event = None
    if ev:
        k, e = ev
        last_event = {"type": f"{'BULLISH' if e[1] > 0 else 'BEARISH'}_{e[0]}", "price": round(e[2], dec), "time": c[k].time, "isBodyClose": True}
    last_sweep = None
    if sweep and (not ev or sweep[0] >= ev[0]):
        k, e = sweep
        last_sweep = {"type": "LIQUIDITY_SWEEP", "side": "BSL" if e[1] > 0 else "SSL", "price": round(e[2], dec), "time": c[k].time,
                      "note": "a wick through the level and a close back inside: liquidity taken, not a break"}
    rng = None
    sh, sl = st.last_sh[i], st.last_sl[i]
    if sh and sl and sh[0] > sl[0]:
        hi, lo = sh[0], sl[0]
        eq = lo + 0.5 * (hi - lo)
        pos = (price - lo) / (hi - lo)
        val = "PREMIUM" if pos > 0.52 else "DISCOUNT" if pos < 0.48 else "EQUILIBRIUM"
        if pos > 1 or pos < 0:
            val = "ABOVE_RANGE" if pos > 1 else "BELOW_RANGE"
        up = htf != "BEARISH"
        ote = (hi - 0.786 * (hi - lo), hi - 0.618 * (hi - lo)) if up else (lo + 0.618 * (hi - lo), lo + 0.786 * (hi - lo))
        rng = {"confirmedSwingLow": {"price": round(lo, dec), "time": c[sl[1]].time}, "confirmedSwingHigh": {"price": round(hi, dec), "time": c[sh[1]].time},
               "equilibrium50": round(eq, dec), "currentValuation": val, "positionPct": round(100 * pos, 1),
               "ote": {"from": round(min(ote), dec), "to": round(max(ote), dec), "side": "BUY" if up else "SELL"}}
    return {"htfBias": htf, "itfBias": itf, "ltfBias": ltf, "lastStructuralEvent": last_event, "lastSweep": last_sweep, "dealingRange": rng}


def agent2(h1v: H1View, m5, price: float, dec: int, bias: str, atr1: float) -> dict:
    c, st = h1v.c, h1v.st
    last = len(c) - 1
    day_now = m5[-1].time // DAY
    today = [x for x in m5 if x.time // DAY == day_now]
    before = [x for x in m5 if x.time // DAY < day_now]
    prev = [x for x in before if x.time // DAY == before[-1].time // DAY] if before else []
    week = (m5[-1].time // DAY + 3) // 7
    prev_week = [x for x in c if (x.time // DAY + 3) // 7 == week - 1]
    asia = [x for x in today if x.time % DAY < 6 * H1S]
    levels = []

    def add(label, p, side, since):
        if p is None:
            return
        swept = any((x.high > p) if side == "BSL" else (x.low < p) for x in since)
        levels.append({"label": label, "price": round(p, dec), "side": side, "swept": swept})
    if prev:
        add("PDH", max(x.high for x in prev), "BSL", today)
        add("PDL", min(x.low for x in prev), "SSL", today)
    if prev_week:
        this_week = [x for x in c if (x.time // DAY + 3) // 7 == week]
        add("PWH", max(x.high for x in prev_week), "BSL", this_week)
        add("PWL", min(x.low for x in prev_week), "SSL", this_week)
    if len(asia) >= 48:
        after = [x for x in today if x.time % DAY >= 6 * H1S]
        add("Asian High", max(x.high for x in asia), "BSL", after)
        add("Asian Low", min(x.low for x in asia), "SSL", after)
    # equal highs / lows: two of the last H1 swings within 0.1 ATR of each other, not taken since
    tol = 0.1 * atr1
    for kind, lst, side in (("EQH", st.swing_highs_after[-12:], "BSL"), ("EQL", st.swing_lows_after[-12:], "SSL")):
        vals = [(k, c[k].high if side == "BSL" else c[k].low) for k in lst]
        for a in range(len(vals) - 1, 0, -1):
            hit = next(((k, p) for k, p in vals[:a] if abs(p - vals[a][1]) <= tol), None)
            if hit:
                lvl = max(hit[1], vals[a][1]) if side == "BSL" else min(hit[1], vals[a][1])
                since = c[vals[a][0] + 1:]
                if not any((x.high > lvl) if side == "BSL" else (x.low < lvl) for x in since):
                    levels.append({"label": kind, "price": round(lvl, dec), "side": side, "swept": False})
                break
    # the IDM of the latest H1 break in the bias' direction
    pois = [p for p in _h1_pois(h1v, "A") if p["break"] >= last - 120]
    d = 1 if bias == "BULLISH" else -1 if bias == "BEARISH" else 0
    p = next((p for p in reversed(pois) if p["dir"] == d), None) if d else None
    idm = None
    if p:
        swept = any((x.low < p["idmLevel"]) if d > 0 else (x.high > p["idmLevel"]) for x in c[p["idm"] + 1:])
        idm = {"price": round(p["idmLevel"], dec), "time": c[p["idm"]].time, "status": "SWEPT" if swept else "UNSWEPT",
               "note": None if swept else "IDM not swept yet: an order block before it is a retail trap"}
    # the draw on liquidity: the nearest unswept pool on the bias side
    draw = None
    side = "BSL" if d > 0 else "SSL" if d < 0 else None
    if side:
        pool = [l for l in levels if l["side"] == side and not l["swept"] and ((l["price"] > price) if side == "BSL" else (l["price"] < price))]
        if pool:
            draw = min(pool, key=lambda l: abs(l["price"] - price))
    trap = None
    recent = m5[-12:]
    for l in levels:
        if l["swept"]:
            took = [x for x in recent if (x.high > l["price"]) if l["side"] == "BSL"] if l["side"] == "BSL" else [x for x in recent if x.low < l["price"]]
            if took and ((recent[-1].close < l["price"]) if l["side"] == "BSL" else (recent[-1].close > l["price"])):
                trap = f"{l['label']} {l['price']} swept in the last hour and price closed back inside: do not chase the breakout"
                break
    return {"idm": idm, "drawOnLiquidity": draw, "liquidityLevels": levels, "retailTrapWarning": trap,
            "trendlineLiquidity": "not mapped (diagonal lines are not read by the rules)"}


def agent3(h1v: H1View, sym: str, dec: int, price: float, rng: Optional[dict]) -> dict:
    c, st, fv = h1v.c, h1v.st, h1v.fv
    last = len(c) - 1
    end = c[last].time + 12 * H1S
    zones = []
    for p in [p for p in _h1_pois(h1v, "A") if p["break"] >= last - 160]:
        d, (lo, hi) = p["dir"], p["zone"]
        after = c[p["break"] + 1:]
        failed = any((x.close < lo) if d > 0 else (x.close > hi) for x in after)
        touched = any((x.low <= hi) if d > 0 else (x.high >= lo) for x in after)
        idm_swept = any((x.low < p["idmLevel"]) if d > 0 else (x.high > p["idmLevel"]) for x in c[p["idm"] + 1:])
        if failed:  # a broken OB flips: a breaker block
            zones.append({"kind": "BREAKER_BLOCK", "dir": -d, "lo": lo, "hi": hi, "t": c[p["ob"]].time, "fvg": True, "fresh": True, "idm": idm_swept,
                          "score": None})
            continue
        score = 1 + 1 + (0 if touched else 1) + (1 if idm_swept else 0)  # FVG after it (required) + the break + fresh + IDM
        zones.append({"kind": "OB", "dir": d, "lo": lo, "hi": hi, "t": c[p["ob"]].time, "fvg": True, "fresh": not touched, "idm": idm_swept, "score": score})
    for p in [p for p in _h1_pois(h1v, "C") if p["break"] >= last - 160]:
        lo, hi = p["zone"]
        zones.append({"kind": "FLIP_ZONE", "dir": p["dir"], "lo": lo, "hi": hi, "t": c[p["ob"]].time, "fvg": True, "fresh": True, "idm": None, "score": None})
    # the last unfilled FVG of each side, and the FVGs closed through by a body (inversion)
    seen = {1: 0, -1: 0}
    for i in range(last, max(2, last - 120), -1):
        g = fv[i]
        if not g:
            continue
        d, lo, hi = g
        after = c[i + 1:]
        inverted = any((x.close < lo) if d > 0 else (x.close > hi) for x in after)
        filled = any((x.low <= lo) if d > 0 else (x.high >= hi) for x in after)
        if inverted and seen[-d] < 1:
            zones.append({"kind": "IFVG", "dir": -d, "lo": lo, "hi": hi, "t": c[i - 2].time, "fvg": True, "fresh": True, "idm": None, "score": None})
            seen[-d] += 1
        elif not filled and not inverted and seen[d] < 2:
            zones.append({"kind": "FVG", "dir": d, "lo": lo, "hi": hi, "t": c[i - 2].time, "fvg": True, "fresh": True, "idm": None, "score": None})
            seen[d] += 1
    # decisional vs extreme: on each side, the OB nearest the dealing range's extreme is the extreme one
    for d in (1, -1):
        obs = [z for z in zones if z["kind"] == "OB" and z["dir"] == d]
        if obs:
            ext = min(obs, key=lambda z: z["lo"]) if d > 0 else max(obs, key=lambda z: z["hi"])
            for z in obs:
                z["kind"] = "EXTREME_OB" if z is ext and len(obs) > 1 else "DECISIONAL_OB"
    out = []
    for n, z in enumerate(sorted(zones, key=lambda z: abs((z["lo"] + z["hi"]) / 2 - price))[:10], 1):
        if abs(z["hi"] - price) / price > 0.2 or abs(z["lo"] - price) / price > 0.2:
            continue
        side = "BULLISH" if z["dir"] > 0 else "BEARISH"
        typ = f"{side}_{z['kind']}" if z["kind"] not in ("FVG",) else f"{side}_FVG"
        mid = (z["lo"] + z["hi"]) / 2
        in_val = None
        if rng:
            in_val = (mid < rng["equilibrium50"]) if z["dir"] > 0 else (mid > rng["equilibrium50"])
        out.append({"id": f"{sym}_1h_{typ}_{n}", "symbol": sym, "timeframe": "1h", "type": typ, "topPrice": round(z["hi"], dec), "bottomPrice": round(z["lo"], dec),
                    "startTime": z["t"], "endTime": end, "hasFVG": z["fvg"], "unmitigated": z["fresh"], "idmSweptBeforeIt": z["idm"],
                    "scoreOutOf4": z["score"], "inRightValuation": in_val})
    return {"zones": out}


def _darija_step(label: str) -> str:
    rules = [("Asian range marked", "تحدد نطاق آسيا (00:00–06:00 UTC)"), ("killzone sweep", "السعر سحب السيولة ديال آسيا فـ الـ killzone"),
             ("Into an HTF POI", "الدخول لمنطقة مهمة ف 1H (premium / discount)"), ("M5 CHoCH", "فـ 5M: CHoCH بإغلاق جسم الشمعة مع FVG"),
             ("Previous day high", "تحددو قمة وقاع البارح (PDH / PDL)"), ("Wick sweep", "السعر سحب السيولة بالذيل ورجع"),
             ("Entry in", "الدخول فـ المنطقة الصحيحة ديال البارح"), ("H1 BOS", "فـ 1H: كسر الهيكلة بالجسم (BOS)"), ("H1 CHOCH", "فـ 1H: تغير السلوك (CHoCH)"),
             ("H1 OB with an FVG", "Order Block ديال 1H خلى FVG"), ("IDM swept", "تسحب الـ IDM (أول تصحيح داخلي)"),
             ("Price taps the fresh OB", "السعر رجع لـ Order Block نقي فـ discount / premium"), ("M5 liquidity sweep", "فـ 5M: سحب سيولة وسط المنطقة"),
             ("H1 supply / demand OB tapped", "السعر قاس منطقة عرض / طلب ف 1H"), ("Broken through", "تهرسات المنطقة بجسم شمعة مع FVG: انقلاب"),
             ("M5 inducement swept", "فـ 5M: تسحب الإغراء الصغير"), ("H1 wick sweep", "شمعة 1H سحبات قمة / قاع بالذيل"),
             ("Strong body close", "وسدات بجسم قوي فـ الاتجاه المعاكس"), ("M5 FVG at the candle", "FVG ديال 5M فـ 50% ديال الشمعة")]
    return next((d for k, d in rules if k.lower() in label.lower()), label)


def agent4(rows: list[dict], bias: str) -> dict:
    if not rows:
        return {"selectedStrategy": None, "ltfConfirmationStatus": "WAITING", "executionSteps": [], "executionStepsDarija": []}
    want = "BUY" if bias == "BULLISH" else "SELL" if bias == "BEARISH" else None
    r = min(rows, key=lambda r: (STATE_ORDER.get(r["status"], 9), 0 if (r.get("setup") or {}).get("direction") == want else 1, r["id"]))
    steps = r.get("steps") or []
    return {"selectedStrategy": STRATEGY_ID[r["id"]], "strategyKey": r["id"], "strategyName": r["name"], "strategyNameDarija": STRATEGY_DARIJA[r["id"]],
            "ltfConfirmationStatus": r["status"], "reason": r["reason"],
            "executionSteps": [{"label": s["label"], "ok": s["ok"], "detail": s["detail"]} for s in steps],
            "executionStepsDarija": [("✓ " if s["ok"] else "✗ ") + _darija_step(s["label"]) for s in steps],
            "test": r.get("test"), "_row": r}


def agent5(a4: dict, m5, dec: int, pip: float, symbol: str) -> dict:
    r = a4.pop("_row", None)
    st = (r or {}).get("setup")
    if not r or not st:
        return {"status": "NO_TRADE", "direction": None, "summaryDarija": "حتى صفقة دابا: كل استراتيجية SMC كتسنا الشروط ديالها.",
                "checklistScore": None}
    buy = st["direction"] == "BUY"
    d = 1 if buy else -1
    entry, sl, tp2 = st["entry"], st["sl"], st["tp"]
    risk = abs(entry - sl)
    rr = abs(tp2 - entry) / risk if risk else 0
    tp1 = entry + d * 3 * risk
    if (tp1 - tp2) * d >= 0:  # the final target is closer than 1:3: TP1 halfway
        tp1 = entry + (tp2 - entry) / 2
    # break-even: after the first M5 internal BOS in favour → the nearest M5 swing beyond the entry
    s5 = Structure(m5[-300:])
    lst = s5.swing_highs_after if buy else s5.swing_lows_after
    cands = [(s5.c[k].high if buy else s5.c[k].low) for k in lst[-10:]]
    cands = [p for p in cands if (p - entry) * d > 0 and (tp2 - p) * d > 0]
    be = (min(cands) if buy else max(cands)) if cands else entry + d * risk
    chk = r.get("checklist") or []
    passed = sum(1 for x in chk if x["ok"])
    status = {"CONFIRMED": "READY_TO_EXECUTE", "RUNNING": "RUNNING", "BLOCKED": "BLOCKED"}.get(r["status"], "WAITING")
    if rr < 3 and status == "READY_TO_EXECUTE":
        status = "BLOCKED"
    side_d = "شراء" if buy else "بيع"
    summ = (f"صفقة {side_d} على {symbol}: {STRATEGY_DARIJA[r['id']]} · الدخول {entry:.{dec}f} · الستوب {sl:.{dec}f} · الهدف {tp2:.{dec}f} (1:{rr:.1f}) · الشروط {passed}/7"
            + (" · جاهزة" if status == "READY_TO_EXECUTE" else " · الشيكليست قال لا" if status == "BLOCKED" else " · خدامة" if status == "RUNNING" else ""))
    return {"status": status, "direction": st["direction"], "entryPrice": round(entry, dec), "entryZone": st.get("entryZone"), "stopLoss": round(sl, dec),
            "tp1_partial50": round(tp1, dec), "tp2_finalRunner": round(tp2, dec), "riskRewardRatio": round(rr, 2),
            "breakevenTriggerPrice": round(be, dec), "breakevenRule": "move the stop to the entry only after the first M5 internal BOS (body close) in favour",
            "partialsRule": "close 50 % at TP1, hold the runner to TP2", "slPips": round(risk / pip, 1), "lots": st.get("lots"),
            "checklistScore": f"{passed}/7" if chk else None, "checklist": chk, "validUntil": st.get("validUntil"), "summaryDarija": summ}


def smc_report(symbol: str, spec: dict, m5, h1, price: float, now: int, market_open: bool, smc_rows: list[dict]) -> dict:
    """The six agents in sequence: the SMCAnalysisReport of one pair."""
    dec, sym = spec["decimals"], spec["symbol"]
    meta = agent0(symbol, spec, m5, h1, price, now, market_open)
    h1v = H1View(h1)
    rngs = [x.high - x.low for x in h1[-15:]]
    atr1 = sum(rngs) / len(rngs) if rngs else 0
    a1 = agent1(h1v, m5, price, dec)
    a2 = agent2(h1v, m5, price, dec, a1["htfBias"], atr1)
    a3 = agent3(h1v, sym, dec, price, a1["dealingRange"])
    a4 = agent4(smc_rows, a1["htfBias"])
    a5 = agent5(a4, m5, dec, spec["pipSize"], symbol)
    if not meta["guard"]["ok"]:
        a5 = {**a5, "status": "NO_TRADE", "summaryDarija": "الداتا ديال هاد الزوج ماشي سليمة دابا: حتى صفقة."}
    rng = a1["dealingRange"]
    bias_d = {"BULLISH": "صاعد", "BEARISH": "هابط"}.get(a1["htfBias"], "عرضي")
    val_d = {"PREMIUM": "فـ الغلاء (premium)", "DISCOUNT": "فـ الرخص (discount)", "EQUILIBRIUM": "فـ الوسط (50%)",
             "ABOVE_RANGE": "فوق النطاق", "BELOW_RANGE": "تحت النطاق"}.get((rng or {}).get("currentValuation"), "")
    idm = a2["idm"]
    lines = [f"الاتجاه ف 1H {bias_d}" + (f"، والسعر {val_d}" if val_d else "") + ".",
             (f"الـ IDM عند {idm['price']} " + ("تسحب." if idm["status"] == "SWEPT" else "مازال ما تسحبش: البلوكات اللي قبل منو فخ.")) if idm else "حتى IDM واضح دابا.",
             (f"السيولة المستهدفة: {a2['drawOnLiquidity']['label']} عند {a2['drawOnLiquidity']['price']}." if a2["drawOnLiquidity"] else ""),
             a5["summaryDarija"]]
    return {"meta": meta, "agent1_structure": a1, "agent2_liquidity": a2, "agent3_pdArrays": a3, "agent4_strategy": a4, "agent5_riskAndTrade": a5,
            "summaryDarija": " ".join(x for x in lines if x)}


def report_drawing(rep: dict) -> dict:
    """The report on the chart, in the chart's drawing contract: its zones, the last break, the dealing range's 50 %, the
    IDM and the liquidity pools. Every id starts with SMC- and carries the symbol."""
    from ..agents.base import BEAR, BULL, line, zone

    sym = rep["meta"]["symbol"]
    now = rep["meta"]["timestampUTC"]
    end = now + 12 * H1S
    zones, lines = [], []
    cat = {"OB": ("OB_BULL", "OB_BEAR"), "FVG": ("FVG_BULL", "FVG_BEAR"), "IFVG": ("FVG_BULL", "FVG_BEAR"), "BREAKER": ("DEMAND_BAND", "SUPPLY_BAND"),
           "FLIP": ("DEMAND_BAND", "SUPPLY_BAND")}
    short = {"DECISIONAL_OB": "OB dec.", "EXTREME_OB": "OB ext.", "FVG": "FVG", "IFVG": "IFVG", "BREAKER_BLOCK": "Breaker", "FLIP_ZONE": "Flip"}
    for z in rep["agent3_pdArrays"]["zones"]:
        if z["symbol"] != sym:
            continue
        bull = z["type"].startswith("BULLISH")
        kind = z["type"].split("_", 1)[1]
        key = "OB" if kind.endswith("OB") else "BREAKER" if kind == "BREAKER_BLOCK" else "FLIP" if kind == "FLIP_ZONE" else kind
        c0, c1 = cat[key]
        label = short.get(kind, kind) + (f" {z['scoreOutOf4']}/4" if z.get("scoreOutOf4") else "")
        zones.append(zone(f"SMC-{z['id']}", c0 if bull else c1, z["startTime"], end, z["topPrice"], z["bottomPrice"], label))
    a1 = rep["agent1_structure"]
    ev = a1.get("lastStructuralEvent")
    if ev:
        lines.append(line(f"SMC-{sym}-EV-{ev['time']}", "CHOCH" if "CHOCH" in ev["type"] else "BOS", ev["time"] - 6 * H1S, ev["time"] + H1S, ev["price"], None,
                          ("CHoCH" if "CHOCH" in ev["type"] else "BOS") + (" ↑" if ev["type"].startswith("BULLISH") else " ↓")))
    rng = a1.get("dealingRange")
    if rng:
        lines.append(line(f"SMC-{sym}-EQ", "EQUILIBRIUM", rng["confirmedSwingLow"]["time"], end, rng["equilibrium50"], None, "EQ 50 %"))
    idm = rep["agent2_liquidity"].get("idm")
    if idm:
        lines.append(line(f"SMC-{sym}-IDM", "MSS_BREAK", idm["time"], end, idm["price"], None, f"IDM {'✓' if idm['status'] == 'SWEPT' else '·'}",
                          "DOTTED", "#A78BFA"))
    for l in rep["agent2_liquidity"]["liquidityLevels"]:
        if l["swept"]:
            continue
        lines.append(line(f"SMC-{sym}-LQ-{l['label']}", "BSL" if l["side"] == "BSL" else "SSL", now - 24 * H1S, end, l["price"], None, l["label"]))
    return {"zones": zones, "priceLines": lines, "markers": []}
