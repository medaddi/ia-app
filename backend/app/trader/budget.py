"""
Position sizing: the forex and gold version of trader-budget (github.com/Jakeschincariol/trader-skill, MIT).

trader-budget turns target weights into dollar amounts per stock. In forex and gold what you size is the RISK: how many
dollars a trade loses if its stop is hit. From the COT targets and your rules:

  1. risk budget   balance × max_total_risk_pct is the most all the trades together may lose
  2. weights       each target gets its weight's share of that budget...
  3. cap           ...but never more than balance × risk_pct on one trade
  4. stop          stop_atr × the daily ATR(14) from the entry (the market's own daily range), target at rr × the stop
  5. lots          risk ÷ (stop in pips × pip value of one lot), rounded DOWN to the lot step; under the minimum lot the
                   trade is dropped (its risk would be more than its share)
  6. margin        all the trades together never use more than margin_buffer_pct of the balance as margin (at your
                   leverage): over it, the lots are scaled down

Risk that cannot be used (a dropped trade, rounding down) is reported as "left idle", never hidden. It never places
anything: it writes proposals that the risk check checks and the tickets show you one by one.
"""

import math
from typing import Optional

from ..core.instrument_specs import INSTRUMENT_CONFIG, key

DEFAULTS = {"balance": 10000.0, "risk_pct": 1.0, "max_total_risk_pct": 3.0, "max_lots": 2.0, "leverage": 30.0,
            "margin_buffer_pct": 50.0, "min_lot": 0.01, "lot_step": 0.01, "stop_atr": 1.0, "rr": 2.0, "top": 3}


def pip_value_usd(symbol: str, fx: dict) -> Optional[float]:
    """Dollars per pip for ONE lot."""
    spec = INSTRUMENT_CONFIG[key(symbol)]
    raw = spec["contract_size"] * spec["pip_size"]  # in the quote currency
    quote = symbol.split("/")[1]
    if quote == "USD":
        return raw
    rate = fx.get(f"USD/{quote}")
    return raw / rate if rate else None


def notional_usd(symbol: str, lots: float, price: float, fx: dict) -> Optional[float]:
    """The position's size in dollars (what the margin is taken on)."""
    spec = INSTRUMENT_CONFIG[key(symbol)]
    base = symbol.split("/")[0]
    if base == "XAU":
        return lots * spec["contract_size"] * price
    if base == "USD":
        return lots * spec["contract_size"]
    rate = fx.get(f"{base}/USD")
    return lots * spec["contract_size"] * rate if rate else None


def size(targets: list[dict], cfg: dict, prices: dict, atrs: dict, fx: dict) -> dict:
    c = {**DEFAULTS, **{k: v for k, v in (cfg or {}).items() if v is not None}}
    bal = float(c["balance"])
    budget = bal * c["max_total_risk_pct"] / 100
    cap = bal * c["risk_pct"] / 100
    step, min_lot = float(c["lot_step"]), float(c["min_lot"])
    orders, skipped = [], []
    for t in targets:
        sym, side = t["symbol"], t["side"]
        spec = INSTRUMENT_CONFIG[key(sym)]
        price, atr, pv = prices.get(sym), atrs.get(sym), pip_value_usd(sym, fx)
        if not price or not atr or not pv:
            skipped.append({"symbol": sym, "why": "no price, daily ATR or conversion rate right now"})
            continue
        share = min(cap, budget * t["weight"] / 100)
        stop = c["stop_atr"] * atr
        stop_pips = stop / spec["pip_size"]
        raw = share / (stop_pips * pv)
        lots = math.floor(raw / step + 1e-9) * step
        lots = min(lots, float(c["max_lots"]))
        if lots < min_lot - 1e-9:
            skipped.append({"symbol": sym, "why": f"${share:,.0f} of risk is less than {min_lot:g} lot with a {stop_pips:.0f}-pip stop"})
            continue
        d = 1 if side == "BUY" else -1
        dec = spec["decimals"]
        orders.append({"symbol": sym, "side": side.lower(), "type": "market", "lots": round(lots, 2), "entry": round(price, dec),
                       "sl": round(price - d * stop, dec), "tp": round(price + d * c["rr"] * stop, dec), "stopPips": round(stop_pips, 1),
                       "riskUsd": round(lots * stop_pips * pv, 2), "rr": c["rr"], "weight": t["weight"], "crowded": t.get("crowded", False),
                       "marginUsd": None})
    # margin: all together within the buffer (scaled down, never up)
    for o in orders:
        n = notional_usd(o["symbol"], o["lots"], o["entry"], fx)
        o["marginUsd"] = round(n / c["leverage"], 2) if n else None
    used = sum(o["marginUsd"] or 0 for o in orders)
    room = bal * c["margin_buffer_pct"] / 100
    if used > room > 0:
        k = room / used
        for o in orders:
            o["lots"] = math.floor(o["lots"] * k / step + 1e-9) * step
            o["lots"] = round(o["lots"], 2)
            pv = pip_value_usd(o["symbol"], fx)
            o["riskUsd"] = round(o["lots"] * o["stopPips"] * pv, 2)
            n = notional_usd(o["symbol"], o["lots"], o["entry"], fx)
            o["marginUsd"] = round(n / c["leverage"], 2) if n else None
        for o in [o for o in orders if o["lots"] < min_lot - 1e-9]:
            skipped.append({"symbol": o["symbol"], "why": "no room left in the margin buffer"})
        orders = [o for o in orders if o["lots"] >= min_lot - 1e-9]
    risk = sum(o["riskUsd"] for o in orders)
    return {"orders": orders, "skipped": skipped, "config": c,
            "summary": {"balance": bal, "riskBudget": round(budget, 2), "riskUsed": round(risk, 2), "riskIdle": round(budget - risk, 2),
                        "marginUsed": round(sum(o["marginUsd"] or 0 for o in orders), 2), "marginRoom": round(room, 2)}}


def size_setup(symbol: str, side: str, entry: float, sl: float, tp: float, cfg: dict, fx: dict) -> dict:
    """One setup sized to your risk: its stop stays where the strategy put it, the lots make that stop lose risk_pct of
    the balance (rounded down, capped at max_lots, never under min_lot)."""
    c = {**DEFAULTS, **{k: v for k, v in (cfg or {}).items() if v is not None}}
    spec = INSTRUMENT_CONFIG[key(symbol)]
    pv = pip_value_usd(symbol, fx)
    stop_pips = abs(entry - sl) / spec["pip_size"]
    out = {"symbol": symbol, "side": side.lower(), "type": "market", "entry": entry, "sl": sl, "tp": tp, "stopPips": round(stop_pips, 1),
           "rr": round(abs(tp - entry) / abs(entry - sl), 2) if entry != sl else 0, "lots": 0.0, "riskUsd": 0.0, "marginUsd": None}
    if not pv or stop_pips <= 0:
        return {**out, "why": "no conversion rate or no stop distance right now"}
    want = float(c["balance"]) * c["risk_pct"] / 100
    lots = min(math.floor(want / (stop_pips * pv) / c["lot_step"] + 1e-9) * c["lot_step"], float(c["max_lots"]))
    if lots < c["min_lot"] - 1e-9:
        return {**out, "why": f"${want:,.0f} of risk is less than {c['min_lot']:g} lot with a {stop_pips:.0f}-pip stop"}
    n = notional_usd(symbol, lots, entry, fx)
    return {**out, "lots": round(lots, 2), "riskUsd": round(lots * stop_pips * pv, 2), "marginUsd": round(n / c["leverage"], 2) if n else None,
            "wantedRiskUsd": round(want, 2)}


def atr(candles, n: int = 14) -> Optional[float]:
    """The average true range of the last n closed candles."""
    if len(candles) < n + 1:
        return None
    trs = [max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)) for p, c in zip(candles[:-1], candles[1:])]
    return sum(trs[-n:]) / n
