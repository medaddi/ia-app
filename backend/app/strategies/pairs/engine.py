"""
The engine of the pair strategies: the pair's rule (rules.py) on its timeframe, replayed one trade at a time with the
app's own lifecycle (so the history, the TP / SL record and the live trade agree with the test), with a checklist, the
rule's levels and the trade's drawings. A pair without a validated plan gets its analysis and no trade.
"""

from ..shared.common import HISTORY_MAX, history_stats, item, new_result, target_hit_pct, to_signal_json, tp_options, trade_record
from ..shared.drawings import trade_drawings
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, snap_sl, snap_tp, to_pips
from ..shared.types import TF_SEC, Candle, closed_only
from .rules import RULES, atr, ema


def _spread(cfg: dict, inp: dict) -> float:
    f = cfg["filters"]
    if inp.get("spread") is not None:
        return inp["spread"]
    return f["assumedSpread"] if "assumedSpread" in f else f["assumedSpreadPips"] * cfg["spec"]["pipSize"]


def _slip(cfg: dict) -> float:
    f = cfg["filters"]
    return f["slippage"] if "assumedSpread" in f else f["slippagePips"] * cfg["spec"]["pipSize"]


def pair_block(cfg: dict) -> dict:
    """What the app shows of the pair's strategy: its analysis, the plan and the test that decided it."""
    return {"name": cfg["name"].split("·", 1)[-1].strip(), "timeframe": cfg["timeframes"]["entry"], "live": cfg["live"], "rule": cfg["rule"],
            "style": cfg["style"], "why": cfg["why"], "test": cfg["test"], "note": cfg.get("note"), "profile": cfg["profile"],
            "params": cfg["params"], "maxBars": cfg["risk"]["maxBars"], "targetR": cfg["risk"]["capR"]}


def _build(c: list[Candle], i: int, b: dict, cfg: dict, spread: float, last: int, tf_sec: int) -> dict:
    R, spec = cfg["risk"], cfg["spec"]
    d = spec["decimals"]
    buy = b["buy"]
    entry, sl = round_to(b["entry"], d), snap_sl(b["sl"], buy, d)
    unit = abs(entry - sl)
    mark = lambda k: snap_tp(entry + k * unit if buy else entry - k * unit, buy, d)  # noqa: E731
    tp1, tp2, tp3 = mark(R["tp1R"]), mark(R["tp2R"]), mark(R["capR"])
    signal_time = c[i].time + tf_sec
    params = {"side": "BUY" if buy else "SELL", "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": None, "marketFillTime": signal_time, "cancelIfTp1BeforeFill": False, "partials": R["partials"],
              "breakeven": R["breakeven"], "maxBars": R["maxBars"], "spread": spread, "slippage": _slip(cfg)}
    tf = cfg["timeframes"]["entry"]
    return {
        "id": f"{spec['symbol']}-PS-{cfg['rule']}-{c[i].time}", "setup": "PAIR", "direction": "BUY" if buy else "SELL", "entryType": "MARKET",
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "tp2Source": f"{js_str(R['tp2R'])}R mark", "tp3Source": f"{js_str(R['capR'])}R target",
        "rrTp2": rr(entry, sl, tp2), "rrTarget": rr(entry, sl, tp3), "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": signal_time + R["marketValidMin"] * 60,
        "invalidation": f"SL {to_fixed(sl, d)}; closed at market after {R['maxBars']} {tf} candles",
        "isFresh": i == last, "lifecycle": simulate_lifecycle(c, params, i + 1, None, None, None), "params": params,
        "anchors": {"pair": {"direction": "BUY" if buy else "SELL", "time": c[i].time, "why": b["why"], "rule": cfg["rule"], "style": cfg["style"]}},
    }


def _trend(c: list[Candle], last: int) -> tuple[str, str, list, list]:
    cl = [x.close for x in c]
    e50, e200 = ema(cl, 50), ema(cl, 200)
    if e50[last] is None or e200[last] is None:
        return "NEUTRAL", "not enough history", e50, e200
    up = e50[last] > e200[last]
    return ("BULLISH" if up else "BEARISH"), f"EMA50 {e50[last]:.5g} {'>' if up else '<'} EMA200 {e200[last]:.5g}", e50, e200


def make_trigger(cfg: dict):
    """Could the plan's rule fire on candle i? Its indicators only look back, so computed once on the whole series they
    give the rule's answer at every candle: the replay runs the full strategy only on those candles."""
    rule = RULES[cfg["rule"]]
    cache: dict = {}

    def trigger(c: list[Candle], i: int) -> bool:
        key = (id(c), len(c))
        if cache.get("key") != key:
            cache.update(key=key, ind=rule["prep"](c, cfg["params"]))
        return i >= 210 and rule["at"](c, i, cache["ind"], cfg["params"]) is not None

    return trigger


def evaluate_pair(inp: dict, cfg: dict) -> dict:
    """The full analysis of the pair on its timeframe (the same shape as every strategy result)."""
    spec = cfg["spec"]
    d = spec["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    tf = cfg["timeframes"]["entry"]
    tf_sec = TF_SEC[tf]
    now = inp["nowSec"]
    c = closed_only(inp["candles"].get(tf) or [], tf_sec, now)[-cfg["history"]:]
    last = len(c) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (c[last].close if c else 0)
    R, FIL, P = cfg["risk"], cfg["filters"], cfg["params"]
    spread = _spread(cfg, inp)
    result = new_result(spec, cfg, inp, price)
    result["pairStrategy"] = pair_block(cfg)

    stale = inp["isMarketOpen"] and len(c) > 0 and now - (c[last].time + tf_sec) > max(3 * tf_sec, 3 * 3600)
    if not inp["isRealData"] or len(c) < 260 or stale:
        result["dataQuality"] = {"ok": False, "source": inp["dataSource"],
                                 "reason": "Live feed unavailable" if not inp["isRealData"] else f"Last {tf} candle is stale" if stale else f"Not enough history ({tf} {len(c)})"}
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    trend, trend_txt, e50, e200 = _trend(c, last)
    a = atr(c)
    sym = spec["symbol"]
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    ccys = "/".join(FIL["news"]["currencies"])
    result["news"] = {"blocked": news["blocked"], "source": inp["news"]["source"],
                      "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else f"No high-impact {ccys} news within ±30 min",
                      "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None}
    result["facts"].update({"price": price, "spread": spread, "atr": round_to(a[last], d) if a[last] else None, "trend": trend.lower(),
                            "ema50": round_to(e50[last], d) if e50[last] else None, "ema200": round_to(e200[last], d) if e200[last] else None,
                            "character": cfg["profile"]["character"]})

    if not cfg["rule"]:
        # No validated plan: the pair's analysis, and no trade
        why = f"No validated strategy on {spec['displaySymbol']}: {cfg['why']}"
        result["facts"]["progress"] = why
        result["checklist"] = [item("edge", "A strategy that held up on the unseen 40 % of 2 years", "استراتيجية نجحت ف الاختبار", False, why, 100, True)]
        result["rejection"] = why
        result["bias"] = {"direction": trend, "detail": trend_txt}
        result["headline"], result["headlineAr"] = "No validated strategy · no trade", "ما كايناش استراتيجية مجربة · بلا صفقة"
        result["history"], result["historyStats"] = [], history_stats([])
        result["drawings"] = []
        return result

    rule = RULES[cfg["rule"]]
    ind = rule["prep"](c, P)
    latest = None
    past: list[dict] = []
    i = 210
    while i <= last:
        b = rule["at"](c, i, ind, P)
        if not b:
            i += 1
            continue
        s = _build(c, i, b, cfg, spread, last, tf_sec)
        latest = (b, s)
        lc = s["lifecycle"]
        if lc["state"] == "CLOSED":
            past.append(trade_record(s, tf_sec, c, i))
        if lc["state"] != "CLOSED":
            break
        i = next((j for j in range(i + 1, last + 1) if c[j].time == lc["exitTime"]), last) + 1

    result["history"] = past[-HISTORY_MAX:]
    result["historyStats"] = history_stats(past)

    setup = None
    if latest and (latest[1]["lifecycle"]["state"] != "CLOSED" or latest[1]["signalIndex"] >= last - R["showLastSetupBars"]):
        setup = latest[1]
    progress = rule["now"](c, ind, P, last)
    result["facts"]["progress"] = progress
    day = inp["day"]
    if setup:
        why = setup["anchors"]["pair"]["why"]
        nb = news_block(setup["signalTime"], inp["news"]["events"], FIL["news"])
        weight = 100 / max(1, len(why) + 1)
        checklist = [item(f"r{k}", w, w, True, f"at {fmt_time(setup['signalTime'])}", weight, True) for k, w in enumerate(why)]
        checklist += [
            item("stop", f"Stop and one target at {js_str(R['capR'])}R", "ستوب وهدف واحد", True, f"SL {f(setup['sl'])} · TP {f(setup['tp3'])}", weight, True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
            item("daily", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} losses per day", "حد الصفقات اليومي",
                 day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"], f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
        ]
    else:
        checklist = [item("rule", "The rule's conditions", "شروط القاعدة", False, progress, 100, True),
                     item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not news["blocked"], result["news"]["detail"], 0, True)]
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

    drawings = [{"id": f"{sym}-PSD-{k}", "layer": "levels", "tf": tf, "t2": None, **dr} for k, dr in enumerate(rule["draw"](c, ind, P, last))]
    if setup:
        an = setup["anchors"]["pair"]
        drawings.append({"id": f"{sym}-PSM-{an['time']}", "layer": "structure", "kind": "marker", "tf": tf, "t1": an["time"], "t2": None,
                         "p1": setup["entry"], "text": "Fade" if cfg["style"] == "reversal" else "Breakout",
                         "color": "bull" if an["direction"] == "BUY" else "bear", "position": "below" if an["direction"] == "BUY" else "above"})
        drawings.extend(trade_drawings(setup, tf, ""))
    result["drawings"] = drawings
    result["facts"]["lastTrade"] = ({"id": latest[1]["id"], "state": latest[1]["lifecycle"]["state"], "outcome": latest[1]["lifecycle"]["outcome"],
                                     "r": latest[1]["lifecycle"]["rMultiple"]} if latest else None)
    result["bias"] = {"direction": ("BULLISH" if setup["direction"] == "BUY" else "BEARISH") if setup else trend, "detail": progress if not setup else trend_txt}
    st = result["status"]
    sd = setup["direction"] if setup else ""
    short = cfg["name"].split("·")[-1].strip()
    result["headline"] = (progress if not setup else f"{sd} market {f(setup['entry'])} · {short}" if st == "SIGNAL" and setup["isFresh"]
                          else f"{sd} {short} {fmt_time(setup['signalTime'])} · {setup['lifecycle']['state']}")
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])}" if st == "SIGNAL" else "إعداد غير مكتمل") if setup else "لا توجد صفقة حالياً"
    return result
