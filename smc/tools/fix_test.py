"""
The fixes of smc/LOSS_ANALYSIS.md, tested (2026-11-19, the owner asked "test the fixes"). Every combination of 4 switches
(alexg.VARIANT: entry, stop floor, sync, score gate) on the same 2 years of H1 as the md's backtest (29 pairs, the
trigger and the follow on H1, the news rule, spread + slippage, one trade per pair).

The rule, fixed BEFORE any result was seen: the combination with the best profit factor on the FIRST 60 % of the time
(at least 60 trades there) is chosen; it is kept only if the LAST 40 % (never used to choose) also has PF > 1.5 and a win
rate >= 50 % (the md's own target). With 81 combinations tried, a good first-60 % number alone proves nothing.

  python smc/tools/fix_test.py <candles.pkl> <out.json>      (candles: {pair: (H1 rows, D1 rows)}, rows = time, o, h, l, c)
"""

import itertools
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

GRID = {"entry": ["md", "mid", "neck"], "sl_floor_adr": [0.0, 0.5, 0.8], "sync": ["md", "swing", "full"], "gate": ["md", "none", "strict"]}
COMBOS = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]


def one_pair(args):
    key, h1r, d1r, split = args
    from app.smc import alexg, playbook
    from smc.tools.playbook_test import load_events
    cfg = alexg.config(key)
    h1 = [playbook._Bar(*x) for x in h1r]
    d1 = [playbook._Bar(*x) for x in d1r]
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    events = load_events()
    out = []
    for v in COMBOS:
        alexg.VARIANT.update(v)
        setups, _ = alexg.scan(key, h1, h1, cost, events, d1, entry_tfs=("H1",))
        out.append([(s["time"], s["result"]["r"]) for s in setups if s["pass"] and "r" in s["result"]])
    return key, out


def agg(rs):
    if not rs:
        return {"n": 0, "win": None, "R": 0.0, "pf": None, "exp": None}
    w = sum(r > 0.05 for r in rs)
    gw, gl = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    return {"n": len(rs), "win": round(100 * w / len(rs), 1), "R": round(sum(rs), 2), "pf": round(gw / gl, 2) if gl else None,
            "exp": round(sum(rs) / len(rs), 3)}


def main(pkl: str, dest: str):
    data = pickle.loads(Path(pkl).read_bytes())
    t0 = min(h[0][0] for h, _ in data.values())
    t1 = max(h[-1][0] for h, _ in data.values())
    split = t0 + int((t1 - t0) * 0.6)
    jobs = [(k, h, d, split) for k, (h, d) in data.items()]
    res = {}
    with ProcessPoolExecutor() as ex:
        for key, out in ex.map(one_pair, jobs):
            res[key] = out
            print(key, "done", flush=True)
    table = []
    for i, v in enumerate(COMBOS):
        rs = [x for k in res for x in res[k][i]]
        table.append({"variant": v, "all": agg([r for _, r in rs]), "in": agg([r for t, r in rs if t < split]),
                      "out": agg([r for t, r in rs if t >= split])})
    ok = [x for x in table if x["in"]["n"] >= 60 and x["in"]["pf"] is not None]
    best = max(ok, key=lambda x: x["in"]["pf"]) if ok else None
    passed = bool(best and (best["out"]["pf"] or 0) > 1.5 and (best["out"]["win"] or 0) >= 50)
    Path(dest).write_text(json.dumps({"split": split, "from": t0, "to": t1, "table": table, "chosen": best, "confirmed": passed}, indent=1))
    f = lambda a: f"{a['n']:4d} · win {a['win']} % · {a['R']:+.1f}R · PF {a['pf']}"  # noqa: E731
    for x in sorted(table, key=lambda x: -(x["in"]["pf"] or 0)):
        print(f"{x['variant']} | first 60 %: {f(x['in'])} | last 40 %: {f(x['out'])} | all: {f(x['all'])}")
    print("CHOSEN on the first 60 %:", best and best["variant"], "→ confirmed on the last 40 %:", passed)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
