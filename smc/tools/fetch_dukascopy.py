"""
Two years of each pair's real M1 candles from Dukascopy (Swiss bank, free historical feed), built into M5 and H1, into
smc/pairs/<PAIR>/data/dukascopy/. Yahoo stays the live source; this is the research source (Yahoo gives only 60 days of M5).

  python -m smc.tools.fetch_dukascopy 365        # every pair, one year (the default is 730 days)
  python -m smc.tools.fetch_dukascopy EURUSD 365

Feed: https://datafeed.dukascopy.com/datafeed/<SYM>/<YYYY>/<MM 0-11>/<DD>/BID_candles_min_1.bi5, one LZMA file per UTC
day of 24-byte records (seconds from 00:00, open, close, low, high as integer points, volume float). BID prices.
Minutes with no tick (volume 0 and a flat candle) are dropped, not filled. Gold here is SPOT XAU/USD (Yahoo has futures).
Each day is cached in data/dukascopy/raw/ (not in git), so a re-run only fetches the missing days. Polite pace, no retries
in a loop: a refused day is listed in the log.
"""

import csv
import lzma
import struct
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from smc.tools.fetch_data import check, iso

ROOT = Path(__file__).resolve().parents[1]
# every instrument of the app (smc/pairs/<PAIR>/config.json): price = points / div (gold and JPY pairs 3 decimals, others 5)
PAIRS = {p.name: (1e3 if p.name == "XAUUSD" or p.name.endswith("JPY") else 1e5) for p in sorted((ROOT / "pairs").iterdir()) if (p / "config.json").exists()}
URL = "https://datafeed.dukascopy.com/datafeed/{s}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"
UA = {"User-Agent": "smc-research (personal backtest; one request at a time)"}


def day_file(client: httpx.Client, pair: str, day: date, raw: Path) -> bytes | None:
    f = raw / f"{day.isoformat()}.bi5"
    if f.exists():
        blob = f.read_bytes()
        try:
            if blob:
                lzma.decompress(blob)
            return blob
        except lzma.LZMAError:
            f.unlink()  # a file cut by a stopped run: fetched again
    for wait in (0, 5, 30):  # three tries at most, then the day is reported missing
        time.sleep(wait or 0.25)
        try:
            r = client.get(URL.format(s=pair, y=day.year, m=day.month - 1, d=day.day))
        except httpx.HTTPError:
            continue
        if r.status_code == 404:
            f.write_bytes(b"")
            return b""
        if r.status_code == 200:
            f.write_bytes(r.content)
            return r.content
        if r.status_code in (429, 503):
            time.sleep(60)
    return None


def minutes(blob: bytes, day: date, div: float) -> list[dict]:
    if not blob:
        return []
    raw = lzma.decompress(blob)
    t0 = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    out = []
    for k in range(len(raw) // 24):
        s, o, c, lo, hi, v = struct.unpack(">5if", raw[k * 24:k * 24 + 24])
        if v <= 0 and o == c == lo == hi:
            continue  # no tick in that minute
        out.append({"time": t0 + s, "open": o / div, "high": hi / div, "low": lo / div, "close": c / div, "volume": round(v, 4)})
    return out


def build(m1: list[dict], step: int) -> list[dict]:
    by: dict[int, dict] = {}
    for r in m1:
        t = r["time"] - r["time"] % step
        b = by.get(t)
        if b is None:
            by[t] = {**r, "time": t}
        else:
            b["high"], b["low"], b["close"], b["volume"] = max(b["high"], r["high"]), min(b["low"], r["low"]), r["close"], b["volume"] + r["volume"]
    return [by[t] for t in sorted(by)]


def main(only: list[str], days: int, end: date | None = None) -> None:
    end = end or datetime.now(timezone.utc).date() - timedelta(days=1)
    with httpx.Client(headers=UA, timeout=40) as client:
        for pair, div in PAIRS.items():
            if only and pair not in only:
                continue
            d = ROOT / "pairs" / pair / "data" / "dukascopy"
            raw = d / "raw"
            raw.mkdir(parents=True, exist_ok=True)
            m1, missing = [], []
            for k in range(days, -1, -1):
                day = end - timedelta(days=k)
                if day.weekday() == 5:
                    continue  # Saturday: market closed
                blob = day_file(client, pair, day, raw)
                if blob is None:
                    missing.append(day.isoformat())
                    continue
                m1 += minutes(blob, day, div)
            lines = [f"# {pair} · Dukascopy data log", "",
                     f"Source: Dukascopy BID M1 `{pair}` · built {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · times in UTC (candle open)",
                     f"Days asked: {days} · days refused / unreachable: {len(missing)}" + (f" ({', '.join(missing[:20])}{' …' if len(missing) > 20 else ''})" if missing else ""), "",
                     "| TF | rows | first | last | duplicates | bad OHLC dropped | wicks fixed | gaps > 4 h (not weekend) |", "|---|---|---|---|---|---|---|---|"]
            for tf, step in (("M5", 300), ("H1", 3600)):
                clean, log = check(build(m1, step), step)
                with open(d / f"{tf}.csv", "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["time", "open", "high", "low", "close", "volume"])
                    w.writeheader()
                    w.writerows(clean)
                lines.append(f"| {tf} | {log['clean']} | {iso(clean[0]['time']) if clean else '—'} | {iso(clean[-1]['time']) if clean else '—'} | "
                             f"{log['duplicates']} | {log['badOhlc']} | {log['fixed']} | {len(log['gaps'])} |")
            (d / "DATA_LOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(pair, "done", len(m1), "minutes,", len(missing), "days missing", flush=True)


if __name__ == "__main__":
    args = [a.upper().replace("/", "") for a in sys.argv[1:] if not a.isdigit()]
    dates = [a for a in sys.argv[1:] if a.count("-") == 2]
    args = [a for a in args if a.count("-") != 2]
    n = next((int(a) for a in sys.argv[1:] if a.isdigit()), 730)
    main(args, n, date.fromisoformat(dates[0]) if dates else None)  # an end date (YYYY-MM-DD) keeps every pair on one window
