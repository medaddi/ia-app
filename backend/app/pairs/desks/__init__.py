"""
One team per pair, each in its own file: its trading hours, how much each member's view counts for THIS pair, and how far
the big players' report is trusted on it. The team engine (pairs/team.py) is shared; the desk makes each team a specialist.
"""

from . import audcad, audchf, eurchf, eurusd, gbpusd, xauusd

DESKS = {m.DESK["symbol"]: m.DESK for m in (xauusd, eurusd, gbpusd, eurchf, audcad, audchf)}


def desk_of(symbol: str) -> dict:
    return DESKS[symbol]
