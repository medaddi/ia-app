"""The blueprint's data contracts (step 1): small typed records shared by the agents. They hold values only."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Swing:
    index: int
    kind: int          # +1 high, -1 low
    price: float       # the body level
    tf: str = ""


@dataclass
class AOI:
    id: str
    kind: str          # "W", "D", "H4", "W+D"
    low: float
    high: float
    touches: int
    width_pips: float
    flip: bool = False
    psych: Optional[float] = None
    t0: int = 0


@dataclass
class ConfluenceBreakdown:
    items: dict = field(default_factory=dict)   # "C1" .. "C8" -> points
    detail: dict = field(default_factory=dict)
    total: int = 0
    grade: str = "D"


@dataclass
class EntryTrigger:
    model: str         # E1 | E2 | E3
    sos_tf: str
    eng_tf: str
    order_type: str    # MARKET | LIMIT_PULLBACK
    time: int


@dataclass
class TradePlan:
    entry: float
    sl: float
    tp: float
    rr: float
    sl_pips: float
    tp_pips: float
    order_type: str
    signal_id: str = ""
    status: str = "SET_AND_FORGET_LOCKED"
