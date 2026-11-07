"""
Which strategy has a high win rate on each pair, and does it hold up on candles it never saw?

The candidates (fixed before the run, nothing tuned to a number):
  strategy   S1 · S2 · S3 · S4
  gate       strict (the 7 questions) · A (S2/S4 may go against H4) · B (A + RR >= 2 accepted) · rules (strategy rules only)
  exit       managed  the current exit: target, 50 % at 1:3, break-even after an M5 BOS
             2R       the whole trade closed at 2R, break-even after an M5 BOS (a nearer target: more wins, smaller wins)

The rule, written BEFORE the run, applied to the first 60 % of the candles only (in-sample):
  chosen     at least MIN_IN trades, win rate >= MIN_WIN %, expectancy > 0 R; the best expectancy per pair and strategy
then the choice is checked on the last 40 % (out-of-sample), never used to choose:
  confirmed  at least MIN_OUT trades, expectancy > 0 R and win rate >= MIN_WIN_OUT %
Only CONFIRMED choices are switched on (tools/make_configs.py reads smc/search.json). VERIFIED from the candles, costs in.

  python -m smc.tools.search dukascopy
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from smc.engine import smc
from smc.engine.candles import load
from smc.engine.manage import managed
from smc.tools.perpair import GATES

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]
MIN_IN, MIN_WIN, MIN_OUT, MIN_WIN_OUT = 8, 45, 4, 40
EXITS = ("managed", "2R")


def trade_r(m5, st5, s: dict, cost: float, exit_: str) -> float | None:
    if exit_ == "managed":
        m = managed(m5, st5, s, cost, trail=False)
        return m.get("r")
    d, risk = s["dir"], abs(s["entry"] - s["sl"])
    tp = s["entry"] + d * 2 * risk
    res = smc.simulate(m5, s["index"], d, s["entry"], s["sl"], tp, smc.EXPIRY[smc.STRATEGY_OF[s["sid"]]], cost)
    if "fill" not in res:
        return None
    m = managed(m5, st5, {**s, "tp": tp, "result": res}, cost, trail=False)
    return m.get("r")


def agg(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0, "win": 0, "R": 0.0, "exp": 0.0}
    return {"n": len(rs), "win": round(100 * sum(r > 0.05 for r in rs) / len(rs)), "R": round(sum(rs), 2), "exp": round(sum(rs) / len(rs), 3)}


def main(source: str) -> None:
    out, d = {}, lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    lines = ["# Per pair: the strategies with a high win rate, chosen on the first 60 %, checked on the last 40 %", ""]
    for p in PAIRS:
        base = ROOT / "pairs" / p
        dd = base / "data" / source if source else base / "data"
        if not (dd / "M5.csv").exists():
            lines += [f"## {p}", "", "no data yet", ""]
            continue
        cfg = json.loads((base / "config.json").read_text(encoding="utf-8"))
        m5, h1 = load(dd / "M5.csv"), load(dd / "H1.csv")
        smc.configure(cfg, [])
        cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
        res = smc.scan_all(m5, h1, cost, cfg["decimals"])
        split = m5[0].time + int((m5[-1].time - m5[0].time) * 0.6)
        rows = []
        for sid in ("S1", "S2", "S3", "S4"):
            for g, fn in GATES.items():
                for ex in EXITS:
                    part = {"in": [], "out": []}
                    for s in res[sid]["setups"]:
                        if "r" not in s["result"] or abs(s["entry"] - s["sl"]) < cfg["min_stop_cost_ratio"] * cost:
                            continue
                        fails = [q.split(" · ", 1)[0] for q, ok, _ in s["checklist"] if not ok]
                        if not fn(s, fails):
                            continue
                        r = trade_r(m5, res["_st5"], s, cost, ex)
                        if r is not None:
                            part["in" if s["time"] < split else "out"].append(r)
                    a, b = agg(part["in"]), agg(part["out"])
                    chosen = a["n"] >= MIN_IN and a["win"] >= MIN_WIN and a["exp"] > 0
                    rows.append({"strategy": sid, "gate": g, "exit": ex, "in": a, "out": b, "chosen": chosen})
        picks = []
        for sid in ("S1", "S2", "S3", "S4"):  # the best in-sample choice per strategy, then its out-of-sample check
            c = sorted((r for r in rows if r["strategy"] == sid and r["chosen"]), key=lambda r: -r["in"]["exp"])
            if c:
                best = c[0]
                best["picked"] = True
                o = best["out"]
                best["confirmed"] = o["n"] >= MIN_OUT and o["exp"] > 0 and o["win"] >= MIN_WIN_OUT
                picks.append(best)
        out[p] = {"from": m5[0].time, "split": split, "to": m5[-1].time, "rows": rows, "picks": picks}
        lines += [f"## {p}", "", f"In-sample {d(m5[0].time)} → {d(split)} · out-of-sample {d(split)} → {d(m5[-1].time)}", "",
                  "| strategy | gate | exit | in-sample | out-of-sample | verdict |", "|---|---|---|---|---|---|"]
        f = lambda a: f"{a['n']} tr · win {a['win']} % · {a['R']:+}R" if a["n"] else "0 tr"  # noqa: E731
        for r in sorted(rows, key=lambda r: (r["strategy"], -r["in"]["exp"])):
            if r["in"]["n"] < 3:
                continue
            v = ("**CONFIRMED**" if r.get("confirmed") else "picked, not confirmed") if r.get("picked") else ("chosen" if r["chosen"] else "")
            lines.append(f"| {r['strategy']} | {r['gate']} | {r['exit']} | {f(r['in'])} | {f(r['out'])} | {v} |")
        lines.append("")
    lines += ["## Switched on", "", "| pair | strategy | gate | exit | in-sample | out-of-sample |", "|---|---|---|---|---|---|"]
    on = 0
    for p, x in out.items():
        for r in x["picks"]:
            if r.get("confirmed"):
                on += 1
                lines.append(f"| {p} | {r['strategy']} | {r['gate']} | {r['exit']} | {r['in']['n']} tr · win {r['in']['win']} % · {r['in']['R']:+}R | "
                             f"{r['out']['n']} tr · win {r['out']['win']} % · {r['out']['R']:+}R |")
    if not on:
        lines.append("| — | nothing confirmed | | | | |")
    lines += ["", f"Rule: in-sample >= {MIN_IN} trades, win >= {MIN_WIN} %, expectancy > 0; confirmed out-of-sample with >= {MIN_OUT} trades, "
              f"expectancy > 0, win >= {MIN_WIN_OUT} %. Under 30 trades a result can still be luck: run it on a demo first."]
    tag = f"_{source}" if source else ""
    (ROOT / f"SEARCH{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / f"search{tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"written SEARCH{tag}.md · {on} confirmed")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
