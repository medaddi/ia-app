"""
The engine of the report strategies: any rule of signals.py on its timeframe, replayed one trade at a time with the app's
own lifecycle (so the history, the TP / SL / BE record and the live trade agree with the backtest), with a checklist, the
rule's drawings and the trade's drawings. A LIVE plan is the pair's strategy; an OBSERVATION plan is computed next to it
(`observation_block`) and shown on the chart without ever sending a signal.
"""

from typing import Optional

from ..shared.common import HISTORY_MAX, history_stats, item, new_result, target_hit_pct, to_signal_json, tp_options, trade_record
from ..shared.drawings import trade_drawings
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, snap_sl, snap_tp, to_pips
from ..shared.types import TF_SEC, Candle, closed_only
from .signals import RULES


def _spread(cfg: dict, inp: dict) -> float:
    f = cfg["filters"]
    if inp.get("spread") is not None:
        return inp["spread"]
    return f["assumedSpread"] if "assumedSpread" in f else f["assumedSpreadPips"] * cfg["spec"]["pipSize"]


def _slip(cfg: dict) -> float:
    f = cfg["filters"]
    return f["slippage"] if "assumedSpread" in f else f["slippagePips"] * cfg["spec"]["pipSize"]


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
        "id": f"{spec['symbol']}-RP-{cfg['rule']}-{c[i].time}", "setup": "REPORT", "direction": "BUY" if buy else "SELL", "entryType": "MARKET",
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "tp2Source": f"{js_str(R['tp2R'])}R mark", "tp3Source": f"{js_str(R['capR'])}R target",
        "rrTp2": rr(entry, sl, tp2), "rrTarget": rr(entry, sl, tp3), "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": signal_time + R["marketValidMin"] * 60,
        "invalidation": f"SL {to_fixed(sl, d)}; closed at market after {R['maxBars']} {tf} candles",
        "isFresh": i == last, "lifecycle": simulate_lifecycle(c, params, i + 1, None, None, None), "params": params,
        "anchors": {"report": {"direction": "BUY" if buy else "SELL", "time": c[i].time, "why": b["why"]}},
    }


def evaluate_report(inp: dict, cfg: dict) -> dict:
    """The full analysis of a report plan on the pair's candles (the same shape as every other strategy)."""
    spec = cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    tf = cfg["timeframes"]["entry"]
    tf_sec = TF_SEC[tf]
    now = inp["nowSec"]
    c = closed_only(inp["candles"].get(tf) or [], tf_sec, now)[-cfg["history"]:]
    last = len(c) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (c[last].close if c else 0)
    R, FIL, P = cfg["risk"], cfg["filters"], cfg["params"]
    rule = RULES[cfg["rule"]]
    spread = _spread(cfg, inp)
    result = new_result(spec, cfg, inp, price)
    result["report"] = {"recommendation": cfg["report"], "test": cfg["test"], "note": cfg.get("note"), "live": cfg["live"], "rule": cfg["rule"]}

    stale = inp["isMarketOpen"] and len(c) > 0 and now - (c[last].time + tf_sec) > max(3 * tf_sec, 3 * 3600)
    if not inp["isRealData"] or len(c) < 260 or stale:
        result["dataQuality"] = {"ok": False, "source": inp["dataSource"],
                                 "reason": "Live feed unavailable" if not inp["isRealData"] else f"Last {tf} candle is stale" if stale else f"Not enough history ({tf} {len(c)})"}
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    ind = rule["prep"](c, P)
    latest = None
    past: list[dict] = []
    done: set = set()
    i = 210
    while i <= last:
        b = rule["at"](c, i, ind, P)
        if not b or (b.get("oncePer") is not None and b["oncePer"] in done):
            i += 1
            continue
        if b.get("oncePer") is not None:
            done.add(b["oncePer"])
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
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    ccys = "/".join(FIL["news"]["currencies"])
    result["news"] = {"blocked": news["blocked"], "source": inp["news"]["source"],
                      "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else f"No high-impact {ccys} news within ±30 min",
                      "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None}

    setup = None
    if latest and (latest[1]["lifecycle"]["state"] != "CLOSED" or latest[1]["signalIndex"] >= last - R["showLastSetupBars"]):
        setup = latest[1]
    progress = rule["now"](c, ind, P, last)
    result["facts"]["progress"] = progress
    day = inp["day"]
    if setup:
        why = setup["anchors"]["report"]["why"]
        nb = news_block(setup["signalTime"], inp["news"]["events"], FIL["news"])
        weight = 100 / max(1, len(why) + 1)
        checklist = [item(f"r{k}", w, w, True, f"at {fmt_time(setup['signalTime'])}", weight, True) for k, w in enumerate(why)]
        checklist += [
            item("stop", f"Stop and one target at {js_str(R['capR'])}R", "ستوب وهدف واحد", True, f"SL {f(setup['sl'])} · TP {f(setup['tp3'])}", weight, True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
            item("daily", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} loss per day", "حد الصفقات اليومي",
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
    result["canNotify"] = bool(cfg["live"] and result["status"] == "SIGNAL" and setup and setup["isFresh"]
                               and setup["lifecycle"]["state"] == "OPEN" and inp["isMarketOpen"])

    sym = spec["symbol"]
    drawings = [{"id": f"{sym}-RPD-{k}", "layer": "levels" if cfg["live"] else "report", "tf": tf, "t2": None, **dr}
                for k, dr in enumerate(rule["draw"](c, ind, P, last))]
    if setup:
        a = setup["anchors"]["report"]
        drawings.append({"id": f"{sym}-RPM-{a['time']}", "layer": "structure" if cfg["live"] else "report", "kind": "marker", "tf": tf, "t1": a["time"], "t2": None,
                         "p1": setup["entry"], "text": "Report setup" if not cfg["live"] else cfg["name"].split("·")[-1].strip().split(" (")[0],
                         "color": "bull" if a["direction"] == "BUY" else "bear", "position": "below" if a["direction"] == "BUY" else "above"})
        drawings.extend(dr if cfg["live"] else {**dr, "layer": "report"} for dr in trade_drawings(setup, tf, ""))
    result["drawings"] = drawings
    result["facts"].update({"price": price, "spread": spread, "atr": round_to(ind["atr"][last], d) if ind.get("atr") and ind["atr"][last] else None,
                            "lastTrade": ({"id": latest[1]["id"], "state": latest[1]["lifecycle"]["state"], "outcome": latest[1]["lifecycle"]["outcome"],
                                           "r": latest[1]["lifecycle"]["rMultiple"]} if latest else None)})
    result["bias"] = {"direction": ("BULLISH" if setup["direction"] == "BUY" else "BEARISH") if setup else "NEUTRAL", "detail": progress}
    st = result["status"]
    sd = setup["direction"] if setup else ""
    short = cfg["name"].split("·")[-1].strip()
    result["headline"] = (progress if not setup else f"{sd} market {f(setup['entry'])} · {short}" if st == "SIGNAL" and setup["isFresh"]
                          else f"{sd} {short} {fmt_time(setup['signalTime'])} · {setup['lifecycle']['state']}")
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])}" if st == "SIGNAL" else "إعداد غير مكتمل") if setup else "لا توجد صفقة حالياً"
    return result


def observation_block(r: dict) -> dict:
    """What the app shows of an OBSERVATION plan next to the pair's live strategy: never a signal."""
    s = r.get("setup")
    return {"name": r["strategyName"], "timeframe": r["timeframes"]["entry"], "live": False, **(r.get("report") or {}),
            "status": r["status"] if s else "NO_TRADE", "headline": r["headline"], "historyStats": r.get("historyStats"),
            "setup": ({k: s[k] for k in ("direction", "entry", "sl", "tp3", "signalTime")} | {"state": s["lifecycle"]["state"],
                      "outcome": s["lifecycle"]["outcome"], "r": s["lifecycle"]["rMultiple"]}) if s else None,
            "drawings": r.get("drawings") or [], "checklist": [{"rule": x["rule"], "passed": x["passed"], "detail": x["detail"]} for x in r.get("checklist") or []]}
