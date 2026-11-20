"""
Agent 4 · ConfluenceScorer (spec 3.4, 3.6): the live confluences at the active AOI (only the last 0, 1, 2 closed bars
count: a historical touch weighs exactly 0), the candlestick table, the classical patterns, the weighted score and the
grade. The round "500" level counts once.
"""

from .structure import bm, bp
from ..config import (EMA_AOI_PIPS, EMA_EPS_PIPS, GAP_PIPS, LIVE_K, PROX_PIPS, PSYCH_TOUCH_PIPS, W_AOI_D, W_AOI_W, W_ALIGN, W_EMA,
                     W_ENTRY, W_H4_CANDLE, W_HTF_CANDLE, W_PATTERN, W_PREV, W_PSYCH)


def body(x) -> float:
    return abs(x.close - x.open)


# ---- 3.4.4 the candlestick table (t = x, t-1 = p, t-2 = a)
def engulfing(p, x, d: int, gap: float) -> bool:
    if d > 0:
        return p.close < p.open and x.close > x.open and x.open <= p.close + gap and x.close > p.open and body(x) > body(p)
    return p.close > p.open and x.close < x.open and x.open >= p.close - gap and x.close < p.open and body(x) > body(p)


def pin(x, d: int, atr: float) -> bool:
    r = x.high - x.low
    up, dn = x.high - bp(x), bm(x) - x.low
    if d > 0:
        return dn >= 2.0 * body(x) and up <= 0.30 * r and r >= 0.5 * atr
    return up >= 2.0 * body(x) and dn <= 0.30 * r and r >= 0.5 * atr


def doji(x, d: int) -> bool:
    r = x.high - x.low
    if r <= 0 or body(x) > 0.12 * r:
        return False
    return (bm(x) - x.low >= 0.65 * r) if d > 0 else (x.high - bp(x) >= 0.65 * r)


def star(a, p, x, d: int, atr: float) -> bool:
    if body(a) < 0.6 * atr or body(p) > 0.35 * body(a):
        return False
    mid = (a.open + a.close) / 2
    return (a.close < a.open and x.close > x.open and x.close > mid) if d > 0 else (a.close > a.open and x.close < x.open and x.close < mid)


def tweezer(p, x, d: int, tol: float) -> bool:
    if d > 0:
        return p.close < p.open and x.close > x.open and abs(x.low - p.low) <= tol
    return p.close > p.open and x.close < x.open and abs(x.high - p.high) <= tol


def inside_break(a, p, x, d: int) -> bool:
    """Inside bar / harami (p inside a) with the next close (x) breaking out in direction d (CHOICE: beyond p's range)."""
    return p.high <= a.high and p.low >= a.low and ((x.close > p.high) if d > 0 else (x.close < p.low))


def pattern_at(c: list, j: int, d: int, atr: float, pip: float, lam: float) -> str | None:
    if j < 2:
        return None
    a, p, x = c[j - 2], c[j - 1], c[j]
    gap, tol = GAP_PIPS * lam * pip, 3 * lam * pip
    for name, ok in (("Engulfing", engulfing(p, x, d, gap)), ("Pin bar", pin(x, d, atr)), ("Doji", doji(x, d)),
                     ("Morning star" if d > 0 else "Evening star", star(a, p, x, d, atr)), ("Tweezer", tweezer(p, x, d, tol)),
                     ("Inside bar break", inside_break(a, p, x, d))):
        if ok:
            return name
    return None


def touches_zone(x, z: dict, pip: float, lam: float) -> bool:
    m = PROX_PIPS * lam * pip
    return x.low <= z["hi"] + m and x.high >= z["lo"] - m


def live_rejection(st, i: int, z: dict, d: int, pip: float, lam: float) -> str | None:
    """A rejection pattern on one of the last 3 closed candles that touches the AOI (+-5 lambda pips)."""
    for j in range(i, max(i - LIVE_K, 2) - 1, -1):
        if touches_zone(st.c[j], z, pip, lam):
            n = pattern_at(st.c, j, d, st.atr[j] or 0, pip, lam)
            if n:
                return n
    return None


def ema_rejection(st, i: int, z: dict, d: int, pip: float, lam: float) -> bool:
    """3.4.1: within the last 0-2 candles L <= EMA + eps and C > EMA (buy), and the EMA now inside the AOI or within 15
    lambda pips of its edge."""
    if i < 1 or st.e50[i] is None:
        return False
    e = st.e50[i]
    near = EMA_AOI_PIPS * lam * pip
    if not (z["lo"] - near <= e <= z["hi"] + near):
        return False
    eps = EMA_EPS_PIPS * lam * pip
    for j in range(i, max(i - LIVE_K, 0) - 1, -1):
        ej, x = st.e50[j], st.c[j]
        if ej is None:
            continue
        if (d > 0 and x.low <= ej + eps and x.close > ej) or (d < 0 and x.high >= ej - eps and x.close < ej):
            return True
    return False


def prev_structure(sts: dict, idx: dict, z: dict, d: int, pip: float, lam: float) -> str | None:
    """3.4.3: the prior W / D / H4 structure point (the "second elbow") inside the AOI +-5 lambda pips, rejected live
    (CHOICE: one of the last 3 candles reaches it within 5 lambda pips and closes beyond it on the trade's side)."""
    m = PROX_PIPS * lam * pip
    for tf in ("W", "D", "H4"):
        st, i = sts[tf], idx[tf]
        e = st.prev_structure(i, d)
        if not e or not (z["lo"] - m <= e[2] <= z["hi"] + m):
            continue
        for j in range(i, max(i - LIVE_K, 0) - 1, -1):
            x = st.c[j]
            if (d > 0 and x.low <= e[2] + m and x.close > e[2]) or (d < 0 and x.high >= e[2] - m and x.close < e[2]):
                return tf
    return None


def psych_live(h1, i: int, z: dict, pip: float, lam: float) -> bool:
    """3.4.2.2: price touches the level now (CHOICE: one of the last 3 H1 candles within 3 lambda pips of it)."""
    L = z.get("psych")
    if L is None or i < 0:
        return False
    tol = PSYCH_TOUCH_PIPS * lam * pip
    return any(h1.c[j].low - tol <= L <= h1.c[j].high + tol for j in range(i, max(i - LIVE_K, 0) - 1, -1))


def h4_structure(h4, i: int, z: dict, d: int, pip: float, lam: float) -> bool:
    """The 4H HL (buy) / LH (sell) confirmation at the AOI (CHOICE: the active one formed inside the AOI +-5 lambda pips
    in the last 12 H4 candles)."""
    if i < 0 or h4.bias[i] != d:
        return False
    lv = h4.hl[i] if d > 0 else h4.lh[i]
    m = PROX_PIPS * lam * pip
    return bool(lv) and i - lv[1] <= 12 and z["lo"] - m <= lv[0] <= z["hi"] + m


def chart_pattern(st, i: int, z: dict, d: int, pip: float, lam: float) -> str | None:
    """3.4.5: double bottom / top and (inverse) head & shoulders on body swings, the neckline inside the AOI (+-5 lambda
    pips), a body close beyond it and a retest. CHOICE: read on the last 60 candles, the break within the last 30."""
    m = PROX_PIPS * lam * pip
    sw = [(j, p) for j, kind, p in st.swings if kind == -d and i - 60 <= j and j + st.k <= i]
    a14 = st.atr[i] or 0

    def neck(j1, j2):
        if j2 - j1 < 2:
            return None
        return max(st.B[j1 + 1:j2]) if d > 0 else min(st.Bm[j1 + 1:j2])

    def confirmed(n, j_from):
        brk = next((q for q in range(j_from + 1, i + 1) if (st.C[q] > n if d > 0 else st.C[q] < n)), None)
        if brk is None or i - brk > 30:
            return False
        return any((st.c[q].low <= n + m) if d > 0 else (st.c[q].high >= n - m) for q in range(brk + 1, i + 1))
    for t in range(len(sw) - 1, 1, -1):  # head & shoulders: three consecutive swings
        (a, sl), (b, hd), (c_, sr) = sw[t - 2], sw[t - 1], sw[t]
        n = neck(a, c_)
        if n is None or not (z["lo"] - m <= n <= z["hi"] + m):
            continue
        head = hd < min(sl, sr) if d > 0 else hd > max(sl, sr)
        if head and abs(sl - sr) <= 0.5 * abs(n - hd) and confirmed(n, c_):
            return "Inverse H&S" if d > 0 else "H&S"
    for t in range(len(sw) - 1, 0, -1):
        (a, l1), (b, l2) = sw[t - 1], sw[t]
        n = neck(a, b)
        if 5 <= b - a <= 30 and abs(l1 - l2) <= 0.35 * a14 and n is not None and z["lo"] - m <= n <= z["hi"] + m and confirmed(n, b):
            return "Double bottom" if d > 0 else "Double top"
    return None


def grade_of(score: int) -> str:
    """3.6: A+ >= 100, A 90-99, B 80-89; below 80: C / D (CHOICE: C 60-79, D under 60)."""
    return "A+" if score >= 100 else "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 60 else "D"


def score(sts: dict, idx: dict, z: dict, d: int, align_kind: str | None, pip: float, lam: float, entry_ok: bool = False) -> dict:
    """ConfluenceReport: the breakdown (factor -> % weight, the TRUE ones only), the pre-entry score (what Tier 1 needs),
    the total with the entry sequence, and the grade."""
    br: dict[str, int] = {}
    detail: dict[str, str] = {}
    if align_kind:
        br[{"full": "W + D + 4H full sync", "retrace": "W + D sync (4H retracing)", "counter": "D + 4H sync (counter-weekly)"}[align_kind]] = W_ALIGN[align_kind]
    if "W" in z["tfs"]:
        br["At Weekly AOI"] = W_AOI_W
    if "D" in z["tfs"]:
        br["At Daily AOI"] = W_AOI_D
    for tf in ("W", "D", "H4"):
        if ema_rejection(sts[tf], idx[tf], z, d, pip, lam):
            br[f"Live {tf} 50 EMA rejection"] = W_EMA
    ps = prev_structure(sts, idx, z, d, pip, lam)
    if ps:
        br["Previous structure point"] = W_PREV
        detail["prev"] = ps
    if psych_live(sts["H1"], idx["H1"], z, pip, lam):
        br["Round 500 level"] = W_PSYCH
    for tf in ("W", "D"):
        n = live_rejection(sts[tf], idx[tf], z, d, pip, lam)
        if n:
            br["HTF candle rejection"] = W_HTF_CANDLE
            detail["htf_candle"] = f"{tf} {n}"
            break
    n4 = live_rejection(sts["H4"], idx["H4"], z, d, pip, lam)
    if n4 or h4_structure(sts["H4"], idx["H4"], z, d, pip, lam):
        br["4H rejection / structure"] = W_H4_CANDLE
        detail["h4"] = n4 or ("4H HL" if d > 0 else "4H LH")
    for tf in ("D", "H4", "H1"):
        n = chart_pattern(sts[tf], idx[tf], z, d, pip, lam)
        if n:
            br["Chart pattern at AOI"] = W_PATTERN
            detail["pattern"] = f"{tf} {n}"
            break
    pre = sum(br.values())
    if entry_ok:
        br["LTF SoS + Engulfing"] = W_ENTRY
    total = sum(br.values())
    return {"breakdown": br, "detail": detail, "pre": pre, "total": total, "grade": grade_of(total)}
