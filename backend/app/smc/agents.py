"""
The seven agents of a pair's team (MASTER BRIEF, "Team roles"). Each one reads its own part of the SAME engine read the
strategies use (closed candles only), states its finding and signs off, or objects. The Lead Strategist publishes the
team's decision with every sign-off. Nothing is invented: a figure is VERIFIED (computed now from the candles or taken
from the pair's backtest files), SCRIPT (the brief's rule) or HYPOTHESIS (untested); every line says which.

  structure   H4 bias (question 1), H1 last BOS / CHoCH, dealing range and where price sits in it
  liquidity   session now (script UTC hours, DST unverified), PDH / PDL, Asian range, the last sweep, news
  entry       the nearest OB / FVG on each side and what each strategy is waiting for
  risk        for a setup: stop, RR, lots at 1 % (formula), stop vs cost; otherwise the risk rules
  backtest    this pair's backtest (smc/ research, bundled in research/<PAIR>.json) and its data verdict
  devil       every objection: data quality, sample size, against the H1 trend, entry near the 50 %, news not tested
  lead        the decision (SETUP only when a strategy's rules AND the 7 questions pass) and the sign-offs

Status of each agent: "ok" (signs off) · "warn" (signs with an objection) · "wait" (nothing to sign yet).
Each finding is said the way a trader says it: a decision in plain words ("I only look for buys", "I pass"), with the
figures behind it in the detail lines. An entry is a ZONE, never one exact price.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from . import engine, playbook
from .skill import portfolio

RESEARCH = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parent / "research").glob("*.json")) if p.stem != "playbook"}
_PB = Path(__file__).parent / "research" / "playbook.json"
PLAY = json.loads(_PB.read_text(encoding="utf-8")) if _PB.exists() else {}  # each pair's playbook strategy, measured (smc/tools/playbook_test.py)
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


def team_agents(pair: str, cfg: dict, m5, h1v, strategies: list[dict], chart: dict, now: int, cot: dict | None = None,
                sent: list[dict] | None = None, news: list[dict] | None = None) -> list[dict]:
    key = pair.replace("/", "")
    dec, pip = cfg["decimals"], cfg["pip"]
    f = lambda v: f"{v:.{dec}f}"  # noqa: E731
    c, st = h1v.c, h1v.st
    i = len(c) - 1
    price = m5[-1].close if m5 else c[-1].close
    trend = st.trend[i]
    htf = h1v.h4_trend(now)  # question 1's HTF bias (H4 structure from H1)
    rng = h1v.range_mid(i)
    segs, boxes = chart.get("segments", []), chart.get("boxes", [])
    signal = next((s["setup"] for s in strategies if s["status"] == "SIGNAL"), None)
    blocked = next((s["setup"] for s in strategies if s["status"] == "BLOCKED"), None)
    out = []

    # 1 · Structure Analyst
    last = next((s for s in reversed(segs) if s["kind"] in ("bos", "choch")), None)
    pos = (price - rng[0]) / (rng[2] - rng[0]) * 100 if rng else None
    tr = {1: "bullish", -1: "bearish"}.get(trend, "undefined")
    tr4 = {1: "bullish", -1: "bearish"}.get(htf, "undefined")
    where = (None if pos is None else "above the range (premium)" if pos > 100 else "below the range (discount)" if pos < 0
             else f"{'premium' if pos > 50 else 'discount'} {pos:.0f} %")
    lines = [f"VERIFIED · HTF bias (question 1): H4 structure {tr4}",
             f"VERIFIED · H1 structure {tr} (last body-close break: {last['label']} {'up' if last['dir'] > 0 else 'down'} at {f(last['price'])})" if last
             else "VERIFIED · no H1 break in the last 200 candles"]
    if rng:
        lines.append(f"VERIFIED · dealing range {f(rng[0])} – {f(rng[2])}, EQ {f(rng[1])}; price {where}")
    if cot:  # the trader-skill's positioning: context, never a trigger
        lines.append(f"VERIFIED · trader-skill COT ({cot['reportDate']}): speculators {cot['netPct']:+.1f} % net → "
                     f"{'no clear side' if cot['bias'] == 'NEUTRAL' else cot['bias']}, 3-year index {cot['score']:.0f}"
                     + (" · CROWDED (3-year extreme)" if cot["crowded"] else "")
                     + f" · context only, {(now - int(datetime.fromisoformat(cot['reportDate']).replace(tzinfo=timezone.utc).timestamp())) // 86400} days old, futures not spot")
    else:
        lines.append("not available · the CFTC COT report could not be read now (trader-skill)")
    idm = next((s for s in segs if s["kind"] == "idm"), None)
    if idm:
        lines.append(f"VERIFIED · IDM of the nearest OB at {f(idm['price'])}: {'swept' if '✓' in idm['label'] else 'not swept yet'}")
    side = {1: "buys", -1: "sells"}.get(htf)
    if not htf:
        say = "No clear H4 trend: I don't pick a side yet"
    elif trend != htf:
        say = f"H4 is {tr4} but H1 is {tr}: they disagree, I wait for H1 to line up"
    elif pos is None:
        say = f"H4 and H1 are both {tr4}: I only look for {side}"
    elif (htf > 0 and pos <= 50) or (htf < 0 and pos >= 50):
        say = f"H4 and H1 are both {tr4} and price is {'cheap' if htf > 0 else 'expensive'} here: good place to look for {side}"
    else:
        say = f"H4 and H1 are both {tr4}, but price is {'expensive' if htf > 0 else 'cheap'} here: I wait for a pullback before any {side[:-1]}"
    out.append(_agent("structure", "ok" if htf and rng else "wait", say, lines))

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
    if news is None:
        lines.append("not available · the news calendar could not be read: the 15-minute news rule is not checked now")
        out.append(_agent("liquidity", "warn", "I can't see the news calendar right now: I stay careful", lines))
    else:
        nxt = next((e for e in news if e["time"] >= now - 15 * 60), None)
        hm = lambda t: f"{(t % 86400) // 3600:02d}:{(t % 3600) // 60:02d}"  # noqa: E731
        near = bool(nxt and abs(nxt["time"] - now) <= 15 * 60)
        lines.append("VERIFIED · news (ForexFactory, high impact, this pair's currencies): "
                     + (f"{nxt['currency']} {nxt['title']} at {hm(nxt['time'])} UTC" + (" · INSIDE the 15-minute window: no entry" if near else "") if nxt else "none left this week"))
        killzone = sess.endswith("killzone")
        say = ("Big news in the next 15 minutes: hands off" if near else
               f"{sess.split(' killzone')[0]} is open and no big news: good time to trade" if killzone else
               "Outside London and New York: I don't open trades now" if "outside" in sess else
               "Asian session: the market builds its range, I watch the highs and lows it leaves")
        out.append(_agent("liquidity", "warn" if near else "ok", say, lines))

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
    out.append(_agent("entry", status, (f"I'd {signal['direction'].lower()} at market {f(signal['entry'])}, on the trigger candle's close" if signal.get("market")
                                        else f"I'd {signal['direction'].lower()} inside {f(signal['zone'][0])} – {f(signal['zone'][1])}: price only has to come into the zone") if signal
                      else (f"I'm waiting: {waiting[0].split(': ', 1)[1]} ({waiting[0].split(' ')[0]})" if waiting else "No clean zone near price: nothing to do"), lines or ["VERIFIED · no valid OB / FVG near price"]))

    # 4 · Risk Manager
    s = signal or blocked
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * pip
    need = playbook.MIN_RR.get((key, (s or {}).get("strategy", "P")), 2.0)  # the strategy's own reward (the guide's question 3)
    if s:
        stop_pips = abs(s["entry"] - s["sl"]) / pip
        ratio = abs(s["entry"] - s["sl"]) / cost
        lines = [f"VERIFIED · stop {stop_pips:.1f} pips · RR 1:{s['rr']} · {ratio:.1f}× the cost (spread + slippage {cfg['spread_pips'] + cfg['slippage_pips']:.1f} pips)",
                 f"SCRIPT · 1 % risk: lots = risk / (stop pips × ${cfg['pip_value_usd_per_lot']} per pip per lot) → {s['lots']['1000']} per $1,000, {s['lots']['10000']} per $10,000",
                 (f"SCRIPT · TP1 {f(s['tp1'])}: close {round(s.get('part', 1) * 100)} %, stop to entry · " if s.get("tp1") is not None else "SCRIPT · one target · ")
                 + "pip value to verify with the broker"]
        if signal:  # the trader-skill's portfolio check, with every setup already live across the six teams
            chk = portfolio.check(pair, signal, sent or [], now)
            lines.append(f"SCRIPT · trader-skill risk check across all teams: {chk['verdict']}"
                         + (f" ({'; '.join(chk['reasons'])})" if chk["reasons"] else f" ({chk['live']} live, limits 1 %/trade, 3 % total, 2 same-way on USD, 5/day)"))
        ok = s["rr"] >= need and ratio >= cfg["min_stop_cost_ratio"] and (not signal or portfolio.check(pair, signal, sent or [], now)["verdict"] == "PASS")
        why = (f"the reward is under {need:g} times the risk" if s["rr"] < need else "the stop is too small next to the spread" if ratio < cfg["min_stop_cost_ratio"]
               else "too much risk is already open across the teams" if signal else "the checklist said no")
        out.append(_agent("risk", "ok" if ok and signal else "warn",
                          f"Worth it: I risk 1 % to make about {s['rr']:.1f} times that" if ok and signal else f"Not worth it: {why}", lines))
    else:
        open_ = portfolio.live(sent or [], now)
        out.append(_agent("risk", "wait", "Nothing to size yet: my risk stays at 1 % per trade", [
            "SCRIPT · risk 1 % of equity per trade, defined before entry", f"SCRIPT · reward at least 1:{need:g} (the playbook's question 3)",
            f"HYPOTHESIS · a stop smaller than {cfg['min_stop_cost_ratio']:g}× the cost is not traded",
            f"SCRIPT · limits across all teams: the guide's correlation cap (EUR/USD + GBP/USD, AUD/CAD + AUD/CHF, EUR/CHF + AUD/CHF), 3 % total, 5 a day "
            f"({len(open_)} setup(s) live now)"]))

    # 5 · Backtest Engineer
    r = RESEARCH.get(key)
    pb = PLAY.get(key)
    if pb:
        d0 = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
        lines = [f"VERIFIED · {pb['source'].capitalize()} candles {d0(pb['from'])} → {d0(pb['to'])}, every trade on M5, costs in"]
        says, best = [], None
        for sid, y in pb["strategies"].items():
            a, i_, o_ = y["all"], y["in"], y["out"]
            lines.append(f"HYPOTHESIS · {sid} {y['name']}: the guide says {y['claimed']}")
            lines.append(f"VERIFIED · {sid} measured: " + (f"{a['trades']} trades, win {a['winRate']} %, {a['totalR']:+.2f}R" if a["trades"] else "0 trades")
                         + f" · first 60 % {i_['trades']} tr" + (f" {i_['winRate']} % {i_['totalR']:+.2f}R" if i_["trades"] else "")
                         + f" · last 40 % {o_['trades']} tr" + (f" {o_['winRate']} % {o_['totalR']:+.2f}R" if o_["trades"] else ""))
            held = a["trades"] >= 20 and i_["totalR"] > 0 and o_["totalR"] > 0
            says.append(f"{sid} {a['winRate']} % on {a['trades']}" if a["trades"] else f"{sid} no trade")
            if held and (best is None or a["totalR"] > best[1]["totalR"]):
                best = (sid, a)
        lines.append("not tested · news (no history) and the correlation cap (each pair alone)")
        if r:
            lines.append(f"VERIFIED · the live feed (Yahoo M5) in the data check: {(r['data'].get('M5') or {}).get('verdict', '?')}")
        if best:
            say = f"{best[0]} held up in the test: win {best[1]['winRate']} % on {best[1]['trades']} trades, {best[1]['totalR']:+.1f}R, positive in both halves"
        else:
            say = "Not confirmed by the test yet (" + " · ".join(says) + ")"
        out.append(_agent("backtest", "ok" if best else "warn", say, lines))
    elif r:
        m5v = (r["data"].get("M5") or {}).get("verdict", "?")
        lines = [f"VERIFIED · data (Yahoo M5): {m5v}" + (f" ({', '.join(r['data']['M5']['why'])})" if r["data"].get("M5", {}).get("why") else "")]
        for sid, b in r["strategies"].items():
            go, ao = b["gatedOut"], b["allOut"]
            lines.append(f"VERIFIED · {sid}: {b['setups']} setups · passed the 7 questions out-of-sample {go.get('trades', 0)}"
                         + (f" · all setups OOS {ao['trades']} tr, {ao['expectancyR']:+.2f}R each" if ao.get("trades") else ""))
        lines.append("VERIFIED · every strategy < 100 trades: statistically weak, no edge shown")
        out.append(_agent("backtest", "warn", "Too few past trades to trust this yet: I treat every setup as a test", lines))
    else:
        out.append(_agent("backtest", "wait", "Never tested on this pair: I wouldn't trust it", ["not tested"]))

    # 6 · Devil's Advocate
    obj = []
    if r and (r["data"].get("M5") or {}).get("verdict") != "FIT":
        v = (r["data"].get("M5") or {}).get("verdict")
        obj.append(f"the M5 candles are {v} in the data check: sweeps and FVGs may be artefacts of the feed")
    if pb:
        for sid, y in pb["strategies"].items():
            a = y["all"]
            if a["trades"] and a["totalR"] <= 0:
                obj.append(f"{sid} {y['name']} lost in the test: win {a['winRate']} % on {a['trades']} trades, {a['totalR']:+.1f}R")
            elif not a["trades"]:
                obj.append(f"{sid} {y['name']} made no trade in a year of tests: its rules are rarely all true")
    obj.append("fewer than 100 backtest trades: any win rate here can be luck")
    if s:
        if htf and (1 if s["direction"] == "BUY" else -1) != htf:
            obj.append("the setup goes against the H4 trend")
        if rng and abs(s["entry"] - rng[1]) < 0.1 * (rng[2] - rng[0]):
            obj.append("the entry sits within 10 % of the range's 50 %: the equilibrium kill zone")
        if s["rr"] < need + 0.5:
            obj.append(f"RR 1:{s['rr']} is close to the 1:{need:g} minimum")
        fails = [q["q"] for q in s["checklist"] if not q["ok"]]
        obj += [f"checklist no: {q}" for q in fails]
    if cot and s:
        d = "BUY" if s["direction"] == "BUY" else "SELL"
        if cot["bias"] not in ("NEUTRAL", d):
            obj.append(f"the big speculators (COT) are net {cot['bias']} ({cot['netPct']:+.0f} %): the setup goes against them")
        elif cot["bias"] == d and cot["crowded"]:
            obj.append(f"the speculators are crowded {d} (3-year extreme): late in the move")
    if last and last["kind"] == "choch":
        obj.append("the last H1 break is a CHoCH: the trend just changed and may be a fake CHoCH (not classified by the engine)")
    if news is None:
        obj.append("news is not checked (the calendar is unavailable)")
    worry = obj[2] if s and len(obj) > 2 else obj[-1]  # the setup's own objection first, the general ones are always true
    out.append(_agent("devil", "warn", f"My worry: {worry}", [f"HYPOTHESIS · {o}" for o in obj]))

    # 7 · Lead Strategist
    signs = {a["key"]: a["status"] for a in out}
    if signal:
        where = f"at market {f(signal['entry'])}" if signal.get("market") else f"in {f(signal['zone'][0])} – {f(signal['zone'][1])}"
        decision = f"I take it: {signal['direction'].lower()} {pair} {where}, stop {f(signal['sl'])}, target {f(signal['tp'])}"
        status = "ok"
    elif blocked:
        why = {"2": "red-folder news is too close", "3": f"the reward is under {need:g} times the risk",
               "5": "a correlated pair already trades the same way", "6": "the volatility regime is wrong for this strategy"}
        no = next((why.get(q["q"].split(" · ", 1)[0], "the checklist says no") for q in blocked["checklist"] if not q["ok"]), "the checklist says no")
        decision = f"I pass on the {blocked['direction'].lower()}: {no}"
        status = "wait"
    else:
        decision = f"No trade: I wait for my setup ({playbook.team_name(key) if key in playbook.NAMES else 'the pair strategy'})"
        status = "wait"
    lines = [f"SCRIPT · this team trades only its pair's strategies from the guide: {playbook.team_name(key) if key in playbook.NAMES else '?'}",
             "SCRIPT · a setup is published only when its rules AND the guide's checklist pass (news, reward, 1 %, correlation, regime)",
             "sign-offs: " + " · ".join(f"{ROLE[k]} {'✓' if v == 'ok' else '!' if v == 'warn' else '…'}" for k, v in signs.items()),
             *[f"HYPOTHESIS · {sid}: the guide says {y['claimed']} · VERIFIED measured "
               + (f"{y['all']['winRate']} % on {y['all']['trades']} trades ({y['all']['totalR']:+.1f}R)" if y["all"]["trades"] else "no trade")
               for sid, y in (pb or {}).get("strategies", {}).items()],
             f"VERIFIED · big players (trader-skill COT): {cot['bias'] if cot else 'not available'}" + (f" ({cot['netPct']:+.0f} % net, report {cot['reportDate']})" if cot else ""),
             "SCRIPT · before any alert, the trader-skill risk check must PASS across all six teams",
             "research, not advice: demo before any live use; nothing here is guaranteed"]
    out.insert(0, _agent("lead", status, decision, lines))
    return out
