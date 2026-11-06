"""Candles from the pair's CSV files (smc/pairs/<PAIR>/data/<TF>.csv, written and checked by tools/fetch_data.py). UTC."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Candle:
    time: int  # unix seconds, the candle's OPEN, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def load(path: Path) -> list[Candle]:
    if not path.exists():
        raise FileNotFoundError(f"missing data file: {path}")
    with open(path, newline="") as f:
        return [Candle(int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r.get("volume") or 0))
                for r in csv.DictReader(f)]


def until(c: list[Candle], t_close: int, step: int) -> list[Candle]:
    """Only the candles CLOSED at time t_close: what a trader had then."""
    return [x for x in c if x.time + step <= t_close]
