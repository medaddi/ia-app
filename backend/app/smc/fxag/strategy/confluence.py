"""
Agent 1 · confluence (blueprint 2.5): the Perfect Trade Checklist scored out of 100 over the AOI interaction window
W_AOI (from the last valid contact with the AOI, at most 12 H1 / 6 H4 candles back, to the trigger): 8 independent criteria
C1..C8, then the grade A+ (>= 85), A (75-84), B+ (68-74: only in the full sync with R:R >= 2.5), below 68: rejected.
"""

from ..config import (EMA_CLOSE_ATR, EMA_TOL_ATR, ENG_BODY_ATR, ENG_BODY_RANGE, ENG_OPP_WICK, ENG_TOL_BODY, GRADE_A, GRADE_A_PLUS, GRADE_BP,
                      PATTERN_GAP, PATTERN_TOL_ATR, PREV_TOL_ATR, PSYCH_PIPS, REJ_WICK, W_C1, W_C2_H4, W_C2_MERGED, W_C2_STRONG, W_C3,
                      W_C4, W_C5, W_C6, W_C7, W_C8)


def body(x) -> float:
    return abs(x.close - x.open)


def bp(x) -> float:
    return max(x.open, x.close)


def bm(x) -> float:
    return min(x.open, x.close)


# ---- 2.6 a clean engulfing
def engulfing(c: list, j: int, d: int, atr: float) -> bool:
    """Candle j engulfs in body the previous candle (or the two previous candles of a pause: a multi-bar engulfing), with the
    0.15-body gap tolerance, a momentum body (>= 0.55 ATR14 and >= 50 % of its range) and no massive opposite wick (<= 30 %)."""
    if j < 2 or not atr:
        return False
    x = c[j]
    rg = x.high - x.low
    if rg <= 0 or (d > 0 and x.close <= x.open) or (d < 0 and x.close >= x.open):
        return False
    if body(x) < ENG_BODY_ATR * atr or body(x) / rg < ENG_BODY_RANGE:
        return False
    if d > 0 and (x.high - bp(x)) / rg > ENG_OPP_WICK or d < 0 and (bm(x) - x.low) / rg > ENG_OPP_WICK:
        return False
    for n in (1, 2):  # the previous candle, or the last two (a multi-bar engulfing)
        prev = c[j - n:j]
        if n == 1 and ((d > 0 and prev[0].close > prev[0].open) or (d < 0 and prev[0].close < prev[0].open)):
            continue
        hi, lo = max(bp(q) for q in prev), min(bm(q) for q in prev)
        tol = ENG_TOL_BODY * body(prev[-1])
        if d > 0 and x.close > hi and x.open <= lo + tol:
            return True
        if d < 0 and x.close < lo and x.open >= hi - tol:
            return True
    return False


def pin(x, d: int) -> bool:
    rg = x.high - x.low
    if rg <= 0:
        return False
    return ((bm(x) - x.low) / rg >= REJ_WICK and body(x) <= rg / 3) if d > 0 else ((x.high - bp(x)) / rg >= REJ_WICK and body(x) <= rg / 3)


def doji_rej(x, d: int) -> bool:
    rg = x.high - x.low
    return rg > 0 and body(x) <= 0.12 * rg and ((bm(x) - x.low) / rg >= 0.5 if d > 0 else (x.high - bp(x)) / rg >= 0.5)


def window_start(h1, i: int, z: dict, d: int, prox: float) -> int | None:
    """W_AOI: the index of the first of the last 12 H1 candles from which the price stayed in contact with the AOI up to the
    last valid contact (None when no candle of the last 12 touched it within prox)."""
    lo = max(0, i - 11)
    contact = [j for j in range(lo, i + 1) if h1.c[j].low <= z["hi"] + prox and h1.c[j].high >= z["lo"] - prox]
    return contact[0] if contact else None


def tf_candles(st, t_from: int, i: int, n_min: int = 2) -> list[int]:
    """The candles of a timeframe that overlap the window: those closing after t_from, and at least the last n_min."""
    out = [j for j in range(max(0, i - 12), i + 1) if st.s.tc[j] > t_from]
    return out if len(out) >= n_min else list(range(max(0, i - n_min + 1), i + 1))


def c3_ema(sts, idx, t_from, z, d, atr_by) -> str | None:
    """EMA50 rejection on W, D, H4 or H1: BUY L <= EMA + 0.25 ATR and C >= EMA - 0.15 ATR (the EMA flat or rising)."""
    for tf in ("W", "D", "H4", "H1"):
        st, i = sts[tf], idx[tf]
        for j in tf_candles(st, t_from, i):
            e, a = st.e50[j], st.atr[j]
            if e is None or not a or j < 1 or st.e50[j - 1] is None:
                continue
            x = st.c[j]
            slope_ok = (e >= st.e50[j - 1] - 0.05 * a) if d > 0 else (e <= st.e50[j - 1] + 0.05 * a)
            if d > 0 and x.low <= e + EMA_TOL_ATR * a and x.close >= e - EMA_CLOSE_ATR * a and slope_ok:
                return tf
            if d < 0 and x.high >= e - EMA_TOL_ATR * a and x.close <= e + EMA_CLOSE_ATR * a and slope_ok:
                return tf
    return None


def c4_prev(sts, idx, z, d) -> str | None:
    """C4: the AOI is an old structure pivot, broken and retested (old HH -> new HL for a buy, old LL -> new LH for a sell)
    within 0.35 ATR14(D). The pivot is a high elbow (low for a sell) of D or W that price has since closed beyond."""
    st = sts["D"]
    i = idx["D"]
    a = st.atr[i] or 0
    tol = PREV_TOL_ATR * a
    for tf in ("D", "W"):
        s2, i2 = sts[tf], idx[tf]
        for j, kind, p in s2.elbows_at(i2):
            if kind != d or not (z["lo"] - tol <= p <= z["hi"] + tol):
                continue
            later = s2.C[j + 1:i2 + 1]
            if later and ((max(later) > p) if d > 0 else (min(later) < p)):
                return tf
    return None


def c6_rejection(sts, idx, t_from, z, d) -> str | None:
    """C6: on H4 / H2 / H1 inside the window: a rejection wick >= 45 % of the range, a pin bar, a rejection doji, or a liquidity
    sweep (the wick pierces the AOI far edge, the close is back inside or beyond)."""
    for tf in ("H4", "H2", "H1"):
        st, i = sts[tf], idx[tf]
        for j in tf_candles(st, t_from, i):
            x = st.c[j]
            rg = x.high - x.low
            if rg <= 0:
                continue
            wick = (bm(x) - x.low) if d > 0 else (x.high - bp(x))
            if wick / rg >= REJ_WICK and ((x.close >= x.open) if d > 0 else (x.close <= x.open)):
                return f"{tf} wick"
            if pin(x, d) or doji_rej(x, d):
                return f"{tf} pin"
            if (d > 0 and x.low < z["lo"] and x.close >= z["lo"]) or (d < 0 and x.high > z["hi"] and x.close <= z["hi"]):
                return f"{tf} sweep"
    return None


def c7_pattern(sts, idx, z, d, pip) -> str | None:
    """C7: a double bottom / top (two pivots 4-35 candles apart inside the AOI, within 0.40 ATR) or a (inverse) head & shoulders
    whose neckline meets the AOI, on D, H4 or H1, with a body close beyond the neckline."""
    for tf in ("D", "H4", "H1"):
        st, i = sts[tf], idx[tf]
        a = st.atr[i] or 0
        if not a:
            continue
        m = PATTERN_TOL_ATR * a
        sw = [(j, p) for j, kind, p in st.elbows_at(i) if kind == -d and i - 80 <= j]
        for t in range(len(sw) - 1, 0, -1):
            (a1, p1), (b1, p2) = sw[t - 1], sw[t]
            if not (PATTERN_GAP[0] <= b1 - a1 <= PATTERN_GAP[1]) or abs(p1 - p2) > m:
                continue
            if not (z["lo"] - m <= p1 <= z["hi"] + m or z["lo"] - m <= p2 <= z["hi"] + m):
                continue
            mid = st.B[a1 + 1:b1] if d > 0 else st.Bm[a1 + 1:b1]
            if not mid:
                continue
            neck = max(mid) if d > 0 else min(mid)
            if any((st.C[q] > neck) if d > 0 else (st.C[q] < neck) for q in range(b1 + 1, i + 1)):
                return f"{tf} {'Double bottom' if d > 0 else 'Double top'}"
        for t in range(len(sw) - 1, 1, -1):
            (a1, s1), (b1, hd), (c1, s2) = sw[t - 2], sw[t - 1], sw[t]
            head = hd < min(s1, s2) if d > 0 else hd > max(s1, s2)
            if not head:
                continue
            mid = st.B[a1 + 1:c1] if d > 0 else st.Bm[a1 + 1:c1]
            if not mid:
                continue
            neck = max(mid) if d > 0 else min(mid)
            if abs(s1 - s2) <= 0.5 * abs(neck - hd) and z["lo"] - m <= neck <= z["hi"] + m and \
                    any((st.C[q] > neck) if d > 0 else (st.C[q] < neck) for q in range(c1 + 1, i + 1)):
                return f"{tf} {'Inverse H&S' if d > 0 else 'H&S'}"
    return None


def c5_psych(z, h1, i, win_start, pip, lam) -> bool:
    """C5: a valid "500" level in the AOI (or within 5 lambda pips), counted once."""
    return z.get("psych") is not None


def grade_of(total: int, scenario: str | None = None, rr: float | None = None) -> str:
    """A+ >= 85, A 75-84, B+ 68-74 only in the full sync (M1) with R:R >= 2.5 (given), else C (rejected)."""
    if total >= GRADE_A_PLUS:
        return "A+"
    if total >= GRADE_A:
        return "A"
    if total >= GRADE_BP:
        return "B+" if (scenario == "M1" and (rr is None or rr >= 2.5)) else "C"
    return "C" if total >= 50 else "D"


def score(sts: dict, idx: dict, z: dict, d: int, scenario: str, pip: float, lam: float, model: str | None = None, prox: float = 0.0) -> dict:
    """The Perfect Trade Checklist: C1..C8 (points), the detail of each, the total /100 and the pre-entry total (C1..C7)."""
    h1, i1 = sts["H1"], idx["H1"]
    ws = window_start(h1, i1, z, d, prox) if i1 >= 0 else None
    t_from = h1.s.tc[ws] - 3600 if ws is not None else (h1.s.tc[i1] - 12 * 3600 if i1 >= 0 else 0)
    br: dict[str, int] = {}
    det: dict[str, str] = {}
    if scenario in W_C1:
        br["C1"] = W_C1[scenario]
    if "W" in z["tfs"] and "D" in z["tfs"]:
        br["C2"], det["C2"] = W_C2_MERGED, "W+D merged"
    elif z["kind"] in ("W", "D") and (z["touches"] >= 3 or z["flip"]):
        br["C2"], det["C2"] = W_C2_STRONG, f"{z['kind']} {z['touches']} touches" + (" · flip" if z["flip"] else "")
    elif z["kind"] == "H4" and z["touches"] >= 2:
        br["C2"], det["C2"] = W_C2_H4, "D/H4 2 touches"
    e = c3_ema(sts, idx, t_from, z, d, None)
    if e:
        br["C3"], det["C3"] = W_C3, f"{e} 50 EMA"
    p = c4_prev(sts, idx, z, d)
    if p:
        br["C4"], det["C4"] = W_C4, f"{p} old structure"
    if c5_psych(z, h1, i1, ws, pip, lam):
        br["C5"], det["C5"] = W_C5, f"500 level {z['psych']}"
    r = c6_rejection(sts, idx, t_from, z, d)
    if r:
        br["C6"], det["C6"] = W_C6, r
    pt = c7_pattern(sts, idx, z, d, pip)
    if pt:
        br["C7"], det["C7"] = W_C7, pt
    pre = sum(br.values())
    if model:
        br["C8"], det["C8"] = W_C8[model], model
    total = sum(br.values())
    return {"breakdown": br, "detail": det, "pre": pre, "total": total, "window": ws, "grade": grade_of(total, scenario)}
