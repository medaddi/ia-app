"""
Each pair's strategies from the guide (backend/app/smc/playbook.py) on stored candles: how many trades, the REAL win rate, the
result in R with costs, on the first 60 % (in-sample) and the last 40 % (out-of-sample), next to the win rate the
playbook claims. Writes smc/PLAYBOOK.md and backend/app/smc/research/playbook.json (the teams show these numbers).

  python -m smc.tools.playbook_test dukascopy

The news rule is the guide's red-folder pause, for every pair: US CPI, NFP, FOMC, BoE, RBA, BoC, SNB (their times from the
stored calendar smc/news/high_impact.csv, ForexFactory, Nov 2025 - Nov 2026) and the EIA crude oil inventories (Wednesdays
10:30 New York): no signal within 15 min of one, and a pending limit is pulled 15 min before one. The AUD/CHF macro gate
reads smc/macro/*.csv (S&P 500, VIX, iron ore daily closes, tools/fetch_macro.py).
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
    return {"trades": len(rs), "wins": w, "winRate": round(100 * w / len(rs)), "totalR": round(sum(rs), 2), "expectancyR": round(sum(rs) / len(rs), 3),
            "grossWinR": round(sum(r for r in rs if r > 0), 3), "grossLossR": round(-sum(r for r in rs if r < 0), 3)}


def load_news() -> dict[str, list[int]]:
    f = ROOT / "news" / "high_impact.csv"
    out: dict[str, list[int]] = {}
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines()[1:]:
        t, cur, _ = line.split(",", 2)
        out.setdefault(cur, []).append(int(t))
    return {k: sorted(set(v)) for k, v in out.items()}


def load_events() -> list[dict]:
    f = ROOT / "news" / "high_impact.csv"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines()[1:]:
        t, cur, name = line.split(",", 2)
        out.append({"time": int(t), "currency": cur, "title": name})
    return out


def load_macro() -> dict | None:
    d = ROOT / "macro"
    try:
        rd = lambda n: [(int(a), float(b)) for a, b in (ln.split(",") for ln in (d / f"{n}.csv").read_text().splitlines()[1:])]  # noqa: E731
        return playbook.macro_view(rd("SPX"), rd("VIX"), rd("IRON"))
    except OSError:
        return None


def load_gold_macro() -> dict | None:
    d = ROOT / "macro"
    try:
        rd = lambda n: [(int(a), float(b)) for a, b in (ln.split(",") for ln in (d / f"{n}.csv").read_text().splitlines()[1:])]  # noqa: E731
        return {"dxy": rd("DXY"), "us10y": rd("US10Y")}
    except OSError:
        return None


def pair_news(news: dict[str, list[int]], pair: str) -> list[int]:
    cur = {"USD"} if pair == "XAUUSD" else {pair[:3], pair[3:]}
    return sorted({t for c in cur for t in news.get(c, [])})


def main(source: str) -> None:
    out = {}
    eur = gbp = None
    NEWS = load_news()
    EVENTS = load_events()
    MACRO = load_macro()
    GOLD_MACRO = load_gold_macro()
    for p in PAIRS:
        base = ROOT / "pairs" / p
        dd = base / "data" / source if source else base / "data"
        cfg = json.loads((base / "config.json").read_text(encoding="utf-8"))
        m5, h1 = load(dd / "M5.csv"), load(dd / "H1.csv")
        if p == "EURUSD":
            eur = m5
        cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
        d1 = playbook.resample(m5, playbook.DAY)
        nw = sorted(playbook.red_folder(EVENTS) + playbook.eia_times(m5[0].time, m5[-1].time)) if EVENTS else []
        shock = sorted({e["time"] for e in EVENTS if e["currency"] in ("EUR", "CHF") and any(w in e["title"] for w in ("Refinancing", "ECB", "SNB", "Monetary Policy Statement"))})
        mac = GOLD_MACRO if p == "XAUUSD" else MACRO
        if p == "EURUSD" and gbp is None:  # EUR/USD's SMT needs GBP/USD
            gbp = load((ROOT / "pairs" / "GBPUSD" / "data" / source if source else ROOT / "pairs" / "GBPUSD" / "data") / "M5.csv")
        if p == "AUDCHF":  # the AUD/CHF Devil's cross check: AUD/CAD and EUR/CHF
            twin = lambda q: load((ROOT / "pairs" / q / "data" / source if source else ROOT / "pairs" / q / "data") / "M5.csv")  # noqa: E731
            em5 = (twin("AUDCAD"), twin("EURCHF"))
        else:
            em5 = eur if p == "GBPUSD" else gbp if p == "EURUSD" else None
        setups, _ = playbook.scan(p, m5, h1, cfg["pip"], cost, nw if EVENTS else None, em5, d1, mac, shock, EVENTS if EVENTS else None, None, cfg["spread_pips"])
        plain, _ = playbook.scan(p, m5, h1, cfg["pip"], cost, None, em5, d1, mac, shock, None, None, cfg["spread_pips"])  # the same without the news rule
        split = m5[0].time + int((m5[-1].time - m5[0].time) * 0.6)
        out[p] = {"source": source or "yahoo", "from": m5[0].time, "split": split, "to": m5[-1].time, "strategies": {},
                  "news": {"events": len(nw), "file": "smc/news/high_impact.csv" if NEWS else None}, "macro": bool(MACRO)}

        def ok_but_off(x):  # measured as if switched on: the OFF mark is the only failing line
            return x["pass"] or (all(o for q, o, _ in x["checklist"] if not q.startswith("0 ·")) and (p, x["sid"]) in playbook.DISABLED)

        def kept(ss):
            return [s for s in ss if ok_but_off(s) and "r" in s["result"] and abs(s["entry"] - s["sl"]) >= cfg["min_stop_cost_ratio"] * cost]

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
                                         "off": (p, sid) in playbook.DISABLED,
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
             "News: the guide's red-folder pause for every pair (US CPI, NFP, FOMC, BoE, RBA, BoC, SNB from the stored ForexFactory "
             "calendar + the EIA Wednesdays): no signal within 15 min of one, a pending limit pulled 15 min before one. "
             "Targets cut when ADR5 / ADR20 < 0.70. AUD/CHF: the S&P 500 / VIX / iron ore gate and its risk-off exit.", "",
             "| pair | strategy | the guide says | trades | win rate | result | first 60 % | last 40 % | without the news rule | kept trades open through a release |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    n = w = 0
    tot = 0.0
    for p, x in out.items():
        for sid, y in x["strategies"].items():
            a = y["all"]
            n, w, tot = n + a["trades"], w + a["wins"], tot + a["totalR"]
            lines.append(f"| {p} | {sid} {y['name']}{' · **OFF**' if y.get('off') else ''} | {y['claimed']} | {a['trades']} | {str(a['winRate']) + ' %' if a['trades'] else '—'} | "
                         f"{a['totalR']:+}R | {f(y['in'])} | {f(y['out'])} | {f(y['withoutNewsRule'])} | {y['openThroughNews']} |")
    on = [y["all"] for x in out.values() for y in x["strategies"].values() if not y.get("off")]
    n_on, w_on, r_on = sum(a["trades"] for a in on), sum(a["wins"] for a in on), sum(a["totalR"] for a in on)
    lines += ["", f"Every strategy, each measured as if switched on: {n} trades, win rate {round(100 * w / n) if n else 0} %, {tot:+.2f}R.",
              f"Switched on only: {n_on} trades, win rate {round(100 * w_on / n_on) if n_on else 0} %, {r_on:+.2f}R "
              "(chosen on this same year: an optimistic number, not a forecast).", "",
              "Not applied here: the correlation cap (each pair alone). "
              "Under 30 trades a win rate can still be luck."]
    (ROOT / "PLAYBOOK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT.parent / "backend" / "app" / "smc" / "research" / "playbook.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
