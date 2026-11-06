"""
Backtest of S1–S4 on one pair: the in-sample period first (rules fixed before), then the later out-of-sample period.

  python -m smc.engine.backtest EURUSD     (from the repository root)

Writes smc/pairs/<PAIR>/trades.csv and results.json. Every number in them is computed from the pair's CSV data.
  costs      spread + slippage (config) paid on every trade, in R; the stop sits one cost beyond the swing
  gated      a trade is TAKEN only when its strategy's rules AND the 7 questions pass (what the playbook trades)
  all        every setup of the strategy, checklist ignored (a bigger sample, to see the raw rule)
  plain      full size to TP / SL, closed at market after 4 h ;  managed: 50 % at 1:3, BE after an M5 BOS
  baseline   random direction at the same moments, same stop and target distance (500 runs): the edge is the gap
"""

import csv
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import smc
from .candles import load
from .manage import managed

ROOT = Path(__file__).resolve().parents[1]


def load_news() -> list[int]:
    p = ROOT / "news" / "high_impact.csv"
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return [int(datetime.fromisoformat(r["time_utc"].replace("Z", "+00:00")).timestamp()) for r in csv.DictReader(f)]


def metrics(rs: list[float]) -> dict:
    if not rs:
        return {"trades": 0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    eq, peak, dd, streak, worst = 0.0, 0.0, 0.0, 0, 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        streak = streak + 1 if r < 0 else 0
        worst = max(worst, streak)
    gl = -sum(losses)
    return {"trades": len(rs), "winRate": round(100 * len(wins) / len(rs), 1), "avgWinR": round(sum(wins) / len(wins), 2) if wins else 0,
            "expectancyR": round(sum(rs) / len(rs), 3), "totalR": round(sum(rs), 2), "profitFactor": round(sum(wins) / gl, 2) if gl else None,
            "maxDrawdownR": round(dd, 2), "longestLosingStreak": worst, "weak": len(rs) < 100}


def baseline(m5, trades: list[dict], cost: float, runs: int = 500, seed: int = 7) -> dict:
    """Random direction at each real setup's moment, entering at market on the next M5 open, same stop and target
    distance, same 4-hour limit."""
    rng = random.Random(seed)
    t5 = {x.time: i for i, x in enumerate(m5)}
    means = []
    for _ in range(runs):
        rs = []
        for s in trades:
            i = t5.get(s["time"])
            if i is None or i >= len(m5):
                continue
            d = rng.choice((1, -1))
            e = m5[i].open
            risk, reward = abs(s["entry"] - s["sl"]), abs(s["tp"] - s["entry"])
            sl, tp = e - d * risk, e + d * reward
            r = None
            for j in range(i, min(len(m5), i + smc.HOLD)):
                x = m5[j]
                if (d > 0 and x.low <= sl) or (d < 0 and x.high >= sl):
                    r = -1.0
                    break
                if (d > 0 and x.high >= tp) or (d < 0 and x.low <= tp):
                    r = reward / risk
                    break
            if r is None:
                j = min(len(m5) - 1, i + smc.HOLD - 1)
                r = (m5[j].close - e) / risk * d
            rs.append(r - cost / risk)
        if rs:
            means.append(sum(rs) / len(rs))
    return {"runs": len(means), "expectancyR": round(sum(means) / len(means), 3) if means else None,
            "p95": round(sorted(means)[int(0.95 * (len(means) - 1))], 3) if means else None}


def session_of(t: int) -> str:
    h = (t % 86400) // 3600
    return "Asia" if h < 7 else "London" if h < 12 else "London/NY" if h < 16 else "NY late" if h < 21 else "Rollover"


def run(pair: str) -> dict:
    d = ROOT / "pairs" / pair
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    m5, h1 = load(d / "data" / "M5.csv"), load(d / "data" / "H1.csv")
    smc.configure(cfg, load_news())
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    res = smc.scan_all(m5, h1, cost, cfg["decimals"])
    st5 = res["_st5"]
    t_split = m5[0].time + int((m5[-1].time - m5[0].time) * cfg["split"]["in_sample"])
    rows, out = [], {"pair": pair, "symbol": cfg["symbol"], "m5From": m5[0].time, "m5To": m5[-1].time, "split": t_split,
                     "cost": cost, "strategies": {}}
    for sid in ("S1", "S2", "S3", "S4"):
        setups = res[sid]["setups"]
        block = {"name": smc.STRATEGY_NAMES[sid], "setups": len(setups)}
        for s in setups:
            s["tooSmall"] = abs(s["entry"] - s["sl"]) < cfg["min_stop_cost_ratio"] * cost
            s["managedResult"] = managed(m5, st5, s, cost)
        for scope in ("gated", "all"):
            for period in ("in", "out"):
                pick = [s for s in setups if (s["pass"] or scope == "all") and not s["tooSmall"]
                        and ((s["time"] < t_split) == (period == "in"))]
                done = [s for s in pick if "r" in s["result"]]
                key = f"{scope}_{period}"
                block[key] = {"plain": metrics([s["result"]["r"] for s in done]),
                              "managed": metrics([s["managedResult"]["r"] for s in done if "r" in s["managedResult"]]),
                              "baseline": baseline(m5, done, cost) if done else None,
                              "bySession": {k: metrics([s["result"]["r"] for s in done if session_of(s["time"]) == k])
                                            for k in sorted({session_of(s["time"]) for s in done})},
                              "byMonth": {k: metrics([s["result"]["r"] for s in done if datetime.fromtimestamp(s["time"], timezone.utc).strftime("%Y-%m") == k])
                                          for k in sorted({datetime.fromtimestamp(s["time"], timezone.utc).strftime("%Y-%m") for s in done})}}
        out["strategies"][sid] = block
        for s in setups:
            r = s["result"]
            fails = [a.split(" · ", 1)[-1] for a, ok, _ in s["checklist"] if not ok]
            rows.append({"strategy": sid, "signal_time_utc": datetime.fromtimestamp(s["time"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
                         "period": "in-sample" if s["time"] < t_split else "out-of-sample", "direction": "BUY" if s["dir"] > 0 else "SELL",
                         "entry": round(s["entry"], cfg["decimals"]), "sl": round(s["sl"], cfg["decimals"]), "tp": round(s["tp"], cfg["decimals"]),
                         "rr": round(s["rr"], 2), "checklist_7_pass": s["pass"], "checklist_fails": "; ".join(fails), "stop_too_small": s["tooSmall"],
                         "state": r["state"], "result_r": round(r["r"], 3) if "r" in r else "",
                         "managed_r": round(s["managedResult"]["r"], 3) if "r" in s["managedResult"] else "",
                         "fill_time_utc": datetime.fromtimestamp(m5[r["fill"]].time, timezone.utc).strftime("%Y-%m-%d %H:%M") if "fill" in r else "",
                         "exit_time_utc": datetime.fromtimestamp(m5[r["at"]].time, timezone.utc).strftime("%Y-%m-%d %H:%M") if "at" in r and "fill" in r else "",
                         "session": session_of(s["time"]), "reasons": " | ".join(a for a, ok, _ in s["steps"] if ok)})
    rows.sort(key=lambda x: x["signal_time_utc"])
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["strategy"])
        w.writeheader()
        w.writerows(rows)
    (d / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    for p in sys.argv[1:] or ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]:
        r = run(p.upper().replace("/", ""))
        print(p, {k: (v["setups"], v["gated_out"]["plain"].get("trades"), v["gated_out"]["plain"].get("expectancyR")) for k, v in r["strategies"].items()})
