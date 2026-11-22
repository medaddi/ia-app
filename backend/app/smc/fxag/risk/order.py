"""
Agent 8 · OrderExecutor (spec 4), SIGNALS ONLY (the owner, 2026-11-20): it builds the exact order with its
deterministic idempotency key hash(symbol, dir, entry_tf, candle_ts), marks it SET_AND_FORGET_LOCKED (its SL and TP
never change: no break-even, no trailing, no partial, no early close), and hands it to the notifier. Nothing is sent to a
broker. The saved record (signals table) is the immutable trade record; the same key is never saved twice.
"""

import hashlib


def client_order_id(symbol: str, d: int, entry_tf: str, candle_ts: int) -> str:
    return hashlib.sha256(f"{symbol}|{d}|{entry_tf}|{candle_ts}".encode()).hexdigest()[:16]


def proposal(symbol: str, d: int, p: dict) -> dict:
    """TradeProposal (7.2) of an approved setup, locked."""
    return {"client_order_id": client_order_id(symbol, d, p["entryTf"], p["time"]), "symbol": symbol, "direction": "BUY" if d > 0 else "SELL",
            "grade": p["grade"], "total_score_pct": p["score"], "sos_timeframe": p["sosTf"], "entry_timeframe": p["entryTf"],
            "order_type": p["orderType"], "entry_price": p["entry"], "stop_loss": p["sl"], "take_profit": p["tp"],
            "rr_ratio": round(p["rr"], 2), "risk_pct": p["riskPct"], "set_and_forget_locked": True}
