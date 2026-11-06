"""
The seven agents of a pair's team (MASTER BRIEF, "Team roles"). Each one reads its own part of the SAME engine read the
strategies use (closed candles only), states its finding and signs off, or objects. The Lead Strategist publishes the
team's decision with every sign-off. Nothing is invented: a figure is VERIFIED (computed now from the candles or taken
from the pair's backtest files), SCRIPT (the brief's rule) or HYPOTHESIS (untested); every line says which.

  structure   H1 bias, last BOS / CHoCH, dealing range and where price sits in it
  liquidity   session now (script UTC hours, DST unverified), PDH / PDL, Asian range, the last sweep, news
  entry       the nearest OB / FVG on each side and what each strategy is waiting for
  risk        for a setup: stop, RR, lots at 1 % (formula), stop vs cost; otherwise the risk rules
  backtest    this pair's backtest (smc/ research, bundled in research/<PAIR>.json) and its data verdict
  devil       every objection: data quality, sample size, against the H1 trend, entry near the 50 %, news not tested
  lead        the decision (SETUP only when a strategy's rules AND the 7 questions pass) and the sign-offs

Status of each agent: "ok" (signs off) · "warn" (signs with an objection) · "wait" (nothing to sign yet).
"""

import json
from pathlib import Path

from . import engine

RESEARCH = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parent / "research").glob("*.json"))}
FOCUS = {  # from each pair's profile in the brief (HYPOTHESIS until tested)
    "XAUUSD": ["S3", "S2"], "EURUSD": ["S2"], "GBPUSD": ["S3"], "EURCHF": [], "AUDCAD": ["S4", "S1"], "AUDCHF": ["S1", "S2"],
}
ROLE = {"lead": "Lead Strategist", "structure": "Structure Analyst", "liquidity": "Liquidity & Session Analyst", "entry": "Entry Specialist",
        "risk": "Risk Manager", "backtest": "Backtest Engineer", "devil": "Devil's Advocate"}


def _agent(key: str, status: str, finding: str, lines: list[str]) -> dict:
    return {"key": key, "role": ROLE[key], "status": status, "finding": finding, "lines": lines}


def _session(t: int) -> str:
    h = (t % engine.DAY) // 3600
    s = engine.SESSIONS
    if s["london"][0] <= h < s["london"][1]:
        return "London killzone"
    if s["newyork"][0] <= h < s["newyork"][1]:
        return "New York killzone"
    if s["asia"][0] <= h < s["asia"][1]:
        return "Asian range (accumulation)"
    return "outside the killzones"


def team_agents(pair: str, cfg: dict, m5, h1v, strategies: list[dict], chart: dict, now: int) -> list[dict]:
    key = pair.replace("/", "")
    dec, pip = cfg["decimals"], cfg["pip"]
    f = lambda v: f"{v:.{dec}f}"  # noqa: E731
    c, st = h1v.c, h1v.st
    i = len(c) - 1
    price = m5[-1].close if m5 else c[-1].close
    trend = st.trend[i]
    rng = h1v.range_mid(i)
    segs, boxes = chart.get("segments", []), chart.get("boxes", [])
    signal = next((s["setup"] for s in strategies if s["status"] == "SIGNAL"), None)
    blocked = next((s["setup"] for s in strategies if s["status"] == "BLOCKED"), None)
    out = []

    # 1 · Structure Analyst
    last = next((s for s in reversed(segs) if s["kind"] in ("bos", "choch")), None)
    pos = (price - rng[0]) / (rng[2] - rng[0]) * 100 if rng else None
    tr = {1: "bullish", -1: "bearish"}.get(trend, "undefined")
    where = (None if pos is None else "above the range (premium)" if pos > 100 else "below the range (discount)" if pos < 0
             else f"{'premium' if pos > 50 else 'discount'} {pos:.0f} %")
    lines = [f"VERIFIED · H1 structure {tr} (last body-close break: {last['label']} {'up' if last['dir'] > 0 else 'down'} at {f(last['price'])})" if last
             else "VERIFIED · no H1 break in the last 200 candles"]
    if rng:
        lines.append(f"VERIFIED · dealing range {f(rng[0])} – {f(rng[2])}, EQ {f(rng[1])}; price {where}")
    idm = next((s for s in segs if s["kind"] == "idm"), None)
    if idm:
        lines.append(f"VERIFIED · IDM of the nearest OB at {f(idm['price'])}: {'swept' if '✓' in idm['label'] else 'not swept yet'}")
    out.append(_agent("structure", "ok" if trend and rng else "wait",
                      f"H1 {tr}" + (f" · {where}" if where else ""), lines))

    # 2 · Liquidity & Session Analyst
    sess = _session(now)
    lv = {s["label"]: s["price"] for s in segs if s["kind"] in ("liquidity", "session")}
    sweep = next((s for s in reversed(segs) if s["kind"] == "sweep"), None)
    lines = [f"SCRIPT · session now: {sess} (UTC hours from the script, not shifted for DST: HYPOTHESIS until checked against the broker)"]
    if "PDH" in lv:
        lines.append(f"VERIFIED · PDH {f(lv['PDH'])} · PDL {f(lv['PDL'])}" + (" · price above PDH" if price > lv["PDH"] else " · price below PDL" if price < lv["PDL"] else ""))
    if "Asian high" in lv:
        lines.append(f"VERIFIED · Asian range {f(lv['Asian low'])} – {f(lv['Asian high'])} ({(lv['Asian high'] - lv['Asian low']) / pip:.0f} pips)")
    if sweep:
        lines.append(f"VERIFIED · last H1 sweep: {'buy-side' if sweep['dir'] > 0 else 'sell-side'} liquidity at {f(sweep['price'])}")
    lines.append("not tested · no high-impact news calendar is loaded: the 15-minute news rule is not checked")
    out.append(_agent("liquidity", "warn", sess + " · news not checked", lines))

    # 3 · Entry Specialist
    lines = []
    for b in boxes:
        edge = b["top"] if b["dir"] > 0 else b["bottom"]
        name = f"FVG ({'bull' if b['dir'] > 0 else 'bear'})" if b["kind"] == "fvg" else b["label"]
        lines.append(f"VERIFIED · {name} {f(b['bottom'])} – {f(b['top'])}, "
                     f"{abs(price - edge) / pip:.0f} pips away")
    waiting = []
    for s in strategies:
        if s["status"] == "WATCHING" and s["watch"]:
            miss = next((x["step"] for x in s["watch"]["steps"] if not x["ok"]), None)
            if miss:
                waiting.append(f"{s['id']} waits for: {miss}")
    lines += [f"VERIFIED · {w}" for w in waiting]
    status = "ok" if signal else "wait"
    out.append(_agent("entry", status, f"{signal['strategy']} {signal['direction']} limit {f(signal['entry'])}" if signal
                      else (waiting[0] if waiting else "no zone being traded"), lines or ["VERIFIED · no valid OB / FVG near price"]))

    # 4 · Risk Manager
    s = signal or blocked
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * pip
    if s:
        stop_pips = abs(s["entry"] - s["sl"]) / pip
        ratio = abs(s["entry"] - s["sl"]) / cost
        lines = [f"VERIFIED · stop {stop_pips:.1f} pips · RR 1:{s['rr']} · {ratio:.1f}× the cost (spread + slippage {cfg['spread_pips'] + cfg['slippage_pips']:.1f} pips)",
                 f"SCRIPT · 1 % risk: lots = risk / (stop pips × ${cfg['pip_value_usd_per_lot']} per pip per lot) → {s['lots']['1000']} per $1,000, {s['lots']['10000']} per $10,000",
                 "SCRIPT · BE only after an M5 BOS in favour · 50 % at 1:3 · pip value to verify with the broker"]
        ok = s["rr"] >= 3 and ratio >= cfg["min_stop_cost_ratio"]
        out.append(_agent("risk", "ok" if ok and signal else "warn", f"1:{s['rr']} · stop {stop_pips:.0f} pips · {s['lots']['10000']} lot / $10k", lines))
    else:
        out.append(_agent("risk", "wait", "no setup to size", [
            "SCRIPT · risk 1 % of equity per trade, defined before entry", "SCRIPT · reward at least 1:3 (question 7)",
            f"HYPOTHESIS · a stop smaller than {cfg['min_stop_cost_ratio']:g}× the cost is not traded"]))

    # 5 · Backtest Engineer
    r = RESEARCH.get(key)
    if r:
        m5v = (r["data"].get("M5") or {}).get("verdict", "?")
        lines = [f"VERIFIED · data (Yahoo M5): {m5v}" + (f" ({', '.join(r['data']['M5']['why'])})" if r["data"].get("M5", {}).get("why") else "")]
        for sid, b in r["strategies"].items():
            go, ao = b["gatedOut"], b["allOut"]
            lines.append(f"VERIFIED · {sid}: {b['setups']} setups · passed the 7 questions out-of-sample {go.get('trades', 0)}"
                         + (f" · all setups OOS {ao['trades']} tr, {ao['expectancyR']:+.2f}R each" if ao.get("trades") else ""))
        lines.append("VERIFIED · every strategy < 100 trades: statistically weak, no edge shown")
        out.append(_agent("backtest", "warn", f"data {m5v} · sample too small", lines))
    else:
        out.append(_agent("backtest", "wait", "no backtest for this pair", ["not tested"]))

    # 6 · Devil's Advocate
    obj = []
    if r and (r["data"].get("M5") or {}).get("verdict") != "FIT":
        v = (r["data"].get("M5") or {}).get("verdict")
        obj.append(f"the M5 candles are {v} in the data check: sweeps and FVGs may be artefacts of the feed")
    obj.append("fewer than 100 backtest trades per strategy: any win rate here can be luck")
    if s:
        if trend and (1 if s["direction"] == "BUY" else -1) != trend:
            obj.append("the setup goes against the H1 trend")
        if rng and abs(s["entry"] - rng[1]) < 0.1 * (rng[2] - rng[0]):
            obj.append("the entry sits within 10 % of the range's 50 %: the equilibrium kill zone")
        if s["rr"] < 3.5:
            obj.append(f"RR 1:{s['rr']} is close to the 1:3 minimum")
        fails = [q["q"] for q in s["checklist"] if not q["ok"]]
        obj += [f"checklist no: {q}" for q in fails]
    if last and last["kind"] == "choch":
        obj.append("the last H1 break is a CHoCH: the trend just changed and may be a fake CHoCH (not classified by the engine)")
    obj.append("news is not checked (no calendar)")
    out.append(_agent("devil", "warn", obj[0], [f"HYPOTHESIS · {o}" for o in obj]))

    # 7 · Lead Strategist
    focus = FOCUS.get(key, [])
    signs = {a["key"]: a["status"] for a in out}
    if signal:
        decision = f"SETUP {signal['strategy']} {signal['direction']} · limit {f(signal['entry'])} · SL {f(signal['sl'])} · TP {f(signal['tp'])} · 1:{signal['rr']}"
        status = "ok"
    elif blocked:
        decision = f"NO TRADE · {blocked['strategy']} {blocked['direction']} found but the checklist says no"
        status = "wait"
    else:
        decision = "NO TRADE · every strategy is waiting for its conditions"
        status = "wait"
    lines = ["SCRIPT · a setup is published only when its strategy's rules AND all 7 questions pass",
             "sign-offs: " + " · ".join(f"{ROLE[k]} {'✓' if v == 'ok' else '!' if v == 'warn' else '…'}" for k, v in signs.items()),
             f"HYPOTHESIS · this pair's focus (pair profile): {', '.join(focus) if focus else 'none: measure the minimum range first'}",
             "research, not advice: demo before any live use; nothing here is guaranteed"]
    out.insert(0, _agent("lead", status, decision, lines))
    return out
