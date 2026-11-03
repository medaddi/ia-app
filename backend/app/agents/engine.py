"""
Runs one pair agent on its closed candles and returns the app's strategy result plus the agent's own chart state
(`overlay`, the AgentChartOverlayState of frontend/src/agentOverlay.ts).

Every setup the agent sees becomes an order (MARKET, or LIMIT with its expiry), even while an earlier one still runs:
the pair agent only looks for setups, the trade-management agent (agents/trade_manager.py) runs the trades. Each order is
replayed with the app's lifecycle (fill, TP1 partial + break-even, stop counted first). Nothing blocks a setup: news,
spread and the day's count are notes, the trader decides and sets the risk. The overlay is the agent's context of the latest candle (its sessions, levels, sweep, MSS), the drawings of the order on
screen and its live trade projection.
"""

from typing import Optional

from ..core.instrument_specs import INSTRUMENT_CONFIG
from ..core.quant_primitives import atr, ema, mt
from ..strategies.shared.common import HISTORY_MAX, history_stats, item, new_result, target_hit_pct, to_signal_json, tp_options, trade_record
from ..strategies.shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..strategies.shared.lifecycle import simulate_lifecycle
from ..strategies.shared.news import news_block
from ..strategies.shared.risk import classify, lot_table, rr, score_checklist, snap_sl, snap_tp, to_pips
from ..strategies.shared.types import TF_SEC, Candle, closed_only
from .base import PairAgent

LIVE = ("PENDING", "OPEN", "TP1_HIT", "TP2_HIT")
ENDED = ("CLOSED", "CANCELLED", "EXPIRED")


def run_scan(agent: PairAgent, c: list[Candle], peer: Optional[list[Candle]], key: str = "") -> dict:
    return agent.scan(c, peer, key)


def _build(agent: PairAgent, cfg: dict, c: list[Candle], i: int, b: dict, spread: float, last: int, tf_sec: int, events: list[dict]) -> dict:
    spec = cfg["spec"]
    d = spec["decimals"]
    buy = b["buy"]
    entry, sl = round_to(b["entry"], d), snap_sl(b["sl"], buy, d)
    tp1, tp2, tp3 = (snap_tp(b[k], buy, d) for k in ("tp1", "tp2", "tp3"))
    signal_time = c[i].time + tf_sec
    limit = b["entryType"] == "LIMIT"
    expiry = signal_time + b["expiryBars"] * tf_sec if limit and b.get("expiryBars") else None
    params = {"side": "BUY" if buy else "SELL", "entryType": b["entryType"], "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": expiry, "marketFillTime": None if limit else signal_time, "cancelIfTp1BeforeFill": bool(limit and b.get("cancelLevel")),
              "cancelLevel": round_to(b["cancelLevel"], d) if b.get("cancelLevel") else None, "beOffset": b.get("beOffset") or 0,
              "partials": b["partials"], "breakeven": b["breakeven"], "maxBars": None, "spread": spread,
              "slippage": cfg["filters"]["slippagePips"] * spec["pipSize"]}
    R = cfg["risk"]
    unit = abs(entry - sl)
    return {
        "id": f"{spec['symbol']}-{agent.name}-{c[i].time}", "setup": "AGENT", "direction": "BUY" if buy else "SELL", "entryType": b["entryType"],
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "tp2Source": "TP2", "tp3Source": "TP2",
        "rrTp2": rr(entry, sl, tp3), "rrTarget": rr(entry, sl, tp3), "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": expiry if expiry is not None else signal_time + R["marketValidMin"] * 60,
        "invalidation": f"SL {to_fixed(sl, d)}" + (f"; the limit is cancelled at {fmt_utc_minute(expiry)} UTC if not filled" if expiry else ""),
        "isFresh": i == last, "lifecycle": simulate_lifecycle(c, params, i + 1, None, None, None), "params": params,
        "anchors": {"pair": {"direction": "BUY" if buy else "SELL", "time": c[i].time, "why": b["why"], "rule": cfg["rule"], "style": "reversal",
                             "agent": agent.agent_id, "session": b.get("session"), "tag": b.get("tag")}},
        "draw": b.get("draw") or {},
    }


def make_trigger(agent: PairAgent):
    """Could the agent fire on candle i? One scan of the series without the peer pair (a superset), cached per series."""
    cache: dict = {}

    def trigger(c: list[Candle], i: int) -> bool:
        k = (id(c), len(c))
        if cache.get("key") != k:
            cache.update(key=k, times={s["time"] for s in run_scan(agent, c, None, "trigger")["setups"]})
        return c[i].time in cache["times"]

    return trigger


def can_signal_at(agent: PairAgent, tf_sec: int):
    if not agent.windows:
        return lambda close: True

    def ok(close: int) -> bool:
        m = mt(close - tf_sec)[1]
        return any(a <= m < b for a, b in agent.windows)

    return ok


def pair_block(agent: PairAgent, cfg: dict) -> dict:
    return {"name": f"{agent.agent_id}", "timeframe": agent.tf, "live": True, "rule": cfg["rule"], "style": "reversal", "why": agent.why,
            "test": None, "note": None, "profile": None, "params": agent.params, "maxBars": None, "targetR": agent.target_range[0],
            "targetRange": list(agent.target_range), "agent": agent.agent_id, "engine": agent.name, "steps": agent.steps,
            "maxSpreadPips": INSTRUMENT_CONFIG[agent.symbol]["max_spread_pips"], "timeframes": agent.timeframes}


def trade_box(s: dict, price: float, pip: float) -> Optional[dict]:
    lc = s["lifecycle"]
    if lc["state"] not in LIVE:
        return None
    buy = s["direction"] == "BUY"
    filled = lc["state"] != "PENDING"
    be = lc["state"] in ("TP1_HIT", "TP2_HIT")
    fill = lc.get("fillPrice") or s["entry"]
    stop = (fill + (s["params"].get("beOffset") or 0) * (1 if buy else -1)) if be else s["sl"]
    return {"direction": "LONG" if buy else "SHORT", "orderType": s["entryType"], "status": "TP1_HIT_BE" if be else "OPEN" if filled else "PENDING",
            "entryTime": int(lc.get("fillTime") or s["signalTime"]), "entryPrice": fill if filled else s["entry"], "stopLoss": stop,
            "tp1Price": s["tp1"], "tp2Price": s["tp3"], "rrRatio": round(s["rrTarget"], 2),
            "floatingPips": round(((price - fill) if buy else (fill - price)) / pip, 1) if filled and price else 0.0}


def overlay_state(agent: PairAgent, ctx: dict, setup: Optional[dict], price: float, spread: float, atr_v: Optional[float],
                  now: int) -> dict:
    pip = agent.pip
    zones, lines, markers = list(ctx["zones"]), list(ctx["priceLines"]), list(ctx["markers"])
    state, banner, tag = ctx["state"], ctx["banner"], ctx["tag"]
    box = None
    if setup:
        dr = setup.get("draw") or {}
        seen = {x["id"] for x in zones + lines + markers}
        lc = setup["lifecycle"]["state"]
        for z in dr.get("zones", []):
            if z["id"] not in seen:
                zones.append({**z, "isMitigated": lc not in ("PENDING",)})
        lines += [x for x in dr.get("priceLines", []) if x["id"] not in seen]
        markers += [x for x in dr.get("markers", []) if x["id"] not in seen]
        box = trade_box(setup, price, pip)
        tag = setup["anchors"]["pair"].get("tag") or tag
        if lc == "PENDING":
            state, banner = "PENDING_ORDER", f"{setup['direction']} LIMIT {setup['entry']} pending · SL {setup['sl']} · TP2 {setup['tp3']}"
        elif lc in ("OPEN", "TP1_HIT", "TP2_HIT"):
            state = "IN_TRADE"
            banner = f"{setup['direction']} in trade from {box['entryPrice']} · {box['floatingPips']:+.1f} pips" + (" · TP1 hit, stop at BE" if lc != "OPEN" else "")
    return {"symbol": agent.symbol, "agentId": agent.agent_id, "fsmState": state, "statusBannerText": f"{agent.symbol} · {state} · {banner}",
            "metrics": {"spreadPips": round(spread / pip, 1), "atrPips": round(atr_v / pip, 1) if atr_v else 0.0,
                        "sessionName": agent.session_name(mt(now)[1]), "confluenceTag": tag or "—"},
            "zones": zones, "priceLines": lines, "markers": markers, "tradeExecutionBox": box, "updatedAt": now}


def evaluate_agent(inp: dict, agent: PairAgent, cfg: dict) -> dict:
    spec = cfg["spec"]
    d = spec["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    tf = agent.tf
    tf_sec = TF_SEC[tf]
    now = inp["nowSec"]
    c = closed_only(inp["candles"].get(tf) or [], tf_sec, now)[-agent.history:]
    peer = closed_only(((inp.get("peer") or {}).get(tf)) or [], tf_sec, now) if agent.peer else None
    last = len(c) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (c[last].close if c else 0)
    R, FIL = cfg["risk"], cfg["filters"]
    spread = inp["spread"] if inp.get("spread") is not None else FIL["assumedSpreadPips"] * spec["pipSize"]
    result = new_result(spec, cfg, inp, price)
    result["pairStrategy"] = pair_block(agent, cfg)

    stale = inp["isMarketOpen"] and len(c) > 0 and now - (c[last].time + tf_sec) > max(3 * tf_sec, 3 * 3600)
    no_peer = agent.peer and len(peer or []) < agent.min_bars
    if not inp["isRealData"] or len(c) < agent.min_bars or stale or no_peer:
        reason = ("Live feed unavailable" if not inp["isRealData"] else f"Last {tf} candle is stale" if stale
                  else f"No {agent.peer} {tf} feed for the SMT check" if no_peer else f"Not enough history ({tf} {len(c)})")
        result["dataQuality"] = {"ok": False, "source": inp["dataSource"], "reason": reason}
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        result["overlay"] = {"symbol": agent.symbol, "agentId": agent.agent_id, "fsmState": "IDLE", "statusBannerText": f"{agent.symbol} · IDLE · {reason}",
                             "metrics": {"spreadPips": round(spread / agent.pip, 1), "atrPips": 0.0, "sessionName": "—", "confluenceTag": "—"},
                             "zones": [], "priceLines": [], "markers": [], "tradeExecutionBox": None, "updatedAt": now}
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
                            "agent": agent.agent_id})

    scan = run_scan(agent, c, peer)
    index_of = {x.time: k for k, x in enumerate(c)}
    events = inp["news"]["events"]
    latest = None
    past: list[dict] = []
    running: list[dict] = []
    for raw in scan["setups"]:  # every setup the agent sees is an order, also while an earlier one still runs
        i = index_of.get(raw["time"])
        if i is None:
            continue
        s = _build(agent, cfg, c, i, raw, spread, last, tf_sec, events)
        lc = s["lifecycle"]
        latest = s
        if lc["state"] == "CLOSED":
            past.append(trade_record(s, tf_sec, c, i))
        elif lc["state"] in LIVE:
            running.append(s)

    result["history"] = past[-HISTORY_MAX:]
    result["historyStats"] = history_stats(past)
    setup = None
    if latest and (latest["lifecycle"]["state"] not in ENDED or latest["signalIndex"] >= last - R["showLastSetupBars"]):
        setup = latest
    ctx = scan["context"]
    progress = ctx["banner"]
    result["facts"]["progress"] = progress
    day = inp["day"]
    sp_pips = spread / spec["pipSize"]
    max_sp = INSTRUMENT_CONFIG[agent.symbol]["max_spread_pips"]
    if setup:
        why = setup["anchors"]["pair"]["why"]
        nb = news_block(setup["signalTime"], events, FIL["news"])
        weight = 100 / max(1, len(why))
        checklist = [item(f"r{k}", w, w, True, f"at {fmt_time(setup['signalTime'])}", weight, True) for k, w in enumerate(why)]
        checklist += [
            # notes for the trader, never a block: the trader decides and sets the risk
            item("spread", f"Spread (usual ≤ {js_str(max_sp)} pips)", "السبريد", sp_pips <= max_sp + 1e-9, f"{sp_pips:.1f} pips", 0, False),
            item("news", f"Red {ccys} news ±30 min", "أخبار قوية ±30 دقيقة", not nb["blocked"],
                 f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, False),
            item("daily", "Trades on this pair today", "صفقات اليوم", True, f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, False),
        ]
    else:
        checklist = [item("rule", f"{agent.agent_id}: {ctx['state']}", "حالة الوكيل", False, progress, 100, True),
                     item("news", f"Red {ccys} news ±30 min", "أخبار قوية ±30 دقيقة", not news["blocked"], result["news"]["detail"], 0, False)]
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
    # the chart's trade projection: the newest order still running, else the newest order just finished
    shown = setup if setup and setup["lifecycle"]["state"] in LIVE else (running[-1] if running else setup)
    result["running"] = [{"id": x["id"], "direction": x["direction"], "entryType": x["entryType"], "entry": x["entry"], "sl": x["sl"], "tp1": x["tp1"],
                          "tp2": x["tp3"], "state": x["lifecycle"]["state"], "signalTime": x["signalTime"]} for x in running]
    result["overlay"] = overlay_state(agent, ctx, shown, price, spread, a[-1], now)
    result["facts"]["lastTrade"] = ({"id": latest["id"], "state": latest["lifecycle"]["state"], "outcome": latest["lifecycle"]["outcome"],
                                     "r": latest["lifecycle"]["rMultiple"]} if latest else None)
    result["bias"] = {"direction": ("BULLISH" if setup["direction"] == "BUY" else "BEARISH") if setup else trend, "detail": progress}
    st = result["status"]
    sd = setup["direction"] if setup else ""
    result["headline"] = (progress if not setup else f"{sd} {setup['entryType'].lower()} {f(setup['entry'])} · {agent.agent_id}" if st == "SIGNAL" and setup["isFresh"]
                          else f"{sd} {agent.name} {fmt_time(setup['signalTime'])} · {setup['lifecycle']['state']}")
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])}" if st == "SIGNAL" else "إعداد غير مكتمل") if setup else "لا توجد صفقة حالياً"
    return result
