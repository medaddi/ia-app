"""
FXAlexG Set & Forget (backend/app/smc/alexg.py, the owner's md of 2026-11-19) on history: how many trades, the win rate,
the result in R with costs, the profit factor, on the whole period, its first 60 % and its last 40 %. Writes
smc/PLAYBOOK.md and backend/app/smc/research/playbook.json (the app shows these numbers).

  PYTHONPATH=. python smc/tools/playbook_test.py feed        the app's own feed: H1 (2 years) and D1 (5 years) per pair
  PYTHONPATH=. python smc/tools/playbook_test.py dukascopy   stored candles in smc/pairs/<PAIR>/data/dukascopy (M5 + H1)

A trade counts only when the desk executes (sync, S_AlexG >= 80 %, SoS + Engulfing, R:R >= 2.5, no veto), one trade
per pair at a time. News: the stored calendar smc/news/high_impact.csv (ForexFactory high impact); no entry within 30
min of a release of the pair's currencies. At +1.5 R the stop goes to the entry and 25 % is banked; the stop before the
target inside a candle; spread + slippage included. The portfolio check is not applied (each pair alone).

"feed" mode: the trigger is read on H1 only (the feed keeps M30 / M15 for 60 days, too short to test), and every
trade is followed on H1 candles, not M5 (a candle that reaches both the stop and the target counts as the stop).
"""

import asyncio
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = str(Path(__file__).resolve().parents[2] / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.smc import alexg, playbook  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def agg(rs: list[float]) -> dict:
    if not rs:
        return {"trades": 0, "wins": 0, "winRate": None, "totalR": 0.0, "expectancyR": None, "grossWinR": 0.0, "grossLossR": 0.0}
    w = sum(r > 0.05 for r in rs)
    return {"trades": len(rs), "wins": w, "winRate": round(100 * w / len(rs)), "totalR": round(sum(rs), 2), "expectancyR": round(sum(rs) / len(rs), 3),
            "grossWinR": round(sum(r for r in rs if r > 0), 3), "grossLossR": round(-sum(r for r in rs if r < 0), 3)}


def pf(a: dict):
    return round(a["grossWinR"] / a["grossLossR"], 2) if a.get("grossLossR") else None


def load_events() -> list[dict]:
    p = ROOT / "news" / "high_impact.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        return [{"time": int(r["time_utc"]), "currency": r["currency"], "title": r["event"]} for r in csv.DictReader(fh)]


def exits(ss: list[dict]) -> dict:
    """How the kept trades ended: the full target, the break-even stop after +1.5 R (+0.375 R banked), the stop."""
    out = {"tp": 0, "be_after_1_5R": 0, "sl": 0}
    for s in ss:
        r = s["result"]["r"]
        out["tp" if r > 1.0 else "be_after_1_5R" if r > 0 else "sl"] += 1
    return out


def pair_result(p: str, follow, h1, d1, cfg: dict, events: list, entry_tfs: tuple, source: str) -> dict:
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    setups, _ = alexg.scan(p, follow, h1, cost, events or None, d1, entry_tfs=entry_tfs)
    split = follow[0].time + int((follow[-1].time - follow[0].time) * 0.6)
    kept = [s for s in setups if s["pass"] and "r" in s["result"]]
    rs = [s["result"]["r"] for s in kept]
    grades: dict[str, int] = {}
    for s in setups:
        grades[s["grade"]] = grades.get(s["grade"], 0) + 1
    a = agg(rs)
    strat = {}
    for sid in playbook.STRATEGIES[p]:
        mine = [s for s in kept if s["sid"] == sid]
        am = agg([s["result"]["r"] for s in mine])
        strat[sid] = {"name": playbook.NAMES[p][sid], "claimed": playbook.CLAIMED[(p, sid)], "setups": len([s for s in setups if s["sid"] == sid]),
                      "all": am, "in": agg([s["result"]["r"] for s in mine if s["time"] < split]),
                      "out": agg([s["result"]["r"] for s in mine if s["time"] >= split]), "pf": pf(am), "exits": exits(mine)}
    vetoes: dict[str, int] = {}
    for s in setups:
        if not s["pass"]:
            for v in s.get("vetoes") or ["gate (score / sync / one per pair)"]:
                vetoes[v] = vetoes.get(v, 0) + 1
    return {"source": source, "from": follow[0].time, "split": split, "to": follow[-1].time, "news": {"events": len(events)},
            "entryTfs": list(entry_tfs), "triggers": len(setups), "grades": grades, "blockedBy": vetoes, "all": a,
            "in": agg([s["result"]["r"] for s in kept if s["time"] < split]), "out": agg([s["result"]["r"] for s in kept if s["time"] >= split]),
            "pf": pf(a), "exits": exits(kept), "strategies": strat, "_rs": rs,
            "_in": [s["result"]["r"] for s in kept if s["time"] < split], "_out": [s["result"]["r"] for s in kept if s["time"] >= split]}


def write(out: dict, source: str, note: str) -> None:
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    f = lambda a: f"{a['trades']} · win {a['winRate']} % · {a['totalR']:+}R" if a["trades"] else "0 trades"  # noqa: E731
    total = [r for x in out.values() for r in x["_rs"]]
    tin = [r for x in out.values() for r in x["_in"]]
    tout = [r for x in out.values() for r in x["_out"]]
    first = next(iter(out.values()))
    lines = ["# FXAlexG Set & Forget, measured", "",
             f"VERIFIED from {source} candles, {d(first['from'])} → {d(first['to'])} (split at 60 %), {len(out)} pairs. {note} "
             "At +1.5 R the stop goes to the entry and 25 % is banked (+0.375 R); spread + slippage included. 1R = the risk of one trade.", "",
             "A win = a result above +0.05 R (a break-even close after +1.5 R is a small win). Exits: full targets / break-even after +1.5 R / stops.", "",
             "| pair | two-step triggers at an AOI | executed (S&F-SWING · S&F-DAY) | win rate | result | PF | first 60 % | last 40 % | exits (TP / BE / SL) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for p, x in out.items():
        a, e = x["all"], x["exits"]
        per = " · ".join(f"{v['all']['trades']}" for v in x["strategies"].values())
        lines.append(f"| {p} | {x['triggers']} | {a['trades']} ({per}) | {str(a['winRate']) + ' %' if a['trades'] else '—'} | {a['totalR']:+}R | "
                     f"{x['pf'] if x['pf'] is not None else '—'} | {f(x['in'])} | {f(x['out'])} | {e['tp']} / {e['be_after_1_5R']} / {e['sl']} |")
    t = agg(total)
    lines += ["", f"**All pairs: {f(t)}, PF {pf(t) if pf(t) is not None else '—'}, expectancy {t['expectancyR'] if t['trades'] else '—'} R per trade.** "
              f"First 60 %: {f(agg(tin))}. Last 40 %: {f(agg(tout))}.", "",
              "The spec's target is PF > 1.5 and a win rate >= 50 %: "
              + (("met" if (pf(t) or 0) > 1.5 and (t["winRate"] or 0) >= 50 else "NOT met") + " on this sample." if t["trades"] else "no trade to judge."),
              "Under 30 trades a win rate can still be luck. The portfolio check is not applied here (each pair alone)."]
    (ROOT / "PLAYBOOK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT.parent / "backend" / "app" / "smc" / "research" / "playbook.json"
    dest.write_text(json.dumps({p: {k: v for k, v in x.items() if not k.startswith("_")} for p, x in out.items()}, indent=1), encoding="utf-8")
    print("\n".join(lines))


async def main_feed() -> None:
    from app.market.data import fetch_candle_series
    events = load_events()
    out = {}
    for key in playbook.ALEXG_PAIRS:
        cfg = alexg.config(key)
        sym = cfg["symbol"]
        h1s, ds = await asyncio.gather(fetch_candle_series(sym, "1H", 13000), fetch_candle_series(sym, "1D", 1600))
        if h1s.get("isSynthetic") or ds.get("isSynthetic"):
            print(key, "no feed data", flush=True)
            continue
        h1, d1 = h1s["candles"][:-1], ds["candles"][:-1]  # the last candle may be forming
        x = await asyncio.to_thread(pair_result, key, h1, h1, d1, cfg, events, ("H1",), h1s.get("source") or "feed")
        out[key] = x
        a = x["all"]
        print(key, len(h1), "H1 /", len(d1), "D1 | triggers", x["triggers"], x["grades"], "| passed", a["trades"], "win", a["winRate"], "R", a["totalR"],
              "PF", x["pf"], x["exits"], "| blocked", x["blockedBy"], flush=True)
    write(out, "the app's feed (Yahoo Finance forex, COMEX GC=F adjusted to spot for gold)",
          "The trigger is read on H1 only and every trade is followed on H1 candles (a candle reaching both the stop and the target counts as the stop).")


def main_stored(source: str) -> None:
    from smc.engine.candles import load
    events = load_events()
    out = {}
    for p in playbook.ALEXG_PAIRS:
        dd = ROOT / "pairs" / p / "data" / source if source else ROOT / "pairs" / p / "data"
        if not (dd / "M5.csv").exists():
            continue
        cfg = json.loads((ROOT / "pairs" / p / "config.json").read_text(encoding="utf-8"))
        m5, h1 = load(dd / "M5.csv"), load(dd / "H1.csv")
        out[p] = pair_result(p, m5, h1, playbook.resample(m5, playbook.DAY), cfg, events, alexg.ENTRY_TFS, source or "stored")
        print(p, out[p]["all"], flush=True)
    if out:
        write(out, f"the stored {source or 'yahoo'}", "Every trade followed on M5.")
    else:
        print("no stored candles")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "feed"
    if arg == "feed":
        asyncio.run(main_feed())
    else:
        main_stored(arg)
