"""
Agent 5 · EntrySniper (spec 3.5): on Tier-1 pairs only. Step 1: the cleanest lower-timeframe Shift of Structure on
M15 / M30 / H1 (a body close beyond the last LTF LH / HL after the counter-trend swing into the AOI), valid 12 hours,
void once its swing extreme breaks. Step 2: an Engulfing on H1 / H2 / H4 (the higher timeframe preferred) with a body
>= 55 % of its range. The anti-chase rule turns a huge engulfing (> 2.2 ATR14) or one whose close gives R:R < 2.0 into a
6-hour limit at the middle of its body, when that price is within 10 lambda pips of the AOI and gives R:R >= 2.2.
"""

from .structure import bm, bp
from .confluence import engulfing
from ..config import BODY_RATIO, ENTRY_TFS, GAP_PIPS, HUGE_ATR, LIMIT_AOI_PIPS, LIMIT_RR, MIN_RR, PROX_PIPS, SOS_TFS, SOS_VALID_SEC
from .zones import dist_pips


def find_sos(st, T: int, z: dict, d: int, pip: float, lam: float) -> dict | None:
    """The latest SoS of direction d on this timeframe closed in [T - 12 h, T], whose counter-trend swing touched the AOI
    (+-5 lambda pips), never broken since. Returns its level, time, swing extreme and clarity Phi."""
    s_ser = st.s
    i = s_ser.idx(T)
    if i < 5:
        return None
    m = PROX_PIPS * lam * pip
    for s in range(i, -1, -1):
        if s_ser.tc[s] < T - SOS_VALID_SEC:
            return None
        ev = st.shift_at.get(s)
        if not ev or ev[0] != d:
            continue
        # the counter-trend leg: back to the last opposite shift (or 96 candles, CHOICE)
        start = max(0, s - 96)
        for q in range(s - 1, start - 1, -1):
            e2 = st.shift_at.get(q)
            if e2 and e2[0] == d:
                start = q
                break
        touch = next((q for q in range(start, s + 1) if st.c[q].low <= z["hi"] + m and st.c[q].high >= z["lo"] - m), None)
        if touch is None:
            return None
        seg = st.c[touch:s + 1]
        ext = min(x.low for x in seg) if d > 0 else max(x.high for x in seg)
        if any((st.c[q].low < ext) if d > 0 else (st.c[q].high > ext) for q in range(s + 1, i + 1)):
            return None  # the swing extreme broke: the SoS is void
        lv = ev[1]
        clean = sum(1 for e in st.elbows_at(s) if touch - 24 <= e[0] <= s)
        lh_i = max([e[0] for e in st.elbows_at(s) if e[1] == -d * -1 and abs(e[2] - lv) < 1e-12] or [touch])
        wick = sum(1 for q in range(lh_i + 1, s) if ((st.c[q].high > lv and st.C[q] <= lv) if d > 0 else (st.c[q].low < lv and st.C[q] >= lv)))
        return {"tf": s_ser.name, "index": s, "time": s_ser.tc[s], "level": lv, "extreme": ext, "touch": s_ser.t[touch],
                "phi": round(clean / (1 + wick), 3), "wick_violations": wick, "clean_elbows": clean}
    return None


def best_sos(sts: dict, T: int, z: dict, d: int, pip: float, lam: float) -> dict | None:
    """Step 1: of M15 / M30 / H1, the SoS with the highest Structural Clarity Phi (the higher timeframe on a tie)."""
    found = [x for x in (find_sos(sts[tf], T, z, d, pip, lam) for tf in SOS_TFS if tf in sts and len(sts[tf].c)) if x]
    return max(found, key=lambda x: (x["phi"], SOS_TFS.index(x["tf"]))) if found else None


def engulf_at(sts: dict, T: int, d: int, pip: float, lam: float, after: int) -> dict | None:
    """Step 2: an Engulfing (3.4.4) with body / range >= 0.55 on a candle of H4, H2 or H1 closing exactly at T and after
    the SoS (`after`); the higher timeframe preferred."""
    gap = GAP_PIPS * lam * pip
    for tf in ENTRY_TFS:
        st = sts[tf]
        j = st.s.idx(T)
        if j < 1 or st.s.tc[j] != T or T < after:
            continue
        p, x = st.c[j - 1], st.c[j]
        r = x.high - x.low
        if r > 0 and engulfing(p, x, d, gap) and abs(x.close - x.open) / r >= BODY_RATIO:
            return {"tf": tf, "index": j, "candle": x, "atr": st.atr[j] or 0, "time": T}
    return None


def order(eng: dict, z: dict, d: int, plan_at, pip: float, lam: float) -> dict | None:
    """The anti-chase rule: market at the close when the candle is normal (R <= 2.2 ATR14) and R:R >= 2.0; otherwise the
    6-hour limit at the body's middle when it is within 10 lambda pips of the AOI and R:R >= 2.2; otherwise nothing."""
    x = eng["candle"]
    huge = eng["atr"] > 0 and x.high - x.low > HUGE_ATR * eng["atr"]
    mk = plan_at(x.close)
    if mk and not huge and mk["rr"] >= MIN_RR:
        return {**mk, "market": True, "orderType": "MARKET", "huge": False}
    mid = (x.open + x.close) / 2
    if dist_pips(mid, z, pip) > LIMIT_AOI_PIPS * lam:
        return {"reject": "ERR_LIMIT_FAR_FROM_AOI", "huge": huge, "rr_close": mk["rr"] if mk else None}
    lim = plan_at(mid)
    if not lim or lim["rr"] < LIMIT_RR:
        return {"reject": "ERR_RR_BELOW_2", "huge": huge, "rr_close": mk["rr"] if mk else None}
    return {**lim, "market": False, "orderType": "LIMIT_PULLBACK", "huge": huge}


_ = (bp, bm)
