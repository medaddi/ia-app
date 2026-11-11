"""
FXAlexG Set & Forget on ALL 29 pairs from the app's own live source (Yahoo Finance): M5 for the last 60 days (Yahoo's
limit, so M15 / M30 entries and the trade follow-up cover those 60 days), H1 for 2 years, D1 for 5 years (W1 resampled:
the AOIs see their full 156 weeks). Gold is COMEX GC=F futures here (Yahoo has no spot history).

  PYTHONPATH=. backend/.venv/Scripts/python smc/tools/yahoo_test.py

The same rules as smc/tools/playbook_test.py: a trade counts only when the execution gate passed, one trade per pair at a
time, no entry within 30 min of a high-impact release (smc/news/high_impact.csv), 25 % banked at +1.5 R with the stop to
the entry, spread + slippage included. Writes smc/YAHOO_TEST.md. Nothing is cached to disk.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = str(Path(__file__).resolve().parents[2] / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.market import data  # noqa: E402
from app.market.pairs import decimals_of  # noqa: E402
from app.smc import alexg, playbook  # noqa: E402
from smc.tools.playbook_test import agg, exits, load_events, pf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


async def candles(sym: str, ticker: str):
    dec = decimals_of(sym)
    m5 = await data._yahoo_candles(ticker, "5m", "60d", dec, True)
    h1 = await data._yahoo_candles(ticker, "1h", "2y", dec, True)
    d1 = await data._yahoo_candles(ticker, "1d", "5y", dec, True)
    now = datetime.now(timezone.utc).timestamp()
    h1 = data.aggregate(h1, 3600)  # Yahoo can stamp the forming bar off its slot
    # closed candles only, each on its UTC slot (Yahoo daily FX bars open at 23:00 UTC the day before: moved to 00:00)
    d1 = [type(x)(x.time + (86400 - x.time % 86400) % 86400 if x.time % 86400 >= 12 * 3600 else x.time - x.time % 86400, x.open, x.high, x.low, x.close, x.volume)
          for x in d1]
    m5 = [x for x in m5 if x.time + 300 <= now]
    h1 = [x for x in h1 if x.time + 3600 <= now]
    d1 = [x for x in d1 if x.time + 86400 <= now]
    return m5, h1, d1


async def main() -> None:
    events = load_events()
    out, total = {}, []
    for key in playbook.ALEXG_PAIRS:
        cfg = json.loads((ROOT / "pairs" / key / "config.json").read_text(encoding="utf-8"))
        sym = cfg["symbol"]
        try:
            m5, h1, d1 = await candles(sym, cfg["yahoo"])
        except Exception as err:
            print(key, "no data:", repr(err), flush=True)
            continue
        if len(m5) < 1000 or len(h1) < 500 or len(d1) < 300:
            print(key, "too little data", len(m5), len(h1), len(d1), flush=True)
            continue
        cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
        setups, _ = alexg.scan(key, m5, h1, cost, events or None, d1)
        kept = [s for s in setups if s["pass"] and "r" in s["result"]]
        open_ = [s for s in setups if s["pass"] and "r" not in s["result"]]
        rs = [s["result"]["r"] for s in kept]
        grades: dict[str, int] = {}
        for s in setups:
            grades[s["grade"]] = grades.get(s["grade"], 0) + 1
        a = agg(rs)
        out[key] = {"from": m5[0].time, "to": m5[-1].time, "triggers": len(setups), "grades": grades, "all": a, "pf": pf(a), "exits": exits(kept),
                    "open": len(open_), "trades": [{"time": s["time"], "dir": s["dir"], "grade": s["grade"], "score": s["gpa"], "etf": s["etf"],
                                                    "r": round(s["result"]["r"], 2)} for s in kept]}
        total += rs
        print(key, "triggers", len(setups), "| passed", a["trades"], "win", a["winRate"], "R", a["totalR"], "PF", pf(a), "| still open", len(open_), flush=True)
    d = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    first = next(iter(out.values()))
    lines = ["# FXAlexG Set & Forget on the 29 pairs (Yahoo, last 60 days)", "",
             f"VERIFIED from Yahoo Finance candles, M5 {d(first['from'])} → {d(first['to'])} (60 days; H1 2 years, D1 5 years for the structure "
             "and the AOIs). Gold is COMEX GC=F futures. Rules as the live app: the execution gate, one trade per pair, no entry 30 min around "
             "high-impact news, 25 % banked at +1.5 R and the stop to the entry, spread + slippage included. A win is a result above +0.05 R "
             "(a break-even close after +1.5 R counts: the exits column shows them apart).", "",
             "| pair | two-step triggers | passed the gate | still open | win rate | result | PF | exits (TP / BE after +1.5R / SL) |",
             "|---|---|---|---|---|---|---|---|"]
    for k, x in out.items():
        a, e = x["all"], x["exits"]
        lines.append(f"| {k} | {x['triggers']} | {a['trades']} | {x['open']} | {str(a['winRate']) + ' %' if a['trades'] else '—'} | {a['totalR']:+}R | "
                     f"{x['pf'] if x['pf'] is not None else '—'} | {e['tp']} / {e['be_after_1_5R']} / {e['sl']} |")
    t = agg(total)
    lines += ["", f"All {len(out)} pairs: {t['trades']} trades, win rate {t['winRate']} %, {t['totalR']:+}R, PF {pf(t) if pf(t) is not None else '—'}, "
              f"expectancy {t['expectancyR']} R per trade." if t["trades"] else f"All {len(out)} pairs: no trade passed the gate.", "",
              "60 days is a short sample: a result here can be luck either way. The portfolio cap is not applied (each pair alone)."]
    (ROOT / "YAHOO_TEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
