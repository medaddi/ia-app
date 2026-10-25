import math

from .jsnum import js_div, js_round, round_to


def lot_size(spec: dict, equity: float, risk_pct: float, entry: float, sl: float) -> float:
    """Lot size for a fixed % risk: (equity × risk%) / (SL distance × contract size), rounded DOWN to the lot step."""
    risk_per_lot = abs(entry - sl) * spec["contractSize"]
    if not (risk_per_lot > 0):
        return 0
    raw = (equity * risk_pct) / 100 / risk_per_lot
    lots = math.floor(raw / spec["lotStep"] + 1e-9) * spec["lotStep"]
    return round_to(lots, 2) if lots >= spec["minLot"] else 0


def lot_table(spec: dict, entry: float, sl: float, risk_pct: float, balances: list[int]) -> dict:
    return {f"{b}$": lot_size(spec, b, risk_pct, entry, sl) for b in balances}


def rr(entry: float, sl: float, tp: float) -> float:
    risk = abs(entry - sl)
    return abs(tp - entry) / risk if risk > 0 else 0


def to_pips(spec: dict, distance: float) -> float:
    return js_round((abs(distance) / spec["pipSize"]) * 10) / 10


def score_checklist(items: list[dict]) -> float:
    """Score = Σ weight × quality / Σ weight × 100 (quality 0-1, defaults to passed ? 1 : 0)."""
    total = 0
    got = 0
    for i in items:
        total += i["weight"]
    for i in items:
        q = i.get("quality")
        got += i["weight"] * (1 if q is None else q) if i["passed"] else 0
    if not total > 0:
        return 0
    s = js_round(js_div(got, total) * 100)
    return int(s) if math.isfinite(s) else s


def classify(score: float, required_ok: bool, thresholds: dict) -> str:
    if not required_ok:
        return "NO_TRADE"
    if score >= thresholds["signal"]:
        return "SIGNAL"
    if score >= thresholds["watch"]:
        return "WATCH"
    return "IGNORE"
