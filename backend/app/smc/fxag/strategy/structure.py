"""
Agent 2 · StructureEngine (spec 3.1, 3.2): body-close Snake-Trick elbows, HH / HL / LH / LL, trend shifts, the chop and
all-time-extreme filters, and the W / D / H4 alignment matrix. Wicks never make structure.
"""

from ...playbook import atr, ema
from ..config import ALPHA, ATH_ATR_W, CHOP_ER, CHOP_N, CHOP_OVERLAP, EPS_PIPS, K


def bp(x) -> float:
    return max(x.open, x.close)


def bm(x) -> float:
    return min(x.open, x.close)


def raw_swings(c: list, k: int) -> list[tuple[int, int, float]]:
    """Step 1: (index, kind +1 high / -1 low, body price). A swing at i is known at the close of i + k."""
    n = len(c)
    B, Bm = [bp(x) for x in c], [bm(x) for x in c]
    out = []
    for i in range(k, n - k):
        hw, lw = B[i - k:i + k + 1], Bm[i - k:i + k + 1]
        if B[i] >= max(hw) and B[i] > min(hw):
            out.append((i, 1, B[i]))
        if Bm[i] <= min(lw) and Bm[i] < max(lw):
            out.append((i, -1, Bm[i]))
    return out


class Structure:
    """One timeframe's structure, computed once and read causally (everything at index i uses candles <= i only)."""

    def __init__(self, series, pip: float, chop: bool = False):
        c = series.c
        self.s, self.c, self.pip = series, c, pip
        self.eps = EPS_PIPS * pip
        self.k = K[series.name]
        n = len(c)
        self.B, self.Bm, self.C = [bp(x) for x in c], [bm(x) for x in c], [x.close for x in c]
        self.atr = atr(c, 14) if n else []
        self.e50 = ema(self.C, 50) if n else []
        self.swings = raw_swings(c, self.k)
        self.els: list[tuple[int, int, float]] = []       # the True Elbows (index, kind, price), final
        self.n_el, self.last_el = [0] * n, [None] * n      # per bar: how many True Elbows were known, and the last one
        self.bias, self.hh, self.hl, self.ll, self.lh = [0] * n, [None] * n, [None] * n, [None] * n, [None] * n
        self.events: list[tuple[int, str, int, float]] = []   # (i, "SHIFT" | "BOS", dir, level)
        self.shift_at: dict[int, tuple[int, float]] = {}
        self._run()
        self.chop = [self._chop(i) for i in range(n)] if chop else [False] * n

    # Step 2: alternating True Elbows with the ATR prominence filter
    def _push(self, sw):
        i, kind, p = sw
        if not self.els:
            self.els.append(sw)
        elif self.els[-1][1] == kind:
            if (kind > 0 and p > self.els[-1][2]) or (kind < 0 and p < self.els[-1][2]):
                self.els[-1] = sw
        else:
            a = self.atr[i] or 0
            if abs(p - self.els[-1][2]) >= ALPHA[self.s.name] * a:  # 2.2 B: delta = alpha_tau x ATR14
                self.els.append(sw)

    # Step 3: the trend state machine on body closes
    def _run(self):
        c, B, Bm, C = self.c, self.B, self.Bm, self.C
        k, si = self.k, 0
        tr, hh, hl, ll, lh = 0, None, None, None, None
        pull = False  # a pullback elbow formed after the active HH (LL): the next break moves HL (LH)
        for i in range(len(c)):
            while si < len(self.swings) and self.swings[si][0] + k <= i:
                self._push(self.swings[si])
                sw = self.els[-1] if self.els else None
                if sw and tr == 1 and sw[1] < 0 and hh and sw[0] > hh[1]:
                    pull = True
                if sw and tr == -1 and sw[1] > 0 and ll and sw[0] > ll[1]:
                    pull = True
                si += 1
            self.n_el[i], self.last_el[i] = len(self.els), (self.els[-1] if self.els else None)
            x = C[i]
            if tr == 0:
                hi = next((e for e in reversed(self.els) if e[1] > 0), None)
                lo = next((e for e in reversed(self.els) if e[1] < 0), None)
                if hi and x > hi[2]:
                    q = min(range(hi[0], i + 1), key=lambda u: Bm[u])
                    tr, hl, hh, pull = 1, (Bm[q], q), (x, i), False
                    self.events.append((i, "SHIFT", 1, hi[2]))
                elif lo and x < lo[2]:
                    q = max(range(lo[0], i + 1), key=lambda u: B[u])
                    tr, lh, ll, pull = -1, (B[q], q), (x, i), False
                    self.events.append((i, "SHIFT", -1, lo[2]))
            elif tr == 1:
                if x < hl[0] - self.eps:            # C_k < HL - eps: bearish (2.2 C)
                    self.events.append((i, "SHIFT", -1, hl[0]))
                    q = max(range(hl[1], i + 1), key=lambda u: B[u])
                    tr, lh, ll, pull = -1, (B[q], q), (x, i), False
                elif x > hh[0]:                     # C_t > HH: continuation
                    if pull:
                        q = min(range(hh[1], i + 1), key=lambda u: Bm[u])
                        hl, pull = (Bm[q], q), False
                        self.events.append((i, "BOS", 1, hh[0]))
                    hh = (x, i)
            else:
                if x > lh[0] + self.eps:            # C_k > LH + eps: bullish
                    self.events.append((i, "SHIFT", 1, lh[0]))
                    q = min(range(lh[1], i + 1), key=lambda u: Bm[u])
                    tr, hl, hh, pull = 1, (Bm[q], q), (x, i), False
                elif x < ll[0]:
                    if pull:
                        q = max(range(ll[1], i + 1), key=lambda u: B[u])
                        lh, pull = (B[q], q), False
                        self.events.append((i, "BOS", -1, ll[0]))
                    ll = (x, i)
            self.bias[i], self.hh[i], self.hl[i], self.ll[i], self.lh[i] = tr, hh, hl, ll, lh
        for i, kind, d, lv in self.events:
            if kind == "SHIFT":
                self.shift_at[i] = (d, lv)

    # 2.2 D: the Kaufman efficiency ratio over the last 12 closes and the share of bodies overlapping the range median
    def _chop(self, i: int) -> bool:
        n = CHOP_N
        if i < n + 1:
            return False
        win = range(i - n + 1, i + 1)
        path = sum(abs(self.C[j] - self.C[j - 1]) for j in win)
        er = abs(self.C[i] - self.C[i - n]) / path if path else 0.0
        hi, lo = max(self.c[j].high for j in win), min(self.c[j].low for j in win)
        med = (hi + lo) / 2
        overlap = sum(1 for j in win if self.Bm[j] <= med <= self.B[j]) / n
        return er < CHOP_ER and overlap > CHOP_OVERLAP

    # readers
    def biased(self, i: int) -> int:
        """The bias at i: 0 before any structure, or when the timeframe is consolidating (W / D)."""
        if i < 0:
            return 0
        return 0 if self.chop[i] else self.bias[i]

    def elbows_at(self, i: int) -> list[tuple[int, int, float]]:
        """The True Elbows known at the close of i."""
        if i < 0 or not self.n_el[i]:
            return []
        n = self.n_el[i]
        return self.els[:n - 1] + [self.last_el[i]]

    def prev_structure(self, i: int, d: int):
        """3.4.3: the "second elbow": in an uptrend the high elbow before the latest one (the old HH, new support); in a
        downtrend the low elbow before the latest (the old LL, new resistance)."""
        side = [e for e in self.elbows_at(i) if e[1] == d]
        return side[-2] if len(side) >= 2 else None


def extreme(w: Structure, i: int, d: int) -> bool:
    """2.2 D.2: EXTREME_ATH for a buy within 0.5 ATR14(W) of the weekly high of the whole history, EXTREME_ATL for a sell."""
    if i < 1 or not w.atr[i]:
        return False
    a = ATH_ATR_W * w.atr[i]
    return w.C[i] > max(x.high for x in w.c[:i + 1]) - a if d > 0 else w.C[i] < min(x.low for x in w.c[:i + 1]) + a
