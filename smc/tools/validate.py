"""
Honest validation of the Set & Forget engine (backend/app/smc/alexg.py), version against version, pair by pair.

  PYTHONPATH=. python smc/tools/validate.py dukascopy   # the stored year (pairs that have smc/pairs/<PAIR>/data/dukascopy)
  PYTHONPATH=. python smc/tools/validate.py yahoo       # the app's own Yahoo feed: M5 60 days, all 29 instruments

What is fixed BEFORE any run (backend/app/smc/strategy.json):
  versions    baseline (the app before v2.4), candidate (H4 fallback zones + the counter-trend gate), candidate_rr3 and
              candidate_rr4 (the same with a minimum R:R of 3 and 4). Nothing is tuned on the results.
  split       chronological: train = first 50 % of the period, validation = next 25 %, test = last 25 %. Out of sample
              (OOS) = validation + test. No shuffling.
  evidence    an instrument is "validated for research" only with >= 100 OOS trades AND a 95 % bootstrap interval of its
              net expectancy above 0 R; with >= 100 OOS trades and not that: "experimental"; otherwise "insufficient data".
  costs       spread + slippage of the pair's config on every trade; the news rule (no entry 30 min around high-impact
              releases, smc/news/high_impact.csv), the session, rollover, Friday rules of the engine; entry at the close
              of the confirmation candle; each trade followed on M5, the stop before the target inside a candle.

Per version, per instrument and per setup type (SF_BR, SF_BOUNCE trend-following; SF_COUNTER counter-trend, never merged):
trades, win rate, average win and loss in R, average cost in R, net expectancy E = p x avgWin - (1 - p) x avgLoss (the R
are after costs), profit factor = gross positive R / |gross negative R|, maximum drawdown in R, the bootstrap interval.

Writes smc/research/VALIDATION_<date>_<source>.md and backend/app/smc/research/validation.json (the app shows each
pair's evidence state from it). It never says a pair is profitable: it says what the sample can and cannot show.
"""

import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = str(Path(__file__).resolve().parents[2] / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.smc import alexg, playbook  # noqa: E402
from smc.engine.candles import load  # noqa: E402
from smc.tools.playbook_test import load_events  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
V = alexg.STRATEGY["validation"]
VERSIONS = list(alexg.STRATEGY["presets"])
SETUPS = list(playbook.SETUP_NAMES)
FAMILY = {"SF_BR": "trend-following", "SF_BOUNCE": "trend-following", "SF_COUNTER": "counter-trend"}
MIN_OOS = V["min_oos_trades_per_instrument"]


def bootstrap(rs: list[float]) -> list[float] | None:
    """The 95 % percentile interval of the mean R (seeded: the same trades always give the same interval)."""
    if len(rs) < 2:
        return None
    rnd = random.Random(V["bootstrap_seed"])
    n = len(rs)
    means = sorted(sum(rnd.choice(rs) for _ in range(n)) / n for _ in range(V["bootstrap_resamples"]))
    return [round(means[int(0.025 * len(means))], 3), round(means[int(0.975 * len(means)) - 1], 3)]


def metrics(tr: list[dict]) -> dict:
    """tr: trades in time order, each {time, r (net of costs), cost (in R)}."""
    rs = [t["r"] for t in tr]
    n = len(rs)
    if not n:
        return {"trades": 0}
    wins, losses = [r for r in rs if r > 0.05], [r for r in rs if r <= 0.05]
    gp, gl = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    peak = cum = dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    p = len(wins) / n
    return {"trades": n, "wins": len(wins), "winRate": round(100 * p, 1), "avgWinR": round(sum(wins) / len(wins), 3) if wins else None,
            "avgLossR": round(-sum(losses) / len(losses), 3) if losses else None, "avgCostR": round(sum(t["cost"] for t in tr) / n, 3),
            "expectancyR": round(sum(rs) / n, 3), "totalR": round(sum(rs), 2), "pf": round(gp / gl, 2) if gl > 0 else None,
            "maxDrawdownR": round(dd, 2), "ci95": bootstrap(rs)}


def state_of(oos: dict) -> str:
    if oos.get("trades", 0) < MIN_OOS:
        return "insufficient data"
    return "validated for research" if oos["ci95"] and oos["ci95"][0] > 0 else "experimental"


def run_pair(key: str, m5, h1, d1, cost: float, events) -> dict:
    """Every version on one pair's candles."""
    t0, t1 = m5[0].time, m5[-1].time
    a = t0 + int((t1 - t0) * V["split"]["train"])
    b = t0 + int((t1 - t0) * (V["split"]["train"] + V["split"]["validation"]))
    out = {"from": t0, "to": t1, "trainEnd": a, "validationEnd": b, "versions": {}}
    for ver in VERSIONS:
        alexg.use(ver)
        setups, _ = alexg.scan(key, m5, h1, cost, events or None, d1)
        kept = sorted((s for s in setups if s["pass"] and "r" in s["result"]), key=lambda s: s["time"])
        tr = [{"time": s["time"], "r": s["result"]["r"], "cost": cost / abs(s["entry"] - s["sl"]), "sid": s["sid"],
               "h4": (s.get("zoneInfo") or {}).get("label") == "4H"} for s in kept]
        seg = lambda lo, hi: [t for t in tr if lo <= t["time"] < hi]  # noqa: E731
        oos = metrics(seg(a, 1 << 62))
        out["versions"][ver] = {"all": metrics(tr), "train": metrics(seg(0, a)), "validation": metrics(seg(a, b)), "test": metrics(seg(b, 1 << 62)),
                                "oos": oos, "state": state_of(oos), "confirmations": len(setups), "h4FallbackTrades": sum(t["h4"] for t in tr),
                                "setups": {sid: metrics([t for t in tr if t["sid"] == sid]) for sid in SETUPS}, "_tr": tr}
    alexg.use()
    return out


def stored(source: str):
    for key in playbook.ALEXG_PAIRS:
        base = ROOT / "pairs" / key
        dd = base / "data" / source
        if not (dd / "M5.csv").exists():
            continue
        cfg = json.loads((base / "config.json").read_text(encoding="utf-8"))
        m5, h1 = load(dd / "M5.csv"), load(dd / "H1.csv")
        yield key, cfg, m5, h1, playbook.resample(m5, playbook.DAY)


async def yahoo():
    from smc.tools.yahoo_test import candles
    for key in playbook.ALEXG_PAIRS:
        cfg = json.loads((ROOT / "pairs" / key / "config.json").read_text(encoding="utf-8"))
        try:
            m5, h1, d1 = await candles(cfg["symbol"], cfg["yahoo"])
        except Exception as err:
            print(key, "no data:", repr(err), flush=True)
            continue
        if len(m5) < 1000 or len(h1) < 500 or len(d1) < 300:
            print(key, "too little data", len(m5), len(h1), len(d1), flush=True)
            continue
        yield key, cfg, m5, h1, d1


def cell(m: dict) -> str:
    if not m.get("trades"):
        return "0"
    ci = f" [{m['ci95'][0]:+.2f}, {m['ci95'][1]:+.2f}]" if m.get("ci95") else ""
    return f"{m['trades']} · {m['winRate']:.0f} % · E {m['expectancyR']:+.2f}R{ci} · PF {m['pf'] if m['pf'] is not None else '—'} · DD {m['maxDrawdownR']}R"


def report(source: str, res: dict, quality: str) -> str:
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    first = next(iter(res.values()))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    L = [f"# Validation of Set & Forget · {source} · {today}", "",
         f"Data: {quality} Period {d(first['from'])} → {d(first['to'])}; train until {d(first['trainEnd'])}, validation until "
         f"{d(first['validationEnd'])}, test after. {len(res)} instruments.", "",
         "Fixed before the run (backend/app/smc/strategy.json): the four versions, the chronological 50 / 25 / 25 split, the rule "
         f"that an instrument needs {MIN_OOS} out-of-sample trades and a 95 % interval above 0 R before it is called validated. "
         "Costs: the config's spread + slippage on every trade. News, session, rollover and Friday rules on. Nothing was tuned on these results.", "",
         "Reading a cell: trades · win rate · net expectancy per trade with its 95 % bootstrap interval · profit factor · maximum drawdown. "
         "R are after costs. With 3R wins and 1R losses the break-even win rate is 25 % before costs (1 / (3 + 1)); with 4R wins, 20 %; costs raise both.", ""]
    agg = {}
    for ver in VERSIONS:
        allt = sorted((t for x in res.values() for t in x["versions"][ver]["_tr"]), key=lambda t: t["time"])
        oos = sorted((t for x in res.values() for t in x["versions"][ver]["_tr"] if t["time"] >= x["trainEnd"]), key=lambda t: t["time"])
        agg[ver] = {"all": metrics(allt), "oos": metrics(oos), "setups": {sid: metrics([t for t in allt if t["sid"] == sid]) for sid in SETUPS},
                    "family": {f: metrics([t for t in allt if FAMILY[t["sid"]] == f]) for f in ("trend-following", "counter-trend")},
                    "h4": sum(t["h4"] for t in allt)}
    L += ["## All instruments together", "", "| version | all trades | out of sample | trend-following | counter-trend (separate) | trades on a 4H fallback zone |", "|---|---|---|---|---|---|"]
    for ver in VERSIONS:
        a = agg[ver]
        L.append(f"| {ver} | {cell(a['all'])} | {cell(a['oos'])} | {cell(a['family']['trend-following'])} | {cell(a['family']['counter-trend'])} | {a['h4']} |")
    L += ["", "## Per setup type (all instruments)", "", "| version | SF_BR | SF_BOUNCE | SF_COUNTER |", "|---|---|---|---|"]
    for ver in VERSIONS:
        L.append(f"| {ver} | " + " | ".join(cell(agg[ver]["setups"][sid]) for sid in SETUPS) + " |")
    L += ["", "## Per instrument (a pair with many trades never hides a losing one)", ""]
    for ver in VERSIONS:
        L += [f"### {ver}", "", "| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |", "|---|---|---|---|---|---|---|"]
        for key, x in res.items():
            v = x["versions"][ver]
            m = v["all"]
            wl = f"{m.get('avgWinR') or '—'} / {m.get('avgLossR') or '—'} / {m.get('avgCostR')}" if m.get("trades") else "—"
            L.append(f"| {key} | {cell(m)} | {cell(v['train'])} | {cell(v['validation'])} | {cell(v['test'])} | {wl} | {v['state']} ({v['oos'].get('trades', 0)} OOS) |")
        L.append("")
    worst = max((x["versions"]["candidate"]["oos"].get("trades", 0) for x in res.values()), default=0)
    L += ["## What this shows", "",
          f"- The most out-of-sample trades any instrument has on the candidate is {worst}; the requirement is {MIN_OOS}. "
          + ("No instrument is validated: the evidence is insufficient." if worst < MIN_OOS else "See the evidence column."),
          "- A positive or negative total on a handful of trades is not a result: the intervals above are wide and most cross 0.",
          "- Nothing here says the strategy is profitable."]
    return "\n".join(L) + "\n"


async def main(source: str) -> None:
    events = load_events()
    res = {}
    if source == "yahoo":
        quality = ("Yahoo Finance through the app's own feed code: M5 60 days, H1 2 years, D1 5 years (full W1 / D1 history for the structure "
                   "and the zones); gold is COMEX GC=F futures; forex has no volume; closed candles only.")
        async for key, cfg, m5, h1, d1 in yahoo():
            res[key] = run_pair(key, m5, h1, d1, (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"], events)
            print(key, {v: res[key]["versions"][v]["all"].get("trades", 0) for v in VERSIONS}, flush=True)
    else:
        quality = (f"stored {source.capitalize()} candles (M5 and H1, one year); D1 and W1 are built from that same year, so the weekly "
                   "structure and the zones see less history than the live app does.")
        for key, cfg, m5, h1, d1 in stored(source):
            res[key] = run_pair(key, m5, h1, d1, (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"], events)
            print(key, {v: res[key]["versions"][v]["all"].get("trades", 0) for v in VERSIONS}, flush=True)
    if not res:
        print("no data")
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = report(source, res, quality)
    (ROOT / "research").mkdir(exist_ok=True)
    (ROOT / "research" / f"VALIDATION_{today}_{source}.md").write_text(text, encoding="utf-8")
    dest = ROOT.parent / "backend" / "app" / "smc" / "research" / "validation.json"
    old = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {"sources": {}}
    for x in res.values():
        for v in x["versions"].values():
            v.pop("_tr")
    old["sources"][source] = {"date": today, "minOosTrades": MIN_OOS, "pairs": res}
    # each pair's evidence state for the app: the live version (candidate), the source with the most out-of-sample trades
    pairs = {}
    for src, blob in old["sources"].items():
        for key, x in blob["pairs"].items():
            v = x["versions"]["candidate"]
            n = v["oos"].get("trades", 0)
            if key not in pairs or n > pairs[key]["oosTrades"]:
                pairs[key] = {"state": v["state"], "oosTrades": n, "needed": MIN_OOS, "trades": v["all"].get("trades", 0),
                              "expectancyR": v["all"].get("expectancyR"), "ci95": v["all"].get("ci95"), "source": src, "date": blob["date"],
                              "from": x["from"], "to": x["to"]}
    old["pairs"] = pairs
    dest.write_text(json.dumps(old, indent=1), encoding="utf-8")
    sys.stdout.buffer.write(text.encode("utf-8"))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "dukascopy"))
