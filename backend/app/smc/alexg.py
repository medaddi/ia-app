"""
FXAlexG "Set & Forget": the ONE engine of the app, for gold and the 28 forex pairs. The user's spec (2026-11-11)
"Complete strategic overhaul: FXAlexG Set & Forget, 5-agent desk, 3-stage notifications", applied to the letter.
Pure price action: no tick volume, no M5 gap veto. M5 only follows the trades.

  3.1  No-Gap candles for every candle pattern: O' = C(t-1), H' = max(H, O', C), L' = min(L, O', C), C' = C
  3.2  EMA 50 on closes for every timeframe; a tap = L' <= EMA + 0.15 ATR 14 and C' > EMA (bull), the mirror (bear)
  3.3  line-chart structure on closes only: pivots C_i = max / min of [i-m, i+m] (m: W1 2, D1 3, H4 3); a trend turns only
       on a close strictly beyond HL / LH; "HH is always in front of HL": HL = the lowest close between the break origin and
       the new HH (the mirror for LL / LH)
  3.4  AOIs on W1 (120 bars) and D1 (250 bars) only: close and wick pivots grouped into zones <= 0.35 ATR 14 (D1) thick;
       a touch = price enters the zone from one side and moves >= 0.75 ATR 14 (D1) away on that side, touches 3+ candles
       apart, support and resistance touches both count; >= 3 touches; a BUY zone lies inside the active bullish
       [HL, HH] of D1 or W1 (a SELL zone inside [LL, LH]); a round number (50 / 100 pips, gold $25 / $50) within 10 pips
  3.5  the closed confirmation on 2H / 1H / 30M / 15M at the AOI: a doji / pinbar (body <= 32 %, rejection wick >= 60 %),
       an engulfing (close beyond the previous body, body >= 80 % of it and >= 50 % of its own range), the LTF SoS, a
       double top / bottom or (inverse) H&S with a close beyond the neckline and a retest
  3.6  the 100-point GPA (9 items) and its grades: A+ >= 90, A 80-89, B 75-79, C+ 70-74, below 70: F (NO_TRADE)
  3.7  entry at the confirmation close (band ± 0.15 ATR 14 1H); SL = min(Z_low, swing) - 0.20 ATR 14 1H - spread; TP 7 pips
       (the spec: 5 to 10) before the next opposing D1 / W1 structure or the round number just inside it, never an
       arbitrary R multiple (the user, 2026-11-11); RR >= 2.0;
       at +1.5 R the stop goes to the entry + 2 pips; a trade not in profit on Friday 20:00 UTC is closed
  4    the 5 agents (trend_director, aoi_architect, confluence_grader, trigger_sniper, risk_guardian), the consensus
       0.25 / 0.25 / 0.20 / 0.20 / 0.10 and the execution rule
  setups  SF_BR (break & retest continuation), SF_BOUNCE (direct pro-trend AOI bounce, the 4th+ touch), SF_COUNTER
          (1D shifted against the 1W, the weekly retracement leg)

Every number the spec leaves open is marked CHOICE and was fixed before any result was seen.
"""

import json
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .playbook import DAY, H1S, H4S, M5S, M15S, NEWS_MIN, _Bar, _make, atr, ema, m5_index_at_close, resample, run

W1S, H2S, M30S = 7 * DAY, 7200, 1800
TF_SEC = {"W1": W1S, "D1": DAY, "H4": H4S, "H2": H2S, "H1": H1S, "M30": M30S, "M15": M15S}
M_PIV = {"W1": 2, "D1": 3, "H4": 3, "H2": 3, "H1": 3, "M30": 3, "M15": 3}  # CHOICE: the LTFs use m = 3 like 1D / 4H
N_AOI = {"W1": 120, "D1": 250}
ENTRY_TFS = ("H2", "H1", "M30", "M15")
STRATEGY_NAME = "FXAlexG Set & Forget"
SETUPS = {"SF_BR": "Set & Forget — Break & Retest Continuation", "SF_BOUNCE": "Set & Forget — Direct AOI Structure Bounce",
          "SF_COUNTER": "Set & Forget — Weekly Retracement Intraday Swing"}
BE_R, BE_PIPS, MIN_RR, FRONT_RUN_PIPS = 1.5, 2.0, 2.0, 7.0  # the TP is always the structure's (no R cap: the user, 2026-11-11)
SESSION = (6, 17)  # 06:00-17:00 UTC: pre-London, London, NY overlap
RISK_BY_GRADE = {"A+": 1.0, "A": 1.0, "B": 0.75, "C+": 0.5}
SOS_BARS, RECENT_BARS, SWING_BARS, REVERSAL_BARS, HOLD_DAYS = 24, 3, 12, 10, 30  # CHOICE (the spec does not size them)
CFG_DIR = Path(__file__).parent / "configs"
_cfg: dict = {}


def config(key: str) -> dict:
    if key not in _cfg:
        _cfg[key] = json.loads((CFG_DIR / f"{key}.json").read_text(encoding="utf-8"))
    return _cfg[key]


def hm(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M")


def badge(s: str) -> str:
    """An agent's badge: at most 55 characters."""
    return s if len(s) <= 55 else s[:54] + "…"


def fmt(v: float, pip: float) -> str:
    return f"{v:.{2 if pip >= 0.1 else 3 if pip >= 0.01 else 5}f}"


# ---------------------------------------------------------------- 3.1 No-Gap candles
def nogap(c) -> list:
    out, prev = [], None
    for x in c:
        o = x.open if prev is None else prev.close
        out.append(_Bar(x.time, o, max(x.high, o, x.close), min(x.low, o, x.close), x.close))
        prev = x
    return out


def doji(x, d: int, zone: Optional[dict] = None) -> bool:
    """A rejection doji / pinbar on a No-Gap candle: body <= 32 % of the range, the rejection wick >= 60 % of it."""
    r = x.high - x.low
    if r <= 0 or abs(x.close - x.open) / r > 0.32:
        return False
    if d > 0:
        return min(x.open, x.close) - x.low >= 0.6 * r and (zone is None or x.close > zone["lo"])
    return x.high - max(x.open, x.close) >= 0.6 * r and (zone is None or x.close < zone["hi"])


def engulf(p, x, d: int) -> bool:
    """An engulfing No-Gap candle: closes beyond the previous body, body >= 80 % of the previous body and >= 50 % of its range."""
    r, b, pb = x.high - x.low, abs(x.close - x.open), abs(p.close - p.open)
    if r <= 0:
        return False
    if d > 0:
        return x.close > x.open and x.close > max(p.open, p.close) and b >= 0.8 * pb and b >= 0.5 * r
    return x.close < x.open and x.close < min(p.open, p.close) and b >= 0.8 * pb and b >= 0.5 * r


def weekly(d1) -> list:
    """W1 candles from D1, weeks starting Monday 00:00 UTC (epoch day 0 is a Thursday)."""
    out, cur = [], None
    for x in d1:
        wk = x.time - ((x.time // DAY + 3) % 7) * DAY
        if cur is None or cur.time != wk:
            cur = _Bar(wk, x.open, x.high, x.low, x.close)
            out.append(cur)
        else:
            cur.high, cur.low, cur.close = max(cur.high, x.high), min(cur.low, x.low), x.close
    return out


# ---------------------------------------------------------------- 3.3 line-chart structure
def pivots(v: list[float], m: int) -> tuple[list[bool], list[bool]]:
    """hi[i] when v[i] is the max of [i-m, i+m], lo[i] the min. A pivot at i is known at the close of i + m."""
    n = len(v)
    hi, lo = [False] * n, [False] * n
    for i in range(m, n - m):
        w = v[i - m:i + m + 1]
        hi[i], lo[i] = v[i] == max(w), v[i] == min(w)
    return hi, lo


def structure(cl: list[float], m: int) -> dict:
    """Per close: trend (+1 / -1 / 0 before the first break), HH, HL, LL, LH as (close, index), events
    [(i, 'BOS' | 'SOS', dir, level)]. CHOICE where the spec is silent: the machine starts at the first close beyond a
    confirmed pivot; after a break the new HH (LL) follows the leg's highest (lowest) close and is fixed by the next
    confirmed pivot."""
    n = len(cl)
    ph, pl = pivots(cl, m)
    out = {k: [None] * n for k in ("trend", "hh", "hl", "ll", "lh")}
    events = []
    tr, hh, hl, ll, lh, pend, brk = 0, None, None, None, None, False, 0
    lp_h = lp_l = None

    def lowest(a, b):
        q = min(range(a, b), key=lambda u: cl[u])
        return cl[q], q

    def highest(a, b):
        q = max(range(a, b), key=lambda u: cl[u])
        return cl[q], q
    for i in range(n):
        j = i - m
        if j >= 0 and ph[j]:
            lp_h = (cl[j], j)
        if j >= 0 and pl[j]:
            lp_l = (cl[j], j)
        x = cl[i]
        if tr == 0:
            if lp_h and x > lp_h[0]:
                tr, hl, hh, pend, brk = 1, lowest(lp_h[1], i), (x, i), True, i
                events.append((i, "BOS", 1, lp_h[0]))
            elif lp_l and x < lp_l[0]:
                tr, lh, ll, pend, brk = -1, highest(lp_l[1], i), (x, i), True, i
                events.append((i, "BOS", -1, lp_l[0]))
        elif tr == 1:
            if x < hl[0]:  # a close strictly below HL: bearish
                events.append((i, "SOS", -1, hl[0]))
                tr, lh, ll, pend, brk = -1, highest(hl[1], i), (x, i), True, i
            elif pend:
                if x > hh[0]:
                    hh = (x, i)
                if lp_h and lp_h[1] >= brk:
                    pend = False
            elif x > hh[0]:
                events.append((i, "BOS", 1, hh[0]))
                hl, hh, pend, brk = lowest(hh[1], i), (x, i), True, i  # HL strictly behind the new HH
        else:
            if x > lh[0]:
                events.append((i, "SOS", 1, lh[0]))
                tr, hl, hh, pend, brk = 1, lowest(lh[1], i), (x, i), True, i
            elif pend:
                if x < ll[0]:
                    ll = (x, i)
                if lp_l and lp_l[1] >= brk:
                    pend = False
            elif x < ll[0]:
                events.append((i, "BOS", -1, ll[0]))
                lh, ll, pend, brk = highest(ll[1], i), (x, i), True, i
        out["trend"][i], out["hh"][i], out["hl"][i], out["ll"][i], out["lh"][i] = tr, hh, hl, ll, lh
    out["events"] = events
    return out


class TF:
    """One timeframe: candles, No-Gap candles, closes, structure, EMA 50, ATR 14, close and wick pivots."""

    def __init__(self, name: str, c):
        self.name, self.c = name, c
        self.g = nogap(c)
        self.t = [x.time for x in c]
        self.step, self.m = TF_SEC[name], M_PIV[name]
        self.cl = [x.close for x in c]
        self.s = structure(self.cl, self.m)
        self.e50 = ema(self.cl, 50)
        self.at = atr(c, 14)
        self.ph, self.pl = pivots(self.cl, self.m)
        self.wh = pivots([x.high for x in c], self.m)[0]
        self.wl = pivots([x.low for x in c], self.m)[1]
        self.ev_at = {}
        for i, kind, d, lv in self.s["events"]:
            self.ev_at.setdefault(i, []).append((kind, d, lv))

    def idx(self, T: int) -> int:
        """The last candle closed at T."""
        return bisect_right(self.t, T - self.step) - 1

    def trend(self, i: int) -> int:
        return self.s["trend"][i] if i >= 0 else 0

    def range_of(self, i: int, d: int) -> Optional[tuple[float, float]]:
        """The active dealing range of direction d: [HL, HH] (bull) or [LL, LH] (bear), when the trend is d."""
        if i < 0 or self.s["trend"][i] != d:
            return None
        a, b = (self.s["hl"][i], self.s["hh"][i]) if d > 0 else (self.s["ll"][i], self.s["lh"][i])
        return (a[0], b[0]) if a and b else None

    def tap(self, q: int, d: int) -> bool:
        """3.2: the No-Gap candle q taps and respects the EMA 50."""
        e, a = self.e50[q], self.at[q]
        if e is None or not a:
            return False
        x = self.g[q]
        return (x.low <= e + 0.15 * a and x.close > e) if d > 0 else (x.high >= e - 0.15 * a and x.close < e)


# ---------------------------------------------------------------- 3.4 AOIs
def touches(c, n0: int, i: int, lo: float, hi: float, rev: float) -> tuple[int, list]:
    """Touches of [lo, hi] in candles n0..i: a candle enters it from one side (the previous close beyond an edge) and, within
    10 candles (CHOICE), price reaches rev beyond that edge before a close through the other edge; touches 3+ candles apart.
    Returns (count, [(index, role)]) with role +1 = support (from above), -1 = resistance (from below)."""
    n, last, roles = 0, -99, []
    for q in range(max(n0, 1), i + 1):
        x = c[q]
        if not (x.low <= hi and x.high >= lo) or q - last < 3:
            continue
        pc = c[q - 1].close
        side = 1 if pc > hi else -1 if pc < lo else 0
        if not side:
            continue
        for r in range(q, min(q + REVERSAL_BARS, i) + 1):
            y = c[r]
            if side > 0:
                if y.close < lo:
                    break
                if y.high >= hi + rev:
                    n, last = n + 1, q
                    roles.append((q, 1))
                    break
            else:
                if y.close > hi:
                    break
                if y.low <= lo - rev:
                    n, last = n + 1, q
                    roles.append((q, -1))
                    break
    return n, roles


def psych_near(lo: float, hi: float, pip: float, step: float) -> Optional[float]:
    """The round number (every `step`: 50 pips, JPY 0.50, gold $25) inside the zone or within 10 pips of it, nearest its middle."""
    mid = (lo + hi) / 2
    p = round(mid / step) * step
    for q in (p, p - step, p + step):
        if lo - 10 * pip <= q <= hi + 10 * pip:
            return round(q, 6)
    return None


def build_zones(tf: TF, i: int, atr_d: float, pip: float, step: float) -> list[dict]:
    if i < 20 or not atr_d:
        return []
    n0 = max(0, i - N_AOI[tf.name] + 1)
    c, m = tf.c, tf.m
    pts = []
    for q in range(max(n0, m), i - m + 1):  # pivots known at i
        if tf.ph[q] or tf.pl[q]:
            pts.append((tf.cl[q], True))
        if tf.wh[q]:
            pts.append((c[q].high, False))
        if tf.wl[q]:
            pts.append((c[q].low, False))
    pts.sort()
    thick, rev = 0.35 * atr_d, 0.75 * atr_d
    seen, cands = set(), []
    for a in range(len(pts)):
        if not pts[a][1]:  # CHOICE: zones are anchored on close pivots (the wicks widen them)
            continue
        grp = [p for p, _ in pts[a:] if p <= pts[a][0] + thick]
        lo, hi = grp[0], grp[-1]
        key = (round(lo / pip), round(hi / pip))
        if key in seen:
            continue
        seen.add(key)
        n, roles = touches(c, n0, i, lo, hi, rev)
        if n >= 3:
            cands.append({"lo": lo, "hi": hi, "touches": n, "roles": roles, "tfs": {tf.name}, "t0": c[roles[0][0]].time})
    cands.sort(key=lambda z: (-z["touches"], z["hi"] - z["lo"]))
    out = []
    for z in cands:
        if all(z["hi"] < y["lo"] or z["lo"] > y["hi"] for y in out):
            out.append(z)
    for z in out:
        z["psych"] = psych_near(z["lo"], z["hi"], pip, step)
        z["width"] = (z["hi"] - z["lo"]) / pip
    return out


def merge_zones(w1: list[dict], d1: list[dict]) -> list[dict]:
    """A W1 zone and a D1 zone that overlap are one W1+D1 zone (the strong AOI)."""
    out, used = [], set()
    for zw in w1:
        z = dict(zw)
        for q, zd in enumerate(d1):
            if zd["lo"] <= z["hi"] and zd["hi"] >= z["lo"]:
                used.add(q)
                z.update(lo=min(z["lo"], zd["lo"]), hi=max(z["hi"], zd["hi"]), touches=max(z["touches"], zd["touches"]),
                         roles=sorted(z["roles"] + zd["roles"]), tfs={"W1", "D1"}, psych=z["psych"] or zd["psych"])
        z["overlap"] = z["tfs"] == {"W1", "D1"}
        out.append(z)
    for q, zd in enumerate(d1):
        if q not in used:
            out.append({**zd, "overlap": False})
    for z in out:
        z["strong"] = z["overlap"] or z["touches"] >= 5
    return out


# ---------------------------------------------------------------- LTF patterns
def pattern(e: TF, t: int, z: dict, d: int, tol: float) -> Optional[tuple[str, float]]:
    """A double bottom / inverse H&S (long) or double top / H&S (short) on close pivots inside the AOI (± tol), the last
    pivot within 20 candles (CHOICE), a close beyond the neckline after it and a retest of the neckline (within 0.15 ATR)
    or of the AOI since. Returns (name, head / extreme) or None."""
    a, b = z["lo"] - tol, z["hi"] + tol
    src, opp = (e.pl, e.ph) if d > 0 else (e.ph, e.pl)
    turns = [(e.cl[q], q) for q in range(max(t - 40, e.m), t - e.m + 1) if src[q]]
    at = e.at[t] or 0
    for n_ in (3, 2):
        if len(turns) < n_:
            continue
        ts = turns[-n_:]
        if not all(a <= p <= b for p, _ in ts) or t - ts[-1][1] > 20:
            continue
        if n_ == 3 and not ((ts[1][0] < min(ts[0][0], ts[2][0])) if d > 0 else (ts[1][0] > max(ts[0][0], ts[2][0]))):
            continue
        mids = [e.cl[q] for q in range(ts[0][1] + 1, ts[-1][1]) if opp[q]]
        if not mids:
            continue
        neck = max(mids) if d > 0 else min(mids)
        brk = next((q for q in range(ts[-1][1] + 1, t + 1) if ((e.cl[q] > neck) if d > 0 else (e.cl[q] < neck))), None)
        if brk is None:
            continue
        if any(((e.c[q].low <= neck + 0.15 * at or e.c[q].low <= z["hi"]) if d > 0 else (e.c[q].high >= neck - 0.15 * at or e.c[q].high >= z["lo"]))
               for q in range(brk + 1, t + 1)):
            ext = min(p for p, _ in ts) if d > 0 else max(p for p, _ in ts)
            name = ("Inverse H&S" if d > 0 else "H&S") if n_ == 3 else ("Double Bottom" if d > 0 else "Double Top")
            return name, ext
    return None


def sos_at(e: TF, t: int, z: dict, d: int, tol: float) -> Optional[dict]:
    """The LTF Shift of Structure: the latest close beyond the LTF LH (long) / HL (short) in the last 24 candles that turned
    the LTF trend d, with the AOI touched in the 12 candles before it (CHOICE: "while retracing into the AOI")."""
    for s in range(t, max(t - SOS_BARS, 0) - 1, -1):
        for kind, dd, lv in e.ev_at.get(s, []):
            if kind == "SOS" and dd == d:
                if any(e.c[q].low <= z["hi"] + tol and e.c[q].high >= z["lo"] - tol for q in range(max(s - SWING_BARS, 0), s + 1)):
                    return {"index": s, "time": e.t[s] + e.step, "level": lv}
                return None
    return None


# ---------------------------------------------------------------- the context of one read
class Ctx:
    def __init__(self, key: str, m5, h1, d1, spread: Optional[float] = None):
        self.key, self.cfg = key, config(key)
        self.pip, self.psych = self.cfg["pip"], self.cfg.get("psych_step", 0.005)
        self.spread = spread if spread else self.cfg["spread_pips"] * self.pip
        self.m5, self.t5 = m5, [x.time for x in m5]
        self.tf = {"W1": TF("W1", weekly(d1)), "D1": TF("D1", d1), "H4": TF("H4", resample(h1, H4S)), "H2": TF("H2", resample(h1, H2S)),
                   "H1": TF("H1", h1), "M30": TF("M30", resample(m5, M30S)), "M15": TF("M15", resample(m5, M15S))}
        self._aoi: dict = {}

    def aois(self, iw: int, id_: int) -> list[dict]:
        if (iw, id_) not in self._aoi:
            d1 = self.tf["D1"]
            atr_d = d1.at[id_] if id_ >= 0 else None
            self._aoi[(iw, id_)] = merge_zones(build_zones(self.tf["W1"], iw, atr_d, self.pip, self.psych),
                                               build_zones(d1, id_, atr_d, self.pip, self.psych))
        return self._aoi[(iw, id_)]

    def adr20(self, id_: int) -> Optional[float]:
        d = self.tf["D1"].c
        if id_ < 5:
            return None
        w = d[max(0, id_ - 19):id_ + 1]
        return sum(x.high - x.low for x in w) / len(w)


_ctx: dict = {}


def context(key: str, m5, h1, d1, spread: Optional[float] = None) -> Ctx:
    """One Ctx per (pair, last candles): the scan, the report and the chart of one read share it."""
    sig = (m5[-1].time, len(m5), h1[-1].time, len(h1), d1[-1].time, len(d1), spread)
    hit = _ctx.get(key)
    if not hit or hit[0] != sig:
        _ctx[key] = (sig, Ctx(key, m5, h1, d1, spread))
    return _ctx[key][1]


def bounded(z: dict, d: int, ranges: dict) -> bool:
    """3.4.1: a BUY zone inside an active bullish [HL, HH] of W1 or D1 (a SELL zone inside [LL, LH])."""
    for tfn in z["tfs"]:
        r = ranges.get(tfn)
        if r and r[0] <= z["lo"] and z["hi"] <= r[1]:
            return True
    return False


GPA = [("w1", 10, "1W trend aligned"), ("d1", 10, "1D trend aligned"), ("h4", 10, "4H aligned (or 4H shift in the AOI)"),
       ("aoi", 10, "Valid 1W / 1D AOI (>= 3 touches)"), ("strong", 10, "Strong AOI (1W+1D, >= 5 touches or psych)"),
       ("ema_htf", 10, "1W / 1D / 4H 50 EMA confluence"), ("sos", 15, "LTF SoS or H&S / double top-bottom"),
       ("candle", 15, "Closed LTF confirmation candle"), ("ltf_ema", 10, "LTF 50 EMA + active session")]


def grade_of(score: int) -> str:
    return "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 75 else "C+" if score >= 70 else "F"


def evaluate(cx: Ctx, etf: str, t: int, d: int, news: Optional[list[int]] = None, exec_T: Optional[int] = None) -> dict:
    """Everything the spec computes for direction d at the close of entry candle t of `etf` (executed at exec_T)."""
    pip = cx.pip
    e = cx.tf[etf]
    T = e.t[t] + e.step
    Tx = exec_T or T
    w1, d1, h4, h1 = cx.tf["W1"], cx.tf["D1"], cx.tf["H4"], cx.tf["H1"]
    iw, id_, i4, ih = w1.idx(T), d1.idx(T), h4.idx(T), h1.idx(T)
    S = {"W1": w1.trend(iw), "D1": d1.trend(id_), "H4": h4.trend(i4)}
    atr_d = d1.at[id_] if id_ >= 0 else None
    tol = 0.3 * atr_d if atr_d else 30 * pip  # CHOICE: "at / approaching" the AOI = within 0.3 ATR 14 (D1), the spec's waiting distance
    ranges = {"W1": w1.range_of(iw, d), "D1": d1.range_of(id_, d)}
    zones = cx.aois(iw, id_) if iw >= 0 and id_ >= 0 else []
    usable = [z for z in zones if bounded(z, d, ranges)]
    g = e.g
    x = g[t]
    recent = [e.c[q] for q in range(max(t - RECENT_BARS + 1, 0), t + 1)]
    touching = [z for z in usable if any(y.low <= z["hi"] and y.high >= z["lo"] for y in recent)]
    dist = lambda q: max(q["lo"] - x.close, x.close - q["hi"], 0)  # noqa: E731
    z = min(touching, key=dist) if touching else None
    near = min(usable, key=dist) if usable else None
    r = {"dir": d, "etf": etf, "t": t, "T": T, "Tx": Tx, "S": S, "zone": z, "zones": zones, "usable": usable, "price": x.close,
         "near": near, "near_atr": (dist(near) / atr_d) if near and atr_d else None, "atr_d": atr_d, "c": {}}
    c = r["c"]
    if z:
        c["sos"] = sos_at(e, t, z, d, tol)
        c["pattern"] = pattern(e, t, z, d, tol)
        c["engulf"] = engulf(g[t - 1], x, d) if t > 0 else False
        c["doji"] = doji(x, d, z)
        c["doji_before"] = any(doji(g[q], d, z) for q in range(max(t - 3, 1), t))
        c["ltf_ema"] = e.e50[t] is not None and d * (x.close - e.e50[t]) > 0
        c["ema_htf"] = None
        for tf, i in (("W1", iw), ("D1", id_), ("H4", i4)):
            T_ = cx.tf[tf]
            if i >= 1 and T_.e50[i] is not None and atr_d and z["lo"] - 0.5 * atr_d <= T_.e50[i] <= z["hi"] + 0.5 * atr_d \
               and (T_.tap(i, d) or T_.tap(i - 1, d)):  # CHOICE: the EMA within 0.5 ATR (D1) of the AOI
                c["ema_htf"] = tf
                break
        c["h4_shift"] = any(kind == "SOS" and dd == d for q in range(max(i4 - 5, 0), i4 + 1) for kind, dd, _ in h4.ev_at.get(q, []))
    session = SESSION[0] <= (T % DAY) // H1S < SESSION[1]
    items = {"w1": S["W1"] == d, "d1": S["D1"] == d, "h4": S["H4"] == d or bool(z and c.get("h4_shift")), "aoi": bool(z),
             "strong": bool(z and (z["strong"] or z["psych"] is not None)), "ema_htf": bool(z and c.get("ema_htf")),
             "sos": bool(z and (c.get("sos") or c.get("pattern"))), "candle": bool(z and (c.get("engulf") or c.get("doji"))),
             "ltf_ema": bool(z and c.get("ltf_ema") and session)}
    r["items"], r["session"] = items, session
    r["gpa"] = sum(p for k, p, _ in GPA if items[k])
    r["grade"] = grade_of(r["gpa"])
    # the setup type
    r["setup"] = ("SF_COUNTER" if S["W1"] != d else
                  "SF_BR" if z and any(role == -d for _, role in z["roles"]) else "SF_BOUNCE") if S["D1"] == d else None
    # 3.7: the plan
    r["rr"] = 0.0
    if z and (c.get("engulf") or c.get("doji")):
        ai = ih if ih >= 0 else 0
        atr1 = h1.at[ai] or (atr_d or 0) / 5
        entry = x.close
        seg = e.c[max(t - SWING_BARS, 0):t + 1]
        swing = min(y.low for y in seg) if d > 0 else max(y.high for y in seg)
        if c.get("pattern"):
            swing = min(swing, c["pattern"][1]) if d > 0 else max(swing, c["pattern"][1])
        sl = (min(z["lo"], swing) - 0.2 * atr1 - cx.spread) if d > 0 else (max(z["hi"], swing) + 0.2 * atr1 + cx.spread)
        # the next OPPOSING structure: a zone whose last touch rejected price against the trade (resistance for a buy)
        tg = [((q["lo"], q["hi"]) if d > 0 else (q["hi"], q["lo"])) for q in zones if q["roles"] and q["roles"][-1][1] == -d and
              ((q["lo"] > entry) if d > 0 else (q["hi"] < entry))]  # (near edge, far edge)
        for tf, i in ((d1, id_), (w1, iw)):
            lv = tf.s["hh" if d > 0 else "ll"][i] if i >= 0 else None
            if lv and (lv[0] - entry) * d > 0:
                tg.append((lv[0], lv[0]))
        if tg and (entry - sl) * d > 0:
            near_edge, far_edge = min(tg) if d > 0 else max(tg)
            target = near_edge
            step = cx.psych
            # the round number AT or just inside the target zone: between 10 pips before its near edge and its far edge
            a_, b_ = (near_edge - 10 * pip, far_edge) if d > 0 else (far_edge, near_edge + 10 * pip)
            k_lo, k_hi = int(a_ / step) - 1, int(b_ / step) + 2
            ps = [k * step for k in range(k_lo, k_hi) if a_ <= k * step <= b_ and (k * step - entry) * d > 0]
            p = (min(ps) if d > 0 else max(ps)) if ps else None
            level = (min(target, p) if d > 0 else max(target, p)) if p else target
            tp = level - d * FRONT_RUN_PIPS * pip
            rr = (tp - entry) * d / ((entry - sl) * d)
            r.update(entry=entry, sl=sl, tp=tp, tp1=entry + d * BE_R * (entry - sl) * d, rr=rr, target=target, psych_tp=p,
                     band=(entry - 0.15 * atr1, entry + 0.15 * atr1), atr1=atr1)
    risk = abs(r["entry"] - r["sl"]) if "entry" in r else None
    r["news"] = [n for n in (news or []) if abs(n - Tx) <= NEWS_MIN * 60]
    r["news_checked"] = news is not None
    tod = Tx % DAY
    r["rollover"] = 21 * H1S + 45 * 60 <= tod < 22 * H1S + 15 * 60
    r["spread_ratio"] = cx.spread / risk if risk else 0.0
    r["weekday"] = datetime.fromtimestamp(Tx, timezone.utc).weekday()
    r["exec_session"] = SESSION[0] <= tod // H1S < SESSION[1]
    adr = cx.adr20(id_)
    r["target_adr"] = (abs(r["tp"] - r["entry"]) / adr) if "entry" in r and adr else None
    return r


# ---------------------------------------------------------------- 4 the 5 agents
ROLES = [("trend", "trend_director", "HTF Trend Director", 0.25), ("aoi", "aoi_architect", "AOI & Psych Level Architect", 0.25),
         ("confluence", "confluence_grader", "GPA Confluence Grader", 0.20), ("trigger", "trigger_sniper", "LTF Trigger Sniper", 0.20),
         ("risk", "risk_guardian", "Session, News & R:R Guardian", 0.10)]
SIDE = {1: "Bullish", -1: "Bearish", 0: "Neutral"}


def squad(r: dict, pip: float, usd_per_pip: float = 10.0) -> dict:
    d, c, S, z = r["dir"], r["c"], r["S"], r["zone"]
    f = lambda v: fmt(v, pip)  # noqa: E731
    word = "BUY" if d > 0 else "SELL"
    # 1 · trend_director
    if S["W1"] == S["D1"] == S["H4"] == d:
        t_st, t_sc, t_b = "ok", 100, f"1W/1D/4H {SIDE[d]} in sync · Pro-trend {word}"
    elif S["W1"] == S["D1"] == d:
        t_st, t_sc, t_b = "ok", 80, f"1W/1D {SIDE[d]} · 4H retracing into AOI"
    elif S["D1"] == d:
        t_st, t_sc, t_b = "warn", 70, f"1D shifted {SIDE[d]} for 1W retracement leg"
    else:
        t_st, t_sc, t_b = "veto", 25, "HTF structure conflicting · Stand aside"
    trend = {"status": t_st, "score": t_sc, "badge": badge(t_b),
             "details": [f"1W {SIDE[S['W1']]} · 1D {SIDE[S['D1']]} · 4H {SIDE[S['H4']]} (body closes only)",
                         f"Direction read: {word} · setup {r['setup'] or 'none'}"]}
    # 2 · aoi_architect
    if z and (z["overlap"] or z["touches"] >= 5) and z["psych"] is not None:
        a_st, a_sc = "ok", 100
        a_b = f"In {'1W+1D' if z['overlap'] else '1D' if 'D1' in z['tfs'] else '1W'} AOI · {z['touches']} touches · Psych {f(z['psych'])}"
    elif z:
        a_st, a_sc = "ok", 85
        a_b = f"In {'1W+1D' if z['overlap'] else '1D' if 'D1' in z['tfs'] else '1W'} AOI @ {f((z['lo'] + z['hi']) / 2)} ({z['touches']} taps)"
    elif r["near"]:
        q = r["near"]
        a_st, a_sc = "wait", 60
        a_b = f"Waiting for pullback to {'1D' if 'D1' in q['tfs'] else '1W'} AOI @ {f((q['lo'] + q['hi']) / 2)} ({q['touches']} taps)"
    else:
        a_st, a_sc, a_b = "veto", 0, "No valid 3-touch 1W/1D AOI in range"
    aoi = {"status": a_st, "score": a_sc, "badge": badge(a_b),
           "details": [f"{len(r['usable'])} AOI(s) inside the active {'[HL, HH]' if d > 0 else '[LL, LH]'} · {len(r['zones'])} on 1W / 1D in all"] +
                      ([f"Zone {f(z['lo'])} – {f(z['hi'])} · {z['width']:.0f} pips · roles {'S/R flip' if len({x for _, x in z['roles']}) > 1 else 'one side'}"] if z else []) +
                      ([f"Nearest {r['near_atr']:.2f} ATR (1D) away"] if r["near_atr"] is not None and not z else [])}
    # 3 · confluence_grader
    gp, items = r["gpa"], r["items"]
    hits = sum(1 for k, _, _ in GPA if items[k])
    if gp >= 70:
        g_st = "ok"
        g_b = f"Grade {r['grade']} ({gp}%) · {hits}/9 Confluences" + (" + 50 EMA tap" if items["ema_htf"] else "") if gp >= 80 else \
            f"Grade {r['grade']} ({gp}%) · Passes min GPA threshold"
    elif gp >= 55:
        g_st, g_b = "wait", f"Grade D ({gp}%) · Waiting for LTF EMA & trigger"
    else:
        g_st, g_b = "veto", f"Grade F ({gp}%) · Below the 70% minimum"
    conf = {"status": g_st, "score": gp, "badge": badge(g_b), "grade": r["grade"],
            "details": [f"{'✅' if items[k] else '▫️'} {lab} (+{p})" for k, p, lab in GPA]}
    # 4 · trigger_sniper
    eng, dj, sos = c.get("engulf"), c.get("doji"), c.get("sos") or c.get("pattern")
    tfw = r["etf"]
    if z and eng and c.get("doji_before") and sos and c.get("ltf_ema"):
        s_st, s_sc, s_b = "ok", 100, f"{tfw} {SIDE[d]} Engulfing + SoS closed {'above' if d > 0 else 'below'} 50 EMA"
    elif z and (eng or (dj and sos)):
        s_st, s_sc = "ok", 85
        s_b = f"{tfw} {SIDE[d]} {'Engulfing' if eng else 'Doji rejection + SoS'} at AOI"
    elif z and sos:
        s_st, s_sc, s_b = "wait", 65, f"Inside AOI + SoS · Awaiting {tfw} Engulfing close"
    else:
        s_st, s_sc, s_b = "wait", 40, "No LTF reaction inside AOI yet"
    trig = {"status": s_st, "score": s_sc, "badge": badge(s_b),
            "details": [f"{r['etf']} · engulfing {bool(eng)} · doji {bool(dj)} (before {bool(c.get('doji_before'))}) · LTF 50 EMA side {bool(c.get('ltf_ema'))}",
                        f"SoS {'at ' + f(c['sos']['level']) if c.get('sos') else 'no'} · pattern {c['pattern'][0] if c.get('pattern') else 'none'}"]}
    # 5 · risk_guardian
    wd = r["weekday"]
    news_txt = "news not checked" if not r["news_checked"] else (f"News {hm(r['news'][0])} UTC" if r["news"] else "Clear news")
    if "entry" in r and r["rr"] < MIN_RR:
        k_st, k_b = "veto", f"R:R {r['rr']:.1f} < 2.0 to the next 1D/1W structure"
    elif r["news"]:
        k_st, k_b = "veto", f"High-impact news at {hm(r['news'][0])} UTC (±30 min)"
    elif r["rollover"]:
        k_st, k_b = "veto", "Daily rollover 21:45-22:15 UTC"
    elif "entry" in r and r["spread_ratio"] > 0.25:
        k_st, k_b = "veto", f"Spread {r['spread_ratio'] * 100:.0f}% of SL (> 25%)"
    elif wd == 4:
        k_st, k_b = "veto", "Friday cutoff · No new swing entries"
    elif wd >= 5:
        k_st, k_b = "wait", "Weekend · market closed"
    elif wd == 3 and "entry" in r and not (r["gpa"] >= 80 and r["target_adr"] is not None and r["target_adr"] <= 1.2):
        k_st, k_b = "veto", "Thursday · needs Grade A+/A and TP <= 1.2 ADR"
    elif not r["exec_session"]:
        k_st, k_b = "wait", ("Confirmation formed · Waiting for 06:00 UTC London pre-open" if "entry" in r else
                             "Outside 06:00-17:00 UTC · entries wait for London")
    elif "entry" not in r:
        k_st, k_b = "wait", f"Nothing to size yet · {news_txt}"
    else:
        k_st, k_b = "ok", f"R:R {r['rr']:.1f} · Spread {r['spread_ratio'] * 100:.1f}% of SL · {news_txt}"
    k_sc = 0 if k_st == "veto" else 50 if k_st == "wait" else 85 if wd == 3 else 100
    rk = RISK_BY_GRADE.get(r["grade"], 0.0)
    risk = {"status": k_st, "score": k_sc, "badge": badge(k_b), "risk_percent": rk,
            "details": [f"{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][wd]} {hm(r['Tx'])} UTC · session 06:00-17:00 · {news_txt}",
                        f"Risk {rk:g} % for grade {r['grade']} · R:R floor 2.0 · spread cap 25 % of SL"]}
    if "entry" in r:
        slp = abs(r["entry"] - r["sl"]) / pip
        lots = int(10000 * rk / 100 / (slp * usd_per_pip) * 100) / 100 if slp else 0
        risk.update(entry=r["entry"], stop_loss=r["sl"], break_even_trigger=r["tp1"], take_profit=r["tp"], rr=round(r["rr"], 2),
                    sl_pips=round(slp, 1), position_size_lots=lots)
    agents = {"trend_director": trend, "aoi_architect": aoi, "confluence_grader": conf, "trigger_sniper": trig, "risk_guardian": risk}
    cons = round(sum(w * agents[k]["score"] for _, k, _, w in ROLES))
    veto = [k for k, a in agents.items() if a["status"] == "veto"]
    execute = bool(cons >= 70 and r["gpa"] >= 70 and not veto and trig["status"] == "ok" and risk["status"] == "ok")
    decision = "EXECUTE" if execute else "VETOED" if veto else "WAIT_FOR_TRIGGER" if z else "WATCH_ONLY"
    radar = bool(trend["status"] == "ok" and aoi["status"] == "ok" and sos and not (eng or (dj and sos)))
    return {"agents": agents, "consensus": cons, "vetoes": veto, "execute": execute, "decision": decision, "radar": radar}


def checklist_of(r: dict) -> list[dict]:
    return [{"key": k, "label": lab, "pts": p, "ok": bool(r["items"][k])} for k, p, lab in GPA]


# ---------------------------------------------------------------- the scan (history and live)
def news_times(key: str, events) -> list[int]:
    cur = set(config(key).get("currencies") or [])
    return sorted({int(e["time"]) for e in (events or []) if e.get("currency") in cur})


def _defer(cx: Ctx, T: int) -> Optional[int]:
    """A confirmation outside 06:00-17:00 UTC executes at the next 06:00 UTC (CHOICE: 17:00-21:00 too). The M5 index
    whose close is that 06:00, or None when the candles do not reach it yet."""
    if SESSION[0] <= (T % DAY) // H1S < SESSION[1]:
        return m5_index_at_close(cx.t5, T)
    D = T - T % DAY
    nxt = D + SESSION[0] * H1S if (T % DAY) < SESSION[0] * H1S else D + DAY + SESSION[0] * H1S
    k = m5_index_at_close(cx.t5, nxt)
    return k if k is not None and cx.m5[k].time + M5S >= nxt else None


def scan(key: str, m5, h1, cost: float, events=None, d1=None, research: Optional[dict] = None, spread: Optional[float] = None) -> tuple[list, list]:
    """Every closed confirmation at an AOI on the candles given, each with its plan, its result followed on M5, its
    checklist and `pass` (the execution rule)."""
    if not d1 or len(h1) < 200 or len(m5) < 300:
        return [], []
    cx = context(key, m5, h1, d1, spread)
    pip = cx.pip
    nw = news_times(key, events) if events is not None else None
    out, seen = [], set()
    end = m5[-1].time + M5S
    for etf in ENTRY_TFS:
        e = cx.tf[etf]
        for t in range(60, len(e.c)):
            if e.t[t] + e.step > end:
                break
            for d in (1, -1):
                if not (engulf(e.g[t - 1], e.g[t], d) or doji(e.g[t], d)):  # the cheapest condition first
                    continue
                T = e.t[t] + e.step
                k0 = _defer(cx, T)
                if k0 is None:
                    continue
                Tx = cx.m5[k0].time + M5S
                r = evaluate(cx, etf, t, d, nw, Tx)
                if not (r["zone"] and "entry" in r):
                    continue
                z = r["zone"]
                vis = (round(z["lo"] / pip), d, cx.tf["D1"].idx(T))  # one setup per AOI visit per day
                if vis in seen:
                    continue
                sq = squad(r, pip, cx.cfg.get("pip_value_usd_per_lot", 10.0))
                if sq["agents"]["trigger_sniper"]["status"] != "ok":
                    continue
                seen.add(vis)
                entry = r["entry"]
                if Tx != T:  # deferred to 06:00: the price then must still be inside the entry band and above the stop
                    px = cx.m5[k0].close
                    lo_seg = min(y.low for y in cx.m5[m5_index_at_close(cx.t5, T) or k0:k0 + 1]) if d > 0 else None
                    hi_seg = max(y.high for y in cx.m5[m5_index_at_close(cx.t5, T) or k0:k0 + 1]) if d < 0 else None
                    if not (r["band"][0] <= px <= r["band"][1]) or (d > 0 and lo_seg <= r["sl"]) or (d < 0 and hi_seg >= r["sl"]):
                        continue
                    entry = px
                    risk_ = (entry - r["sl"]) * d
                    if risk_ <= 0:
                        continue
                    r.update(entry=entry, tp1=entry + d * BE_R * risk_, rr=(r["tp"] - entry) * d / risk_)
                    sq = squad(r, pip, cx.cfg.get("pip_value_usd_per_lot", 10.0))
                steps = [(f"1W {r['S']['W1']:+d} · 1D {r['S']['D1']:+d} · 4H {r['S']['H4']:+d}", r["S"]["D1"] == d, r["setup"] or ""),
                         (f"In {'1W+1D' if z['overlap'] else '+'.join(sorted(z['tfs']))} AOI {fmt(z['lo'], pip)}-{fmt(z['hi'], pip)} ({z['touches']} touches)", True, ""),
                         (f"{etf} closed confirmation", True, "engulfing" if r["c"].get("engulf") else "doji"),
                         (f"GPA {r['gpa']} % (grade {r['grade']})", r["gpa"] >= 70, ""), (f"R:R {r['rr']:.2f} >= 2.0", r["rr"] >= MIN_RR, "")]
                s = _make(key, r["setup"] or "SF_BOUNCE", d, m5, k0, entry, r["sl"], r["tp1"], r["tp"], 0.0, True, 0, Tx + HOLD_DAYS * DAY, steps,
                          {"aoi": (z["lo"], z["hi"], z["t0"]), "sos": (r["c"]["sos"]["level"], r["c"]["sos"]["time"]) if r["c"].get("sos") else None},
                          cost, zone=r["band"], be_off=BE_PIPS * pip)
                if not s:
                    continue
                s["result"] = run(m5, k0, d, entry, r["sl"], r["tp1"], r["tp"], 0.0, True, 0, s["holdUntil"], cost, None, None, None,
                                  BE_PIPS * pip, None, 0, True)
                rk = RISK_BY_GRADE.get(r["grade"], 0.0)
                s.update(gpa=r["gpa"], grade=r["grade"], setupType=r["setup"], riskPct=rk, etf=etf, consensus=sq["consensus"], vetoes=sq["vetoes"],
                         checklistGpa=checklist_of(r), confirmedAt=T, deferred=Tx != T, fridayExit=True,
                         desk=[{"key": k2, "role": role, "status": sq["agents"][name]["status"], "badge": sq["agents"][name]["badge"],
                                "score": sq["agents"][name]["score"]} for k2, name, role, _ in ROLES],
                         zoneInfo={"low": z["lo"], "high": z["hi"], "tfs": sorted(z["tfs"], reverse=True), "touches": z["touches"],
                                   "width": round(z["width"]), "psych": z["psych"], "overlap": z["overlap"]},
                         psychTp=r.get("psych_tp"), slPips=round(abs(entry - r["sl"]) / pip, 1), tpPips=round(abs(r["tp"] - entry) / pip, 1),
                         bePips=round(abs(r["tp1"] - entry) / pip, 1))
                s["checklist"] = [(f"1 · Consensus >= 70 ({sq['consensus']})", sq["consensus"] >= 70, ""),
                                  (f"2 · GPA >= 70 % ({r['gpa']} %, grade {r['grade']})", r["gpa"] >= 70, ""),
                                  ("3 · No agent in veto", not sq["vetoes"], ", ".join(sq["vetoes"]) or "none"),
                                  ("4 · Trigger sniper and risk guardian ok", sq["agents"]["trigger_sniper"]["status"] == "ok" and
                                   sq["agents"]["risk_guardian"]["status"] == "ok", sq["agents"]["risk_guardian"]["badge"])]
                s["pass"] = sq["execute"]
                out.append(s)
    out.sort(key=lambda s: (s["time"], ENTRY_TFS.index(s["etf"])))
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("5 · One trade per pair at a time", False, "the previous trade is still open"))
            continue
        busy = m5[s["result"]["at"]].time + M5S if "at" in s["result"] else 1 << 62
    return out, []


# ---------------------------------------------------------------- the live read: the 5 agents and the pairReport
def report(key: str, m5, h1, now: int, setups: list, news_events, d1, usd_per_pip: Optional[float] = None, spread: Optional[float] = None) -> dict:
    cx = context(key, m5, h1, d1, spread)
    pip = cx.pip
    pv = usd_per_pip or cx.cfg.get("pip_value_usd_per_lot", 10.0)
    nw = news_times(key, news_events) if news_events is not None else None
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE") and s["pass"]]
    cand = live[-1] if live else None
    best = None
    for etf in ENTRY_TFS:  # the read now: each entry timeframe's last closed candle, both directions; the most advanced one
        e = cx.tf[etf]
        t = e.idx(m5[-1].time + M5S)
        if t < 60:
            continue
        for d in (1, -1):
            r = evaluate(cx, etf, t, d, nw, now)
            c = r["c"]
            rank = (r["S"]["D1"] == d, bool(r["zone"]), bool(c.get("engulf") or c.get("doji")), bool(c.get("sos")), r["gpa"], -ENTRY_TFS.index(etf))
            if best is None or rank > best[0]:
                best = (rank, r)
    r = best[1]
    if cand:  # a live passing setup: the read of the candle it fired on
        e = cx.tf[cand["etf"]]
        tt = e.idx(cand["confirmedAt"])
        if tt >= 60:
            r = evaluate(cx, cand["etf"], tt, cand["dir"], nw, cand["time"])
            if "entry" in r:
                r.update(entry=cand["entry"], tp1=cand["tp1"], rr=cand["rr"])
    sq = squad(r, pip, pv)
    execute = bool(cand) and sq["execute"]
    decision = sq["decision"] if (execute or sq["decision"] != "EXECUTE") else "WAIT_FOR_TRIGGER"
    d, c, z = r["dir"], r["c"], r["zone"]
    radar = None
    if sq["radar"] and z:
        st = c["sos"]["time"] if c.get("sos") else r["T"]
        radar = {"id": f"RADAR-{key}-{'B' if d > 0 else 'S'}-{round(z['lo'] / pip)}-{st}", "direction": "BUY" if d > 0 else "SELL",
                 "tf": "1W+1D" if z["overlap"] else ("1D" if "D1" in z["tfs"] else "1W"), "touches": z["touches"], "low": z["lo"], "high": z["hi"],
                 "psych": z["psych"], "etf": r["etf"], "gpa": r["gpa"], "grade": r["grade"], "time": st, "setup": r["setup"]}
    contract = {"pair": cx.cfg["symbol"], "strategy_name": STRATEGY_NAME, "setup_type": r["setup"],
                "timestamp_utc": datetime.fromtimestamp(m5[-1].time + M5S, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "direction": "BUY" if d > 0 else "SELL", "consensus_score": sq["consensus"], "gpa_score": r["gpa"], "grade": r["grade"],
                "final_decision": decision, "checklist": checklist_of(r), "agents": sq["agents"]}
    ui = [{"key": k, "id": name, "name": role, "role": role, "status": sq["agents"][name]["status"], "finding": sq["agents"][name]["badge"],
           "badge": sq["agents"][name]["badge"], "score": sq["agents"][name]["score"], "weight": w, "lines": sq["agents"][name]["details"],
           "details": sq["agents"][name]["details"]} for k, name, role, w in ROLES]
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand if execute else None, "radar": radar, "read": r}


# ---------------------------------------------------------------- the chart
def draw_objects(key: str, m5, h1, d1, now: int, r_fn=round, spread: Optional[float] = None) -> dict:
    """1W / 1D AOI boxes (touches, psych), the round number line, the 1D and 4H body-close HH / HL / LH / LL, the LTF SoS
    line. The EMA 50 is drawn by the chart itself on every timeframe."""
    cx = context(key, m5, h1, d1, spread)
    pip = cx.pip
    w1, dd, h4 = cx.tf["W1"], cx.tf["D1"], cx.tf["H4"]
    iw, id_, i4 = w1.idx(now), dd.idx(now), h4.idx(now)
    end = m5[-1].time + M5S
    px = m5[-1].close
    boxes, segs, labels = [], [], []
    zs = sorted(cx.aois(iw, id_), key=lambda z: max(z["lo"] - px, px - z["hi"], 0))[:8] if iw >= 0 and id_ >= 0 else []
    for z in zs:
        tfl = "1W/1D" if z["overlap"] else ("1D" if "D1" in z["tfs"] else "1W")
        boxes.append({"from": z["t0"], "to": end + 6 * H1S, "top": r_fn(z["hi"]), "bottom": r_fn(z["lo"]), "kind": "ob", "dir": 1 if z["hi"] < px else -1,
                      "label": f"{tfl} AOI · {z['touches']} Touches" + (f" · Psych {fmt(z['psych'], pip)}" if z["psych"] is not None else "")})
        if z["psych"] is not None:
            segs.append({"from": z["t0"], "to": end, "price": r_fn(z["psych"]), "kind": "eq", "dir": 0, "label": f"Psych {fmt(z['psych'], pip)}"})
    for tf, i in ((dd, id_), (h4, i4)):
        if i < 0:
            continue
        st = tf.s
        tr = st["trend"][i]
        names = (("HH", "hh", 1), ("HL", "hl", -1)) if tr >= 0 else (("LH", "lh", 1), ("LL", "ll", -1))
        for name, k, dirn in names:
            lv = st[k][i]
            if lv and lv[1] >= i - 150:
                segs.append({"from": tf.t[lv[1]], "to": end, "price": r_fn(lv[0]), "kind": "liquidity", "dir": dirn, "label": f"{tf.name.replace('D1', '1D').replace('H4', '4H')} {name}"})
                labels.append({"time": tf.t[lv[1]], "price": r_fn(lv[0]), "text": name, "above": dirn > 0, "kind": "structure"})
    e = cx.tf["H1"]
    t = e.idx(end)
    if t > 60 and id_ >= 0:
        atr_d = dd.at[id_] or 0
        for d in (1, -1):
            for z in zs:
                res = sos_at(e, t, z, d, 0.3 * atr_d)
                if res:
                    segs.append({"from": res["time"] - 6 * H1S, "to": end, "price": r_fn(res["level"]), "kind": "bos", "dir": d, "label": "1H SoS"})
                    break
    return {"boxes": boxes, "segments": segs, "labels": labels, "lines": []}
