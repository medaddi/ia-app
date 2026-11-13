"""
Is each pair's data fit for an SMC test? SMC reads wicks, gaps and sweeps, so a feed whose candles are sampled quotes
(not real OHLC) makes fake FVGs and fake sweeps. Writes smc/DATA_QUALITY.md and smc/pairs/<PAIR>/quality.json.

  python -m smc.tools.data_quality

Checks per timeframe (VERIFIED: computed from the CSV files)
  flat       share of candles with high == low (a candle with no price movement at all)
  jumps      share of candles opening more than half the previous candle's range away from its close (real M5 forex
             opens at the previous close almost always; jumps make 3-candle gaps out of nothing)
  median     median candle range in pips
  verdict    NOT FIT when flat >= 2 % or jumps >= 5 % (VERIFIED defects of the candles themselves)
             SUSPECT when a cross's median range is above EUR/USD's on the same timeframe (HYPOTHESIS: EUR/CHF and AUD/CHF
             usually move less than EUR/USD; a bigger range may mean a feed built from two legs. To confirm with a
             second source.)  FIT otherwise.
"""

import json
from pathlib import Path

from smc.engine.candles import load

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]
CROSSES = {"EURCHF", "AUDCAD", "AUDCHF"}


def measure(c, pip):
    n = len(c)
    if n < 2:
        return None
    flat = sum(x.high == x.low for x in c) / n
    jumps = sum(abs(b.open - a.close) > 0.5 * (a.high - a.low + 1e-12) for a, b in zip(c, c[1:])) / n
    med = sorted(x.high - x.low for x in c)[n // 2] / pip
    return {"rows": n, "flat": round(flat, 4), "jumps": round(jumps, 4), "medianRangePips": round(med, 1)}


def main() -> None:
    res = {}
    for p in PAIRS:
        cfg = json.loads((ROOT / "pairs" / p / "config.json").read_text(encoding="utf-8"))
        res[p] = {tf: measure(load(ROOT / "pairs" / p / "data" / f"{tf}.csv"), cfg["pip"]) for tf in ("H1", "M15", "M5")}
    lines = ["# Data quality", "", "VERIFIED from the CSV files (Yahoo Finance). NOT FIT: flat >= 2 % or opening jumps >= 5 % (defects of the candles). "
             "SUSPECT (HYPOTHESIS): a cross whose median range is above EUR/USD's on the same timeframe. FIT otherwise.", "",
             "| pair | TF | rows | flat | jumps | median range (pips) | verdict |", "|---|---|---|---|---|---|---|"]
    for p in PAIRS:
        for tf, m in res[p].items():
            ref = res["EURUSD"][tf]["medianRangePips"]
            bad = [x for x, on in (("flat candles", m["flat"] >= 0.02), ("opening jumps", m["jumps"] >= 0.05)) if on]
            suspect = p in CROSSES and m["medianRangePips"] > ref
            m["verdict"] = "NOT FIT" if bad else "SUSPECT" if suspect else "FIT"
            m["why"] = bad + ([f"range above EUR/USD ({ref})"] if suspect else [])
            lines.append(f"| {p} | {tf} | {m['rows']} | {m['flat']:.1%} | {m['jumps']:.1%} | {m['medianRangePips']} | "
                         f"{m['verdict']}{': ' + ', '.join(m['why']) if m['why'] else ''} |")
        (ROOT / "pairs" / p / "quality.json").write_text(json.dumps(res[p], indent=2), encoding="utf-8")
    lines += ["", "Gold (GC=F) is COMEX futures, not spot: its candles are clean, its levels are not spot prices."]
    (ROOT / "DATA_QUALITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
