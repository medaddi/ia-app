"""
Each pair's strategies from the guide (backend/app/smc/playbook.py) on stored candles: how many trades, the REAL win rate, the
result in R with costs, on the first 60 % (in-sample) and the last 40 % (out-of-sample), next to the win rate the
playbook claims. Writes smc/PLAYBOOK.md and backend/app/smc/research/playbook.json (the teams show these numbers).

  python -m smc.tools.playbook_test dukascopy

The news rule is applied with the stored calendar smc/news/high_impact.csv (ForexFactory high-impact events for USD, EUR,
GBP, CHF, AUD, CAD, Nov 2025 - Nov 2026, read from its month pages): a signal within 15 min of one of the pair's releases
is not taken, and a pending limit is pulled 15 min before a release. Each pair counts its own currencies (gold: USD).
The result WITHOUT the news rule is shown next to it, and how many kept trades were still open through a release.
The correlation cap is not applied here (each pair alone). VERIFIED from the candles.
"""

import json
import sys
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

_backend = str(Path(__file__).resolve().parents[2] / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.smc import playbook  # noqa: E402
from smc.engine.candles import load  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]


def agg(rs: list[float]) -> dict:
    if not rs:
        return {"trades": 0, "wins": 0, "winRate": None, "totalR": 0.0, "expectancyR": None}
    w = sum(r > 0.05 for r in rs)
    return {"trades": len(rs), "wins": w, "winRate": round(100 * w / len(rs)), "totalR": round(sum(rs), 2), "expectancyR": round(sum(rs) / len(rs), 3)}


def load_news() -> dict[str, list[int]]:
    f = ROOT / "news" / "high_impact.csv"
    out: dict[str, list[int]] = {}
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines()[1:]:
        t, cur, _ = line.split(",", 2)
        out.setdefault(cur, []).append(int(t))
    return {k: sorted(set(v)) for k, v in out.items()}


def pair_news(news: dict[str, list[int]], pair: str) -> list[int]:
    cur = {"USD"} if pair == "XAUUSD" else {pair[:3], pair[3:]}
    return sorted({t for c in cur for t in news.get(c, [])})


def main(source: str) -> None:
    out = {}
    eur = None
    NEWS = load_news()
    for p in PAIRS:
        base = ROOT / "pairs" / p
        dd = base / "data" / source if source else base / "data"
        cfg = json.loads((base / "config.json").read_text(encoding="utf-8"))
        m5, h1 = load(dd / "M5.csv"), load(dd / "H1.csv")
        if p == "EURUSD":
            eur = m5
        cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
        d1 = playbook.resample(m5, playbook.DAY)
        nw = pair_news(NEWS, p)
        setups, _ = playbook.scan(p, m5, h1, cfg["pip"], cost, nw if NEWS else None, None, d1)
        plain, _ = playbook.scan(p, m5, h1, cfg["pip"], cost, None, None, d1)  # the same without the news rule
        split = m5[0].time + int((m5[-1].time - m5[0].time) * 0.6)
        out[p] = {"source": source or "yahoo", "from": m5[0].time, "split": split, "to": m5[-1].time, "strategies": {},
                  "news": {"events": len(nw), "file": "smc/news/high_impact.csv" if NEWS else None}}

        def kept(ss):
            return [s for s in ss if s["pass"] and "r" in s["result"] and abs(s["entry"] - s["sl"]) >= cfg["min_stop_cost_ratio"] * cost]

        for sid in playbook.STRATEGIES[p]:
            parts = {"in": [], "out": [], "all": []}
            states: dict[str, int] = {}
            mine = [s for s in setups if s["sid"] == sid]
            through = 0
            for s in mine:
                states[s["result"]["state"]] = states.get(s["result"]["state"], 0) + 1
            for s in kept(mine):
                r = s["result"]["r"]
                parts["all"].append(r)
                parts["in" if s["time"] < split else "out"].append(r)
                t0 = m5[s["result"]["fill"]].time if s["result"].get("fill") is not None else s["time"]
                t1 = m5[s["result"]["at"]].time if "at" in s["result"] else t0
                if any(t0 <= n <= t1 for n in nw[bisect_left(nw, t0):bisect_left(nw, t1 + 1)]):
                    through += 1
            before = agg([s["result"]["r"] for s in kept([x for x in plain if x["sid"] == sid])])
            out[p]["strategies"][sid] = {"name": playbook.NAMES[p][sid], "claimed": playbook.CLAIMED[(p, sid)], "setups": len(mine),
                                         "states": states, "all": agg(parts["all"]), "in": agg(parts["in"]), "out": agg(parts["out"]),
                                         "withoutNewsRule": before, "openThroughNews": through}
            print(p, sid, out[p]["strategies"][sid]["all"], "| without the news rule", before, flush=True)
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    first = next(iter(out.values()))
    f = lambda a: f"{a['trades']} · win {a['winRate']} % · {a['totalR']:+}R" if a["trades"] else "0 trades"  # noqa: E731
    lines = ["# The guide's strategies, measured", "",
             f"VERIFIED from the {(source or 'yahoo').capitalize()} candles, {d(first['from'])} → {d(first['to'])} (split {d(first['split'])}). "
             "Every trade followed on M5, the stop before the target inside a candle, spread + slippage included. "
             "1R = the risk of one trade (1 % of the account). A trade counts only when its checklist passed.", "",
             "News: the stored ForexFactory calendar (high impact, the pair's currencies): no signal within 15 min of a release, "
             "a pending limit pulled 15 min before one.", "",
             "| pair | strategy | the guide says | trades | win rate | result | first 60 % | last 40 % | without the news rule | kept trades open through a release |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    n = w = 0
    tot = 0.0
    for p, x in out.items():
        for sid, y in x["strategies"].items():
            a = y["all"]
            n, w, tot = n + a["trades"], w + a["wins"], tot + a["totalR"]
            lines.append(f"| {p} | {sid} {y['name']} | {y['claimed']} | {a['trades']} | {str(a['winRate']) + ' %' if a['trades'] else '—'} | "
                         f"{a['totalR']:+}R | {f(y['in'])} | {f(y['out'])} | {f(y['withoutNewsRule'])} | {y['openThroughNews']} |")
    lines += ["", f"All: {n} trades, win rate {round(100 * w / n) if n else 0} %, {tot:+.2f}R.", "",
              "Not applied here: the correlation cap (each pair alone). "
              "Under 30 trades a win rate can still be luck."]
    (ROOT / "PLAYBOOK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT.parent / "backend" / "app" / "smc" / "research" / "playbook.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
