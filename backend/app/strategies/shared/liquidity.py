"""
Liquidity levels and sweeps.
Levels: PDH/PDL, PWH/PWL, Asian high/low, previous session high/low, equal highs/lows
(within tol × ATR) and round numbers. A level only exists from `availableFrom` (e.g. the
Asian high exists once the Asian session has closed).
Sweep: a candle wicks beyond the level and CLOSES back inside, on the first candle that takes it.
"""

import math
from dataclasses import dataclass

from .jsnum import js_str
from .sessions import trading_day_key, trading_week_key
from .structure import Swing
from .types import Candle


@dataclass(slots=True)
class Level:
    id: str
    kind: str  # PDH PDL PWH PWL ASIA_H ASIA_L PSH PSL EQH EQL ROUND SWING_H SWING_L
    label: str
    price: float
    side: str  # HIGH = buy-side liquidity above, LOW = sell-side below
    time: int  # when it formed (for drawing)
    availableFrom: int  # first time a candle may sweep it
    weight: float  # importance for scoring (0-1)

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "label": self.label, "price": self.price, "side": self.side,
                "time": self.time, "availableFrom": self.availableFrom, "weight": self.weight}


@dataclass(slots=True)
class Sweep:
    id: str
    level: Level
    index: int
    time: int
    extreme: float  # wick extreme
    depthAtr: float

    def to_dict(self):
        return {"id": self.id, "level": self.level.to_dict(), "index": self.index, "time": self.time,
                "extreme": self.extreme, "depthAtr": self.depthAtr}


def daily_weekly_levels(c: list[Candle]) -> list[Level]:
    """PDH/PDL and PWH/PWL from intraday candles, using the 17:00 New York rollover."""
    if not c:
        return []
    last_key = trading_day_key(c[-1].time)
    last_week = trading_week_key(c[-1].time)
    days: dict[str, list] = {}
    weeks: dict[str, list] = {}
    for x in c:
        for m, key in ((days, trading_day_key(x.time)), (weeks, trading_week_key(x.time))):
            r = m.get(key)
            if r is None:
                m[key] = [x.high, x.low, x.time, x.time]
            else:
                if x.high > r[0]:
                    r[0] = x.high
                if x.low < r[1]:
                    r[1] = x.low
                r[3] = x.time
    out: list[Level] = []
    prev_days = [k for k in days if k < last_key]
    if prev_days:
        k = prev_days[-1]
        h, lo, start, end = days[k]
        out.append(Level(f"PDH-{k}", "PDH", "PDH", h, "HIGH", start, end, 0.9))
        out.append(Level(f"PDL-{k}", "PDL", "PDL", lo, "LOW", start, end, 0.9))
    prev_weeks = [k for k in weeks if k < last_week]
    if prev_weeks:
        k = prev_weeks[-1]
        h, lo, start, end = weeks[k]
        out.append(Level(f"PWH-{k}", "PWH", "PWH", h, "HIGH", start, end, 1))
        out.append(Level(f"PWL-{k}", "PWL", "PWL", lo, "LOW", start, end, 1))
    return out


def equal_levels(swings: list[Swing], atr: float, tol: float, upto_index: int) -> list[Level]:
    """Equal highs / lows: two or more untaken swings within tol × ATR of each other."""
    out: list[Level] = []
    for kind in ("HIGH", "LOW"):
        live = [s for s in swings if s.kind == kind and s.confirmedIndex <= upto_index and (s.takenIndex is None or s.takenIndex > upto_index)]
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                if abs(live[i].price - live[j].price) > tol * atr:
                    continue
                price = max(live[i].price, live[j].price) if kind == "HIGH" else min(live[i].price, live[j].price)
                name = "EQH" if kind == "HIGH" else "EQL"
                out.append(Level(f"{name}-{live[i].time}-{live[j].time}", name, "$$$", price, kind, live[i].time, live[j].time, 0.8))
    return out


def round_number_levels(price: float, steps: list[float], count: int, since_time: int) -> list[Level]:
    """Round-number levels ($10 / $50 for gold) around the current price."""
    out: list[Level] = []
    for step in steps:
        base = math.floor(price / step) * step
        for k in range(-count, count + 2):
            p = base + k * step
            out.append(Level(f"ROUND-{js_str(step)}-{js_str(p)}", "ROUND", js_str(p), p, "HIGH" if p >= price else "LOW",
                             since_time, since_time, 0.6 if step >= 50 else 0.4))
    # Keep the biggest step when two steps share a price (first occurrence wins, as in JS)
    seen: set[float] = set()
    kept = []
    for lv in out:
        if lv.price in seen:
            continue
        seen.add(lv.price)
        kept.append(lv)
    return kept


def find_sweeps(c: list[Candle], levels: list[Level], frm: int, to: int, atr: float) -> list[Sweep]:
    """
    Sweeps of `levels` by candles in [frm, to]. The candle that first trades beyond the level
    after it became available is the take; it is a sweep only if that candle closes back inside.
    """
    out: list[Sweep] = []
    n = min(to + 1, len(c))
    for lv in levels:
        high_side = lv.side == "HIGH"
        price = lv.price
        for i in range(n):
            x = c[i]
            if x.time <= lv.availableFrom:
                continue
            if not (x.high > price if high_side else x.low < price):
                continue
            closed_back = x.close < price if high_side else x.close > price
            if closed_back and i >= frm:
                extreme = x.high if high_side else x.low
                out.append(Sweep(f"SWEEP-{lv.id}-{x.time}", lv, i, x.time, extreme, abs(extreme - price) / atr if atr > 0 else 0))
            break  # only the first take counts
    out.sort(key=lambda s: (s.index, -s.level.weight))
    return out
