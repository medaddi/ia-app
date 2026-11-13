"""
The check before a found trade is sent. Since 2026-11-13 the owner wants every pair's trade sent when it is found: the
cross-pair limits (5 a day, 3 % total risk, 2 bets the same way per currency, the correlation caps) are gone. One rule
stays: ONE live trade per pair, so a pair never sends a second trade while its first one can still run.

A setup is "live" from its signal until its `liveUntil` (the last moment the trade can still run), or for an older
setup its limit's end plus 4 hours. A setup the trade manager closed (or that expired) no longer counts. Each user sizes
their own lot from their own USD risk (sizing.py), so the risk across pairs is the user's own choice.
"""

from typing import Iterable, Optional

HOLD_SEC = 4 * 3600
ENDED = {"CLOSED", "EXPIRED", "MISSED"}


def exposure(symbol: str, direction: str) -> dict[str, int]:
    """+1 / -1 per currency leg: BUY GBP/JPY = long GBP, short JPY. Gold has only its dollar leg (BUY = short USD)."""
    a, b = symbol.split("/")
    s = 1 if direction == "BUY" else -1
    return {c: v for c, v in ((a, s), (b, -s)) if c in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD")}


def live(sent: Iterable[dict], now: int) -> list[dict]:
    """The setups sent that may still be open (not closed or expired by the trade manager, and inside their live time)."""
    return [s for s in sent if s.get("state") not in ENDED and (s.get("liveUntil") or (s.get("validUntil") or s.get("time", 0)) + HOLD_SEC) > now]


def check(symbol: str, setup: dict, sent: list[dict], now: int, limits: Optional[dict] = None) -> dict:
    """`sent`: the setups already sent (each with symbol, direction, time, validUntil / liveUntil, state).
    PASS unless this pair already has a live trade."""
    open_ = live(sent, now)
    mine = [s for s in open_ if s["symbol"] == symbol]
    reasons = [f"duplicate: a {symbol} trade is still live (one trade per pair at a time)"] if mine else []
    return {"verdict": "BLOCK" if reasons else "PASS", "reasons": reasons, "live": len(open_), "riskPct": 1.0, "notes": []}
