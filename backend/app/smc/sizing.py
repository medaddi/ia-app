"""
Position size from ONE user's own USD risk (the owner's prompt "risk USD par utilisateur, calcul du lot", 2026-11-11).

For a symbol quoted in currency Q (EUR/GBP: GBP, USD/JPY: JPY, XAU/USD: USD):
  distance          = |entry - stop|                                   (the signal's saved, fixed stop)
  costs per lot     = (spread + slippage, in pips) x pip x contract units x Q-to-USD + commission per lot   (once)
  risk per lot USD  = distance x contract units per lot x Q-to-USD + costs per lot
  raw lots          = the user's USD risk / risk per lot
  lots              = raw lots rounded DOWN to the lot step; below the minimum lot: "size unavailable" (never rounded up)
  estimated loss    = lots x risk per lot, checked <= the user's USD risk

Q-to-USD comes from the app's own live prices (Q/USD, or 1 / USD/Q): a missing, "last known", unavailable or stale
quote (older than 15 min while the market is open, 72 h while it is closed) makes the size unavailable. The contract
size, pip, spread, slippage, commission, minimum lot and lot step come from the pair's config (configs/<PAIR>.json); a
missing field makes the size unavailable too. Nothing is guessed, nothing is shared between users, no order is placed.
"""

import math
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal, User, UserSignalSize

STALE_OPEN_SEC = 15 * 60       # CHOICE: a conversion quote older than this is stale while the market is open
STALE_CLOSED_SEC = 72 * 3600   # CHOICE: over a weekend the last close is the price; older than 3 days is stale
DIRECT = {"EUR", "GBP", "AUD", "NZD"}   # Q/USD is an app pair: Q-to-USD = its price
INVERSE = {"JPY", "CHF", "CAD"}         # USD/Q is an app pair: Q-to-USD = 1 / its price
NEEDED = ("contract_size", "pip", "spread_pips", "slippage_pips", "commission_usd_per_lot", "min_lot", "lot_step")


def valid_risk(v) -> Optional[float]:
    """A finite, positive USD amount (at most 1,000,000), or None."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, 2) if math.isfinite(x) and 0 < x <= 1_000_000 else None


def quote_ccy(symbol: str) -> str:
    return symbol.split("/")[1]


def _fresh(q: dict, now: float) -> Optional[str]:
    """Why a live quote cannot be used, or None."""
    if not q or not (q.get("price") or 0) > 0:
        return "no price"
    src = str(q.get("source") or "")
    if src == "unavailable" or "last known" in src:
        return f"the price is not live ({src})"
    age = now - float(q.get("quoteTime") or 0)
    limit = STALE_OPEN_SEC if q.get("isMarketOpen", True) else STALE_CLOSED_SEC
    if age > limit:
        return f"the price is {int(age // 60)} min old (limit {limit // 60} min)"
    return None


async def conversion(symbol: str, now: Optional[float] = None) -> dict:
    """{rate, pair, price, source, quoteTime} for Q-to-USD, or {error}."""
    from ..market.data import fetch_live_price
    now = now or time.time()
    q = quote_ccy(symbol)
    if q == "USD":
        return {"rate": 1.0, "pair": None, "source": "USD-quoted: 1 unit of the quote currency = 1 USD"}
    if q in DIRECT:
        pair, inv = f"{q}/USD", False
    elif q in INVERSE:
        pair, inv = f"USD/{q}", True
    else:
        return {"error": f"no app price converts {q} to USD"}
    p = await fetch_live_price(pair)
    why = _fresh(p, now)
    if why:
        return {"error": f"{pair} conversion unavailable: {why}"}
    return {"rate": (1 / p["price"]) if inv else p["price"], "pair": pair, "price": p["price"], "source": p.get("source"), "quoteTime": p.get("quoteTime")}


def compute(cfg: dict, entry: float, sl: float, risk_usd: Optional[float], conv: dict) -> dict:
    """The size for one user's risk. {status: 'ok', lots, ...} or {status: 'unavailable', reason, ...}. Pure: no I/O."""
    base = {"riskUsd": risk_usd, "symbol": cfg.get("symbol"), "entry": entry, "sl": sl}
    if risk_usd is None:
        return {**base, "status": "unavailable", "reason": "set your USD risk per trade in My account to see a lot size"}
    missing = [k for k in NEEDED if cfg.get(k) is None]
    if missing:
        return {**base, "status": "unavailable", "reason": f"contract data missing for {cfg.get('symbol')}: {', '.join(missing)}"}
    if "error" in conv:
        return {**base, "status": "unavailable", "reason": conv["error"]}
    dist = abs(entry - sl)
    if not (math.isfinite(dist) and dist > 0):
        return {**base, "status": "unavailable", "reason": "the stop is not away from the entry"}
    units, rate, step, mn = float(cfg["contract_size"]), float(conv["rate"]), float(cfg["lot_step"]), float(cfg["min_lot"])
    costs = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"] * units * rate + cfg["commission_usd_per_lot"]
    per_lot = dist * units * rate + costs
    raw = risk_usd / per_lot
    dec = max(0, -int(math.floor(math.log10(step) + 1e-9)))
    lots = round(math.floor(raw / step + 1e-9) * step, dec)
    while lots > 0 and lots * per_lot > risk_usd + 1e-9:  # never above the user's risk, even by a rounding hair
        lots = round(lots - step, dec)
    meta = {"contractSize": units, "pip": cfg["pip"], "quoteCcy": quote_ccy(cfg["symbol"]), "quoteToUsd": rate, "conversion": conv,
            "minLot": mn, "lotStep": step, "spreadPips": cfg["spread_pips"], "slippagePips": cfg["slippage_pips"],
            "commissionUsdPerLot": cfg["commission_usd_per_lot"], "costsPerLotUsd": round(costs, 4), "riskPerLotUsd": round(per_lot, 4),
            "stopPips": round(dist / cfg["pip"], 1), "rawLots": raw}
    if lots < mn - 1e-12:
        return {**base, "status": "unavailable", "meta": meta,
                "reason": f"${risk_usd:g} buys {raw:.4f} lots with this stop: under the minimum lot {mn:g} (never rounded up)"}
    return {**base, "status": "ok", "lots": lots, "estLossUsd": round(lots * per_lot, 2), "meta": meta}


def snapshot_json(row: UserSignalSize) -> dict:
    return {"signalId": row.signal_id, "source": row.source, "status": "ok", "riskUsd": row.risk_usd, "lots": row.lots,
            "estLossUsd": row.est_loss_usd, "meta": row.meta, "symbol": row.symbol, "direction": row.direction, "entry": row.entry,
            "sl": row.sl, "tp": row.tp, "createdAt": row.created_at.replace(tzinfo=timezone.utc).isoformat() if row.created_at.tzinfo is None else row.created_at.isoformat(),
            "saved": True}


def own_snapshot(db: Session, user_id: int, signal_id: str) -> Optional[UserSignalSize]:
    """THIS user's saved size for a signal (the query is scoped by user: another user's row is never read)."""
    return db.scalar(select(UserSignalSize).where(UserSignalSize.user_id == user_id, UserSignalSize.signal_id == signal_id))


async def size_for(db: Session, user: User, sig: Signal, source: str = "app") -> dict:
    """The user's size for a saved signal: their saved snapshot when there is one (a later risk change never rewrites it),
    else computed now from THEIR risk, the signal's saved fixed stop and the live contract / conversion data, and saved."""
    row = own_snapshot(db, user.id, sig.id)
    if row:
        return snapshot_json(row)
    from .desk import BY_SYMBOL
    cfg = BY_SYMBOL.get(sig.symbol)
    if not cfg:
        return {"status": "unavailable", "reason": f"{sig.symbol} is not a pair of the app", "signalId": sig.id}
    risk = valid_risk(user.risk_usd)
    conv = await conversion(sig.symbol) if risk is not None else {}
    out = compute(cfg, sig.entry, sig.sl, risk, conv)
    out["signalId"] = sig.id
    if out["status"] != "ok":
        return {**out, "saved": False}
    row = UserSignalSize(user_id=user.id, signal_id=sig.id, source=source, risk_usd=risk, lots=out["lots"], est_loss_usd=out["estLossUsd"],
                         meta={**out["meta"], "calculatedAt": datetime.now(timezone.utc).isoformat()}, symbol=sig.symbol, direction=sig.direction,
                         entry=sig.entry, sl=sig.sl, tp=sig.tp2)
    db.add(row)
    db.commit()
    db.refresh(row)
    return snapshot_json(row)
