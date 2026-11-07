"""
The last N days (default 60) with the app's EXACT rules: what each pair's team would have taken, and what it would have
made. Same engine, same configs, same costs, same gate as the live app (a strategy's rules + all 7 questions + a stop of
at least min_stop_cost_ratio × the cost), then the trader-skill risk check across the six teams in time order, as the
notifier applies it. Writes smc/LAST60.md. VERIFIED numbers only (from the CSV candles).

  python -m smc.tools.last60 [days]

Money: 1 % risk per trade on a $10,000 account, not compounded (1R = $100). Costs (spread + slippage) are in every trade.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from smc.engine import smc
from smc.engine.candles import load
from smc.engine.manage import managed
from app.smc.skill import portfolio  # importable once smc.engine has put the backend on the path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]
R_USD = 100.0  # 1 % of $10,000


def stats(rs: list[float]) -> dict:
    if not rs:
        return {"trades": 0, "wins": 0, "winRate": None, "totalR": 0.0, "usd": 0.0, "maxDD": 0.0}
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    wins = sum(r > 0 for r in rs)
    return {"trades": len(rs), "wins": wins, "winRate": round(100 * wins / len(rs)), "totalR": round(sum(rs), 2),
            "usd": round(sum(rs) * R_USD), "maxDD": round(dd, 2)}


def run(pair: str, days: int) -> dict:
    d = ROOT / "pairs" / pair
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    m5, h1 = load(d / "data" / "M5.csv"), load(d / "data" / "H1.csv")
    smc.configure(cfg, [])
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    res = smc.scan_all(m5, h1, cost, cfg["decimals"])
    t0 = m5[-1].time - days * 86400
    st5 = res["_st5"]
    setups = [s for sid in ("S1", "S2", "S3", "S4") for s in res[sid]["setups"] if s["time"] >= t0]
    for s in setups:
        s["big"] = abs(s["entry"] - s["sl"]) >= cfg["min_stop_cost_ratio"] * cost
        s["managedResult"] = managed(m5, st5, s, cost)
    done = lambda xs: [x for x in xs if "r" in x["result"]]  # noqa: E731
    taken = done([s for s in setups if s["pass"] and s["big"]])
    fails = Counter(q.split(" · ", 1)[0] for s in setups for q, ok, _ in s["checklist"] if not ok)
    rows = [{"time": datetime.fromtimestamp(s["time"], timezone.utc).strftime("%m-%d %H:%M"), "sid": s["sid"],
             "dir": "BUY" if s["dir"] > 0 else "SELL", "rr": round(s["rr"], 2), "state": s["result"]["state"],
             "r": round(s["result"]["r"], 2), "managedR": round(s["managedResult"].get("r", 0), 2)} for s in taken]
    raw = [{"symbol": cfg["symbol"], "direction": "BUY" if s["dir"] > 0 else "SELL", "time": s["time"],
            "validUntil": s["time"] + smc.EXPIRY[smc.STRATEGY_OF[s["sid"]]] * smc.M5S, "r": s["result"]["r"], "sid": s["sid"]} for s in taken]
    return {"raw": raw, "pair": cfg["symbol"], "from": t0, "to": m5[-1].time, "setups": len(setups), "taken": stats([s["result"]["r"] for s in taken]),
            "takenManaged": stats([s["managedResult"]["r"] for s in taken if "r" in s["managedResult"]]),
            "allSetups": stats([s["result"]["r"] for s in done(setups)]), "fails": dict(fails), "trades": rows,
            "bySid": {sid: len([s for s in setups if s["sid"] == sid]) for sid in ("S1", "S2", "S3", "S4")}}


def main(days: int) -> None:
    out = [run(p, days) for p in PAIRS]
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    lines = [f"# The last {days} days with the app's exact rules", "",
             f"VERIFIED from the Yahoo candles ({d(out[0]['from'])} → {d(out[0]['to'])}). Money: 1 % risk per trade on $10,000 (1R = $100), "
             "costs included, not compounded. Research, not advice: a backtest this short proves nothing either way.", "",
             "| Pair | setups found | taken (rules + 7 questions) | wins | result | $ at 1 % of $10k | managed result | every setup (checklist ignored) |",
             "|---|---|---|---|---|---|---|---|"]
    for r in out:
        t, m, a = r["taken"], r["takenManaged"], r["allSetups"]
        lines.append(f"| {r['pair']} | {r['setups']} | {t['trades']} | {t['wins']} | {t['totalR']:+}R | ${t['usd']:+,} | {m['totalR']:+}R | "
                     f"{a['trades']} tr, {a['totalR']:+}R (${a['usd']:+,}) |")
    tot = [x for r in out for x in r["trades"]]
    # the trader-skill risk check across the six teams, in time order (as the notifier sends them)
    kept, blocked = [], []
    for x in sorted((x for r in out for x in r["raw"]), key=lambda x: x["time"]):
        chk = portfolio.check(x["symbol"], x, kept, x["time"])
        (kept if chk["verdict"] == "PASS" else blocked).append({**x, "why": chk["reasons"]})
    ks = stats([x["r"] for x in kept])
    lines += ["", f"**Total taken by the teams: {len(tot)} trades, {sum(x['r'] for x in tot):+.2f}R (${sum(x['r'] for x in tot) * R_USD:+,.0f}).**",
              f"**After the trader-skill risk check across the teams: {ks['trades']} trades sent, {ks['wins']} wins"
              + (f" (win rate {ks['winRate']} %)" if ks["trades"] else "") + f", {ks['totalR']:+}R (${ks['usd']:+,}); {len(blocked)} blocked.**"]
    lines += [f"- blocked: {x['symbol']} {x['sid']} {x['direction']} · {'; '.join(x['why'])}" for x in blocked]
    lines += ["",
              "## Why setups were not taken (all pairs; one setup can fail several questions)", ""]
    fails = Counter()
    for r in out:
        fails.update(r["fails"])
    lines += [f"- {k}: {v}" for k, v in fails.most_common()]
    lines += ["", "## The trades taken", ""]
    for r in out:
        for x in r["trades"]:
            lines.append(f"- {r['pair']} {x['time']} UTC · {x['sid']} {x['dir']} · RR 1:{x['rr']} · {x['state']} {x['r']:+}R (managed {x['managedR']:+}R)")
    if not tot:
        lines.append("- none")
    (ROOT / "LAST60.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    (ROOT / "last60.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
