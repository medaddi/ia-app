"""
Agent 1 · ZoneArchitect (blueprint 2.4): Weekly (150) and Daily (250) AOIs, and H4 (200) ones for the daily counter-weekly
scenario, from the True Elbows. Adaptive width W_max (ATR-bound), validity (>= 3 body pivots, or >= 2 with a flip, or >= 2
with 2 wick rejections), W + D fusion, the "every 500" level, suspension and flip, and the weekly runway.
"""

from ..config import (BREAK_ATR_H4, FLIP_MERGE_PIPS, MIN_BODY_TOUCHES, N_AOI, PSYCH_PIPS, TOUCH_GAP, WMAX)


def spaced(idx: list[int]) -> list[int]:
    out = []
    for q in sorted(idx):
        if not out or q - out[-1] >= TOUCH_GAP:
            out.append(q)
    return out


def wmax(tf: str, atr: float, pip: float, lam: float) -> float:
    """2.4.1: min(cap x lam x pip, max(floor x lam x pip, share x ATR14))."""
    cap, floor, share = WMAX[tf]
    return min(cap * lam * pip, max(floor * lam * pip, share * atr))


def build(st, i: int, pip: float, lam: float) -> list[dict]:
    """The valid AOIs of one timeframe at the close of candle i. The pivots are the True Elbows (body levels)."""
    tf = st.s.name
    if i < 10 or not st.atr[i]:
        return []
    lo_i = i - N_AOI[tf] + 1
    el = sorted(((p, j, kind) for j, kind, p in st.elbows_at(i) if j >= lo_i), key=lambda x: x[0])
    W = wmax(tf, st.atr[i], pip, lam)
    need_body = MIN_BODY_TOUCHES if tf != "H4" else 2
    cands = []
    for a in range(len(el)):
        for b in range(a, len(el)):
            if el[b][0] - el[a][0] > W:
                break
            grp = el[a:b + 1]
            hits = spaced([j for _, j, _ in grp])
            lo, hi = el[a][0], el[b][0]
            kinds = {k for _, j, k in grp if j in hits}
            flip = kinds == {1, -1}
            wick = spaced([j for j in range(max(lo_i, 0), i + 1) if j not in hits and (
                (st.c[j].high >= lo and st.B[j] < lo) or (st.c[j].low <= hi and st.Bm[j] > hi))])
            n = len(hits)
            valid = n >= need_body or (n >= 2 and flip) or (n >= 2 and len(wick) >= 2)
            if valid:
                cands.append({"lo": lo, "hi": hi, "touches": n, "hits": hits, "flip": flip, "roles": kinds, "tf": tf, "t0": st.c[hits[0]].time,
                              "wicks": len(wick)})
    # the best candidate of each neighbourhood: most touches, then the narrowest; the zones kept never overlap
    cands.sort(key=lambda z: (-z["touches"], z["hi"] - z["lo"]))
    out = []
    for z in cands:
        if all(z["hi"] < y["lo"] or z["lo"] > y["hi"] for y in out):
            out.append(z)
    return out


def merge(w: list[dict], d: list[dict], pip: float, lam: float, wmax_w: float) -> list[dict]:
    """2.4.2 (6): a W and a D AOI overlapping or within 15 lambda pips become one W+D zone (priority), bounded by W_max(W)."""
    gap = FLIP_MERGE_PIPS * lam * pip
    out, used = [], set()
    for zw in w:
        hit = [(q, zd) for q, zd in enumerate(d) if zw["lo"] - gap <= zd["hi"] and zd["lo"] <= zw["hi"] + gap]
        if not hit:
            out.append({**zw, "kind": "W", "tfs": {"W"}, "overlap": False, "sl_lo": zw["lo"], "sl_hi": zw["hi"]})
            continue
        for q, zd in hit:
            used.add(q)
            lo, hi = min(zw["lo"], zd["lo"]), max(zw["hi"], zd["hi"])
            base = {"touches": max(zw["touches"], zd["touches"]), "flip": zw["flip"] or zd["flip"], "roles": zw["roles"] | zd["roles"],
                    "t0": min(zw["t0"], zd["t0"]), "hits": zd["hits"], "wicks": zw["wicks"] + zd["wicks"], "tfs": {"W", "D"}, "overlap": True}
            if hi - lo <= wmax_w:
                out.append({**base, "lo": lo, "hi": hi, "kind": "W+D", "tf": "D", "sl_lo": lo, "sl_hi": hi})
            else:  # the Daily core nested in the Weekly envelope: the outer bounds protect the stop
                out.append({**base, "lo": zd["lo"], "hi": zd["hi"], "kind": "W+D", "tf": "D", "sl_lo": lo, "sl_hi": hi})
    for q, zd in enumerate(d):
        if q not in used:
            out.append({**zd, "kind": "D", "tfs": {"D"}, "overlap": False, "sl_lo": zd["lo"], "sl_hi": zd["hi"]})
    return out


def snap_500(z: dict, pip: float, lam: float, step: float, wmax_z: float) -> dict:
    """2.4.3: L = round(Z_mid / step) x step; valid inside the zone or within 5 lambda pips of an edge (the edge then widens to
    hold it while the width stays <= W_max)."""
    L = round(round((z["lo"] + z["hi"]) / 2 / step) * step, 6)
    tol = PSYCH_PIPS * lam * pip
    z["psych"] = None
    if z["lo"] <= L <= z["hi"]:
        z["psych"] = L
    elif z["lo"] - tol <= L <= z["hi"] + tol and max(z["hi"], L) - min(z["lo"], L) <= wmax_z:
        z["lo"], z["hi"], z["psych"] = min(z["lo"], L), max(z["hi"], L), L
        z["sl_lo"], z["sl_hi"] = min(z["sl_lo"], z["lo"]), max(z["sl_hi"], z["hi"])
    z["width_pips"] = round((z["hi"] - z["lo"]) / pip, 1)
    z["id"] = f"{z['kind']}-{round(z['lo'] / pip)}-{round(z['hi'] / pip)}"
    return z


def zone_map(st, idx: dict, pip: float, lam: float, step: float, with_h4: bool = False) -> list[dict]:
    """The zone map: W + D merged (always), the H4 zones too when the daily counter-weekly scenario can use them."""
    iw, id_ = idx["W"], idx["D"]
    if iw < 0 or id_ < 0:
        return []
    ww = wmax("W", st["W"].atr[iw] or 0, pip, lam)
    zs = merge(build(st["W"], iw, pip, lam), build(st["D"], id_, pip, lam), pip, lam, ww)
    if with_h4 and idx["H4"] >= 0:
        for z in build(st["H4"], idx["H4"], pip, lam):
            if all(z["hi"] < y["lo"] or z["lo"] > y["hi"] for y in zs):
                zs.append({**z, "kind": "H4", "tfs": {"D", "H4"}, "overlap": False, "sl_lo": z["lo"], "sl_hi": z["hi"]})
    out = []
    for z in zs:
        wz = wmax("W" if "W" in z["tfs"] else "D", st["W" if "W" in z["tfs"] else "D"].atr[iw if "W" in z["tfs"] else id_] or 0, pip, lam)
        out.append(snap_500(z, pip, lam, step, wz))
    return out


def dist_pips(P: float, z: dict, pip: float) -> float:
    return 0.0 if z["lo"] <= P <= z["hi"] else ((z["lo"] - P) if P < z["lo"] else (P - z["hi"])) / pip


def suspended(z: dict, d: int, dst, i_d: int, h4, i_4: int, pip: float) -> bool:
    """2.4.4: a Daily body close (or two consecutive H4 closes) beyond the AOI by 0.35 ATR14(H4) suspends it (a flip) until a
    body close back beyond its other edge. CHOICE: the last 60 D and 120 H4 candles are read."""
    m = BREAK_ATR_H4 * (h4.atr[i_4] or 0) if i_4 >= 0 else 0.0
    broke_d = None
    for j in range(max(0, i_d - 59), i_d + 1):
        cl = dst.C[j]
        if (d > 0 and cl < z["lo"] - m) or (d < 0 and cl > z["hi"] + m):
            broke_d = j
        elif broke_d is not None and ((d > 0 and cl > z["hi"]) or (d < 0 and cl < z["lo"])):
            broke_d = None
    if broke_d is not None:
        return True
    run = 0
    for j in range(max(0, i_4 - 119), i_4 + 1):
        cl = h4.C[j]
        if (d > 0 and cl < z["lo"] - m) or (d < 0 and cl > z["hi"] + m):
            run += 1
        elif (d > 0 and cl > z["hi"]) or (d < 0 and cl < z["lo"]):
            run = 0
    return run >= 2


def opposing_weekly(zones: list[dict], active: dict, d: int, entry: float):
    """The nearest Weekly AOI beyond the entry along the trade, and the runway to its near edge."""
    ahead = [z for z in zones if "W" in z["tfs"] and z is not active and ((z["lo"] > entry) if d > 0 else (z["hi"] < entry))]
    if not ahead:
        return None, None
    z = min(ahead, key=lambda q: q["lo"]) if d > 0 else max(ahead, key=lambda q: q["hi"])
    return z, ((z["lo"] - entry) if d > 0 else (entry - z["hi"]))


def polarity_ok(z: dict, d: int) -> bool:
    """2.4: a buy zone has acted as support (a body-low pivot), a sell zone as resistance (a body-high pivot), or as both (flip)."""
    return (-d) in z["roles"] or z["flip"]
