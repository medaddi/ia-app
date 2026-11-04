"""
The two scenarios of the Analyse button: what would make the pair a BUY, and what would make it a SELL, at that moment.

Every strategy says what it waits for on each side (its trigger: the level, the entry, the stop and the target its rules
would use, and what still blocks it: hours, ADX, trend side, killzone...). Each side keeps its best trigger, weighted by
  · the strategy's own test (a proven plan's unseen 40 %, an SMC strategy's last ~2 months of M5), never above its proof
  · how close price is to the trigger (in ATR)
  · whether it can fire now or still waits for its hours / filter
and the market context adds its points (H1 trend, H1 SMC structure, premium / discount). The side with more points is
the agent's preference; both scenarios stay on the table, because the market decides which trigger comes first.
"""

from typing import Optional

from ..strategies.shared.types import TF_SEC


def _in_hours(t: int, hours) -> bool:
    if not hours:
        return True
    h, (a, b) = (t // 3600) % 24, hours
    return a <= h < b if a < b else (h >= a or h < b)


def plan_triggers(ind, s: dict, spec: dict, price: float) -> list[dict]:
    """A proven plan's trigger on each side it can trade now: a close beyond the channel the NEXT candle is judged against."""
    c, p = ind.c, s["p"]
    last = len(c) - 1
    hi, lo = ind.channel(p["n"], last + 1)
    a = ind.a[last]
    if hi is None or not a:
        return []
    pip, d_ = spec["pipSize"], spec["decimals"]
    risk = p["sl"] * a
    nxt = c[last].time + TF_SEC[s["tf"]]
    blockers = []
    if p.get("hours") and not _in_hours(nxt, p["hours"]):
        blockers.append(f"trades {p['hours'][0]:02d}:00–{p['hours'][1]:02d}:00 GMT only")
    ax = ind.ax[last] or 0
    sides = []
    if s["fam"] == "breakout":
        e50, e200 = ind.e50[last], ind.e200[last]
        if e50 is None or e200 is None:
            return []
        if p.get("adx") and ax < p["adx"]:
            blockers.append(f"ADX {ax:.0f} < {p['adx']}")
        sides = [(1, hi, f"{s['tf']} close above {hi:.{d_}f}")] if e50 > e200 else [(-1, lo, f"{s['tf']} close below {lo:.{d_}f}")]
    else:
        if p.get("adx") and ax >= p["adx"]:
            blockers.append(f"ADX {ax:.0f} ≥ {p['adx']}: trend too strong")
        sides = [(1, lo, f"{s['tf']} close below {lo:.{d_}f}"), (-1, hi, f"{s['tf']} close above {hi:.{d_}f}")]
        if p.get("trend") and ind.e200[last] is not None:
            up = c[last].close > ind.e200[last]
            sides = [x for x in sides if (x[0] > 0) == up]
    out = []
    for d, lvl, word in sides:
        extra = []
        if p.get("rsi"):
            extra.append(f"with RSI(14) {'below ' + str(p['rsi']) if d > 0 else 'above ' + str(100 - p['rsi'])}")
        sl, tp = lvl - d * risk, lvl + d * s["rr"] * risk
        out.append({"family": "plan", "id": s["id"], "name": s["name"], "dir": "BUY" if d > 0 else "SELL",
                    "trigger": word + (" " + " ".join(extra) if extra else ""), "order": "MARKET at that close",
                    "level": lvl, "entry": lvl, "sl": sl, "tp": tp, "rr": s["rr"], "distPips": abs(price - lvl) / pip,
                    "blockers": blockers, "ready": not blockers, "maxHours": s["mb"] * (1 if s["tf"] == "H1" else 4),
                    "test": {"kind": "2 years, unseen 40 %", **s["test"]["unseen"]}})
    return out


def _quality(t: dict) -> float:
    """How much a trigger's own test backs it: expectancy per trade, bounded (a losing test counts very little)."""
    te = t["test"]
    n = te.get("trades") or 0
    if not n:
        return 0.15
    exp = (te.get("totalR") or 0) / n
    q = 0.5 + 3 * exp if t["family"] == "plan" else 0.3 + exp
    return max(0.1, min(1.5, q))


def build(triggers: list[dict], ctx: dict, price: float, atr_pips: Optional[float], dec: int) -> dict:
    atr = atr_pips or 1.0
    for t in triggers:
        prox = 1 / (1 + t["distPips"] / atr)
        t["weight"] = round(_quality(t) * prox * (1 if t["ready"] else 0.6), 3)
        for k in ("level", "entry", "sl", "tp"):
            t[k] = round(t[k], dec)
        t["distPips"] = round(t["distPips"], 1)
        t["rr"] = round(t["rr"], 2)
    out = {}
    for side in ("BUY", "SELL"):
        mine = sorted((t for t in triggers if t["dir"] == side), key=lambda t: -t["weight"])
        pts = []
        d = 1 if side == "BUY" else -1
        if ctx.get("trend"):
            pts.append(("H1 trend (EMA50 / 200) " + ctx["trend"], (1 if ctx["trend"] == "bullish" else -1) == d))
        if ctx.get("structure") in ("bullish", "bearish"):
            pts.append(("H1 SMC structure " + ctx["structure"], (1 if ctx["structure"] == "bullish" else -1) == d))
        if ctx.get("zone"):
            prem = "premium" in ctx["zone"]
            pts.append(("price " + ctx["zone"], prem == (d < 0)))
        score = sum(t["weight"] for t in mine[:3]) + 0.35 * sum(1 for _, ok in pts if ok)
        out[side.lower()] = {"side": side, "main": mine[0] if mine else None, "others": mine[1:4], "context": [{"label": a, "ok": ok} for a, ok in pts],
                             "supporters": len(mine), "score": round(score, 2)}
    b, s = out["buy"]["score"], out["sell"]["score"]
    tot = b + s or 1
    out["buyPct"] = round(100 * b / tot)
    out["sellPct"] = 100 - out["buyPct"]
    out["bias"] = "BUY" if out["buyPct"] >= 58 else "SELL" if out["sellPct"] >= 58 else "NEUTRAL"
    out["compare"] = sorted(triggers, key=lambda t: -t["weight"])
    return out
