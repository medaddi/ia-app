"""
Swings and market structure.
- Swing: fractal with N candles on each side, strictly higher/lower. Confirmed only once the
  N right-side candles have closed (confirmedIndex = index + N).
- BOS: candle CLOSE beyond the last confirmed swing in the trend direction.
- CHoCH / MSS: first candle CLOSE beyond the last confirmed swing against the current trend.
"""

from dataclasses import asdict, dataclass
from typing import Optional

from .indicators import body
from .types import Candle


@dataclass(slots=True)
class Swing:
    index: int
    time: int
    price: float
    kind: str  # "HIGH" | "LOW"
    confirmedIndex: int
    label: Optional[str] = None  # HH | LH | HL | LL
    takenIndex: Optional[int] = None  # first candle that traded beyond the swing

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class StructureEvent:
    type: str  # "BOS" | "CHOCH"
    direction: str  # "BULLISH" | "BEARISH"
    level: float
    pivotIndex: int
    pivotTime: int
    breakIndex: int
    breakTime: int
    legStartIndex: int  # extreme of the leg that produced the break
    displacementIndex: Optional[int]  # strongest candle of the leg if body > mult × avg body
    displacementMult: float  # strongest body / avg body in the leg

    def to_dict(self):
        return asdict(self)


def detect_swings(c: list[Candle], n: int) -> list[Swing]:
    swings: list[Swing] = []
    for i in range(n, len(c) - n):
        hi, lo = c[i].high, c[i].low
        is_high = is_low = True
        for k in range(1, n + 1):
            if c[i - k].high >= hi or c[i + k].high >= hi:
                is_high = False
            if c[i - k].low <= lo or c[i + k].low <= lo:
                is_low = False
            if not is_high and not is_low:
                break
        if is_high:
            swings.append(Swing(i, c[i].time, hi, "HIGH", i + n))
        if is_low:
            swings.append(Swing(i, c[i].time, lo, "LOW", i + n))
    prev_high = prev_low = None
    size = len(c)
    for s in swings:
        if s.kind == "HIGH":
            if prev_high:
                s.label = "HH" if s.price > prev_high.price else "LH"
            prev_high = s
            for j in range(s.index + 1, size):
                if c[j].high > s.price:
                    s.takenIndex = j
                    break
        else:
            if prev_low:
                s.label = "HL" if s.price > prev_low.price else "LL"
            prev_low = s
            for j in range(s.index + 1, size):
                if c[j].low < s.price:
                    s.takenIndex = j
                    break
    return swings


def detect_structure(c: list[Candle], swings: list[Swing], avg_body: list[float], displacement_mult: float):
    """Returns (events, trend)."""
    events: list[StructureEvent] = []
    trend = "NEUTRAL"
    active_high: Optional[Swing] = None
    active_low: Optional[Swing] = None
    by_confirm: dict[int, list[Swing]] = {}
    for s in swings:
        by_confirm.setdefault(s.confirmedIndex, []).append(s)

    for j in range(len(c)):
        for s in by_confirm.get(j, ()):
            if s.kind == "HIGH":
                active_high = s
            else:
                active_low = s
        bull_break = active_high is not None and c[j].close > active_high.price
        bear_break = active_low is not None and c[j].close < active_low.price
        if not bull_break and not bear_break:
            continue
        direction = "BULLISH" if bull_break else "BEARISH"
        pivot = active_high if bull_break else active_low

        # The leg starts at the opposite extreme between the pivot and the break
        leg_start = pivot.index
        for i in range(pivot.index, j + 1):
            if (c[i].low < c[leg_start].low) if direction == "BULLISH" else (c[i].high > c[leg_start].high):
                leg_start = i
        best_idx = None
        best_mult = 0.0
        for i in range(leg_start, j + 1):
            dir_ok = c[i].close > c[i].open if direction == "BULLISH" else c[i].close < c[i].open
            ab = avg_body[i]
            if not dir_ok or not (ab > 0):
                continue
            m = body(c[i]) / ab
            if m > best_mult:
                best_mult = m
                best_idx = i

        events.append(StructureEvent(
            type="CHOCH" if trend != "NEUTRAL" and trend != direction else "BOS",
            direction=direction,
            level=pivot.price,
            pivotIndex=pivot.index,
            pivotTime=pivot.time,
            breakIndex=j,
            breakTime=c[j].time,
            legStartIndex=leg_start,
            displacementIndex=best_idx if best_mult > displacement_mult else None,
            displacementMult=best_mult,
        ))
        trend = direction
        if bull_break:
            active_high = None
        else:
            active_low = None
    return events, trend


def structure_from_labels(swings: list[Swing]) -> str:
    """Latest swing high and swing low labels describe the structure (HH/HL = bullish, LH/LL = bearish)."""
    last_high = next((s for s in reversed(swings) if s.kind == "HIGH" and s.label), None)
    last_low = next((s for s in reversed(swings) if s.kind == "LOW" and s.label), None)
    if last_high and last_high.label == "HH" and last_low and last_low.label == "HL":
        return "BULLISH"
    if last_high and last_high.label == "LH" and last_low and last_low.label == "LL":
        return "BEARISH"
    return "NEUTRAL"
