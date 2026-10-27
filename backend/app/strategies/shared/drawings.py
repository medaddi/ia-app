"""
Converts detector output into chart drawings, the way a trader marks a chart by hand:
few objects, most recent first, max `maxPerType` per type, higher-timeframe objects
prefixed with their timeframe ("H1 OB").
"""

from .jsnum import js_str, to_fixed
from .liquidity import Level, Sweep
from .sessions import SessionRange
from .structure import StructureEvent, Swing
from .zones import Fvg, OrderBlock


def _prefix(tf: str, chart_tf: str) -> str:
    return "" if tf == chart_tf else f"{tf} "


def _tail(items: list, n: int) -> list:
    """Array.slice(-n) (n = 0 keeps everything, like JS)."""
    return items[-n:] if n > 0 else list(items)


def structure_drawings(events: list[StructureEvent], tf: str, entry_tf: str, max_n: int) -> list[dict]:
    return [{
        "id": f"{tf}-{e.type}-{e.breakTime}", "layer": "structure", "kind": "hline", "tf": tf,
        "t1": e.pivotTime, "t2": e.breakTime, "p1": e.level,
        "text": f"{_prefix(tf, entry_tf)}{'CHoCH' if e.type == 'CHOCH' else 'BOS'}",
        "color": "bull" if e.direction == "BULLISH" else "bear",
        "style": "dashed" if e.type == "CHOCH" else "solid",
    } for e in _tail(events, max_n)]


def swing_drawings(swings: list[Swing], tf: str, max_n: int) -> list[dict]:
    return [{
        "id": f"{tf}-SW-{s.kind}-{s.time}", "layer": "swings", "kind": "label", "tf": tf,
        "t1": s.time, "t2": s.time, "p1": s.price, "text": s.label, "color": "muted",
        "position": "above" if s.kind == "HIGH" else "below",
    } for s in _tail([s for s in swings if s.label], max_n + 1)]


def fvg_drawings(fvgs: list[Fvg], tf: str, entry_tf: str, max_n: int) -> list[dict]:
    return [{
        "id": f.id, "layer": "fvg", "kind": "box", "tf": tf, "t1": f.startTime, "t2": f.mitigatedTime,
        "p1": f.top, "p2": f.bottom, "text": f"{_prefix(tf, entry_tf)}FVG",
        "color": "bull" if f.direction == "BULLISH" else "bear", "faded": f.state == "MITIGATED", "midline": True,
    } for f in _tail([f for f in fvgs if f.state != "FILLED"], max_n)]


def ob_drawings(obs: list[OrderBlock], tf: str, entry_tf: str, max_n: int) -> list[dict]:
    return [{
        "id": o.id, "layer": "ob", "kind": "box", "tf": tf, "t1": o.time, "t2": None, "p1": o.top, "p2": o.bottom,
        "text": f"{_prefix(tf, entry_tf)}{'Demand OB' if o.direction == 'BULLISH' else 'Supply OB'}",
        "color": "bull" if o.direction == "BULLISH" else "bear", "faded": o.state == "MITIGATED",
    } for o in _tail([o for o in obs if o.state != "BROKEN"], max_n)]


LEVEL_LAYER = {
    "PDH": "levels", "PDL": "levels", "PWH": "levels", "PWL": "levels",
    "ASIA_H": "liquidity", "ASIA_L": "liquidity", "PSH": "liquidity", "PSL": "liquidity",
    "EQH": "liquidity", "EQL": "liquidity", "ROUND": "levels", "SWING_H": "liquidity", "SWING_L": "liquidity",
}


def level_drawings(levels: list[Level]) -> list[dict]:
    return [{
        "id": f"LV-{lv.id}", "layer": LEVEL_LAYER[lv.kind], "kind": "hline", "tf": "", "t1": lv.time, "t2": None,
        "p1": lv.price, "text": lv.label,
        "color": "liquidity" if lv.kind in ("EQH", "EQL") else "muted",
        "style": "dotted" if lv.kind in ("EQH", "EQL", "ROUND") else "dashed",
    } for lv in levels]


def sweep_drawings(sweeps: list[Sweep], tf: str, max_n: int) -> list[dict]:
    return [{
        "id": s.id, "layer": "liquidity", "kind": "marker", "tf": tf, "t1": s.time, "t2": s.time, "p1": s.extreme,
        "text": "Sweep", "color": "gold", "position": "above" if s.level.side == "HIGH" else "below",
    } for s in _tail(sweeps, max_n)]


def session_drawings(sessions: list[SessionRange]) -> list[dict]:
    out = []
    for s in sessions:
        color = "asia" if s.name == "Asia" else "london" if s.name == "London" else "ny"
        out.append({"id": f"SES-{s.name}-{s.dateKey}", "layer": "sessions", "kind": "session", "tf": "", "t1": s.startSec, "t2": s.endSec,
                    "p1": s.high, "p2": s.low, "text": s.name, "color": color})
        if s.name == "Asia":
            out.append({"id": f"SES-AH-{s.dateKey}", "layer": "sessions", "kind": "box", "tf": "", "t1": s.startSec, "t2": s.endSec,
                        "p1": s.high, "p2": s.low, "text": "Asia range", "color": "asia"})
    return out


_EXIT_MARKERS = ("TP1", "TP2", "TP3", "SL", "BE_EXIT", "TRAIL_EXIT", "TIME_EXIT")


def trade_drawings(setup: dict, entry_tf: str, lot_text: str) -> list[dict]:
    bull = setup["direction"] == "BUY"
    t1 = setup["signalTime"]
    sid = setup["id"]
    # Box spans the life of the order: pending → until expiry; filled → until exit (open = right edge)
    lc = setup["lifecycle"]
    cancel = next((e for e in lc["events"] if e["type"] in ("CANCEL", "EXPIRE")), None)
    end = lc["exitTime"] if lc["fillTime"] is not None else cancel["time"] if cancel else setup["expiresAt"]
    # Set & forget (no breakeven): the box runs to the single target TP3
    single = setup.get("params", {}).get("breakeven", True) is False
    goal, goal_name = (setup["tp3"], "TP") if single else (setup["tp2"], "TP2")
    rr_text = f"1:{to_fixed(abs(goal - setup['entry']) / abs(setup['entry'] - setup['sl']), 1)}"
    s = js_str
    out = [
        {"id": f"TR-TP-{sid}", "layer": "trade", "kind": "box", "tf": entry_tf, "t1": t1, "t2": end, "p1": setup["entry"], "p2": goal, "text": f"{goal_name} {s(goal)} · {rr_text}", "color": "bull"},
        {"id": f"TR-SL-{sid}", "layer": "trade", "kind": "box", "tf": entry_tf, "t1": t1, "t2": end, "p1": setup["entry"], "p2": setup["sl"], "text": f"SL {s(setup['sl'])} · {s(setup['slPips'])}p" + (f" · {lot_text}" if lot_text else ""), "color": "bear"},
        {"id": f"TR-EN-{sid}", "layer": "trade", "kind": "hline", "tf": entry_tf, "t1": t1, "t2": end, "p1": setup["entry"], "text": f"Entry {s(setup['entry'])}", "color": "entry", "style": "solid"},
    ]
    if not single:  # one-target trades: TP1 / TP2 are only progress marks, the box already ends at the target
        out += [
            {"id": f"TR-T1-{sid}", "layer": "trade", "kind": "hline", "tf": entry_tf, "t1": t1, "t2": end, "p1": setup["tp1"], "text": f"TP1 {s(setup['tp1'])}", "color": "bull", "style": "dashed"},
            {"id": f"TR-T3-{sid}", "layer": "trade", "kind": "hline", "tf": entry_tf, "t1": t1, "t2": end, "p1": setup["tp3"], "text": f"TP3 {s(setup['tp3'])}", "color": "bull", "style": "dotted"},
        ]
    for e in lc["events"]:
        t = e["type"]
        if ((t == "FILL" and setup["entryType"] == "LIMIT") or t in _EXIT_MARKERS) and not (single and t in ("TP1", "TP2")):
            out.append({"id": f"TR-EV-{t}-{sid}", "layer": "trade", "kind": "marker", "tf": entry_tf, "t1": e["time"], "t2": None, "p1": e["price"],
                        "text": "Filled" if t == "FILL" else t.replace("_", " ", 1),
                        "color": "bear" if t == "SL" else "entry" if t == "FILL" else "bull",
                        "position": "below" if bull == (t == "SL") else "above"})
    return out


def declutter_zones(drawings: list[dict]) -> list[dict]:
    """
    Declutters zones like a trader would: when two boxes of the same layer and side overlap in
    price by more than half of the smaller one, only the newest is kept.
    """
    boxes = [d for d in drawings if d["kind"] == "box" and d["layer"] in ("fvg", "ob") and "p2" in d]
    drop: set[str] = set()
    ordered = sorted(boxes, key=lambda d: -d["t1"])  # newest first (stable)
    for i, a in enumerate(ordered):
        if a["id"] in drop:
            continue
        a_top, a_bot = max(a["p1"], a["p2"]), min(a["p1"], a["p2"])
        for b in ordered[i + 1:]:
            if b["id"] in drop or b["color"] != a["color"]:
                continue
            b_top, b_bot = max(b["p1"], b["p2"]), min(b["p1"], b["p2"])
            overlap = min(a_top, b_top) - max(a_bot, b_bot)
            if overlap > 0.5 * min(a_top - a_bot, b_top - b_bot):
                drop.add(b["id"])
    return [d for d in drawings if d["id"] not in drop]
