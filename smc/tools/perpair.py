"""
Each pair, each strategy, each gate: in-sample (first 60 % of the M5 history) and out-of-sample (the last 40 %, never
used to choose). A strategy is CHOSEN for a pair only from the in-sample part, by a rule written before the run:

  chosen   in-sample managed expectancy > 0 R with at least MIN_TRADES trades

then the chosen strategies are measured on the out-of-sample part. That last number is the only honest one.
Writes smc/PERPAIR.md and smc/perpair.json. VERIFIED from the CSV candles; costs included.

  python -m smc.tools.perpair              # the Yahoo candles (data/)
  python -m smc.tools.perpair dukascopy    # two years of Dukascopy candles (data/dukascopy/) → PERPAIR_dukascopy.md
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from smc.engine import smc
from smc.engine.candles import load
from smc.engine.manage import managed

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]
MIN_TRADES = 3
GATES = {
    "strict": lambda s, fails: not fails,
    "A": lambda s, fails: not [f for f in fails if not (f == "1" and s["sid"] in ("S2", "S4"))],
    "B": lambda s, fails: not [f for f in fails if not ((f == "1" and s["sid"] in ("S2", "S4")) or (f == "7" and s["rr"] >= 2))],
    "rules": lambda s, fails: True,  # the strategy's own rules only, no checklist: shows what the 7 questions add or remove
}


def agg(rs):
    if not rs:
        return {"n": 0, "win": None, "R": 0.0, "exp": None}
    return {"n": len(rs), "win": round(100 * sum(r > 0 for r in rs) / len(rs)), "R": round(sum(rs), 2), "exp": round(sum(rs) / len(rs), 2)}


def main(source: str = "") -> None:
    out = {}
    for p in PAIRS:
        d = ROOT / "pairs" / p
        cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
        dd = d / "data" / source if source else d / "data"
        m5, h1 = load(dd / "M5.csv"), load(dd / "H1.csv")
        smc.configure(cfg, [])
        cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
        res = smc.scan_all(m5, h1, cost, cfg["decimals"])
        split = m5[0].time + int((m5[-1].time - m5[0].time) * 0.6)
        rows = {}
        for sid in ("S1", "S2", "S3", "S4"):
            for g, fn in GATES.items():
                part = {"in": [], "out": []}
                for s in res[sid]["setups"]:
                    if "r" not in s["result"] or abs(s["entry"] - s["sl"]) < cfg["min_stop_cost_ratio"] * cost:
                        continue
                    fails = [q.split(" · ", 1)[0] for q, ok, _ in s["checklist"] if not ok]
                    if not fn(s, fails):
                        continue
                    m = managed(m5, res["_st5"], s, cost, trail=False)
                    if "r" in m:
                        part["in" if s["time"] < split else "out"].append(m["r"])
                rows[f"{sid}|{g}"] = {"in": agg(part["in"]), "out": agg(part["out"]), "outR": part["out"]}
        out[p] = {"split": split, "from": m5[0].time, "to": m5[-1].time, "rows": rows}
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    first = next(iter(out.values()))
    lines = ["# Each pair: which strategy, chosen on the first part, held up on the unseen part?", "",
             f"VERIFIED from the {source.capitalize() or 'Yahoo'} candles. In-sample {d(first['from'])} → {d(first['split'])}, out-of-sample {d(first['split'])} → {d(first['to'])}. "
             "Results with the management (50 % at 1:3 + break-even after an M5 BOS), costs included, in R (1R = $100 at 1 % of $10,000).", "",
             f"Rule written BEFORE the run: a strategy is chosen for a pair when its in-sample expectancy is > 0 R with at least {MIN_TRADES} trades. "
             "Only the out-of-sample column tests that choice.", ""]
    summary = {g: [] for g in GATES}
    for p, x in out.items():
        lines += [f"## {p}", "", "| strategy | gate | in-sample | chosen? | out-of-sample |", "|---|---|---|---|---|"]
        for key, r in x["rows"].items():
            sid, g = key.split("|")
            chosen = r["in"]["n"] >= MIN_TRADES and (r["in"]["exp"] or 0) > 0
            if chosen:
                summary[g] += [(p, sid, v) for v in r["outR"]]
            fmt = lambda a: f"{a['n']} tr" + (f" · win {a['win']} % · {a['R']:+}R" if a["n"] else "")  # noqa: E731
            lines.append(f"| {sid} | {g} | {fmt(r['in'])} | {'**yes**' if chosen else 'no'} | {fmt(r['out'])} |")
        lines.append("")
    lines += ["## What the choices did on the unseen part", "", "| gate | strategies chosen (pair · strategy) | out-of-sample trades | win rate | result |", "|---|---|---|---|---|"]
    for g, xs in summary.items():
        picks = sorted({f"{p} {s}" for p, s, _ in xs})
        rs = [v for _, _, v in xs]
        a = agg(rs)
        lines.append(f"| {g} | {', '.join(picks) or '—'} | {a['n']} | {str(a['win']) + ' %' if a['n'] else '—'} | {a['R']:+}R (${a['R'] * 100:+,.0f}) |")
    lines += ["", "Under 30 out-of-sample trades, a positive number is a hint to keep testing, not proof."]
    tag = f"_{source}" if source else ""
    (ROOT / f"PERPAIR{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / f"perpair{tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
