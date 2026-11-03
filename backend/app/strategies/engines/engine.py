"""
The engine of the three pair agents: the agent's strategy (asian_sweep / london_judas / mean_reversion) scans the closed
candles and returns its setups; the engine turns each into an order (MARKET or LIMIT with its expiry), replays it with the
app's own lifecycle (fill, break-even, partials, the stop counted first), keeps one trade at a time and two a day, and
gives the result in the same shape as every other strategy (checklist, signal, history, drawings).

Fast: a finished day is scanned once and kept in memory (M5 agents), so a new M5 close only re-reads today's candles.
"""

from ..shared.common import HISTORY_MAX, history_stats, item, new_result, target_hit_pct, to_signal_json, tp_options, trade_record
from ..shared.drawings import trade_drawings
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, snap_sl, snap_tp, to_pips
from ..shared.sessions import trading_day_key
from ..shared.types import TF_SEC, Candle, closed_only
from ..pairs.rules import atr, ema
from .config import ENGINES
from .primitives import london

_memo: dict[str, dict] = {}  # rule → {London date: (signature, day result)}


def run_scan(cfg: dict, c: list[Candle], peer: list[Candle] | None) -> dict:
    eng = ENGINES[cfg["rule"]]
    memo = _memo.setdefault(f"{cfg['rule']}|{peer is not None}", {})
    return eng.scan(c, {"params": cfg["params"], "pip": cfg["spec"]["pipSize"], "peer": peer, "memo": memo})


def _spread(cfg: dict, inp: dict) -> float:
    return inp["spread"] if inp.get("spread") is not None else cfg["filters"]["assumedSpreadPips"] * cfg["spec"]["pipSize"]


def _news_cut(t: int, events: list[dict], rule: dict, before_sec: int = 900) -> int | None:
    """The time pending orders must be gone: 15 min before the next high-impact news of the pair's currencies."""
    kws = [k.lower() for k in rule["keywords"]]
    nxt = [e["time"] for e in events if e.get("impact") == "High" and e.get("currency") in rule["currencies"] and e["time"] > t
           and (not kws or any(k in str(e.get("title", "")).lower() for k in kws))]
    return min(nxt) - before_sec if nxt else None


def _build(c: list[Candle], i: int, b: dict, cfg: dict, spread: float, last: int, tf_sec: int, events: list[dict]) -> dict:
    spec = cfg["spec"]
    d = spec["decimals"]
    buy = b["buy"]
    entry, sl = round_to(b["entry"], d), snap_sl(b["sl"], buy, d)
    tp1, tp2, tp3 = (snap_tp(b[k], buy, d) for k in ("tp1", "tp2", "tp3"))
    unit = abs(entry - sl)
    signal_time = c[i].time + tf_sec
    limit = b["entryType"] == "LIMIT"
    expiry = signal_time + b["expiryBars"] * tf_sec if limit and b.get("expiryBars") else None
    cut = _news_cut(signal_time, events, cfg["filters"]["news"]) if limit else None
    if expiry is not None and cut is not None and cut < expiry:
        expiry = max(signal_time, cut)
    params = {"side": "BUY" if buy else "SELL", "entryType": b["entryType"], "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": expiry, "marketFillTime": None if limit else signal_time, "cancelIfTp1BeforeFill": bool(limit and b.get("cancelLevel")),
              "cancelLevel": snap_tp(b["cancelLevel"], buy, d) if b.get("cancelLevel") else None,
              "partials": b["partials"], "breakeven": b["breakeven"], "maxBars": None, "spread": spread,
              "slippage": cfg["filters"]["slippagePips"] * spec["pipSize"]}
    tf = cfg["timeframes"]["entry"]
    R = cfg["risk"]
    return {
        "id": f"{spec['symbol']}-A{cfg['agent']}-{c[i].time}", "setup": "AGENT", "direction": "BUY" if buy else "SELL", "entryType": b["entryType"],
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "tp2Source": "target", "tp3Source": "target", "rrTp2": rr(entry, sl, tp2), "rrTarget": rr(entry, sl, tp3),
        "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit), "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": expiry if expiry is not None else signal_time + R["marketValidMin"] * 60,
        "invalidation": f"SL {to_fixed(sl, d)}" + (f"; the limit is deleted at {fmt_utc_minute(expiry)} UTC if not filled" if expiry else ""),
        "isFresh": i == last, "lifecycle": simulate_lifecycle(c, params, i + 1, None, None, None), "params": params,
        "anchors": {"pair": {"direction": "BUY" if buy else "SELL", "time": c[i].time, "why": b["why"], "rule": cfg["rule"], "style": cfg["style"],
                             "zone": b.get("zone"), "agent": cfg["agent"]}},
    }


def make_trigger(cfg: dict):
    """Could the agent fire on candle i? One scan of the series (the peer pair is not read here: a superset, the full run
    decides), cached per series."""
    cache: dict = {}

    def trigger(c: list[Candle], i: int) -> bool:
        key = (id(c), len(c))
        if cache.get("key") != key:
            cache.update(key=key, times={s["time"] for s in run_scan(cfg, c, None)["setups"]})
        return c[i].time in cache["times"]

    return trigger


def can_signal_at(cfg: dict):
    """The close of an entry candle may give a signal only inside the agent's windows (London clock)."""
    wins = cfg.get("agentWindows")
    tf_sec = TF_SEC[cfg["timeframes"]["entry"]]
    if not wins:
        return lambda close: True

    def ok(close: int) -> bool:
        m = london(close - tf_sec)[1]
        return any(a <= m < b for a, b in wins)

    return ok


def pair_block(cfg: dict) -> dict:
    return {"name": cfg["name"].split("·", 1)[-1].strip(), "timeframe": cfg["timeframes"]["entry"], "live": cfg["live"], "rule": cfg["rule"],
            "style": cfg["style"], "why": cfg["why"], "test": cfg["test"], "note": cfg.get("note"), "profile": cfg["profile"],
            "params": cfg["params"], "maxBars": None, "targetR": cfg["targetRange"][0], "targetRange": cfg["targetRange"],
            "agent": cfg["agent"], "engine": cfg["engine"], "steps": cfg["steps"], "maxSpreadPips": cfg["filters"]["maxSpreadPips"]}


def evaluate_agent(inp: dict, cfg: dict) -> dict:
    spec = cfg["spec"]
    d = spec["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    tf = cfg["timeframes"]["entry"]
    tf_sec = TF_SEC[tf]
    now = inp["nowSec"]
    c = closed_only(inp["candles"].get(tf) or [], tf_sec, now)[-cfg["history"]:]
    peer = None
    if cfg.get("peer"):
        peer = closed_only(((inp.get("peer") or {}).get(tf)) or [], tf_sec, now)
    last = len(c) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (c[last].close if c else 0)
    R, FIL = cfg["risk"], cfg["filters"]
    spread = _spread(cfg, inp)
    result = new_result(spec, cfg, inp, price)
    result["pairStrategy"] = pair_block(cfg)

    stale = inp["isMarketOpen"] and len(c) > 0 and now - (c[last].time + tf_sec) > max(3 * tf_sec, 3 * 3600)
    no_peer = cfg.get("peer") and len(peer or []) < cfg["minBars"]
    if not inp["isRealData"] or len(c) < cfg["minBars"] or stale or no_peer:
        result["dataQuality"] = {"ok": False, "source": inp["dataSource"],
                                 "reason": "Live feed unavailable" if not inp["isRealData"] else f"Last {tf} candle is stale" if stale
                                 else f"No {cfg['peer']} {tf} feed for the SMT check" if no_peer else f"Not enough history ({tf} {len(c)})"}
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    cl = [x.close for x in c[-600:]]
    e50, e200 = ema(cl, 50), ema(cl, 200)
    a = atr(c[-300:])
    trend = "NEUTRAL" if e50[-1] is None or e200[-1] is None else ("BULLISH" if e50[-1] > e200[-1] else "BEARISH")
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    ccys = "/".join(FIL["news"]["currencies"])
    result["news"] = {"blocked": news["blocked"], "source": inp["news"]["source"],
                      "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else f"No high-impact {ccys} news within ±30 min",
                      "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None}
    result["facts"].update({"price": price, "spread": spread, "atr": round_to(a[-1], d) if a[-1] else None, "trend": trend.lower(),
                            "ema50": round_to(e50[-1], d) if e50[-1] else None, "ema200": round_to(e200[-1], d) if e200[-1] else None,
                            "character": cfg["profile"]["character"], "agent": cfg["agent"], "engine": cfg["engine"]})

    scan = run_scan(cfg, c, peer)
    index_of = {x.time: k for k, x in enumerate(c)}
    events = inp["news"]["events"]
    latest = None
    past: list[dict] = []
    free_from = 0  # one trade at a time: the next setup must come after the previous one ended
    per_day: dict[str, list[dict]] = {}
    for raw in scan["setups"]:
        i = index_of.get(raw["time"])
        if i is None or i < free_from:
            continue
        dk = trading_day_key(c[i].time + tf_sec)
        today = per_day.setdefault(dk, [])
        losses = sum(t["lifecycle"]["outcome"] == "LOSS" and (t["lifecycle"]["exitTime"] or 0) <= c[i].time for t in today)
        if len(today) >= FIL["maxTradesPerDay"] or losses >= FIL["maxLossesPerDay"]:
            continue
        if news_block(c[i].time + tf_sec, events, FIL["news"])["blocked"]:
            continue
        s = _build(c, i, raw, cfg, spread, last, tf_sec, events)
        lc = s["lifecycle"]
        if lc["state"] not in ("CANCELLED", "EXPIRED"):
            today.append(s)
        latest = s
        if lc["state"] == "CLOSED":
            past.append(trade_record(s, tf_sec, c, i))
        if lc["state"] in ("CLOSED", "CANCELLED", "EXPIRED"):
            end_t = lc["exitTime"] or (lc["events"][-1]["time"] if lc["events"] else c[i].time)
            free_from = index_of.get(end_t, i) + 1
            continue
        break  # open or pending now: that is the live trade

    result["history"] = past[-HISTORY_MAX:]
    result["historyStats"] = history_stats(past)
    setup = None
    if latest and (latest["lifecycle"]["state"] not in ("CLOSED", "CANCELLED", "EXPIRED") or latest["signalIndex"] >= last - R["showLastSetupBars"]):
        setup = latest
    progress = scan["status"]
    result["facts"]["progress"] = progress
    day = inp["day"]
    live_spread_pips = spread / spec["pipSize"]
    if setup:
        why = setup["anchors"]["pair"]["why"]
        nb = news_block(setup["signalTime"], events, FIL["news"])
        weight = 100 / max(1, len(why))
        checklist = [item(f"r{k}", w, w, True, f"at {fmt_time(setup['signalTime'])}", weight, True) for k, w in enumerate(why)]
        checklist += [
            item("spread", f"Spread ≤ {js_str(FIL['maxSpreadPips'])} pips", "السبريد", live_spread_pips <= FIL["maxSpreadPips"] + 1e-9,
                 f"{live_spread_pips:.1f} pips", 0, True),
            item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
            item("daily", f"Max {FIL['maxTradesPerDay']} trades per pair per day", "حد الصفقات اليومي",
                 day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"], f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
        ]
    else:
        checklist = [item("rule", "The agent's conditions", "شروط الاستراتيجية", False, progress, 100, True),
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
    result["canNotify"] = bool(result["status"] == "SIGNAL" and setup and setup["isFresh"] and setup["lifecycle"]["state"] in ("OPEN", "PENDING")
                               and inp["isMarketOpen"])

    sym = spec["symbol"]
    drawings = [{"id": f"{sym}-AGD-{k}", "layer": "levels", "tf": tf, "t2": None, **dr} for k, dr in enumerate(scan["drawings"])]
    if setup:
        an = setup["anchors"]["pair"]
        z = an.get("zone")
        if z:
            drawings.append({"id": f"{sym}-AGZ-{an['time']}", "layer": "fvg" if z["label"] == "FVG" else "ob", "kind": "box", "tf": tf,
                             "t1": z["time"], "t2": None, "p1": z["top"], "p2": z["bottom"], "text": z["label"],
                             "color": "bull" if an["direction"] == "BUY" else "bear", "midline": z["label"] == "FVG"})
        drawings.append({"id": f"{sym}-AGM-{an['time']}", "layer": "structure", "kind": "marker", "tf": tf, "t1": an["time"], "t2": None,
                         "p1": setup["entry"], "text": f"Agent {cfg['agent']}", "color": "bull" if an["direction"] == "BUY" else "bear",
                         "position": "below" if an["direction"] == "BUY" else "above"})
        drawings.extend(trade_drawings(setup, tf, ""))
    result["drawings"] = drawings
    result["facts"]["lastTrade"] = ({"id": latest["id"], "state": latest["lifecycle"]["state"], "outcome": latest["lifecycle"]["outcome"],
                                     "r": latest["lifecycle"]["rMultiple"]} if latest else None)
    result["bias"] = {"direction": ("BULLISH" if setup["direction"] == "BUY" else "BEARISH") if setup else trend, "detail": progress}
    st = result["status"]
    sd = setup["direction"] if setup else ""
    short = cfg["engine"]
    result["headline"] = (progress if not setup else f"{sd} {setup['entryType'].lower()} {f(setup['entry'])} · {short}" if st == "SIGNAL" and setup["isFresh"]
                          else f"{sd} {short} {fmt_time(setup['signalTime'])} · {setup['lifecycle']['state']}")
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])}" if st == "SIGNAL" else "إعداد غير مكتمل") if setup else "لا توجد صفقة حالياً"
    return result
