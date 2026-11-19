"""
FXAlexG "Set & Forget": the ONE engine of the app, for gold and the 28 forex pairs. The owner's spec (2026-11-19)
"FXAlexG Set & Forget — Redesigned 5-Agent Architecture, Profitable Mathematical Engine, Notification Pipeline",
applied to the letter. Pure price action on CLOSED candles (c.time + tf_sec <= now): no tick volume, no M5 gap veto.
M5 only follows the trades.

  3.1  body-only candles: B+ = max(O, C), B- = min(O, C), dB = B+ - B-, R = H - L, UW = H - B+, LW = B- - L.
       Snake Trick elbows (k: W1 2, D1 / H4 / H1 / M30 / M15 3): an upper elbow at t when B+_t is the max of B+ over
       [t-k, t+k] and a close of [t+1, t+k] is below it (P = B+_t, W = max H of [t-1, t+1]); the lower elbow mirrors it.
       Structure S in {+1, -1}: bullish -> bearish iff a close < P(HL) - 0.5 pip, bearish -> bullish iff a close
       > P(LH) + 0.5 pip. Sync(d): S&F-SWING  W1 = D1 = d (H4 = d, or H4 pulling back into the AOI);
       S&F-DAY  D1 = H4 = d at a D1 AOI with no opposing W1 AOI within 1.5 R.
  3.2  AOIs: elbows of W1 (last 156 bars) and D1 (last 300) clustered into zones 12 pips <= width <= W_max with >= 3 D1
       touches (or >= 2 W1) >= 4 bars apart; overlapping W1 and D1 zones merged; the "every 500" level
       round(Z_mid / step) * step within 8 pips widens the zone. InAOI: one of the last 24 H1 candles within
       d_prox = max(8 pips, 0.12 ADR20) of the zone, the close beyond Z_distal (Z_low - 10 pips for a buy), the D1
       close not more than 10 pips beyond the distal edge.
  3.3  S_AlexG: 18 items, 160 % in all; A+ >= 100, A 90-99, B 80-89 (the minimum), WAIT < 80.
  3.4  the two-step trigger on H1, then M30, then M15: SoS (a body close beyond the LTF LH / HL after the swing at
       the AOI), then an Engulfing (C > O, C > B+_{t-1}, dB >= 0.85 dB_{t-1}) at the SoS or within 24 candles, above
       L_swing. Market at the close when RR >= 2.5 and R <= 1.8 ATR14, else a limit at the candle's middle.
  3.5  SL = min(Z_low, L_swing) - max(5 pips, 2 spread), at most 1.2 ADR20 from the entry; TP = min(opposing D1 / W1
       structure - 5 pips, entry + 3.5 R), RR >= 2.5; at +1.5 R the stop goes to the entry and 25 % is banked.
  4    the 5 agents (weights 0.25 / 0.25 / 0.25 / 0.15 / 0.10) and the execution gate.

Every number the spec leaves open is marked CHOICE and was fixed before any result was seen.
"""

import json
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .playbook import DAY, H1S, H4S, M5S, M15S, NEWS_MIN, _Bar, _make, atr, ema, m5_index_at_close, resample

W1S, M30S = 7 * DAY, 1800
TF_SEC = {"W1": W1S, "D1": DAY, "H4": H4S, "H1": H1S, "M30": M30S, "M15": M15S}
K = {"W1": 2, "D1": 3, "H4": 3, "H1": 3, "M30": 3, "M15": 3}
N_AOI = {"W1": 156, "D1": 300}
MIN_TOUCH = {"W1": 2, "D1": 3}
TOUCH_GAP, MIN_W_PIPS, PSYCH_PIPS = 4, 12.0, 8.0
PROX_PIPS, PROX_ADR, H1_WINDOW, DISTAL_PIPS, APPROACH_PIPS = 8.0, 0.12, 24, 10.0, 15.0
ENTRY_TFS = ("H1", "M30", "M15")
RETEST_BARS, ENGULF_RATIO, MARKET_ATR = 24, 0.85, 1.8
BUF_PIPS, BUF_SPREAD, SL_MAX_ADR, FRONT_PIPS, TP_CAP_R, MIN_RR = 5.0, 2.0, 1.2, 5.0, 3.5, 2.5
BE_R, PART, BE_OFF = 1.5, 0.25, 0.0  # at +1.5 R: the stop to the entry (+0), 25 % banked
GRADE_MIN, RADAR_MIN, SPREAD_MAX, W1_OPP_R = 80, 65, 0.15, 1.5
SWING_BARS = 24  # CHOICE: the swing before the SoS is looked for in the 24 candles up to it
HISTORY_BARS = 40  # CHOICE: an HTF chart pattern is read on the last 40 candles, its last turn within 20
LIMIT_BARS = 24  # CHOICE: a limit order waits 24 candles of its entry timeframe, then it is cancelled
HOLD_DAYS = 30  # CHOICE: a trade still open after 30 days is closed at market (Set & Forget, no other time exit)
STRATEGY_NAME = "FXAlexG Set & Forget"
# Research switches (smc/tools/fix_test.py). The defaults ARE the md: the live app never changes them.
#   entry  "md": market at the close when R:R >= 2.5 and the range is normal, else the 50 % limit;
#          "mid": always the 50 % limit;  "neck": always a limit at the SoS neckline
#   sl_floor_adr  0: the md's stop; x > 0: the stop at least x ADR20 from the entry (still <= 1.2 ADR20)
#   sync   "md": S&F-SWING and S&F-DAY;  "swing": S&F-SWING only;  "full": W1 = D1 = H4 only
#   gate   "md": S_AlexG >= 80;  "none": no score gate;  "strict": >= 50 without the near-always items (TRIVIAL)
VARIANT = {"entry": "md", "sl_floor_adr": 0.0, "sync": "md", "gate": "md"}
TRIVIAL = ("psych", "aoi_d1", "elbow_d1", "elbow_h4")
SETUPS = {"SF_SWING": "S&F-SWING — W1 + D1 in sync", "SF_DAY": "S&F-DAY — D1 + H4 in sync"}
CFG_DIR = Path(__file__).parent / "configs"
_cfg: dict = {}


def config(key: str) -> dict:
    if key not in _cfg:
        _cfg[key] = json.loads((CFG_DIR / f"{key}.json").read_text(encoding="utf-8"))
    return _cfg[key]


def season_risk(T: int) -> float:
    """The seasonal risk: 1 % Jan-Mar and Oct-Dec, 0.75 % Apr-May and Aug-Sep, 0.5 % Jun-Jul."""
    m = datetime.fromtimestamp(T, timezone.utc).month
    return 0.5 if m in (6, 7) else 0.75 if m in (4, 5, 8, 9) else 1.0


def hm(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M")


def badge(s: str) -> str:
    """An agent's badge: at most 60 characters."""
    return s if len(s) <= 60 else s[:59] + "…"


def fmt(v: float, pip: float) -> str:
    return f"{v:.{2 if pip >= 0.1 else 3 if pip >= 0.01 else 5}f}"


def bp(x) -> float:
    return max(x.open, x.close)


def bm(x) -> float:
    return min(x.open, x.close)


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


# ---------------------------------------------------------------- the candle patterns
def engulf(p, x, d: int) -> bool:
    """3.4 step 2: C > O, C > B+(t-1), dB >= 0.85 dB(t-1) for a buy; the mirror for a sell."""
    b, pb = abs(x.close - x.open), abs(p.close - p.open)
    if d > 0:
        return x.close > x.open and x.close > bp(p) and b >= ENGULF_RATIO * pb
    return x.close < x.open and x.close < bm(p) and b >= ENGULF_RATIO * pb


def pinbar(x, d: int) -> bool:
    """CHOICE (the spec names the pin bar without sizing it): body <= 1/3 of the range, the rejection wick >= 60 % of it."""
    r = x.high - x.low
    if r <= 0 or abs(x.close - x.open) > r / 3:
        return False
    return (bm(x) - x.low >= 0.6 * r) if d > 0 else (x.high - bp(x) >= 0.6 * r)


def star(a, b, c, d: int) -> bool:
    """CHOICE: a morning (evening) star: a strong opposite candle (body >= half its range), a small one (body <= 30 % of
    the first body), then a candle of the trade's side closing beyond the middle of the first body."""
    r1, b1 = a.high - a.low, abs(a.close - a.open)
    if r1 <= 0 or b1 < 0.5 * r1 or abs(b.close - b.open) > 0.3 * b1:
        return False
    mid = (a.open + a.close) / 2
    if d > 0:
        return a.close < a.open and c.close > c.open and c.close > mid
    return a.close > a.open and c.close < c.open and c.close < mid


# ---------------------------------------------------------------- 3.1 Snake Trick elbows and the structure
def find_elbows(c, k: int) -> tuple[list[tuple], list[tuple]]:
    """(upper, lower) elbows as (index, P, W). An elbow at t is known at the close of t + k."""
    n = len(c)
    B, Bm, C = [bp(x) for x in c], [bm(x) for x in c], [x.close for x in c]
    up, dn = [], []
    for t in range(k, n - k):
        if B[t] == max(B[t - k:t + k + 1]) and min(C[t + 1:t + k + 1]) < B[t]:
            up.append((t, B[t], max(x.high for x in c[t - 1:t + 2])))
        if Bm[t] == min(Bm[t - k:t + k + 1]) and max(C[t + 1:t + k + 1]) > Bm[t]:
            dn.append((t, Bm[t], min(x.low for x in c[t - 1:t + 2])))
    return up, dn


def trace_structure(c, up: list, dn: list, k: int, pip: float) -> dict:
    """Per candle: S (+1 / -1, 0 before the first break), HH, HL, LL, LH as (P, index), and events
    [(i, 'BOS' | 'SOS', dir, level)]. Shifts exactly as the spec: a close < P(HL) - 0.5 pip, a close > P(LH) + 0.5 pip.
    CHOICE where the spec is silent: the machine starts at the first close beyond a confirmed elbow; a close beyond the
    last confirmed elbow of the trend's side (a BOS) moves the protected HL to the lowest body of the pullback before it
    (HH is always in front of HL), the mirror for LH."""
    n, eps = len(c), 0.5 * pip
    B, Bm = [bp(x) for x in c], [bm(x) for x in c]
    out = {q: [None] * n for q in ("trend", "hh", "hl", "ll", "lh")}
    events = []
    tr, hh, hl, ll, lh, top, bot = 0, None, None, None, None, None, None
    last_up = last_dn = None
    ui = di = 0

    def lowest(a, b):
        q = min(range(a, b + 1), key=lambda u: Bm[u])
        return Bm[q], q

    def highest(a, b):
        q = max(range(a, b + 1), key=lambda u: B[u])
        return B[q], q
    for i in range(n):
        while ui < len(up) and up[ui][0] + k <= i:
            last_up = up[ui]
            ui += 1
            if tr == 1 and last_up[0] > hl[1]:
                top = last_up
        while di < len(dn) and dn[di][0] + k <= i:
            last_dn = dn[di]
            di += 1
            if tr == -1 and last_dn[0] > lh[1]:
                bot = last_dn
        x = c[i].close
        if tr == 0:
            if last_up and x > last_up[1] + eps:
                tr, hl, top = 1, lowest(last_up[0], i), None
                hh = highest(hl[1], i)
                events.append((i, "BOS", 1, last_up[1]))
            elif last_dn and x < last_dn[1] - eps:
                tr, lh, bot = -1, highest(last_dn[0], i), None
                ll = lowest(lh[1], i)
                events.append((i, "BOS", -1, last_dn[1]))
        elif tr == 1:
            if x < hl[0] - eps:
                events.append((i, "SOS", -1, hl[0]))
                tr, lh, bot = -1, highest(hl[1], i), None
                ll = lowest(lh[1], i)
            elif top and x > top[1]:
                events.append((i, "BOS", 1, top[1]))
                hl, top = lowest(top[0], i), None
                hh = highest(hl[1], i)
            elif B[i] > hh[0]:
                hh = (B[i], i)
        else:
            if x > lh[0] + eps:
                events.append((i, "SOS", 1, lh[0]))
                tr, hl, top = 1, lowest(lh[1], i), None
                hh = highest(hl[1], i)
            elif bot and x < bot[1]:
                events.append((i, "BOS", -1, bot[1]))
                lh, bot = highest(bot[0], i), None
                ll = lowest(lh[1], i)
            elif Bm[i] < ll[0]:
                ll = (Bm[i], i)
        out["trend"][i], out["hh"][i], out["hl"][i], out["ll"][i], out["lh"][i] = tr, hh, hl, ll, lh
    out["events"] = events
    return out


class TF:
    """One timeframe: candles, elbows, structure, EMA 50, ATR 14."""

    def __init__(self, name: str, c, pip: float):
        self.name, self.c, self.pip = name, c, pip
        self.t = [x.time for x in c]
        self.step, self.k = TF_SEC[name], K[name]
        self.cl = [x.close for x in c]
        self.up, self.dn = find_elbows(c, self.k)
        self.s = trace_structure(c, self.up, self.dn, self.k, pip)
        self.e50 = ema(self.cl, 50)
        self.at = atr(c, 14)
        self.sos_at: dict[int, list] = {}
        for i, kind, d, lv in self.s["events"]:
            if kind == "SOS":
                self.sos_at.setdefault(i, []).append((d, lv))

    def idx(self, T: int) -> int:
        """The last candle closed at T."""
        return bisect_right(self.t, T - self.step) - 1

    def trend(self, i: int) -> int:
        return self.s["trend"][i] if i >= 0 else 0

    def elbows(self, i: int, n: int) -> list[tuple]:
        """The elbows known at the close of i among the last n candles: (index, P, kind) with kind +1 upper, -1 lower."""
        lo = i - n + 1
        out = [(q, p, 1) for q, p, _ in self.up if lo <= q and q + self.k <= i]
        out += [(q, p, -1) for q, p, _ in self.dn if lo <= q and q + self.k <= i]
        return out


# ---------------------------------------------------------------- 3.2 AOIs
def spaced(idxs: list[int]) -> list[int]:
    """The touches counted: elbow indexes at least 4 candles apart (in time order, greedy)."""
    out = []
    for q in sorted(idxs):
        if not out or q - out[-1] >= TOUCH_GAP:
            out.append(q)
    return out


def build_aois(tf: TF, i: int, pip: float, wmax: float) -> list[dict]:
    """Zones of one timeframe at the close of i: the elbows' P clustered into [lo, hi] no wider than W_max with the
    minimum of touches. CHOICE: of the clusters starting at an elbow, the one with the most touches (then the
    narrowest) is kept; the zones kept never overlap (the most touches first); a cluster narrower than 12 pips is
    widened to 12 around its middle (the spec's 12-pip floor)."""
    if i < 2 * tf.k + 2:
        return []
    pts = sorted(tf.elbows(i, N_AOI[tf.name]), key=lambda e: e[1])
    need, cands = MIN_TOUCH[tf.name], []
    for a in range(len(pts)):
        best = None
        for b in range(a, len(pts)):
            if (pts[b][1] - pts[a][1]) / pip > wmax:
                break
            grp = pts[a:b + 1]
            hits = spaced([q for q, _, _ in grp])
            if len(hits) >= need and (best is None or len(hits) > best[0]):
                best = (len(hits), b, hits, grp)
        if best:
            n_, b, hits, grp = best
            cands.append({"lo": pts[a][1], "hi": pts[b][1], "touches": n_, "hits": hits, "tfs": {tf.name},
                          "roles": [(q, -kind) for q, _, kind in grp], "t0": tf.t[hits[0]]})
    cands.sort(key=lambda z: (-z["touches"], z["hi"] - z["lo"]))
    out = []
    for z in cands:
        if all(z["hi"] < y["lo"] or z["lo"] > y["hi"] for y in out):
            out.append(z)
    for z in out:
        if (z["hi"] - z["lo"]) / pip < MIN_W_PIPS:
            mid = (z["hi"] + z["lo"]) / 2
            z["lo"], z["hi"] = mid - MIN_W_PIPS * pip / 2, mid + MIN_W_PIPS * pip / 2
        z["t_" + tf.name.lower()] = z["touches"]
    return out


def merge_zones(w1: list[dict], d1: list[dict]) -> list[dict]:
    """A W1 zone and the D1 zones that overlap it are one W1+D1 zone."""
    out, used = [], set()
    for zw in w1:
        z = {**zw, "tfs": set(zw["tfs"]), "t_d1": 0}
        for q, zd in enumerate(d1):
            if zd["lo"] <= z["hi"] and zd["hi"] >= z["lo"]:
                used.add(q)
                z.update(lo=min(z["lo"], zd["lo"]), hi=max(z["hi"], zd["hi"]), t_d1=max(z["t_d1"], zd["touches"]),
                         roles=sorted(z["roles"] + zd["roles"]), t0=min(z["t0"], zd["t0"]))
                z["tfs"].add("D1")
        z["touches"] = max(z["t_w1"], z["t_d1"])
        out.append(z)
    for q, zd in enumerate(d1):
        if q not in used:
            out.append({**zd, "tfs": set(zd["tfs"]), "t_w1": 0})
    for z in out:
        z["overlap"] = z["tfs"] == {"W1", "D1"}
    return out


def snap_psych(z: dict, pip: float, step: float) -> dict:
    """The "every 500" rule: P = round(Z_mid / step) * step; inside [Z_low - 8 pips, Z_high + 8 pips] it widens the zone."""
    p = round(round((z["lo"] + z["hi"]) / 2 / step) * step, 6)
    if z["lo"] - PSYCH_PIPS * pip <= p <= z["hi"] + PSYCH_PIPS * pip:
        z["lo"], z["hi"], z["psych"] = min(z["lo"], p), max(z["hi"], p), p
    else:
        z["psych"] = None
    z["width"] = (z["hi"] - z["lo"]) / pip
    return z


def dist(lo: float, hi: float, z: dict) -> float:
    """The distance between the price range [lo, hi] and the zone (0 when they overlap)."""
    return max(z["lo"] - hi, lo - z["hi"], 0.0)


# ---------------------------------------------------------------- HTF confluences at the zone
def htf_ema(tf: TF, i: int, z: dict, d: int, prox: float) -> bool:
    """CHOICE: the 50 EMA as dynamic support (resistance): at the zone (within d_prox) and the close on the trade's side."""
    e = tf.e50[i] if i >= 0 else None
    return e is not None and z["lo"] - prox <= e <= z["hi"] + prox and d * (tf.cl[i] - e) > 0


def htf_elbow(tf: TF, i: int, z: dict, d: int, prox: float) -> bool:
    """CHOICE: a prior structure elbow of this timeframe at the zone (within d_prox), rejected by one of the last 3
    candles: it reached the elbow (within d_prox) and closed beyond it on the trade's side."""
    if i < 3:
        return False
    for q, p, _ in tf.elbows(i - 3, N_AOI.get(tf.name, 300)):
        if z["lo"] - prox <= p <= z["hi"] + prox:
            for j in range(i - 2, i + 1):
                x = tf.c[j]
                if (x.low <= p + prox and x.close > p) if d > 0 else (x.high >= p - prox and x.close < p):
                    return True
    return False


def htf_candle(tf: TF, i: int, z: dict, d: int, prox: float) -> Optional[str]:
    """A pin bar, an engulfing or a star on one of the last 2 closed candles, at the zone (within d_prox)."""
    for j in (i, i - 1):
        if j < 2:
            continue
        x = tf.c[j]
        if dist(x.low, x.high, z) > prox:
            continue
        if pinbar(x, d):
            return "Pin bar"
        if engulf(tf.c[j - 1], x, d):
            return "Engulfing"
        if star(tf.c[j - 2], tf.c[j - 1], x, d):
            return "Morning star" if d > 0 else "Evening star"
    return None


def htf_pattern(tf: TF, i: int, z: dict, d: int, prox: float) -> Optional[str]:
    """CHOICE: a double bottom / inverse H&S (buy) or double top / H&S (sell) on this timeframe's elbows at the zone
    (within d_prox), in the last 40 candles, its last turn within 20, and a close beyond the neckline since."""
    turns = sorted((q, p) for q, p, kind in tf.elbows(i, HISTORY_BARS) if kind == -d)
    opp = sorted((q, p) for q, p, kind in tf.elbows(i, HISTORY_BARS) if kind == d)
    for n_ in (3, 2):
        if len(turns) < n_:
            continue
        ts = turns[-n_:]
        if i - ts[-1][0] > 20 or not all(z["lo"] - prox <= p <= z["hi"] + prox for _, p in ts):
            continue
        if n_ == 3 and not ((ts[1][1] < min(ts[0][1], ts[2][1])) if d > 0 else (ts[1][1] > max(ts[0][1], ts[2][1]))):
            continue
        mids = [p for q, p in opp if ts[0][0] < q < ts[-1][0]]
        if not mids:
            continue
        neck = max(mids) if d > 0 else min(mids)
        if any((tf.cl[q] > neck) if d > 0 else (tf.cl[q] < neck) for q in range(ts[-1][0] + 1, i + 1)):
            return ("Inverse H&S" if d > 0 else "H&S") if n_ == 3 else ("Double bottom" if d > 0 else "Double top")
    return None


# ---------------------------------------------------------------- 3.4 the LTF trigger
def find_sos(e: TF, t: int, z: dict, d: int, prox: float) -> Optional[dict]:
    """Step 1: the latest shift of the entry timeframe's structure to d in the last 24 candles (a body close beyond the
    LTF LH / HL), whose swing (the lowest low of the 24 candles up to it for a buy) formed at the zone (within d_prox),
    and never broken since (the retest stays above L_swing)."""
    for s in range(t, max(t - RETEST_BARS, 1) - 1, -1):
        for dd, lv in e.sos_at.get(s, []):
            if dd != d:
                continue
            a = max(s - SWING_BARS, 0)
            seg = range(a, s + 1)
            q = min(seg, key=lambda u: e.c[u].low) if d > 0 else max(seg, key=lambda u: e.c[u].high)
            swing = e.c[q].low if d > 0 else e.c[q].high
            if dist(e.c[q].low, e.c[q].high, z) > prox:
                return None
            if any((e.c[u].low <= swing) if d > 0 else (e.c[u].high >= swing) for u in range(s + 1, t + 1)):
                return None
            return {"index": s, "time": e.t[s] + e.step, "level": lv, "swing": swing}
    return None


# ---------------------------------------------------------------- the context of one read
class Ctx:
    def __init__(self, key: str, m5, h1, d1, spread: Optional[float] = None):
        self.key, self.cfg = key, config(key)
        self.pip, self.psych = self.cfg["pip"], self.cfg.get("psych_step", 0.005)
        self.wmax = float(self.cfg.get("max_aoi_pips", 60))
        self.spread = spread if spread else self.cfg["spread_pips"] * self.pip
        self.m5, self.t5 = m5, [x.time for x in m5]
        p = self.pip
        self.tf = {"W1": TF("W1", weekly(d1), p), "D1": TF("D1", d1, p), "H4": TF("H4", resample(h1, H4S), p),
                   "H1": TF("H1", h1, p), "M30": TF("M30", resample(m5, M30S), p), "M15": TF("M15", resample(m5, M15S), p)}
        self._aoi: dict = {}

    def aois(self, iw: int, id_: int) -> list[dict]:
        if (iw, id_) not in self._aoi:
            zs = merge_zones(build_aois(self.tf["W1"], iw, self.pip, self.wmax) if iw >= 0 else [],
                             build_aois(self.tf["D1"], id_, self.pip, self.wmax) if id_ >= 0 else [])
            self._aoi[(iw, id_)] = [snap_psych(z, self.pip, self.psych) for z in zs]
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


CONF = [("sync", 20, "2+ consecutive TFs in sync"), ("aoi_w1", 10, "Active W1 AOI reaction"), ("aoi_d1", 10, "Active D1 AOI reaction"),
        ("ema_w1", 5, "W1 50 EMA dynamic S/R"), ("ema_d1", 5, "D1 50 EMA dynamic S/R"), ("ema_h4", 5, "H4 50 EMA dynamic S/R"),
        ("psych", 5, "Round psych 500 level inside AOI"), ("elbow_w1", 10, "W1 prior structure elbow rejection"),
        ("elbow_d1", 10, "D1 prior structure elbow rejection"), ("elbow_h4", 5, "H4 prior structure elbow rejection"),
        ("candle_w1", 10, "W1 candle rejection (pin bar / engulfing / star)"), ("candle_d1", 10, "D1 candle rejection (pin bar / engulfing / star)"),
        ("candle_h4", 5, "H4 candle rejection (pin bar / engulfing / star)"), ("pattern_w1", 10, "W1 chart pattern (H&S / double top-bottom)"),
        ("pattern_d1", 10, "D1 chart pattern (H&S / double top-bottom)"), ("pattern_h4", 10, "H4 chart pattern (H&S / double top-bottom)"),
        ("sos", 10, "LTF shift of structure (SoS)"), ("engulf", 10, "LTF engulfing trigger")]


def grade_of(score: int) -> str:
    return "A+" if score >= 100 else "A" if score >= 90 else "B" if score >= GRADE_MIN else "WAIT"


def _plan(cx: Ctx, e: TF, q: int, z: dict, d: int, sos: dict, adr: Optional[float], iw: int, id_: int) -> dict:
    """3.4 / 3.5: the order type, the entry, the stop, the +1.5 R step and the target from the engulfing candle q."""
    pip, x = cx.pip, e.c[q]
    buf = max(BUF_PIPS * pip, BUF_SPREAD * cx.spread)
    base = (min(z["lo"], sos["swing"]) - buf) if d > 0 else (max(z["hi"], sos["swing"]) + buf)
    levels = []  # the opposing D1 / W1 structure: their elbows of the trade's far side, and the opposing zones' near edges
    for name, i in (("D1", id_), ("W1", iw)):
        if i >= 0:
            levels += [p for _, p, kind in cx.tf[name].elbows(i, N_AOI[name]) if kind == d]
    for y in cx.aois(iw, id_):
        levels.append(y["lo"] if d > 0 else y["hi"])
    prox = max(PROX_PIPS * pip, PROX_ADR * adr) if adr else PROX_PIPS * pip
    # CHOICE: the elbows that built the zone in play are not "opposing": only levels beyond it (and its d_prox) count
    levels = [p for p in levels if ((p > z["hi"] + prox) if d > 0 else (p < z["lo"] - prox))]

    def at(entry: float) -> dict:
        sl = base
        if adr and VARIANT["sl_floor_adr"] and (entry - sl) * d < VARIANT["sl_floor_adr"] * adr:
            sl = entry - d * VARIANT["sl_floor_adr"] * adr
        if adr and (entry - sl) * d > SL_MAX_ADR * adr:
            sl = entry - d * SL_MAX_ADR * adr
        risk = (entry - sl) * d
        if risk <= 0:
            return {"entry": entry, "sl": sl, "rr": 0.0}
        ahead = [p for p in levels if (p - entry) * d > 0]
        struct = (min(ahead) if d > 0 else max(ahead)) if ahead else None
        cap = entry + d * TP_CAP_R * risk
        tp = cap if struct is None else (min(struct - FRONT_PIPS * pip, cap) if d > 0 else max(struct + FRONT_PIPS * pip, cap))
        return {"entry": entry, "sl": sl, "tp": tp, "tp1": entry + d * BE_R * risk, "rr": (tp - entry) * d / risk, "struct": struct, "risk": risk}
    a14 = e.at[q] or 0
    big = a14 > 0 and x.high - x.low > MARKET_ATR * a14
    if VARIANT["entry"] == "neck":
        lim = at(sos["level"])
        return {**lim, "market": False, "band": (sos["level"], sos["level"]), "big": big}
    mk = at(x.close)
    if VARIANT["entry"] == "md" and mk["rr"] >= MIN_RR and not big:
        return {**mk, "market": True, "band": (x.close, x.close), "big": big}
    mid = (x.open + x.close) / 2
    lim = at(mid)
    return {**lim, "market": False, "band": (min(sos["level"], mid), max(sos["level"], mid)), "big": big}


def evaluate(cx: Ctx, etf: str, t: int, d: int, news: Optional[list[int]] = None, exec_T: Optional[int] = None) -> dict:
    """Everything the spec computes for direction d at the close of candle t of `etf`."""
    pip = cx.pip
    e = cx.tf[etf]
    T = e.t[t] + e.step
    Tx = exec_T or T
    w1, d1, h4, h1 = cx.tf["W1"], cx.tf["D1"], cx.tf["H4"], cx.tf["H1"]
    iw, id_, i4, ih = w1.idx(T), d1.idx(T), h4.idx(T), h1.idx(T)
    S = {"W1": w1.trend(iw), "D1": d1.trend(id_), "H4": h4.trend(i4)}
    adr = cx.adr20(id_)
    prox = max(PROX_PIPS * pip, PROX_ADR * adr) if adr else PROX_PIPS * pip
    zones = cx.aois(iw, id_) if iw >= 0 and id_ >= 0 else []
    C = e.cl[t]
    dclose = d1.cl[id_] if id_ >= 0 else C
    win = h1.c[max(ih - H1_WINDOW + 1, 0):ih + 1] if ih >= 0 else []
    distal = lambda z: (z["lo"] - DISTAL_PIPS * pip) if d > 0 else (z["hi"] + DISTAL_PIPS * pip)  # noqa: E731
    touched = [z for z in zones if win and min(dist(y.low, y.high, z) for y in win) <= prox]
    broken = [z for z in touched if d * (dclose - distal(z)) <= 0]
    live = [z for z in touched if z not in broken and d * (C - distal(z)) > 0]
    gap = lambda z: dist(C, C, z)  # noqa: E731
    z = min(live, key=gap) if live else None
    side = [y for y in zones if d * (C - distal(y)) > 0]  # the zones on the trade's side (support below a buy)
    near = min(side, key=gap) if side else None
    r = {"dir": d, "etf": etf, "t": t, "T": T, "Tx": Tx, "S": S, "zone": z, "zones": zones, "near": near, "price": C,
         "near_pips": gap(near) / pip if near else None, "broken": bool(broken and not live), "prox": prox, "adr": adr, "c": {}}
    full = S["W1"] == S["D1"] == S["H4"] == d
    w1d1 = S["W1"] == d and S["D1"] == d
    swing = w1d1 and (S["H4"] == d or z is not None)  # H4 with the trend, or pulling back into the AOI
    day = S["D1"] == d and S["H4"] == d and (z is None or "D1" in z["tfs"])
    r["sync_kind"] = "full" if full else "day" if day else "swing" if w1d1 else None
    if VARIANT["sync"] == "swing":
        day = False
    elif VARIANT["sync"] == "full":
        swing, day = swing and full, False
    r["setup"] = "SF_SWING" if swing else "SF_DAY" if day else None
    c = r["c"]
    items = {k: False for k, _, _ in CONF}
    items["sync"] = bool(r["setup"])
    if z:
        items["aoi_w1"], items["aoi_d1"], items["psych"] = "W1" in z["tfs"], "D1" in z["tfs"], z["psych"] is not None
        for name, i in (("W1", iw), ("D1", id_), ("H4", i4)):
            tf, lo = cx.tf[name], name.lower()
            items["ema_" + lo] = htf_ema(tf, i, z, d, prox)
            items["elbow_" + lo] = htf_elbow(tf, i, z, d, prox)
            c["candle_" + lo] = htf_candle(tf, i, z, d, prox)
            c["pattern_" + lo] = htf_pattern(tf, i, z, d, prox)
            items["candle_" + lo], items["pattern_" + lo] = bool(c["candle_" + lo]), bool(c["pattern_" + lo])
        sos = find_sos(e, t, z, d, prox)
        c["sos"] = sos
        if sos:
            q = next((u for u in range(t, sos["index"] - 1, -1) if u >= 1 and engulf(e.c[u - 1], e.c[u], d)), None)
            c["engulf_at"] = q
            items["sos"], items["engulf"] = True, q is not None
            if q is not None:
                r.update(_plan(cx, e, q, z, d, sos, adr, iw, id_))
    r["items"] = items
    r["score"] = sum(p for k, p, _ in CONF if items[k])
    r["grade"] = grade_of(r["score"])
    r["news"] = [n for n in (news or []) if abs(n - Tx) <= NEWS_MIN * 60]
    r["news_checked"] = news is not None
    r["risk_pct"] = season_risk(Tx)
    r["spread_ratio"] = cx.spread / r["risk"] if r.get("risk") else 0.0
    # trading into an opposing W1 AOI within 1.5 R, or at a multi-year extreme (beyond every W1 body of the 156 weeks)
    r["w1_block"] = None
    if "entry" in r and r.get("risk"):
        for y in zones:
            edge = y["lo"] if d > 0 else y["hi"]
            if "W1" in y["tfs"] and y is not z and 0 < (edge - r["entry"]) * d < W1_OPP_R * r["risk"]:
                r["w1_block"] = f"Opposing W1 AOI {fmt(edge, pip)} within 1.5R"
                break
        if r["w1_block"] is None and iw >= 1:
            wk = w1.c[max(0, iw - N_AOI['W1'] + 1):iw]
            if wk and ((r["entry"] > max(bp(x) for x in wk)) if d > 0 else (r["entry"] < min(bm(x) for x in wk))):
                r["w1_block"] = "At a multi-year extreme"
    return r


# ---------------------------------------------------------------- 4 the 5 agents
ROLES = [("trend", "trend_director", "Trend & Structure Director", 0.25), ("aoi", "aoi_architect", "AOI & Location Architect", 0.25),
         ("confluence", "confluence_grader", "Confluence & Grade Scorer", 0.25), ("trigger", "trigger_sniper", "SoS & Engulfing Sniper", 0.15),
         ("risk", "risk_guardian", "Risk, RR & News Guardian", 0.10)]
SIDE = {1: "Bullish", -1: "Bearish", 0: "Neutral"}
SCORE_OF = {"ok": 100, "warn": 60, "wait": 30, "veto": 0}  # CHOICE: an agent's score from its status (the spec gives the weights only)


def zone_name(z: dict) -> str:
    return "W1+D1" if z["overlap"] else ("D1" if "D1" in z["tfs"] else "W1")


def squad(r: dict, pip: float, usd_per_pip: float = 10.0) -> dict:
    d, c, S, z = r["dir"], r["c"], r["S"], r["zone"]
    f = lambda v: fmt(v, pip)  # noqa: E731
    sd = SIDE[d]
    # 1 · trend_director
    k = r["sync_kind"]
    if r["w1_block"]:
        t_st, t_b = "veto", r["w1_block"]
    elif k == "full":
        t_st, t_b = "ok", f"W1+D1+H4 {sd} Snake Sync"
    elif k == "day":
        t_st, t_b = "ok", f"D1+H4 {sd} Snake Sync (S&F-DAY)"
    elif k == "swing":
        t_st, t_b = "warn", f"W1+D1 {sd} · H4 pulling back"
    else:
        t_st, t_b = "wait", "No 2-timeframe sync"
    trend = {"status": t_st, "badge": badge(t_b),
             "details": [f"W1 {SIDE[S['W1']]} · D1 {SIDE[S['D1']]} · H4 {SIDE[S['H4']]} (body closes only)",
                         f"Setup {SETUPS[r['setup']] if r['setup'] else 'none'}"]}
    # 2 · aoi_architect
    if z:
        a_st = "ok"
        a_b = f"{zone_name(z)} AOI {f(z['lo'])}–{f(z['hi'])}" + (f" + Psych {f(z['psych'])}" if z["psych"] is not None else "")
    elif r["broken"]:
        a_st, a_b = "veto", "D1 closed > 10 pips beyond the AOI"
    elif r["near"] and r["near_pips"] is not None and r["near_pips"] <= APPROACH_PIPS:
        a_st, a_b = "warn", f"Approaching {zone_name(r['near'])} AOI · {r['near_pips']:.0f} pips"
    else:
        a_st, a_b = "wait", "No man's land" + (f" · {zone_name(r['near'])} AOI {r['near_pips']:.0f} pips away" if r["near"] else "")
    aoi = {"status": a_st, "badge": badge(a_b),
           "details": [f"{len(r['zones'])} AOI(s) on W1 / D1 · interaction window {r['prox'] / pip:.0f} pips"] +
                      ([f"{zone_name(z)} {f(z['lo'])} – {f(z['hi'])} · {z['touches']} touches · {z['width']:.0f} pips"] if z else [])}
    # 3 · confluence_grader
    sc = r["score"]
    g_st = "ok" if sc >= GRADE_MIN else "warn" if sc >= RADAR_MIN else "wait"
    conf = {"status": g_st, "badge": badge(f"Grade {r['grade']} ({sc}%)" + (" confirmed" if g_st == "ok" else "")), "grade": r["grade"], "score100": sc,
            "details": [f"{'✅' if r['items'][q] else '▫️'} {lab} (+{p}%)" for q, p, lab in CONF]}
    # 4 · trigger_sniper
    sos, eq = c.get("sos"), c.get("engulf_at")
    etf = r["etf"]
    if sos and eq is not None:
        s_st, s_b = "ok", f"{etf} SoS + {sd} Engulfing"
    elif sos:
        s_st, s_b = "warn", f"{etf} SoS at {f(sos['level'])} · awaiting Engulfing"
    else:
        s_st, s_b = "wait", "Awaiting the LTF SoS" if z else "Awaiting the AOI"
    trig = {"status": s_st, "badge": badge(s_b),
            "details": [f"{etf} · SoS {'at ' + f(sos['level']) + ' · swing ' + f(sos['swing']) if sos else 'no'} · engulfing {eq is not None}"]}
    # 5 · risk_guardian
    news_txt = "news not checked" if not r["news_checked"] else (f"News {hm(r['news'][0])} UTC" if r["news"] else "Clear news")
    rk = r["risk_pct"]
    if "entry" not in r:
        k_st, k_b = "wait", f"Nothing to size yet · {news_txt}"
    elif r["rr"] < MIN_RR:
        k_st, k_b = "veto", f"R:R {r['rr']:.2f} < 2.5"
    elif r["spread_ratio"] > SPREAD_MAX:
        k_st, k_b = "veto", f"Spread {r['spread_ratio'] * 100:.0f}% of SL (> 15%)"
    elif r["news"]:
        k_st, k_b = "veto", f"High-impact news {hm(r['news'][0])} UTC (±30 min)"
    elif rk <= 0.5:
        k_st, k_b = "warn", f"{r['rr']:.1f}R · Summer 0.5% regime · {news_txt}"
    else:
        k_st, k_b = "ok", f"{r['rr']:.1f}R · Spread {r['spread_ratio'] * 100:.1f}% of SL · {news_txt}"
    risk = {"status": k_st, "badge": badge(k_b), "risk_percent": rk,
            "details": [f"Seasonal risk {rk:g}% · R:R floor 2.5 · spread cap 15% of SL · news ±30 min · {news_txt}"]}
    if "entry" in r and r.get("risk"):
        slp = r["risk"] / pip
        lots = int(10000 * rk / 100 / (slp * usd_per_pip) * 100) / 100 if slp else 0
        risk.update(entry=r["entry"], stop_loss=r["sl"], break_even_trigger=r["tp1"], take_profit=r["tp"], rr=round(r["rr"], 2),
                    sl_pips=round(slp, 1), position_size_lots=lots, market=r["market"])
    agents = {"trend_director": trend, "aoi_architect": aoi, "confluence_grader": conf, "trigger_sniper": trig, "risk_guardian": risk}
    for name, a in agents.items():
        a["score"] = min(100, sc) if name == "confluence_grader" else SCORE_OF[a["status"]]
    cons = round(sum(w * agents[n]["score"] for _, n, _, w in ROLES))
    veto = [n for n, a in agents.items() if a["status"] == "veto"]
    g = VARIANT["gate"]
    gate_ok = sc >= GRADE_MIN if g == "md" else True if g == "none" else         sum(p for q, p, _ in CONF if r["items"][q] and q not in TRIVIAL) >= 50
    execute = bool(r["setup"] and gate_ok and sos and eq is not None and "entry" in r and r["rr"] >= MIN_RR and not veto)
    decision = "EXECUTE" if execute else "VETOED" if veto and z else "WAIT_FOR_TRIGGER" if z else "WATCH_ONLY"
    radar = bool(t_st == "ok" and a_st == "ok" and sc >= RADAR_MIN and s_st == "warn")
    return {"agents": agents, "consensus": cons, "vetoes": veto, "execute": execute, "decision": decision, "radar": radar}


def checklist_of(r: dict) -> list[dict]:
    return [{"key": k, "label": lab, "pts": p, "ok": bool(r["items"][k])} for k, p, lab in CONF]


# ---------------------------------------------------------------- the scan (history and live)
def news_times(key: str, events) -> list[int]:
    cur = set(config(key).get("currencies") or [])
    return sorted({int(e["time"]) for e in (events or []) if e.get("currency") in cur})


def scan(key: str, m5, h1, cost: float, events=None, d1=None, research: Optional[dict] = None, spread: Optional[float] = None,
         entry_tfs: tuple = ENTRY_TFS) -> tuple[list, list]:
    """Every closed two-step trigger (SoS + Engulfing) at an AOI on the candles given, each with its plan, its result
    followed on `m5`, its checklist and `pass` (the execution gate). One trade per pair at a time."""
    if not d1 or len(h1) < 200 or len(m5) < 300:
        return [], []
    cx = context(key, m5, h1, d1, spread)
    pip = cx.pip
    nw = news_times(key, events) if events is not None else None
    fstep = min(b.time - a.time for a, b in zip(m5[-50:-1], m5[-49:]))  # the follow candles' step (M5 live)
    pv = cx.cfg.get("pip_value_usd_per_lot", 10.0)
    out, seen, passed = [], set(), set()
    end = m5[-1].time + fstep
    for etf in entry_tfs:
        e = cx.tf[etf]
        for t in range(60, len(e.c)):
            T = e.t[t] + e.step
            if T > end:
                break
            for d in (1, -1):
                if not engulf(e.c[t - 1], e.c[t], d) or not any(dd == d for s in range(max(t - RETEST_BARS, 0), t + 1) for dd, _ in e.sos_at.get(s, [])):
                    continue  # the cheapest conditions first: an engulfing now and a SoS of its side in the last 24 candles
                k0 = m5_index_at_close(cx.t5, T)
                if k0 is None or T - (cx.m5[k0].time + fstep) > e.step:  # the follow candles must reach the trigger's close
                    continue
                r = evaluate(cx, etf, t, d, nw, T)
                if not (r["zone"] and "entry" in r and r["c"].get("engulf_at") == t):
                    continue
                z, sos = r["zone"], r["c"]["sos"]
                wave = (round(z["lo"] / pip), d, sos["time"])  # one trade per AOI visit (the SoS wave)
                if wave in passed or (wave, etf) in seen:
                    continue
                seen.add((wave, etf))
                sq = squad(r, pip, pv)
                steps = [(f"W1 {r['S']['W1']:+d} · D1 {r['S']['D1']:+d} · H4 {r['S']['H4']:+d}", bool(r["setup"]), r["setup"] or ""),
                         (f"In {zone_name(z)} AOI {fmt(z['lo'], pip)}-{fmt(z['hi'], pip)} ({z['touches']} touches)", True, ""),
                         (f"{etf} SoS at {fmt(sos['level'], pip)}", True, ""), (f"{etf} engulfing close", True, ""),
                         (f"S_AlexG {r['score']}% (grade {r['grade']})", r["score"] >= GRADE_MIN, ""), (f"R:R {r['rr']:.2f} >= 2.5", r["rr"] >= MIN_RR, "")]
                expiry = 0 if r["market"] else max(1, LIMIT_BARS * e.step // fstep)
                s = _make(key, r["setup"] or "SF_SWING", d, m5, k0, r["entry"], r["sl"], r["tp1"], r["tp"], PART, r["market"], expiry,
                          T + HOLD_DAYS * DAY, steps, {"aoi": (z["lo"], z["hi"], z["t0"]), "sos": (sos["level"], sos["time"])}, cost,
                          zone=r["band"], be_off=BE_OFF)
                if not s:
                    continue
                s.update(gpa=r["score"], score=r["score"], grade=r["grade"], setupType=r["setup"], riskPct=r["risk_pct"], etf=etf,
                         consensus=sq["consensus"], vetoes=sq["vetoes"], checklistGpa=checklist_of(r), confirmedAt=T, fridayExit=False,
                         desk=[{"key": k2, "role": role, "status": sq["agents"][name]["status"], "badge": sq["agents"][name]["badge"],
                                "score": sq["agents"][name]["score"]} for k2, name, role, _ in ROLES],
                         zoneInfo={"low": z["lo"], "high": z["hi"], "tfs": sorted(z["tfs"], reverse=True), "touches": z["touches"],
                                   "width": round(z["width"]), "psych": z["psych"], "overlap": z["overlap"]},
                         sos={"level": sos["level"], "time": sos["time"], "swing": sos["swing"]}, struct=r.get("struct"),
                         slPips=round(r["risk"] / pip, 1), tpPips=round(abs(r["tp"] - r["entry"]) / pip, 1),
                         bePips=round(abs(r["tp1"] - r["entry"]) / pip, 1), spreadPct=round(r["spread_ratio"] * 100, 1),
                         lots10k=sq["agents"]["risk_guardian"].get("position_size_lots"), newsClear=r["news_checked"] and not r["news"],
                         newsChecked=r["news_checked"], syncKind=r["sync_kind"],
                         confirmations={k3: r["c"].get(k3) for k3 in ("candle_w1", "candle_d1", "candle_h4", "pattern_w1", "pattern_d1", "pattern_h4")})
                s["checklist"] = [("1 · Timeframes in sync", bool(r["setup"]), r["setup"] or "no sync"),
                                  (f"2 · S_AlexG >= 80 % ({r['score']} %, grade {r['grade']})", r["score"] >= GRADE_MIN, ""),
                                  ("3 · SoS + Engulfing", True, etf),
                                  (f"4 · R:R >= 2.5 and no veto ({r['rr']:.2f})", r["rr"] >= MIN_RR and not sq["vetoes"], ", ".join(sq["vetoes"]) or "none")]
                s["pass"] = sq["execute"]
                if s["pass"]:
                    passed.add(wave)
                out.append(s)
    out.sort(key=lambda s: (s["time"], entry_tfs.index(s["etf"])))
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("5 · One trade per pair at a time", False, "the previous trade is still open"))
            continue
        busy = m5[s["result"]["at"]].time + fstep if "at" in s["result"] else 1 << 62
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
    for etf in ENTRY_TFS:  # H1, then M30, then M15: each one's last closed candle, both directions; the most advanced read
        e = cx.tf[etf]
        t = e.idx(m5[-1].time + M5S)
        if t < 60:
            continue
        for d in (1, -1):
            r = evaluate(cx, etf, t, d, nw, now)
            c = r["c"]
            rank = (bool(r["setup"]), bool(r["zone"]), bool(c.get("sos")), c.get("engulf_at") is not None, r["score"], -ENTRY_TFS.index(etf))
            if best is None or rank > best[0]:
                best = (rank, r)
    r = best[1]
    if cand:  # a live passing setup: the read of the candle it fired on
        e = cx.tf[cand["etf"]]
        tt = e.idx(cand["confirmedAt"])
        if tt >= 60:
            r2 = evaluate(cx, cand["etf"], tt, cand["dir"], nw, cand["confirmedAt"])
            if "entry" in r2:
                r = r2
    sq = squad(r, pip, pv)
    execute = bool(cand) and sq["execute"]
    decision = sq["decision"] if (execute or sq["decision"] != "EXECUTE") else "WAIT_FOR_TRIGGER"
    d, c, z = r["dir"], r["c"], r["zone"]
    radar = None
    if sq["radar"] and z and c.get("sos"):
        st = c["sos"]["time"]
        radar = {"id": f"RADAR-{key}-{'B' if d > 0 else 'S'}-{round(z['lo'] / pip)}-{st}", "direction": "BUY" if d > 0 else "SELL",
                 "tf": zone_name(z), "touches": z["touches"], "low": z["lo"], "high": z["hi"], "psych": z["psych"], "etf": r["etf"],
                 "gpa": r["score"], "score": r["score"], "grade": r["grade"], "time": st, "setup": r["setup"], "sosLevel": c["sos"]["level"],
                 "trend": "+".join(n for n in ("W1", "D1", "H4") if r["S"][n] == d)}
    contract = {"pair": cx.cfg["symbol"], "strategy_name": STRATEGY_NAME, "setup_type": r["setup"],
                "timestamp_utc": datetime.fromtimestamp(m5[-1].time + M5S, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "direction": "BUY" if d > 0 else "SELL", "consensus_score": sq["consensus"], "gpa_score": r["score"], "alexg_score": r["score"],
                "grade": r["grade"], "final_decision": decision, "pass": execute, "checklist": checklist_of(r), "agents": sq["agents"]}
    ui = [{"key": k, "id": name, "name": role, "role": role, "status": sq["agents"][name]["status"], "finding": sq["agents"][name]["badge"],
           "badge": sq["agents"][name]["badge"], "score": sq["agents"][name]["score"], "weight": w, "lines": sq["agents"][name]["details"],
           "details": sq["agents"][name]["details"]} for k, name, role, w in ROLES]
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand if execute else None, "radar": radar, "read": r}


# ---------------------------------------------------------------- the chart
def draw_objects(key: str, m5, h1, d1, now: int, r_fn=round, spread: Optional[float] = None, focus: Optional[dict] = None) -> dict:
    """What the chart draws. ESSENTIAL (always shown): the zone in play (`focus`) or, with none, the zone around the
    price, the nearest below and the nearest above; the D1 structure levels. DETAIL (`detail: True`, shown with the
    chart's "Details" switch): the other zones, the round numbers, the H4 levels, the HH / HL markers, the H1 SoS line."""
    cx = context(key, m5, h1, d1, spread)
    pip = cx.pip
    w1, dd, h4 = cx.tf["W1"], cx.tf["D1"], cx.tf["H4"]
    iw, id_, i4 = w1.idx(now), dd.idx(now), h4.idx(now)
    end = m5[-1].time + M5S
    px = m5[-1].close
    boxes, segs, labels = [], [], []
    zs = sorted(cx.aois(iw, id_), key=lambda z: dist(px, px, z))[:8] if iw >= 0 and id_ >= 0 else []
    same = lambda a, b: abs(a["lo"] - b["lo"]) < pip / 2 and abs(a["hi"] - b["hi"]) < pip / 2  # noqa: E731
    if focus and not any(same(focus, z) for z in zs):
        zs = [focus, *zs]
    if focus:
        main = [focus]
    else:
        below, above = [z for z in zs if z["hi"] < px], [z for z in zs if z["lo"] > px]
        main = [z for z in zs if z["lo"] <= px <= z["hi"]][:1] + below[:1] + above[:1]
    for z in zs:
        tfl = "1W/1D" if z["overlap"] else ("1D" if "D1" in z["tfs"] else "1W")
        boxes.append({"from": z["t0"], "to": end + 6 * H1S, "top": r_fn(z["hi"]), "bottom": r_fn(z["lo"]), "kind": "ob", "dir": 1 if z["hi"] < px else -1,
                      "label": f"{tfl} zone · {z['touches']} touches", "detail": not any(same(z, q) for q in main)})
        if z["psych"] is not None:
            segs.append({"from": z["t0"], "to": end, "price": r_fn(z["psych"]), "kind": "eq", "dir": 0, "label": f"Psych {fmt(z['psych'], pip)}", "detail": True})
    for tf, i in ((dd, id_), (h4, i4)):
        if i < 0:
            continue
        st = tf.s
        tr = st["trend"][i]
        names = (("HH", "hh", 1), ("HL", "hl", -1)) if tr >= 0 else (("LH", "lh", 1), ("LL", "ll", -1))
        for name, k, dirn in names:
            lv = st[k][i]
            if lv and lv[1] >= i - 150:
                segs.append({"from": tf.t[lv[1]], "to": end, "price": r_fn(lv[0]), "kind": "liquidity", "dir": dirn,
                             "label": f"{tf.name.replace('D1', '1D').replace('H4', '4H')} {name}", "detail": tf.name != "D1"})
                labels.append({"time": tf.t[lv[1]], "price": r_fn(lv[0]), "text": name, "above": dirn > 0, "kind": "structure", "detail": True})
    e = cx.tf["H1"]
    t = e.idx(end)
    if t > 60 and id_ >= 0:
        adr = cx.adr20(id_)
        prox = max(PROX_PIPS * pip, PROX_ADR * adr) if adr else PROX_PIPS * pip
        for d in (1, -1):
            res = next((x for x in (find_sos(e, t, z, d, prox) for z in zs) if x), None)
            if res:
                segs.append({"from": res["time"] - 6 * H1S, "to": end, "price": r_fn(res["level"]), "kind": "bos", "dir": d, "label": "1H SoS", "detail": True})
    return {"boxes": boxes, "segments": segs, "labels": labels, "lines": []}
