"""
Fair Value Gaps and Order Blocks.
- FVG: candle1.high < candle3.low (bullish) / candle1.low > candle3.high (bearish), gap >= minAtr × ATR(14).
  Mitigated once price fills 50% of the gap, filled at 100%.
- Order Block: last opposite-coloured candle before the displacement that caused a BOS/CHoCH.
  Only valid if the displacement body > mult × average body (20).
"""

from dataclasses import asdict, dataclass
from typing import Optional

from .structure import StructureEvent
from .types import Candle


@dataclass(slots=True)
class Fvg:
    id: str
    direction: str
    top: float
    bottom: float
    ce: float
    startTime: int
    createdIndex: int
    createdTime: int
    sizeAtr: float
    state: str = "OPEN"  # OPEN | MITIGATED | FILLED
    mitigatedTime: Optional[int] = None
    filledTime: Optional[int] = None

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class OrderBlock:
    id: str
    direction: str
    top: float
    bottom: float
    mid: float
    time: int
    index: int
    breakTime: int
    breakIndex: int
    state: str = "OPEN"  # OPEN | MITIGATED | BROKEN
    mitigatedTime: Optional[int] = None
    brokenTime: Optional[int] = None

    def to_dict(self):
        return asdict(self)


def detect_fvgs(c: list[Candle], atr: list[float], min_atr: float, tf: str) -> list[Fvg]:
    out: list[Fvg] = []
    n = len(c)
    for k in range(2, n):
        a = atr[k]
        if not (a > 0):
            continue
        c1, c3 = c[k - 2], c[k]
        if c1.high < c3.low and c3.low - c1.high >= min_atr * a:
            direction, top, bottom = "BULLISH", c3.low, c1.high
        elif c1.low > c3.high and c1.low - c3.high >= min_atr * a:
            direction, top, bottom = "BEARISH", c1.low, c3.high
        else:
            continue
        fvg = Fvg(f"{tf}-FVG-{c1.time}", direction, top, bottom, (top + bottom) / 2, c1.time, k, c3.time, (top - bottom) / a)
        for m in range(k + 1, n):
            x = c[m]
            if direction == "BULLISH":
                if x.low <= fvg.bottom:
                    fvg.state, fvg.filledTime = "FILLED", x.time
                    if fvg.mitigatedTime is None:
                        fvg.mitigatedTime = x.time
                    break
                if x.low <= fvg.ce and fvg.state == "OPEN":
                    fvg.state, fvg.mitigatedTime = "MITIGATED", x.time
            else:
                if x.high >= fvg.top:
                    fvg.state, fvg.filledTime = "FILLED", x.time
                    if fvg.mitigatedTime is None:
                        fvg.mitigatedTime = x.time
                    break
                if x.high >= fvg.ce and fvg.state == "OPEN":
                    fvg.state, fvg.mitigatedTime = "MITIGATED", x.time
        out.append(fvg)
    return out


def detect_order_blocks(c: list[Candle], events: list[StructureEvent], tf: str) -> list[OrderBlock]:
    out: list[OrderBlock] = []
    ids: set[str] = set()
    for e in events:
        if e.displacementIndex is None:
            continue
        bull = e.direction == "BULLISH"
        ob_idx = -1
        for i in range(e.displacementIndex - 1, max(0, e.legStartIndex - 3) - 1, -1):
            if (c[i].close < c[i].open) if bull else (c[i].close > c[i].open):
                ob_idx = i
                break
        if ob_idx < 0:
            continue
        x = c[ob_idx]
        ob = OrderBlock(f"{tf}-OB-{x.time}", e.direction, x.high, x.low, (x.high + x.low) / 2, x.time, ob_idx, e.breakTime, e.breakIndex)
        for m in range(e.breakIndex + 1, len(c)):
            y = c[m]
            if (y.close < ob.bottom) if bull else (y.close > ob.top):
                ob.state, ob.brokenTime = "BROKEN", y.time
                break
            if ob.state == "OPEN" and ((y.low <= ob.top) if bull else (y.high >= ob.bottom)):
                ob.state, ob.mitigatedTime = "MITIGATED", y.time
        if ob.id not in ids:
            ids.add(ob.id)
            out.append(ob)
    return out
