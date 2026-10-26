"""
Shared types for the LiquidityDissection strategies (XAUUSD and EURUSD).
Times are unix seconds (UTC). A candle's `time` is its OPEN time.
Field names are camelCase on purpose: these objects are serialized straight to the frontend.
"""

from dataclasses import dataclass

from .jsnum import round_to


@dataclass(slots=True)
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0

    def to_dict(self):
        return {"time": self.time, "open": self.open, "high": self.high, "low": self.low, "close": self.close, "volume": self.volume}


TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


def closed_only(candles: list[Candle], tf_sec: int, now_sec: float) -> list[Candle]:
    """Keeps only candles that had fully closed at `now_sec` (no look-ahead)."""
    end = len(candles)
    while end > 0 and candles[end - 1].time + tf_sec > now_sec:
        end -= 1
    return candles if end == len(candles) else candles[:end]


def candles_from_rows(rows) -> list[Candle]:
    """[[time, o, h, l, c, v], ...] or [{time, open, ...}, ...] → candles."""
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(Candle(int(r["time"]), r["open"], r["high"], r["low"], r["close"], r.get("volume") or 0))
        else:
            out.append(Candle(int(r[0]), r[1], r[2], r[3], r[4], r[5] if len(r) > 5 else 0))
    return out


__all__ = ["Candle", "TF_SEC", "closed_only", "candles_from_rows", "round_to"]
