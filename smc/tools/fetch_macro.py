"""
The AUD/CHF macro gate's daily data (the guide's "3-pillar gate"): S&P 500 (^GSPC), VIX (^VIX) and iron ore 62 % Fe CFR
China futures (TIO=F), two years of daily closes from Yahoo Finance into smc/macro/<NAME>.csv (time, close).
VERIFIED from Yahoo; a missing series is reported, never filled.

  python -m smc.tools.fetch_macro
"""

import csv
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SERIES = {"SPX": "^GSPC", "VIX": "^VIX", "IRON": "TIO=F", "DXY": "DX-Y.NYB", "US10Y": "^TNX"}  # DXY / US10Y: the gold Devil's check
UA = {"User-Agent": "Mozilla/5.0 (smc research; daily closes for a personal backtest)"}


def fetch(ticker: str) -> list[tuple[int, float]]:
    r = httpx.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}", params={"interval": "1d", "range": "2y"}, headers=UA, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    return [(int(t) - int(t) % 86400, c) for t, c in zip(res["timestamp"], closes) if c is not None]


def main() -> None:
    d = ROOT / "macro"
    d.mkdir(exist_ok=True)
    for name, ticker in SERIES.items():
        rows = fetch(ticker)
        with open(d / f"{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time", "close"])
            w.writerows(rows)
        print(name, ticker, len(rows), "days")
        time.sleep(1.0)


if __name__ == "__main__":
    main()
