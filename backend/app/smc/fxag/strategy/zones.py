"""
Agent 3 · ZoneArchitect (spec 3.3, 3.4.2): Weekly and Daily AOIs from structural body touches (>= 3, at least 3 bars
apart, at most 60 lambda pips wide, the narrowest cluster holding >= 80 % of the local touches), polarity, W + D merging,
the "every 500" snap, the live 5-pip proximity rule, the break-and-retest suspension and the opposing-Weekly No-Trap rule.
"""

import math

from ..config import BREAK_PIPS, CAPTURE, DELTA_PIPS, MIN_TOUCHES, N_AOI, PROX_PIPS, TOUCH_GAP, W_MAX_PIPS


def spaced(idx: list[int]) -> list[int]:
    out = []
    for q in sorted(idx):
        if not out or q - out[-1] >= TOUCH_GAP:
            out.append(q)
    return out


def build(st, i: int, pip: float, lam: float) -> list[dict]:
    """3.3.1 on one timeframe (W or D) at the close of candle i. CHOICE: the "structural body touches" are the body
    pivots (Step 1 swings) of the lookback, a swing low = a support touch, a swing high = a resistance touch."""
    if i < 10:
        return []
    tf = st.s.name
    lo_i = i - N_AOI[tf] + 1
    pts = sorted(((p, j, kind) for j, kind, p in st.swings if j >= lo_i and j + st.k <= i), key=lambda x: x[0])
    wmax, dlt = W_MAX_PIPS * lam * pip, DELTA_PIPS * lam * pip

    def touches(a: float, b: float):
        g = [(j, kind) for p, j, kind in pts if a - dlt <= p <= b + dlt]
        hits = spaced([j for j, _ in g])
        return hits, {kind for j, kind in g if j in hits}
    cands = []
    for a in range(len(pts)):
        top = [p for p, _, _ in pts[a:] if p <= pts[a][0] + wmax]
        full, _ = touches(pts[a][0], top[-1])
        need = max(MIN_TOUCHES, math.ceil(CAPTURE * len(full)))
        if len(full) < MIN_TOUCHES:
            continue
        for b in top:  # the narrowest cluster capturing >= 80 % of the local touches
            hits, roles = touches(pts[a][0], b)
            if len(hits) >= need:
                cands.append({"lo": pts[a][0], "hi": b, "touches": len(hits), "hits": hits, "roles": roles, "tf": tf,
                              "t0": st.c[hits[0]].time})
                break
    cands.sort(key=lambda z: (-z["touches"], z["hi"] - z["lo"]))
    out = []
    for z in cands:
        if all(z["hi"] < y["lo"] or z["lo"] > y["hi"] for y in out):
            out.append(z)
    return out


def merge(w: list[dict], d: list[dict], pip: float, lam: float) -> list[dict]:
    """3.3.2: an overlapping W and D AOI merge into one Priority Combined Zone when the union is <= W_max; otherwise the
    Daily core stays, nested in the Weekly envelope (overlap_flag), the outer Weekly bounds protecting the stop."""
    wmax = W_MAX_PIPS * lam * pip
    out, used = [], set()
    for zw in w:
        hit = [(q, zd) for q, zd in enumerate(d) if zw["lo"] <= zd["hi"] and zd["lo"] <= zw["hi"]]
        if not hit:
            out.append({**zw, "tfs": {"W"}, "kind": "W", "sl_lo": zw["lo"], "sl_hi": zw["hi"], "overlap": False})
            continue
        for q, zd in hit:
            used.add(q)
            lo, hi = min(zw["lo"], zd["lo"]), max(zw["hi"], zd["hi"])
            base = {"touches": max(zw["touches"], zd["touches"]), "roles": zw["roles"] | zd["roles"], "tfs": {"W", "D"},
                    "t0": min(zw["t0"], zd["t0"]), "hits": zd["hits"], "tf": "D", "overlap": True}
            if hi - lo <= wmax:
                out.append({**base, "lo": lo, "hi": hi, "kind": "W+D_MERGED", "sl_lo": lo, "sl_hi": hi})
            else:
                out.append({**base, "lo": zd["lo"], "hi": zd["hi"], "kind": "D_IN_W", "sl_lo": lo, "sl_hi": hi})
    for q, zd in enumerate(d):
        if q not in used:
            out.append({**zd, "tfs": {"D"}, "kind": "D", "sl_lo": zd["lo"], "sl_hi": zd["hi"], "overlap": False})
    return out


def snap_500(z: dict, pip: float, lam: float, step: float) -> dict:
    """3.4.2.1: L = round(Z_mid / step) * step; inside the zone: valid; within 5 lambda pips of an edge: the zone widens to
    hold it when its width stays <= W_max; otherwise no psych level."""
    L = round(round((z["lo"] + z["hi"]) / 2 / step) * step, 6)
    tol, wmax = PROX_PIPS * lam * pip, W_MAX_PIPS * lam * pip
    z["psych"] = None
    if z["lo"] <= L <= z["hi"]:
        z["psych"] = L
    elif min(abs(L - z["lo"]), abs(L - z["hi"])) <= tol and max(z["hi"], L) - min(z["lo"], L) <= wmax:
        z["lo"], z["hi"], z["psych"] = min(z["lo"], L), max(z["hi"], L), L
        z["sl_lo"], z["sl_hi"] = min(z["sl_lo"], z["lo"]), max(z["sl_hi"], z["hi"])
    z["width_pips"] = round((z["hi"] - z["lo"]) / pip, 1)
    z["id"] = f"{z['kind']}-{round(z['lo'] / pip)}-{round(z['hi'] / pip)}"
    return z


def zone_map(w, d, iw: int, id_: int, pip: float, lam: float, step: float) -> list[dict]:
    """ZoneMap: the merged W / D AOIs with their psych level."""
    return [snap_500(z, pip, lam, step) for z in merge(build(w, iw, pip, lam), build(d, id_, pip, lam), pip, lam)]


def dist_pips(P: float, z: dict, pip: float) -> float:
    """3.3.3: 0 inside the zone, else the distance to its nearest edge in pips."""
    return 0.0 if z["lo"] <= P <= z["hi"] else ((z["lo"] - P) if P < z["lo"] else (P - z["hi"])) / pip


def polarity_ok(z: dict, d: int) -> bool:
    """3.3.1: support for buys (a swing-low touch, role -1), resistance for sells (a swing-high touch, role +1); an S/R
    flip has both and serves either side."""
    return -d in z["roles"]


def suspended(z: dict, d: int, dst, i_d: int, wst, i_w: int, pip: float, lam: float) -> bool:
    """3.3.3: a D or W body close decisively through the zone (5 lambda pips beyond its far edge) suspends it until a
    body close back beyond the other edge (the break and retest). CHOICE: the last 60 D and 20 W candles are read."""
    m = BREAK_PIPS * lam * pip
    for st, i, n in ((dst, i_d, 60), (wst, i_w, 20)):
        broke = None
        for j in range(max(0, i - n + 1), i + 1):
            cl = st.C[j]
            if (d > 0 and cl < z["lo"] - m) or (d < 0 and cl > z["hi"] + m):
                broke = j
            elif broke is not None and ((d > 0 and cl > z["hi"]) or (d < 0 and cl < z["lo"])):
                broke = None
        if broke is not None:
            return True
    return False


def opposing_weekly(zones: list[dict], active: dict, d: int, entry: float):
    """3.3.4: the nearest Weekly AOI along the path to the target (beyond the entry), and the runway to it."""
    ahead = [z for z in zones if "W" in z["tfs"] and z is not active and ((z["lo"] > entry) if d > 0 else (z["hi"] < entry))]
    if not ahead:
        return None, None
    z = min(ahead, key=lambda q: q["lo"]) if d > 0 else max(ahead, key=lambda q: q["hi"])
    return z, ((z["lo"] - entry) if d > 0 else (entry - z["hi"]))
