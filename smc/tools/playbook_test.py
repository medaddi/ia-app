"""
FXAlexG Set & Forget (backend/app/smc/alexg.py) on stored candles, for every pair that has data in smc/pairs/<PAIR>/data:
how many trades, the win rate, the result in R with costs, the profit factor, on the whole period, its first 60 % and
its last 40 %. Writes smc/PLAYBOOK.md and backend/app/smc/research/playbook.json (the app shows these numbers).

  PYTHONPATH=. python smc/tools/playbook_test.py dukascopy

A trade counts only when the desk executes (consensus >= 70, GPA >= 70 %, no veto, trigger and guardian ok),
one trade per pair at a time. News: the stored calendar smc/news/high_impact.csv (ForexFactory high impact); no entry
within 30 min of a release of the pair's currencies. Every trade is followed
on M5: at +1.5 R the stop goes to the entry + 2 pips, the trade runs to the front-run target, a trade not in profit on
Friday 20:00 UTC is closed; the stop before the target inside a candle; spread + slippage included. The portfolio cap is not applied (each pair alone).
D1 and W1 are built from the same stored candles (one year: W1 AOIs see 52 weeks, not the live 156).
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = str(Path(__file__).resolve().parents[2] / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.smc import alexg, playbook  # noqa: E402
from smc.engine.candles import load  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def agg(rs: list[float]) -> dict:
    if not rs:
        return {"trades": 0, "wins": 0, "winRate": None, "totalR": 0.0, "expectancyR": None}
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
    """How the kept trades ended: the full target, break-even after the +1.5 R step, the stop, the time exit."""
    out = {"tp": 0, "be_after_1_5R": 0, "sl": 0}
    for s in ss:
        r = s["result"]["r"]
        out["tp" if r > 1.0 else "be_after_1_5R" if r > 0 else "sl"] += 1  # a time exit falls where its R puts it
    return out


def main(source: str) -> None:
    out = {}
    events = load_events()
    pairs = [k for k in playbook.ALEXG_PAIRS if ((ROOT / "pairs" / k / "data" / source if source else ROOT / "pairs" / k / "data") / "M5.csv").exists()]
    total, tin, tout, tplain = [], [], [], []
    for p in pairs:
        base = ROOT / "pairs" / p
        dd = base / "data" / source if source else base / "data"
        cfg = json.loads((base / "config.json").read_text(encoding="utf-8"))
        m5, h1 = load(dd / "M5.csv"), load(dd / "H1.csv")
        cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
        d1 = playbook.resample(m5, playbook.DAY)
        setups, _ = alexg.scan(p, m5, h1, cost, events or None, d1)
        plain, _ = alexg.scan(p, m5, h1, cost, None, d1)  # the same without the news rule
        split = m5[0].time + int((m5[-1].time - m5[0].time) * 0.6)
        kept = [s for s in setups if s["pass"] and "r" in s["result"]]
        rs = [s["result"]["r"] for s in kept]
        r_in, r_out = [s["result"]["r"] for s in kept if s["time"] < split], [s["result"]["r"] for s in kept if s["time"] >= split]
        r_plain = [s["result"]["r"] for s in plain if s["pass"] and "r" in s["result"]]
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
        out[p] = {"source": source or "yahoo", "from": m5[0].time, "split": split, "to": m5[-1].time, "news": {"events": len(events)},
                  "triggers": len(setups), "grades": grades, "all": a, "in": agg(r_in), "out": agg(r_out), "withoutNewsRule": agg(r_plain),
                  "pf": pf(a), "exits": exits(kept), "strategies": strat}
        total += rs
        tin += r_in
        tout += r_out
        tplain += r_plain
        print(p, "confirmations", len(setups), grades, "| passed", a["trades"], "win", a["winRate"], "R", a["totalR"], "PF", pf(a), exits(kept), flush=True)
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    f = lambda a: f"{a['trades']} · win {a['winRate']} % · {a['totalR']:+}R" if a["trades"] else "0 trades"  # noqa: E731
    first = next(iter(out.values()))
    lines = ["# FXAlexG Set & Forget, measured", "",
             f"VERIFIED from the {(source or 'yahoo').capitalize()} candles, {d(first['from'])} → {d(first['to'])} (split {d(first['split'])}), "
             f"{len(pairs)} pairs with stored data. Every trade followed on M5: at +1.5 R the stop goes to the entry + 2 pips; a trade not in profit "
             "is closed on Friday 20:00 UTC; the stop before the target inside a candle; spread + slippage included. 1R = the risk of one trade.", "",
             "A win = a result above +0.05 R; a close at entry + 2 pips after +1.5 R is a small win. "
             "The exits column shows full targets / closes between 0 and 1 R / stops apart.", "",
             "| pair | closed confirmations at an AOI | executed (SF_BR · SF_BOUNCE · SF_COUNTER) | win rate | result | PF | first 60 % | last 40 % | without the news rule | exits (TP / BE / SL) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for p, x in out.items():
        a, e = x["all"], x["exits"]
        per = " · ".join(f"{k} {v['all']['trades']}" for k, v in x["strategies"].items())
        lines.append(f"| {p} | {x['triggers']} | {a['trades']} ({per}) | {str(a['winRate']) + ' %' if a['trades'] else '—'} | {a['totalR']:+}R | {x['pf'] if x['pf'] is not None else '—'} | "
                     f"{f(x['in'])} | {f(x['out'])} | {f(x['withoutNewsRule'])} | {e['tp']} / {e['be_after_1_5R']} / {e['sl']} |")
    for sid in playbook.SETUP_NAMES:
        rs_ = [y for x in out.values() for y in [x["strategies"][sid]["all"]]]
        n_ = sum(q["trades"] for q in rs_)
        w_ = sum(q["wins"] for q in rs_)
        lines.append(f"| all · {sid} | | {n_} | {round(100 * w_ / n_) if n_ else '—'} % | {sum(q['totalR'] for q in rs_):+.2f}R | | | | | |")
    t = agg(total)
    lines += ["", f"All pairs: {f(t)}, PF {pf(t) if pf(t) is not None else '—'}, expectancy {t['expectancyR'] if t['trades'] else '—'} R per trade. "
              f"First 60 %: {f(agg(tin))}. Last 40 %: {f(agg(tout))}. Without the news rule: {f(agg(tplain))}.", "",
              "Under 30 trades a win rate can still be luck. "
              "The portfolio cap is not applied here (each pair alone)."]
    (ROOT / "PLAYBOOK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT.parent / "backend" / "app" / "smc" / "research" / "playbook.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
