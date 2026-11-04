"""
Pre-trade risk check: the forex and gold version of trader-risk (github.com/Jakeschincariol/trader-skill, MIT).

Every proposed order gets PASS or BLOCK with its reasons. Orders are checked in their order as if each PASS had filled,
so trades that are fine one by one but break a limit together are caught. The verdicts are kept with a fingerprint of
each exact order: a ticket is READY only if THIS order passed TODAY.

What blocks an order:
  format      unknown instrument, side not buy / sell, lots not positive, a stop or a target on the wrong side
  blocked     an instrument on your blocked list
  size        under the minimum lot, over your max lots per order
  risk        the trade risks more than max_risk_pct of the balance, or all the trades together more than
              max_total_risk_pct
  margin      all the trades together would use more than margin_buffer_pct of the balance as margin
  dollar      more than max_usd_same_side trades betting the same way on the US dollar (they move together)
  news        a high-impact release on one of its currencies within news_minutes of now
  market      the market is closed (weekend)
  duplicate   the same instrument twice in this batch, or already approved today
  daily       more than max_orders_per_day orders approved today
"""

import hashlib
import json
from typing import Optional

from ..core.instrument_specs import INSTRUMENT_CONFIG, key, usd_direction
from ..strategies._pairs import PAIRS

INSTRUMENTS = ["XAU/USD", *PAIRS]

DEFAULTS = {"balance": 10000.0, "max_risk_pct": 2.0, "max_total_risk_pct": 5.0, "max_lots": 5.0, "min_lot": 0.01, "leverage": 30.0,
            "margin_buffer_pct": 50.0, "max_usd_same_side": 2, "news_minutes": 30, "max_orders_per_day": 5, "blocked": []}
CORE = ("symbol", "side", "type", "lots", "entry", "sl", "tp")


def fingerprint(order: dict) -> str:
    """The exact order (same function in the risk check and the tickets)."""
    core = {k: order[k] for k in CORE if order.get(k) is not None}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def check(orders: list[dict], cfg: dict, news_events: list[dict], now: int, market_open: bool, approved_today: list[dict]) -> dict:
    c = {**DEFAULTS, **{k: v for k, v in (cfg or {}).items() if v is not None}}
    bal = float(c["balance"])
    blocked = {str(b).upper() for b in c.get("blocked") or []}
    done_syms = {str(r.get("symbol", "")).upper() for r in approved_today}
    count = len(approved_today)
    total_risk, total_margin, usd = 0.0, 0.0, {1: 0, -1: 0}
    seen = set()
    results = []
    for i, o in enumerate(orders, 1):
        reasons, warns = [], []
        sym = str(o.get("symbol", "")).upper()
        side = str(o.get("side", "")).lower()
        lots, entry, sl, tp = (o.get(k) for k in ("lots", "entry", "sl", "tp"))
        if sym not in INSTRUMENTS:
            reasons.append(f"format: {sym or '?'} is not one of the app's instruments")
        if side not in ("buy", "sell"):
            reasons.append(f"format: side must be buy or sell, got {o.get('side')!r}")
        if not isinstance(lots, (int, float)) or lots <= 0:
            reasons.append("format: lots must be a positive number")
        d = 1 if side == "buy" else -1
        if isinstance(entry, (int, float)) and isinstance(sl, (int, float)) and (sl - entry) * d >= 0:
            reasons.append("format: the stop is on the wrong side of the entry")
        if isinstance(entry, (int, float)) and isinstance(tp, (int, float)) and (tp - entry) * d <= 0:
            reasons.append("format: the target is on the wrong side of the entry")
        if sym in blocked:
            reasons.append(f"blocked: {sym} is on your blocked list")
        if isinstance(lots, (int, float)):
            if lots < c["min_lot"] - 1e-9:
                reasons.append(f"size: {lots:g} lot is under the {c['min_lot']:g} minimum")
            if lots > c["max_lots"] + 1e-9:
                reasons.append(f"size: {lots:g} lots is over your {c['max_lots']:g} max per order")
        risk = float(o.get("riskUsd") or 0)
        if risk > bal * c["max_risk_pct"] / 100 + 0.01:
            reasons.append(f"risk: ${risk:,.0f} is {100 * risk / bal:.1f} % of the balance, over your {c['max_risk_pct']:g} % per trade")
        if total_risk + risk > bal * c["max_total_risk_pct"] / 100 + 0.01:
            reasons.append(f"risk: with this one the trades risk ${total_risk + risk:,.0f}, over your {c['max_total_risk_pct']:g} % in total")
        margin = float(o.get("marginUsd") or 0)
        if total_margin + margin > bal * c["margin_buffer_pct"] / 100 + 0.01:
            reasons.append(f"margin: ${total_margin + margin:,.0f} of margin, over the {c['margin_buffer_pct']:g} % of the balance you allow")
        ud = usd_direction(sym, side.upper()) if sym in INSTRUMENTS else 0
        if ud and usd[ud] + 1 > c["max_usd_same_side"]:
            reasons.append(f"dollar: already {usd[ud]} trade(s) {'selling' if ud < 0 else 'buying'} the US dollar, your max is {c['max_usd_same_side']}")
        ccys = {"XAU", "USD"} if sym.startswith("XAU") else set(sym.split("/"))
        hit = next((e for e in news_events if e.get("impact") == "High" and e.get("currency") in ccys
                    and abs(e["time"] - now) <= c["news_minutes"] * 60), None)
        if hit:
            reasons.append(f"news: {hit['currency']} {hit['title']} within {c['news_minutes']} minutes")
        if not market_open:
            reasons.append("market: closed (the forex and gold week runs Sunday 22:00 to Friday 21:00 UTC)")
        if sym in seen:
            reasons.append(f"duplicate: {sym} is already in this batch")
        if sym in done_syms:
            reasons.append(f"duplicate: an order on {sym} was already approved today")
        if count + 1 > c["max_orders_per_day"]:
            reasons.append(f"daily: {count} order(s) approved today, your max is {c['max_orders_per_day']}")
        if o.get("crowded"):
            warns.append("crowded: the big players' side is at its 3-year extreme, the late part of a move")
        verdict = "BLOCK" if reasons else "PASS"
        if verdict == "PASS":  # simulated as filled for the next orders
            total_risk += risk
            total_margin += margin
            if ud:
                usd[ud] += 1
            count += 1
        seen.add(sym)
        results.append({"index": i, "symbol": sym, "side": side, "verdict": verdict, "reasons": reasons, "warnings": warns,
                        "fingerprint": fingerprint(o)})
    return {"results": results, "pass": sum(r["verdict"] == "PASS" for r in results), "block": sum(r["verdict"] == "BLOCK" for r in results),
            "config": c}
