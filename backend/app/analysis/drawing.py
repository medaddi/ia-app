"""
What the Analyse button draws on the pair's chart for the setup that applies now (frontend analysisDrawing.ts merges it
into the chart's overlay): the trade (entry, stop, target), and the levels that made the setup, in the chart's own
drawing contract (agents/base.py zone / line / marker).

  a proven plan   the channel level the close crossed, the signal marker, a MARKET trade box
  an SMC setup    the swept level (Asian range box / previous day high-low / H1 swing), the entry FVG or OB zone, the H1
                  equilibrium, the signal marker, a LIMIT trade box (PENDING until price reaches the entry)
"""

from typing import Optional

from ..agents.base import BEAR, BULL, line, marker, zone

H1S, M5S = 3600, 300


def _box(direction: str, order: str, status: str, t: int, entry: float, sl: float, tp: float, rr: float, price: float, pip: float) -> dict:
    buy = direction == "BUY"
    live = status == "OPEN" and price
    return {"direction": "LONG" if buy else "SHORT", "orderType": order, "status": status, "entryTime": int(t), "entryPrice": entry,
            "stopLoss": sl, "tp1Price": tp, "tp2Price": tp, "rrRatio": round(rr, 2),
            "floatingPips": round(((price - entry) if buy else (entry - price)) / pip, 1) if live else 0.0}


def plan_drawing(sym: str, row: dict, price: float, pip: float) -> Optional[dict]:
    s = row.get("setup")
    if not s:
        return None
    g = s.get("geo") or {}
    buy = s["direction"] == "BUY"
    t, tf = s["since"], 3600 if row["timeframe"] == "H1" else 14400
    lines, markers = [], []
    if g.get("level") is not None:
        lines.append(line(f"AN-{sym}-LVL-{t}", "MSS_BREAK", g["t0"], t, g["level"], None, f"{g['n']}-candle {'high' if g['side'] > 0 else 'low'}"))
    markers.append(marker(f"AN-{sym}-SIG-{t}", t - tf, s["entry"], not buy, f"{row['id']} {s['direction']}", BULL if buy else BEAR))
    return {"label": f"{row['name']} · {s['direction']} {s['entry']}", "family": "plan", "id": row["id"],
            "zones": [], "priceLines": lines, "markers": markers,
            "tradeExecutionBox": _box(s["direction"], "MARKET", "OPEN", t, s["entry"], s["sl"], s["tp"], s["rr"], price, pip)}


def smc_drawing(sym: str, row: dict, price: float, pip: float) -> Optional[dict]:
    s = row.get("setup")
    if not s:
        return None
    g = s.get("geo") or {}
    buy = s["direction"] == "BUY"
    t = s["since"]
    end = s["validUntil"] + 4 * H1S
    zones, lines, markers = [], [], []
    if g.get("box"):
        hi, lo, t0, t1 = g["box"]
        zones.append(zone(f"AN-{sym}-ASIA-{t}", "ASIAN_BOX", t0, t1, hi, lo, "Asian range"))
    if g.get("pd"):
        pdh, pdl, t0 = g["pd"]
        lines.append(line(f"AN-{sym}-PDH-{t}", "PDH", t0, end, pdh, None, "PDH"))
        lines.append(line(f"AN-{sym}-PDL-{t}", "PDL", t0, end, pdl, None, "PDL"))
    if g.get("sweep"):
        lvl, ts = g["sweep"]
        lines.append(line(f"AN-{sym}-SWP-{t}", "SSL" if buy else "BSL", ts - 6 * M5S, end, lvl, None, "liquidity swept"))
    if g.get("ob"):
        top, bot, t0 = g["ob"]
        zones.append(zone(f"AN-{sym}-OB-{t}", "OB_BULL" if buy else "OB_BEAR", t0, end, top, bot, "H1 OB" if row["id"] == "A" else "flip zone",
                          mid=(top + bot) / 2))
    if g.get("candle"):
        hi, lo, t0 = g["candle"]
        zones.append(zone(f"AN-{sym}-SC-{t}", "OTE_GOLD_ZONE", t0, t0 + H1S, hi, lo, "single candle", mid=(hi + lo) / 2))
    if g.get("gap"):
        bot, top, t0 = g["gap"]
        zones.append(zone(f"AN-{sym}-FVG-{t}", "FVG_BULL" if buy else "FVG_BEAR", t0, end, top, bot, "M5 FVG · entry", mid=(top + bot) / 2))
    if g.get("eq") is not None:
        lines.append(line(f"AN-{sym}-EQ-{t}", "EQUILIBRIUM", t - 24 * H1S, end, g["eq"], None, "H1 50 %"))
    markers.append(marker(f"AN-{sym}-SMC-{t}", t - M5S, s["entry"], not buy, f"SMC {row['id']} {s['direction']}", BULL if buy else BEAR))
    status = "PENDING" if row["status"] in ("CONFIRMED", "BLOCKED") and not s.get("filled") else "OPEN"
    return {"label": f"SMC {row['id']} · {row['name']} · {s['direction']} LIMIT {s['entry']}", "family": "smc", "id": row["id"],
            "zones": zones, "priceLines": lines, "markers": markers,
            "tradeExecutionBox": _box(s["direction"], "LIMIT", status, t, s["entry"], s["sl"], s["tp"], s["rr"], price, pip)}


def scenario_drawing(sym: str, t: dict, now: int) -> dict:
    """One scenario on the chart: its trigger level, the entry zone, the stop and the target, as lines from now on."""
    buy = t["dir"] == "BUY"
    col = BULL if buy else BEAR
    t0, t1 = now - 10 * H1S, now + 12 * H1S  # from the last candles on: the labels sit inside the view
    side = "BUY" if buy else "SELL"
    tol = abs(t["entry"] - t["sl"]) * 0.1
    lines = [line(f"AN-{sym}-SC{side}-LVL", "MSS_BREAK", t0, t1, t["level"], None, f"{side} trigger", "DASHED", col),
             line(f"AN-{sym}-SC{side}-SL", "MSS_BREAK", t0, t1, t["sl"], None, f"{side} SL", "DOTTED", "#F43F5E"),
             line(f"AN-{sym}-SC{side}-TP", "MSS_BREAK", t0, t1, t["tp"], None, f"{side} TP", "DOTTED", "#10B981")]
    zones = [zone(f"AN-{sym}-SC{side}-Z", "FVG_BULL" if buy else "FVG_BEAR", t0, t1, t["entry"] + tol, t["entry"] - tol, f"{side} entry zone", mid=t["entry"])]
    return {"label": f"{side} scenario: {t['name']}", "family": "scenario", "id": side.lower(), "zones": zones, "priceLines": lines,
            "markers": [], "tradeExecutionBox": None}
