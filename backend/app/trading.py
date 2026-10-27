"""
Trade bookkeeping: P&L of a trade from the lot the user took, statistics (win rate, counts,
profit factor, cumulative P&L curve), the daily loss limit, and the outcome tracker that
follows every sent signal with the strategy's own lifecycle.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .market import data as market_data
from .models import Signal, Trade
from .strategies.replay import outcome
from .strategies.service import STRATEGY_DEFS, normalize_symbol
from .strategies.shared.jsnum import round_to
from .strategies.shared.sessions import trading_day_key

# Units per lot: gold 100 oz, every forex pair 100,000 units of the base currency
CONTRACT = {sym: 100 if sym == "XAU/USD" else 100_000 for sym in STRATEGY_DEFS}
# Used only until the app has seen a live price for the conversion pair
FALLBACK_USD_PER = {"CAD": 0.72, "CHF": 1.25}


def _last_price(sym: str) -> float:
    return float((market_data._last_known.get(sym) or {}).get("price") or 0)


def usd_per_quote(symbol: str) -> float:
    """US dollars per 1 unit of the pair's quote currency (P&L of a CAD/CHF-quoted pair is converted to USD)."""
    sym = normalize_symbol(symbol)
    quote = sym.split("/")[1]
    if quote == "USD":
        return 1.0
    if quote == "CAD":
        usdcad = _last_price("USD/CAD")
        return 1 / usdcad if usdcad > 0 else FALLBACK_USD_PER["CAD"]
    if quote == "CHF":
        eurusd, eurchf = _last_price("EUR/USD"), _last_price("EUR/CHF")
        return eurusd / eurchf if eurusd > 0 and eurchf > 0 else FALLBACK_USD_PER["CHF"]
    return 1.0


def contract_size(symbol: str) -> float:
    """US dollars per 1.0 price move per lot."""
    sym = normalize_symbol(symbol)
    return CONTRACT[sym] * usd_per_quote(sym)


LOT_STEP, MIN_LOT = 0.01, 0.01


def effective_risk(risk_usd: Optional[float], capital: Optional[float], risk_pct: Optional[float]) -> Optional[float]:
    """$ risked per trade: the fixed amount if set, else risk % × capital (None when neither is set)."""
    if risk_usd:
        return round_to(risk_usd, 2)
    if capital and capital > 0 and risk_pct and risk_pct > 0:
        return round_to(capital * risk_pct / 100, 2)
    return None


def lot_for_risk(symbol: str, entry: float, sl: float, risk_usd: float) -> dict:
    """Lot that loses `risk_usd` if the strategy's stop is hit (rounded DOWN to 0.01; the stop never moves)."""
    per_lot = abs(entry - sl) * contract_size(symbol)  # $ lost per 1.00 lot at the stop
    if per_lot <= 0 or risk_usd <= 0:
        return {"lots": 0.0, "riskUsd": risk_usd, "actualRisk": 0.0, "perLot": 0.0, "tooSmall": False}
    lots = int(risk_usd / per_lot / LOT_STEP + 1e-9) * LOT_STEP
    too_small = lots < MIN_LOT
    lots = round_to(max(lots, MIN_LOT), 2)
    return {"lots": lots, "riskUsd": risk_usd, "actualRisk": round_to(lots * per_lot, 2), "perLot": round_to(per_lot, 2), "tooSmall": too_small}


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
        "entry": t.entry, "sl": t.sl, "tp1": t.tp1, "tp2": t.tp2, "tp3": t.tp3, "lots": t.lots,
        "riskAmount": round_to(abs(t.entry - t.sl) * t.lots * contract_size(t.symbol), 2),
        "status": t.status, "result": t.result, "exitPrice": t.exit_price, "pnl": t.pnl, "rMultiple": t.r_multiple, "breakeven": t.breakeven,
        "source": t.source, "notes": t.notes,
        "openedAt": _iso(t.opened_at), "closedAt": _iso(t.closed_at),
    }


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def stats(items: Iterable, kind: str = "trade") -> dict:
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
        out["totalLots"] = round_to(sum(x.lots for x in rows), 2)
        out["bestPnl"] = round_to(max(pnl), 2) if pnl else None
        out["worstPnl"] = round_to(min(pnl), 2) if pnl else None
        # Cumulative P&L of closed trades (from the lots taken), starting at 0
        curve, eq = [], 0.0
        for x in sorted(closed, key=lambda t: _iso(t.closed_at) or ""):
            eq += x.pnl or 0
            curve.append({"time": _iso(x.closed_at), "pnl": round_to(eq, 2)})
        out["pnlCurve"] = curve
        peak, dd = 0.0, 0.0
        for p in curve:
            peak = max(peak, p["pnl"])
            dd = max(dd, peak - p["pnl"])
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


def today_status(trades: Iterable[Trade], limit: Optional[float], now: Optional[datetime] = None) -> dict:
    """Today's realised P&L against the user's daily loss limit. The trading day rolls over at 17:00 New York."""
    day = trading_day_key(int((now or datetime.now(timezone.utc)).timestamp()))
    closed_today = [t for t in trades if t.status == "CLOSED" and t.closed_at and trading_day_key(int(_aware(t.closed_at).timestamp())) == day]
    pnl = round_to(sum(t.pnl or 0 for t in closed_today), 2)
    reached = bool(limit) and pnl <= -float(limit)
    return {"day": day, "pnl": pnl, "trades": len(closed_today), "limit": limit, "reached": reached,
            "remaining": round_to(float(limit) + pnl, 2) if limit else None}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def daily_breakdown(rows: Iterable, value, closed_ts, now: Optional[datetime] = None) -> dict:
    """Result per trading day (17:00 New York rollover): profit days, loss days, best/worst day, streak, week and month.
    `value(x)` = $ P&L (trades) or R (signals); `closed_ts(x)` = unix seconds of the close, None if still open."""
    days: dict[str, dict] = {}
    for x in rows:
        ts = closed_ts(x)
        if ts is None:
            continue
        d = days.setdefault(trading_day_key(int(ts)), {"value": 0.0, "trades": 0, "wins": 0, "losses": 0})
        v = value(x) or 0
        d["value"] += v
        d["trades"] += 1
        d["wins"] += v > 0
        d["losses"] += v < 0
    out = [{"day": k, "value": round_to(v["value"], 2), "trades": v["trades"], "wins": v["wins"], "losses": v["losses"]} for k, v in sorted(days.items())]
    profit = [d for d in out if d["value"] > 0]
    loss = [d for d in out if d["value"] < 0]
    streak = 0  # +n profit days in a row, -n loss days in a row (latest days first)
    for d in reversed(out):
        sign = 1 if d["value"] > 0 else -1 if d["value"] < 0 else 0
        if sign == 0 or (streak and (streak > 0) != (sign > 0)):
            break
        streak += sign
    today = trading_day_key(int((now or datetime.now(timezone.utc)).timestamp()))
    ty, tm, td = (int(p) for p in today.split("-"))
    week_start = (datetime(ty, tm, td) - timedelta(days=datetime(ty, tm, td).weekday())).date().isoformat()
    period = lambda pred: round_to(sum(d["value"] for d in out if pred(d["day"])), 2)  # noqa: E731
    decided = len(profit) + len(loss)
    return {
        "days": out,
        "profitDays": len(profit), "lossDays": len(loss), "flatDays": len(out) - decided,
        "dayWinRate": round_to(len(profit) / decided * 100, 1) if decided else None,
        "bestDay": max(out, key=lambda d: d["value"]) if out else None,
        "worstDay": min(out, key=lambda d: d["value"]) if out else None,
        "avgProfitDay": round_to(sum(d["value"] for d in profit) / len(profit), 2) if profit else None,
        "avgLossDay": round_to(sum(d["value"] for d in loss) / len(loss), 2) if loss else None,
        "streak": streak,
        "today": period(lambda k: k == today), "week": period(lambda k: k >= week_start), "month": period(lambda k: k[:7] == today[:7]),
    }


def trade_days(trades: Iterable[Trade], now: Optional[datetime] = None) -> dict:
    return daily_breakdown([t for t in trades if t.status == "CLOSED"], lambda t: t.pnl,
                           lambda t: _aware(t.closed_at).timestamp() if t.closed_at else None, now)


def signal_days(signals: Iterable[Signal], now: Optional[datetime] = None) -> dict:
    return daily_breakdown([s for s in signals if s.state == "CLOSED"], lambda s: s.r_multiple, lambda s: s.exit_time, now)


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
