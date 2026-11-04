"""
The "Analyse" button: the pair read now (trend, volatility, the SMC view) and every library strategy checked on the
latest CLOSED candles (library.py):

  SETUP    the strategy fired on a recent candle, its trade has hit neither the stop nor the target, its time limit is
           not over and less than half the move to the target is done: it can still be taken (entry, SL, TP, lots)
  LATE     it fired, but more than half of the move to the target is done: too late to enter
  WAITING  no setup: what it waits for (the channel level and its distance, the hours, ADX / RSI / trend side)

One request per press, nothing polled: the candles come from the feed's cache (refreshed at most once a minute).
"""

import time
from typing import Optional

from ..agents.registry import AGENT_CONFIGS
from ..agents.smc import smc_view
from ..core.quant_primitives import adx, atr, ema, rsi
from ..market.data import fetch_candle_series, fetch_live_price, market_session_status
from ..strategies.shared.jsnum import fmt_utc_minute, round_to
from ..strategies.shared.risk import lot_table
from ..strategies.shared.types import TF_SEC, closed_only
from .library import LIBRARY

PROVIDER = {"H1": ("1H", 12500), "H4": ("4H", 3200)}


def in_hours(t: int, hours) -> bool:
    if not hours:
        return True
    h, (a, b) = (t // 3600) % 24, hours
    return a <= h < b if a < b else (h >= a or h < b)


class _Ind:
    """The indicators of one timeframe, computed once for every strategy that reads it."""

    def __init__(self, c):
        cl = [x.close for x in c]
        self.c, self.a, self.ax, self.r = c, atr(c), adx(c), rsi(c)
        self.e50, self.e200 = ema(cl, 50), ema(cl, 200)
        self._ch: dict[int, tuple[list, list]] = {}

    def channel(self, n: int, i: int) -> tuple[Optional[float], Optional[float]]:
        if i < n:
            return None, None
        w = self.c[i - n:i]
        return max(x.high for x in w), min(x.low for x in w)


def _signal(ind: _Ind, s: dict, i: int) -> Optional[int]:
    """+1 buy / −1 sell when the strategy fires on candle i (its rules exactly as tested), else None."""
    c, p = ind.c, s["p"]
    hi, lo = ind.channel(p["n"], i)
    a = ind.a[i]
    if hi is None or a is None or not in_hours(c[i].time, p.get("hours")):
        return None
    x = c[i]
    if s["fam"] == "breakout":
        if ind.e50[i] is None or ind.e200[i] is None or (p.get("adx") and (ind.ax[i] is None or ind.ax[i] < p["adx"])):
            return None
        if x.close > hi and ind.e50[i] > ind.e200[i]:
            return 1
        if x.close < lo and ind.e50[i] < ind.e200[i]:
            return -1
        return None
    if p.get("adx") and (ind.ax[i] is None or ind.ax[i] >= p["adx"]):
        return None
    d = -1 if x.close > hi else 1 if x.close < lo else 0
    if not d:
        return None
    r = ind.r[i]
    if p.get("rsi") and (r is None or (d > 0 and r > p["rsi"]) or (d < 0 and r < 100 - p["rsi"])):
        return None
    if p.get("trend") and (ind.e200[i] is None or (d > 0) != (x.close > ind.e200[i])):
        return None
    return d


def _waiting(ind: _Ind, s: dict, last: int, pip: float, now: int) -> str:
    """What the strategy waits for on the next candle, in plain words."""
    c, p = ind.c, s["p"]
    hi, lo = ind.channel(p["n"], last + 1 if last + 1 <= len(c) else last)
    if hi is None:
        return "Not enough history"
    px = c[last].close
    up, dn = (hi - px) / pip, (px - lo) / pip
    if p.get("hours") and not in_hours(c[last].time + TF_SEC[s["tf"]], p["hours"]):
        return f"Trades only {p['hours'][0]:02d}:00–{p['hours'][1]:02d}:00 GMT: waiting for the window"
    if s["fam"] == "breakout":
        e50, e200 = ind.e50[last], ind.e200[last]
        if e50 is None or e200 is None:
            return "Not enough history"
        if p.get("adx") and (ind.ax[last] or 0) < p["adx"]:
            return f"ADX {ind.ax[last] or 0:.0f} < {p['adx']}: no momentum for a breakout yet"
        return (f"Uptrend: a {s['tf']} close above {hi:.5g} ({up:.0f} pips away) buys" if e50 > e200
                else f"Downtrend: a {s['tf']} close below {lo:.5g} ({dn:.0f} pips away) sells")
    if p.get("adx") and (ind.ax[last] or 0) >= p["adx"]:
        return f"ADX {ind.ax[last]:.0f} ≥ {p['adx']}: a strong trend, no fade"
    side = ""
    if p.get("trend") and ind.e200[last] is not None:
        side = " (buy side only: price above EMA200)" if px > ind.e200[last] else " (sell side only: price below EMA200)"
    rsi_txt = f", RSI(14) beyond {p['rsi']} / {100 - p['rsi']}" if p.get("rsi") else ""
    return f"A {s['tf']} close below {lo:.5g} ({dn:.0f} pips) buys / above {hi:.5g} ({up:.0f} pips) sells{rsi_txt}{side}"


def _check(ind: _Ind, s: dict, spec: dict, price: float, now: int) -> dict:
    c = ind.c
    last = len(c) - 1
    pip = spec["pipSize"]
    d = spec["decimals"]
    out = {"id": s["id"], "name": s["name"], "timeframe": s["tf"], "family": s["fam"], "targetR": s["rr"], "maxBars": s["mb"], "test": s["test"]}
    # the most recent signal whose trade could still be running (within its time limit)
    for i in range(last, max(210, last - s["mb"] + 1) - 1, -1):  # entered at the close of i, out by the close of i + mb
        sd = _signal(ind, s, i)
        if not sd:
            continue
        e = c[i].close
        risk = s["p"]["sl"] * ind.a[i]
        sl, tp = e - sd * risk, e + sd * s["rr"] * risk
        hit = None
        for x in c[i + 1:]:
            if (sd > 0 and x.low <= sl) or (sd < 0 and x.high >= sl):
                hit = "SL"
                break
            if (sd > 0 and x.high >= tp) or (sd < 0 and x.low <= tp):
                hit = "TP"
                break
        when = c[i].time + TF_SEC[s["tf"]]
        if hit:
            out.update(status="WAITING", reason=_waiting(ind, s, last, pip, now),
                       last={"direction": "BUY" if sd > 0 else "SELL", "at": when, "result": hit})
            return out
        done = (price - e) / risk * sd if risk else 0  # R already made from the entry
        hi_i, lo_i = ind.channel(s["p"]["n"], i)
        side = (1 if sd > 0 else -1) * (1 if s["fam"] == "breakout" else -1)  # +1: the close crossed the channel high
        geo = {"level": round_to(hi_i if side > 0 else lo_i, d), "side": side, "n": s["p"]["n"], "t0": c[max(0, i - s["p"]["n"])].time}
        setup = {"geo": geo, "direction": "BUY" if sd > 0 else "SELL", "entry": round_to(e, d), "sl": round_to(sl, d), "tp": round_to(tp, d), "rr": s["rr"],
                 "since": when, "closeBy": when + s["mb"] * TF_SEC[s["tf"]], "rNow": round(done, 2),
                 "slPips": round(risk / pip, 1), "lots": lot_table(spec, e, sl, 1, [500, 1000, 5000, 10000])}
        late = done > 0.5 * s["rr"]
        out.update(status="LATE" if late else "SETUP", setup=setup,
                   reason=(f"Fired {fmt_utc_minute(when)} UTC, {done:+.2f}R already: most of the move is done" if late
                           else f"Fired {fmt_utc_minute(when)} UTC · now {done:+.2f}R from the entry · closed at market by {fmt_utc_minute(setup['closeBy'])} UTC"))
        return out
    out.update(status="WAITING", reason=_waiting(ind, s, last, pip, now))
    return out


async def analyse(pair: str) -> dict:
    """The pair now: price, trend, volatility, the SMC read, and every library strategy's state."""
    now = int(time.time())
    spec = AGENT_CONFIGS[pair]["spec"]
    live = await fetch_live_price(pair)
    price = live.get("price") or 0
    inds: dict[str, _Ind] = {}
    for tf in sorted({s["tf"] for s in LIBRARY[pair]}):
        code, n = PROVIDER[tf]
        series = await fetch_candle_series(pair, code, n, price)
        inds[tf] = _Ind(closed_only(series["candles"], TF_SEC[tf], now))
    main = inds["H1"] if "H1" in inds else next(iter(inds.values()))
    if len(main.c) < 260:
        return {"success": False, "symbol": pair, "error": "Not enough history from the feed"}
    last = len(main.c) - 1
    price = price or main.c[last].close
    a_now = main.a[last]
    usual = sorted(v for v in main.a[-200:] if v)
    ratio = a_now / usual[len(usual) // 2] if a_now and usual else 1
    trend = "bullish" if (main.e50[last] or 0) > (main.e200[last] or 0) else "bearish"
    smc = smc_view(main.c, spec["symbol"], TF_SEC["H1" if "H1" in inds else "H4"])
    rows = [_check(inds[s["tf"]], s, spec, price, now) for s in LIBRARY[pair]]
    from .scenarios import plan_triggers

    triggers = [t for s in LIBRARY[pair] for t in plan_triggers(inds[s["tf"]], s, spec, price)]
    order = {"SETUP": 0, "LATE": 1, "WAITING": 2}
    rows.sort(key=lambda r: (order[r["status"]], -r["test"]["unseen"]["winRate"]))
    setups = [r for r in rows if r["status"] == "SETUP"]
    return {
        "success": True, "symbol": pair, "price": price, "priceSource": live.get("source"), "quoteTime": live.get("quoteTime"), "at": now,
        "marketOpen": market_session_status(pair)["isOpen"], "decimals": spec["decimals"],
        "read": {"trend": trend, "volatility": "high" if ratio > 1.5 else "low" if ratio < 0.7 else "normal", "atrRatio": round(ratio, 2),
                 "atrPips": round(a_now / spec["pipSize"], 1) if a_now else None, "smc": smc["summary"]},
        "verdict": (f"{len(setups)} setup(s) can be taken now" if setups else "No setup right now: every strategy is waiting"),
        "strategies": rows, "triggers": triggers,
    }


async def analyse_smc(pair: str) -> dict:
    """The "SMC" button: the four mechanical SMC strategies on M5 (H1 context), a confirmed setup when every rule is met."""
    from ..agents.registry import ASSUMED_SPREAD_PIPS, SLIPPAGE_PIPS
    from .smc_setups import smc_now

    now = int(time.time())
    spec = AGENT_CONFIGS[pair]["spec"]
    live = await fetch_live_price(pair)
    price = live.get("price") or 0
    m5 = closed_only((await fetch_candle_series(pair, "5M", 20000, price))["candles"], TF_SEC["M5"], now)
    h1 = closed_only((await fetch_candle_series(pair, "1H", 12500, price))["candles"], TF_SEC["H1"], now)
    if len(m5) < 600 or len(h1) < 260:
        return {"success": False, "symbol": pair, "error": "Not enough history from the feed"}
    price = price or m5[-1].close
    sym = spec["symbol"]
    cost = (ASSUMED_SPREAD_PIPS.get(sym, 1.0) + SLIPPAGE_PIPS.get(sym, 0.2)) * spec["pipSize"]
    from ..agents.registry import NEWS_CURRENCIES
    from ..strategies.shared.news import load_news_calendar, news_block

    cal = await load_news_calendar()
    rule = {"keywords": [], "currencies": NEWS_CURRENCIES.get(sym, ["USD"]), "minutesBefore": 15, "minutesAfter": 15}

    def news(ts: int):
        hit = news_block(ts, cal.get("events") or [], rule)["event"]
        return f"{hit.get('currency')} {hit.get('title')}" if hit else None

    out = smc_now(m5, h1, cost, spec, price, lambda e, s: lot_table(spec, e, s, 1, [500, 1000, 5000, 10000]), news)
    return {"success": True, "symbol": pair, "price": price, "priceSource": live.get("source"), "at": now,
            "marketOpen": market_session_status(pair)["isOpen"], "decimals": spec["decimals"], **out}


async def analyse_all(pair: str) -> dict:
    """The one Analyse button: the proven plans AND the SMC strategies checked on the latest closed candles, the setup that
    applies now picked (a proven plan's SETUP first, else an SMC setup CONFIRMED by its rules and the 7 questions), and the
    drawing of each setup for the pair's chart."""
    import asyncio

    from .drawing import plan_drawing, smc_drawing

    plan, smc = await asyncio.gather(analyse(pair), analyse_smc(pair))
    if not plan.get("success"):
        return plan
    spec = AGENT_CONFIGS[pair]["spec"]
    sym, pip, price = spec["symbol"], spec["pipSize"], plan["price"]
    for r in plan["strategies"]:
        r["draw"] = plan_drawing(sym, r, price, pip) if r["status"] in ("SETUP", "LATE") else None
    if smc.get("success"):
        for r in smc["strategies"]:
            r["draw"] = smc_drawing(sym, r, price, pip) if r.get("setup") else None
    pick = next((("plan", r) for r in plan["strategies"] if r["status"] == "SETUP"), None) or \
        next((("smc", r) for r in (smc.get("strategies") or []) if r["status"] == "CONFIRMED"), None)
    n_plan = sum(r["status"] == "SETUP" for r in plan["strategies"])
    n_smc = sum(r["status"] == "CONFIRMED" for r in (smc.get("strategies") or []))
    if pick:
        fam, r = pick
        verdict = (f"Applies now: {r['name']} ({'proven plan' if fam == 'plan' else 'SMC, every rule and the 7 questions met'}) · "
                   f"{r['setup']['direction']} {r['setup']['entry']}" + (f" · {n_plan + n_smc - 1} more" if n_plan + n_smc > 1 else ""))
    else:
        verdict = "No strategy applies right now: each one is waiting for its conditions"
    # the pair's agent answers: its read of the market now, the setup it confirms, and its radar (what is closest)
    from ..agents.registry import AGENTS

    ag = AGENTS[pair]
    rd, sr = plan["read"], (smc.get("read") if smc.get("success") else None) or {}
    read = " · ".join(x for x in (
        f"trend {rd['trend']}", f"volatility {rd['volatility']}",
        f"H1 structure {sr['trend']}" if sr.get("trend") else "",
        (f"last {sr['lastBreak']['kind']} {sr['lastBreak']['dir']} at {sr['lastBreak']['level']}" if sr.get("lastBreak") else ""),
        f"price {sr['zone']}" if sr.get("zone") else "") if x)
    radar = []
    for r in (smc.get("strategies") or []):
        if r["status"] in ("FORMING", "BLOCKED", "RUNNING"):
            radar.append({"family": "smc", "id": r["id"], "name": r["name"], "status": r["status"], "line": r["reason"]})
    for r in plan["strategies"]:
        if r["status"] == "LATE":
            radar.append({"family": "plan", "id": r["id"], "name": r["name"], "status": "LATE", "line": r["reason"]})
    radar.sort(key=lambda x: {"FORMING": 0, "RUNNING": 1, "LATE": 2, "BLOCKED": 3}.get(x["status"], 4))
    if not radar:
        w = next((r for r in plan["strategies"] if r["status"] == "WAITING"), None)
        if w:
            radar.append({"family": "plan", "id": w["id"], "name": w["name"], "status": "WATCHING", "line": w["reason"]})
    agent = {"id": ag.agent_id, "name": ag.name, "read": read}
    from .drawing import scenario_drawing
    from .scenarios import build as build_scenarios

    sc = build_scenarios(plan.get("triggers", []) + ((smc.get("triggers") or []) if smc.get("success") else []),
                         {"trend": rd["trend"], "structure": sr.get("trend"), "zone": sr.get("zone")}, price, rd.get("atrPips"), spec["decimals"])
    for side in ("buy", "sell"):
        if sc[side]["main"]:
            sc[side]["draw"] = scenario_drawing(sym, sc[side]["main"], plan["at"])
    if sc["buy"].get("draw") and sc["sell"].get("draw"):
        b, s_ = sc["buy"]["draw"], sc["sell"]["draw"]
        sc["bothDraw"] = {"label": "BUY and SELL scenarios", "family": "scenario", "id": "both", "zones": b["zones"] + s_["zones"],
                          "priceLines": b["priceLines"] + s_["priceLines"], "markers": [], "tradeExecutionBox": None}
    return {**plan, "verdict": verdict, "smc": smc if smc.get("success") else None, "agent": agent, "radar": radar[:4], "scenarios": sc,
            "pick": {"family": pick[0], "id": pick[1]["id"], "draw": pick[1]["draw"]} if pick else None}


_radar_cache: dict[str, tuple[int, dict]] = {}
_radar_locks: dict[str, "asyncio.Lock"] = {}


async def agent_radar(pair: str) -> dict:
    """The agent's radar, asked every second by the screens. Its strategies decide on CLOSED candles, so it reads the
    whole market again as soon as a new M5 candle has closed (every 5 minutes, H1 / H4 closes included), and between
    two closes it checks the live price against the setup it holds (inside the entry zone, past the stop or the target)."""
    import asyncio

    bucket = int(time.time()) // 300
    hit = _radar_cache.get(pair)
    if not hit or hit[0] != bucket:
        lock = _radar_locks.setdefault(pair, asyncio.Lock())
        async with lock:  # one re-read per pair at a time, however many screens ask
            hit = _radar_cache.get(pair)
            if not hit or hit[0] != bucket:
                fresh = await analyse_all(pair)
                if fresh.get("success"):
                    _radar_cache[pair] = hit = (bucket, fresh)
                elif not hit:
                    return {"success": False, "symbol": pair, "error": fresh.get("error")}
    r = hit[1]
    if not r.get("success"):
        return {"success": False, "symbol": pair, "error": r.get("error")}
    pick = r.get("pick")
    row = None
    if pick:
        rows = r["strategies"] if pick["family"] == "plan" else r["smc"]["strategies"]
        row = next((x for x in rows if x["id"] == pick["id"]), None)
    top = next((x for x in r["radar"] if x["status"] == "FORMING"), r["radar"][0] if r["radar"] else None)
    live = (await fetch_live_price(pair)).get("price") or 0
    zone_now = None
    if row and live:
        st = row["setup"]
        lo, hi = st.get("entryZone") or (st["entry"], st["entry"])
        buy = st["direction"] == "BUY"
        if (buy and live <= st["sl"]) or (not buy and live >= st["sl"]):
            zone_now = "past the stop"
        elif (buy and live >= st["tp"]) or (not buy and live <= st["tp"]):
            zone_now = "target reached"
        elif lo <= live <= hi or (pick["family"] == "plan"):
            zone_now = "price in the entry zone now" if pick["family"] == "smc" else "in trade"
        else:
            zone_now = f"{abs(live - (hi if buy else lo)) / AGENT_CONFIGS[pair]['spec']['pipSize']:.1f} pips from the entry zone"
    return {"success": True, "symbol": pair, "at": r["at"], "agent": r["agent"], "price": live, "zoneNow": zone_now,
            "nextRead": (bucket + 1) * 300,
            "status": "SETUP" if pick else ("FORMING" if top and top["status"] == "FORMING" else "WATCHING"),
            "headline": (f"{row['name']}: {row['setup']['direction']} {row['setup'].get('entryZone') or row['setup']['entry']}" if row else
                         f"{top['id']} · {top['line']}" if top else "Watching"),
            "draw": pick["draw"] if pick else None}
