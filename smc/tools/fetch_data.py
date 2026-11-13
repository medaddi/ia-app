"""
Downloads each pair's real candles from Yahoo Finance (the source the app already uses) into smc/pairs/<PAIR>/data/,
checks them and writes what it found to data/DATA_LOG.md. Nothing is invented: a missing or broken series is reported.

  python smc/tools/fetch_data.py            # every pair
  python smc/tools/fetch_data.py EURUSD     # one pair

Depth Yahoo gives (it decides, not us): D1 ~5 years, H1 ~2 years, M15 / M5 60 days, M1 7 days.
Gold: Yahoo has no spot gold history; GC=F is COMEX gold FUTURES (a few dollars above spot). Structure and percentages
are the same, absolute levels are not spot: flagged in every gold report.
"""

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PAIRS = {"XAUUSD": "GC=F", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "EURCHF": "EURCHF=X", "AUDCAD": "AUDCAD=X", "AUDCHF": "AUDCHF=X"}
SERIES = {"D1": ("1d", "5y", 86400), "H1": ("1h", "730d", 3600), "M15": ("15m", "60d", 900), "M5": ("5m", "60d", 300), "M1": ("1m", "7d", 60)}
UA = {"User-Agent": "Mozilla/5.0 (smc research; candles for a personal backtest)"}


def fetch(ticker: str, interval: str, rng: str) -> list[dict]:
    r = httpx.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}", params={"interval": interval, "range": rng},
                  headers=UA, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for k, t in enumerate(res.get("timestamp") or []):
        o, h, l, c = q["open"][k], q["high"][k], q["low"][k], q["close"][k]
        if None in (o, h, l, c):
            continue  # Yahoo leaves empty slots: dropped and counted
        out.append({"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": q.get("volume", [0] * (k + 1))[k] or 0})
    return out


def check(rows: list[dict], step: int) -> tuple[list[dict], dict]:
    """Documented cleaning: sort by time, one candle per slot (the last one kept), bad OHLC fixed or dropped.
    A gap longer than 3 slots outside the weekend is counted and listed (not filled)."""
    log = {"raw": len(rows), "duplicates": 0, "badOhlc": 0, "fixed": 0, "gaps": []}
    by = {}
    for r in sorted(rows, key=lambda r: r["time"]):
        if step < 86400:
            r["time"] -= r["time"] % step  # snapped to the slot open (UTC)
        if r["time"] in by:
            log["duplicates"] += 1
        by[r["time"]] = r
    out = []
    for r in by.values():
        hi, lo = max(r["open"], r["close"], r["high"]), min(r["open"], r["close"], r["low"])
        if r["high"] < r["low"] or hi <= 0:
            log["badOhlc"] += 1
            continue
        if hi != r["high"] or lo != r["low"]:
            log["fixed"] += 1  # a wick that does not contain the body: widened to the body (documented rule)
            r["high"], r["low"] = hi, lo
        out.append(r)
    for a, b in zip(out, out[1:]):
        gap = b["time"] - a["time"]
        wd = datetime.fromtimestamp(a["time"], timezone.utc).weekday()
        weekend = wd >= 4 and gap <= 3 * 86400  # Friday close → Sunday open
        if step < 86400 and gap > 3 * step and not weekend and gap > 4 * 3600:
            log["gaps"].append((a["time"], gap))
    log["clean"] = len(out)
    return out, log


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


def main(only: list[str]) -> None:
    for pair, ticker in PAIRS.items():
        if only and pair not in only:
            continue
        d = ROOT / "pairs" / pair / "data"
        d.mkdir(parents=True, exist_ok=True)
        lines = [f"# {pair} data log", "", f"Source: Yahoo Finance `{ticker}` · fetched {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · times in UTC (candle open)", ""]
        if pair == "XAUUSD":
            lines += ["**Gold caveat:** GC=F is COMEX gold futures, not spot. Levels sit a few dollars above spot; the rules use "
                      "structure and relative sizes, so they apply, but absolute prices differ from a spot broker.", ""]
        lines += ["| TF | rows | first | last | duplicates | bad OHLC dropped | wicks fixed | gaps > 4 h (not weekend) |", "|---|---|---|---|---|---|---|---|"]
        for tf, (interval, rng, step) in SERIES.items():
            try:
                rows = fetch(ticker, interval, rng)
            except Exception as err:
                lines.append(f"| {tf} | **MISSING** ({err.__class__.__name__}) | | | | | | |")
                continue
            clean, log = check(rows, step)
            with open(d / f"{tf}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["time", "open", "high", "low", "close", "volume"])
                w.writeheader()
                w.writerows(clean)
            lines.append(f"| {tf} | {log['clean']} | {iso(clean[0]['time']) if clean else '—'} | {iso(clean[-1]['time']) if clean else '—'} | "
                         f"{log['duplicates']} | {log['badOhlc']} | {log['fixed']} | {len(log['gaps'])} |")
            time.sleep(1.0)  # polite pace
        (d / "DATA_LOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(pair, "done")


if __name__ == "__main__":
    main([a.upper().replace("/", "") for a in sys.argv[1:]])
