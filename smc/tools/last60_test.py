"""
FXAlexG (the md of 2026-11-19, as written: alexg.VARIANT at the md's values) on the LAST 60 DAYS, the way the live app
runs it: the trigger on H1, then M30, then M15 (M30 / M15 built from M5), every trade followed on M5 (the feed keeps
5-minute candles for 60 days). W1 / D1 / H4 context from the feed's D1 (5 years) and H1 (2 years). News: the stored
calendar smc/news/high_impact.csv. Spread + slippage included; one trade per pair at a time.

  python smc/tools/last60_test.py <cache dir>      writes smc/LAST60_ALEXG.md and smc/last60_alexg.json
"""

import asyncio
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.smc import alexg, playbook  # noqa: E402
from smc.tools.playbook_test import agg, load_events, pf  # noqa: E402


async def fetch(cache: Path) -> dict:
    p = cache / "candles60.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    from app.market.data import fetch_candle_series
    data = {}
    for key in playbook.ALEXG_PAIRS:
        sym = alexg.config(key)["symbol"]
        m5s, h1s, ds = await asyncio.gather(fetch_candle_series(sym, "5M", 20000), fetch_candle_series(sym, "1H", 13000),
                                            fetch_candle_series(sym, "1D", 1600))
        row = lambda c: (c.time, c.open, c.high, c.low, c.close)  # noqa: E731
        data[key] = ([row(c) for c in m5s["candles"][:-1]], [row(c) for c in h1s["candles"][:-1]], [row(c) for c in ds["candles"][:-1]],
                     m5s.get("source"))
        print(key, len(data[key][0]), "M5", flush=True)
    p.write_bytes(pickle.dumps(data))
    return data


def main(cache: Path) -> None:
    data = asyncio.run(fetch(cache))
    events = load_events()
    out, allr, alltrades = {}, [], []
    for key, (m5r, h1r, d1r, src) in data.items():
        cfg = alexg.config(key)
        m5, h1, d1 = ([playbook._Bar(*x) for x in rows] for rows in (m5r, h1r, d1r))
        cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
        setups, _ = alexg.scan(key, m5, h1, cost, events, d1)
        kept = [s for s in setups if s["pass"]]
        closed = [s for s in kept if "r" in s["result"]]
        rs = [s["result"]["r"] for s in closed]
        out[key] = {"from": m5[0].time, "to": m5[-1].time, "triggers": len(setups), "passed": len(kept),
                    "open": len(kept) - len(closed), "all": agg(rs), "pf": pf(agg(rs)),
                    "byTf": {tf: agg([s["result"]["r"] for s in closed if s["etf"] == tf]) for tf in alexg.ENTRY_TFS},
                    "trades": [{"time": s["time"], "dir": s["dir"], "etf": s["etf"], "setup": s["setupType"], "grade": s["grade"], "score": s["score"],
                                "market": s["market"], "rr": round(s["rr"], 2), "state": s["result"]["state"], "r": round(s["result"].get("r", 0.0), 2)}
                               for s in kept]}
        allr += rs
        alltrades += [(key, x) for x in out[key]["trades"]]
        a = out[key]["all"]
        print(key, "triggers", len(setups), "passed", len(kept), "closed", a["trades"], "win", a["winRate"], "R", a["totalR"], flush=True)
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    first = next(iter(out.values()))
    t = agg(allr)
    tf = {k: agg([x["r"] for _, x in alltrades if x["etf"] == k and x["state"] not in ("PENDING", "ACTIVE")]) for k in alexg.ENTRY_TFS}
    lines = ["# FXAlexG Set & Forget, the last 60 days", "",
             f"VERIFIED from the app's feed (Yahoo Finance; gold COMEX GC=F adjusted to spot), {d(first['from'])} → {d(first['to'])}, 29 pairs. "
             "The md as written: the trigger on H1, M30, M15; every trade followed on M5; at +1.5R the stop to the entry and 25 % banked; "
             "spread + slippage included. News: the stored calendar (smc/news/high_impact.csv).", "",
             "| pair | triggers | passed | still open | closed | win | result | PF |", "|---|---|---|---|---|---|---|---|"]
    for k, x in out.items():
        a = x["all"]
        lines.append(f"| {k} | {x['triggers']} | {x['passed']} | {x['open']} | {a['trades']} | {str(a['winRate']) + ' %' if a['trades'] else '—'} | "
                     f"{a['totalR']:+}R | {x['pf'] if x['pf'] is not None else '—'} |")
    lines += ["", f"**All pairs, closed trades: {t['trades']} · win {t['winRate']} % · {t['totalR']:+}R · PF {pf(t)} · "
              f"expectancy {t['expectancyR']} R per trade.**", "",
              "By entry timeframe: " + " · ".join(f"{k} {v['trades']} trades, {v['totalR']:+}R" for k, v in tf.items()), "",
              "60 days is a short sample: under 30 trades a win rate is mostly luck."]
    (ROOT / "smc" / "LAST60_ALEXG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "smc" / "last60_alexg.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
