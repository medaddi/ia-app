"""
Agent 1 · entry (blueprint 2.6): the Shift of Structure on M15 / M30 / H1 (a body close beyond the last micro LH / HL by
0.5 pip, after the counter-trend swing that touched the AOI), the clean engulfing on M30 / H1 / H2 / H4, and the three
execution models:
  E1  SoS, then a pullback (1-8 candles of the engulfing timeframe), then the engulfing  -> MARKET
  E2  an H1 / H2 / H4 engulfing that closes beyond the last M15 / M30 micro LH / HL itself (the SoS is inside it) -> MARKET
  E3  a huge engulfing (> 1.6 ATR14) or one whose close gives R:R < 2.0 while the 50 % limit gives >= 2.2 -> LIMIT, 8 h
"""

from ..config import (E1_MAX_CANDLES, ENG_TFS, HUGE_BODY_ATR, LIMIT_RR, MIN_RR, PROX_ATR_H1, PROX_PIPS, SOS_VALID_SEC)
from .confluence import body, engulfing

SOS_FOR = {"M30": ("M15", "M30"), "H1": ("M15", "M30"), "H2": ("M15", "M30", "H1"), "H4": ("M30", "H1")}
STEP = {"M15": 900, "M30": 1800, "H1": 3600, "H2": 7200, "H4": 14400}


def prox(h1, i1: int, pip: float, lam: float) -> float:
    """delta_prox = max(5 lambda pips, 0.25 ATR14(H1)): the tolerance of the contact with the AOI (the rejection point)."""
    return max(PROX_PIPS * lam * pip, PROX_ATR_H1 * ((h1.atr[i1] or 0) if i1 >= 0 else 0))


def find_sos(st, T: int, z: dict, d: int, dprox: float, max_age: int = SOS_VALID_SEC) -> dict | None:
    """The latest SoS of direction d on this timeframe closed in [T - max_age, T] whose counter-trend swing touched the AOI
    (within delta_prox), with the swing extreme P_anchor and it never broken since. Phi = clean elbows / (1 + wick violations)."""
    ser = st.s
    i = ser.idx(T)
    if i < 5:
        return None
    for s in range(i, -1, -1):
        if ser.tc[s] < T - max_age:
            return None
        ev = st.shift_at.get(s)
        if not ev or ev[0] != d:
            continue
        start = max(0, s - 96)
        for q in range(s - 1, start - 1, -1):
            e2 = st.shift_at.get(q)
            if e2 and e2[0] == d:
                start = q
                break
        touch = next((q for q in range(start, s + 1) if st.c[q].low <= z["hi"] + dprox and st.c[q].high >= z["lo"] - dprox), None)
        if touch is None:
            return None
        seg = st.c[touch:s + 1]
        ext = min(x.low for x in seg) if d > 0 else max(x.high for x in seg)
        if any((st.c[q].low < ext) if d > 0 else (st.c[q].high > ext) for q in range(s + 1, i + 1)):
            return None  # the anchor broke: the SoS is void
        lv = ev[1]
        clean = sum(1 for e in st.elbows_at(s) if touch - 24 <= e[0] <= s)
        wick = sum(1 for q in range(touch, s) if ((st.c[q].high > lv and st.C[q] <= lv) if d > 0 else (st.c[q].low < lv and st.C[q] >= lv)))
        return {"tf": ser.name, "index": s, "time": ser.tc[s], "level": lv, "extreme": ext, "touch": ser.t[touch],
                "phi": round(clean / (1 + wick), 3), "wick_violations": wick, "clean_elbows": clean}
    return None


def best_sos(sts: dict, T: int, z: dict, d: int, dprox: float, tfs=("M15", "M30", "H1")) -> dict | None:
    """Of the allowed timeframes, the SoS with the highest structural clarity Phi (the higher timeframe on a tie)."""
    found = [x for x in (find_sos(sts[tf], T, z, d, dprox) for tf in tfs if len(sts[tf].c)) if x]
    return max(found, key=lambda x: (x["phi"], STEP[x["tf"]])) if found else None


def triggers(sts: dict, T: int, z: dict, d: int, dprox: float) -> list[dict]:
    """The clean engulfings closing exactly at T on M30 / H1 / H2 / H4, each with its model (E1 / E2) and the SoS that arms it;
    the higher timeframe first. E3 is decided with the plan (order())."""
    out = []
    for tf in reversed(ENG_TFS):
        st = sts[tf]
        j = st.s.idx(T)
        if j < 3 or st.s.tc[j] != T or not engulfing(st.c, j, d, st.atr[j] or 0):
            continue
        x = st.c[j]
        e2 = None
        # E2 "imprime un Engulfing propre depuis l'AOI": the engulfing candle or one of the 3 before it touches the AOI
        from_aoi = any(st.c[q].low <= z["hi"] + dprox and st.c[q].high >= z["lo"] - dprox for q in range(max(0, j - 3), j + 1))
        if False and tf in ("H1", "H2", "H4") and from_aoi:  # E2 (disabled: 16% win in the 60-day test): the engulfing's own close shifts the M15 / M30 structure
            for ltf in ("M15", "M30"):
                s = find_sos(sts[ltf], T, z, d, dprox, max_age=STEP[tf])
                if s and s["time"] > T - STEP[tf] and (e2 is None or s["phi"] > e2["phi"]):
                    e2 = s
        e1 = None
        for ltf in SOS_FOR[tf]:
            s = find_sos(sts[ltf], T - 1, z, d, dprox)  # a SoS closed BEFORE the engulfing
            if s and s["time"] <= T - STEP[tf] // 2 and T - s["time"] <= E1_MAX_CANDLES * STEP[tf] and (e1 is None or s["phi"] > e1["phi"]):
                e1 = s
        if e1:
            out.append({"model": "E1", "eng_tf": tf, "eng_index": j, "candle": x, "atr": st.atr[j] or 0, "sos": e1})
    return out


def order(tr: dict, d: int, plan_at, h4_atr: float) -> dict:
    """E3: the huge-engulfing rule. Market at the close when the candle is normal (body <= 1.6 ATR14) and R:R >= 2.0; else a LIMIT
    at the 50 % retracement of the body (valid 8 h) when its R:R >= 2.2; else nothing."""
    x = tr["candle"]
    huge = tr["atr"] > 0 and body(x) > HUGE_BODY_ATR * tr["atr"]
    mk = plan_at(x.close)
    if mk and not huge and mk["rr"] >= MIN_RR:
        return {**mk, "orderType": "MARKET", "market": True, "huge": False, "model": tr["model"]}
    lim_px = x.close - 0.5 * (x.close - x.open)
    lim = plan_at(lim_px)
    if lim and lim["rr"] >= LIMIT_RR and (huge or (mk is not None and mk["rr"] < MIN_RR)):
        return {**lim, "orderType": "LIMIT_PULLBACK", "market": False, "huge": huge, "model": "E3"}
    return {"reject": "RR_BELOW_MIN", "huge": huge, "rr_close": mk["rr"] if mk else None}
