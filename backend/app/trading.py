"""
Trade bookkeeping: P&L of a trade, statistics (win rate, counts, profit factor, equity curve)
and the outcome tracker that follows every sent signal with the strategy's own lifecycle.
"""

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Signal, Trade
from .strategies.replay import outcome
from .strategies.service import STRATEGY_DEFS, normalize_symbol
from .strategies.shared.jsnum import round_to

CONTRACT = {"XAU/USD": 100, "EUR/USD": 100_000}
LOT_STEP = 0.01


def contract_size(symbol: str) -> int:
    return CONTRACT[normalize_symbol(symbol)]


def lot_for(symbol: str, capital: float, risk_pct: float, entry: float, sl: float) -> float:
    """(capital × risk%) / (SL distance × contract size), rounded down to 0.01."""
    per_lot = abs(entry - sl) * contract_size(symbol)
    if per_lot <= 0 or capital <= 0:
        return 0
    lots = int((capital * risk_pct / 100) / per_lot / LOT_STEP + 1e-9) * LOT_STEP
    return round_to(lots, 2) if lots >= 0.01 else 0


def trade_pnl(t: Trade, exit_price: float) -> tuple[float, float]:
    """(P&L in account currency, R multiple) for closing the whole position at `exit_price`."""
    sign = 1 if t.direction == "BUY" else -1
    move = (exit_price - t.entry) * sign
    risk = abs(t.entry - t.sl)
    return round_to(move * t.lots * contract_size(t.symbol), 2), round_to(move / risk, 3) if risk > 0 else 0


def result_of(r_multiple: float) -> str:
    return "WIN" if r_multiple > 0.05 else "LOSS" if r_multiple < -0.05 else "BREAKEVEN"


def close_trade(t: Trade, exit_price: float, r_multiple: Optional[float] = None) -> Trade:
    pnl, r = trade_pnl(t, exit_price)
    if r_multiple is not None:  # signal-tracked close: partials already in the strategy's R
        r = r_multiple
        pnl = round_to(r * abs(t.entry - t.sl) * t.lots * contract_size(t.symbol), 2)
    t.status, t.exit_price, t.pnl, t.r_multiple, t.result = "CLOSED", exit_price, pnl, r, result_of(r)
    t.closed_at = datetime.now(timezone.utc)
    return t


def trade_json(t: Trade) -> dict:
    return {
        "id": t.id, "userId": t.user_id, "chatId": t.chat_id, "signalId": t.signal_id, "symbol": t.symbol, "direction": t.direction,
        "entry": t.entry, "sl": t.sl, "tp1": t.tp1, "tp2": t.tp2, "tp3": t.tp3, "lots": t.lots, "capital": t.capital, "riskPct": t.risk_pct,
        "riskAmount": round_to(abs(t.entry - t.sl) * t.lots * contract_size(t.symbol), 2),
        "status": t.status, "result": t.result, "exitPrice": t.exit_price, "pnl": t.pnl, "rMultiple": t.r_multiple, "breakeven": t.breakeven,
        "source": t.source, "notes": t.notes,
        "openedAt": _iso(t.opened_at), "closedAt": _iso(t.closed_at),
    }


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def stats(items: Iterable, kind: str = "trade", starting_capital: float = 0) -> dict:
    """Works for trades (pnl in $) and signals (R only). Win rate excludes breakevens."""
    rows = list(items)
    is_trade = kind == "trade"
    if is_trade:
        cancelled = [x for x in rows if x.result == "CANCELLED"]
        closed = [x for x in rows if x.status == "CLOSED" and x.result != "CANCELLED"]
    else:
        cancelled = [x for x in rows if x.state in ("CANCELLED", "EXPIRED")]
        closed = [x for x in rows if x.state == "CLOSED"]
    res_of = (lambda x: x.result) if is_trade else (lambda x: x.outcome)
    wins = [x for x in closed if res_of(x) == "WIN"]
    losses = [x for x in closed if res_of(x) == "LOSS"]
    bes = [x for x in closed if res_of(x) == "BREAKEVEN"]
    r_vals = [x.r_multiple or 0 for x in closed]
    gross_win = sum(r for r in r_vals if r > 0)
    gross_loss = -sum(r for r in r_vals if r < 0)
    decided = len(wins) + len(losses)
    out = {
        "total": len(rows),
        "open": len(rows) - len(closed) - len(cancelled),
        "closed": len(closed),
        "cancelledOrExpired": len(cancelled),
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(bes),
        "winRate": round_to(len(wins) / decided * 100, 1) if decided else None,
        "totalR": round_to(sum(r_vals), 2),
        "avgR": round_to(sum(r_vals) / len(r_vals), 2) if r_vals else None,
        "profitFactor": round_to(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "bestR": round_to(max(r_vals), 2) if r_vals else None,
        "worstR": round_to(min(r_vals), 2) if r_vals else None,
    }
    if is_trade:
        pnl = [x.pnl or 0 for x in closed]
        out["totalPnl"] = round_to(sum(pnl), 2)
        out["startingCapital"] = starting_capital
        out["currentCapital"] = round_to(starting_capital + sum(pnl), 2)
        out["returnPct"] = round_to(sum(pnl) / starting_capital * 100, 2) if starting_capital > 0 else None
        curve, eq = [], starting_capital
        for x in sorted(closed, key=lambda t: _iso(t.closed_at) or ""):
            eq += x.pnl or 0
            curve.append({"time": _iso(x.closed_at), "equity": round_to(eq, 2)})
        out["equityCurve"] = curve
        peak, dd = starting_capital, 0.0
        for p in curve:
            peak = max(peak, p["equity"])
            dd = max(dd, peak - p["equity"])
        out["maxDrawdown"] = round_to(dd, 2)
    by_symbol: dict[str, dict] = {}
    for x in closed:
        b = by_symbol.setdefault(x.symbol, {"closed": 0, "wins": 0, "losses": 0, "totalR": 0.0})
        b["closed"] += 1
        b["wins"] += res_of(x) == "WIN"
        b["losses"] += res_of(x) == "LOSS"
        b["totalR"] = round_to(b["totalR"] + (x.r_multiple or 0), 2)
    for b in by_symbol.values():
        decided_b = b["wins"] + b["losses"]
        b["winRate"] = round_to(b["wins"] / decided_b * 100, 1) if decided_b else None
    out["bySymbol"] = by_symbol
    return out


def signal_json(s: Signal) -> dict:
    return {"id": s.id, "symbol": s.symbol, "setup": s.setup, "direction": s.direction, "entryType": s.entry_type, "entry": s.entry, "sl": s.sl,
            "tp1": s.tp1, "tp2": s.tp2, "tp3": s.tp3, "rrTp2": s.rr_tp2, "score": s.score, "signalTime": s.signal_time,
            "sentAt": _iso(s.sent_at), "recipients": s.recipients, "latencyMs": s.latency_ms, "state": s.state, "outcome": s.outcome,
            "rMultiple": s.r_multiple, "exitTime": s.exit_time}


TERMINAL = ("CLOSED", "CANCELLED", "EXPIRED")


def update_signal_outcomes(db: Session, symbol: str, entry_candles: list) -> int:
    """Re-runs the lifecycle of every unfinished signal of `symbol` on the latest candles."""
    sym = normalize_symbol(symbol)
    d = STRATEGY_DEFS[sym]
    index_of = {c.time: i for i, c in enumerate(entry_candles)}
    changed = 0
    for s in db.scalars(select(Signal).where(Signal.symbol == sym, Signal.state.not_in(TERMINAL))):
        lc = outcome(d, entry_candles, index_of, {"signalTime": s.signal_time, "params": s.params, "lifecycle": {"state": s.state}})
        if lc["state"] == s.state and lc.get("rMultiple") == s.r_multiple:
            continue
        s.state, s.outcome, s.r_multiple, s.exit_time = lc["state"], lc.get("outcome"), lc.get("rMultiple"), lc.get("exitTime")
        changed += 1
        if lc["state"] in TERMINAL:
            exit_price = lc["events"][-1]["price"] if lc["events"] else s.entry
            for t in db.scalars(select(Trade).where(Trade.signal_id == s.id, Trade.status == "OPEN")):
                if lc["state"] == "CLOSED":
                    close_trade(t, exit_price, lc["rMultiple"])
                else:  # order never filled: the trade did not happen
                    t.status, t.result, t.pnl, t.r_multiple, t.exit_price = "CLOSED", "CANCELLED", 0, 0, t.entry
                    t.closed_at = datetime.now(timezone.utc)
    if changed:
        db.commit()
    return changed
