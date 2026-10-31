"""
Forex — "FXAlexG · Set & Forget GPA" (EUR/USD, GBP/USD, USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD, AUD/CHF).

1. Trend (3 sync rule): W1, D1 and H4 market structure. Bullish = HH/HL, bearish = LL/LH; the trend only
   shifts on a candle BODY close beyond the last confirmed swing (shared.structure.detect_structure).
   Trade the majority (≥ 2 of 3), ideally all three. Below H4 is for the entry only.
2. AOI: zones built from W1 / D1 swing points only, valid with ≥ 3 touches. Buys when price is above the
   AOI and the trend is bullish, sells below it and bearish.
3. GPA: ten confluences, 10% each — W1, D1, H4 trend · price at a valid AOI · H4 50 EMA rejection ·
   H4 structure rejection · H4 rejection candle · 1H H&S / double top-bottom · 1H 50 EMA rejection ·
   30m engulfing at the London / New York open. A+ ≥ 80%, B ≥ 70%, C+ ≥ 60% (minimum), else no trade.
4. Entry: AOI touched + an H4 rejection + the 30m engulfing at the London / New York open → MARKET at its
   close. SL beyond the pattern's head (conservative), else beyond the last 12 H1 candles. TP at the next
   W1 / D1 zone (≥ 3 touches), pulled in front of a round level; below 1:2 = no trade. Set & forget.
D1 / W1 are built from H1 with the 22:00 UTC rollover. One trade at a time, replayed in order like the backtest.
"""

import bisect
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..shared.common import HISTORY_MAX, active_window, item, new_result, to_signal_json, tp_options, trade_record
from ..shared.drawings import trade_drawings
from ..shared.indicators import atr_series, avg_body_series, ema_series
from ..shared.jsnum import fmt_time, fmt_utc_minute, js_str, round_to, to_fixed
from ..shared.lifecycle import simulate_lifecycle
from ..shared.news import news_block
from ..shared.risk import classify, lot_table, rr, score_checklist, snap_sl, snap_tp, to_pips
from ..shared.structure import detect_structure, detect_swings
from ..shared.types import Candle, closed_only
from .config import grade_of

TF = {"M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 5 * 86400}  # W1 "closes" Friday
ROLLOVER = 2 * 3600  # the forex day starts at 22:00 UTC


def _resample(c: list[Candle], key) -> list[Candle]:
    out: list[Candle] = []
    k0 = None
    for x in c:
        k = key(x.time)
        if out and k == k0:
            y = out[-1]
            y.high, y.low, y.close = max(y.high, x.high), min(y.low, x.low), x.close
        else:
            out.append(Candle(x.time, x.open, x.high, x.low, x.close))
            k0 = k
    return out


def _day_key(t: int):
    return datetime.fromtimestamp(t + ROLLOVER, timezone.utc).date()


def _week_key(t: int):
    return datetime.fromtimestamp(t + ROLLOVER, timezone.utc).isocalendar()[:2]


def _engulfing(p: Candle, x: Candle, buy: bool) -> bool:
    if buy:
        return x.close > x.open and p.close < p.open and x.close >= p.open and x.open <= p.close
    return x.close < x.open and p.close > p.open and x.close <= p.open and x.open >= p.close


def _rejection_candle(x: Candle, buy: bool, cfg: dict) -> Optional[str]:
    rng = x.high - x.low
    if rng <= 0:
        return None
    body = abs(x.close - x.open)
    wick = (min(x.open, x.close) - x.low) if buy else (x.high - max(x.open, x.close))
    if wick >= cfg["pinWickBody"] * body and wick >= cfg["wickRange"] * rng:
        return "pin bar"
    if wick >= cfg["wickRange"] * rng and ((x.close - x.low) if buy else (x.high - x.close)) >= 0.5 * rng:
        return "wick rejection"
    return None


@dataclass
class Zone:
    lo: float
    hi: float
    touches: int
    tfs: str  # "D1", "W1" or "D1+W1"

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2


class _Ctx:
    """Everything the rules read, computed once per evaluation (no look-ahead: each rule asks for time T)."""

    def __init__(self, e: list[Candle], ltf: list[Candle], h4: list[Candle], h1: list[Candle], cfg: dict):
        self.cfg = cfg
        self.e, self.l, self.h4 = e, ltf, h4
        self.e_sec, self.l_sec = TF[cfg["entryTf"]], TF[cfg["ltfTf"]]
        self.d1, self.w1 = _resample(h1, _day_key), _resample(h1, _week_key)
        p = cfg["atrPeriod"]
        self.atr_l, self.atr_h4, self.atr_d1 = atr_series(ltf, p), atr_series(h4, p), atr_series(self.d1, p)
        self.ema_h4 = ema_series([x.close for x in h4], cfg["emaPeriod"])
        self.ema_l = ema_series([x.close for x in ltf], cfg["emaPeriod"])
        self.t = {"E": [x.time for x in e], "L": [x.time for x in ltf], "H4": [x.time for x in h4],
                  "D1": [x.time for x in self.d1], "W1": [x.time for x in self.w1]}
        # Trend per timeframe = direction of the last body close beyond a confirmed swing
        self.trend_events: dict[str, tuple[list[int], list[int]]] = {}
        for name, c in (("W1", self.w1), ("D1", self.d1), ("H4", h4)):
            sw = detect_swings(c, cfg["trend"]["swingN"][name])
            events, _ = detect_structure(c, sw, avg_body_series(c, 20), 1e9)
            times = [c[ev.breakIndex].time + TF[name] for ev in events]
            dirs = [1 if ev.direction == "BULLISH" else -1 for ev in events]
            self.trend_events[name] = (times, dirs)
        A = cfg["aoi"]
        self.sw_d1 = sorted(detect_swings(self.d1, A["swingN"]), key=lambda s: s.confirmedIndex)
        self.sw_w1 = sorted(detect_swings(self.w1, A["swingN"]), key=lambda s: s.confirmedIndex)
        self.sw_h4 = sorted(detect_swings(h4, cfg["trend"]["swingN"]["H4"]), key=lambda s: s.confirmedIndex)
        self.sw_l = sorted(detect_swings(ltf, cfg["ltf"]["swingN"]), key=lambda s: s.confirmedIndex)
        self._zones: dict[int, list[Zone]] = {}

    def last_closed(self, key: str, sec: int, t: int) -> int:
        """Index of the last candle of `key` fully closed at time t (−1 if none)."""
        return bisect.bisect_right(self.t[key], t - sec) - 1

    def trend_at(self, name: str, t: int) -> int:
        times, dirs = self.trend_events[name]
        k = bisect.bisect_right(times, t) - 1
        return dirs[k] if k >= 0 else 0

    def zones_at(self, t: int) -> list[Zone]:
        di = self.last_closed("D1", TF["D1"], t)
        if di < self.cfg["atrPeriod"] + 1:
            return []
        if di in self._zones:
            return self._zones[di]
        A = self.cfg["aoi"]
        wi = self.last_closed("W1", TF["W1"], t)
        pts = [(s.price, "D1") for s in self.sw_d1 if s.confirmedIndex <= di and s.index >= di - A["lookbackD1"]]
        pts += [(s.price, "W1") for s in self.sw_w1 if s.confirmedIndex <= wi and s.index >= wi - A["lookbackW1"]]
        atr = self.atr_d1[di]
        zones: list[Zone] = []
        group: list[tuple[float, str]] = []
        for price, tf in sorted(pts) + [(math.inf, "")]:
            if group and price - group[0][0] > A["clusterAtr"] * atr:  # a zone is at most clusterAtr × ATR(D1) wide (no chaining)
                lo, hi = group[0][0], group[-1][0]
                w = A["minWidthAtr"] * atr
                if hi - lo < w:
                    m = (hi + lo) / 2
                    lo, hi = m - w / 2, m + w / 2
                kinds = sorted({k for _, k in group})
                zones.append(Zone(lo, hi, len(group), "+".join(kinds)))
                group = []
            group.append((price, tf))
        self._zones[di] = zones
        return zones


def _ltf_pattern(ctx: _Ctx, li: int, buy: bool) -> Optional[dict]:
    """Inverse H&S / double bottom (buys) or H&S / double top (sells) in the last lower-timeframe candles."""
    L = ctx.cfg["ltf"]
    a = ctx.atr_l[li]
    if not (a > 0):
        return None
    kind = "LOW" if buy else "HIGH"
    k_end = bisect.bisect_right([s.confirmedIndex for s in ctx.sw_l], li)
    pts = [s for s in ctx.sw_l[:k_end] if s.kind == kind and s.index >= li - L["patternBars"]]
    better = (lambda x, y: x < y) if buy else (lambda x, y: x > y)  # "lower" for buys, "higher" for sells
    c = ctx.l
    if len(pts) >= 3:
        ls, hd, rs = pts[-3:]
        if better(hd.price, ls.price) and better(hd.price, rs.price) and abs(ls.price - rs.price) <= L["shoulderTolAtr"] * a:
            seg = c[ls.index:rs.index + 1]
            neck = max(x.high for x in seg) if buy else min(x.low for x in seg)
            return {"type": "inverse H&S" if buy else "H&S", "head": hd.price, "points": [(ls.time, ls.price), (hd.time, hd.price), (rs.time, rs.price)],
                    "neckline": neck, "rightShoulder": rs.price}
    if len(pts) >= 2:
        p1, p2 = pts[-2:]
        if abs(p1.price - p2.price) <= L["doubleTolAtr"] * a and p2.index - p1.index >= L["doubleMinGap"]:
            seg = c[p1.index:p2.index + 1]
            neck = max(x.high for x in seg) if buy else min(x.low for x in seg)
            if abs(neck - p1.price) >= a:
                head = min(p1.price, p2.price) if buy else max(p1.price, p2.price)
                return {"type": "double bottom" if buy else "double top", "head": head, "points": [(p1.time, p1.price), (p2.time, p2.price)],
                        "neckline": neck, "rightShoulder": p2.price}
    return None


def _grade(ctx: _Ctx, i: int) -> dict:
    """The 10 GPA confluences on entry candle i (closed), plus what the entry needs. Used for signals AND for the live read."""
    cfg = ctx.cfg
    A, H, L = cfg["aoi"], cfg["h4"], cfg["ltf"]
    pip = cfg["spec"]["pipSize"]
    f = lambda v: to_fixed(v, cfg["spec"]["decimals"])  # noqa: E731
    x = ctx.e[i]
    T = x.time + ctx.e_sec
    tr = {tf: ctx.trend_at(tf, T) for tf in ("W1", "D1", "H4")}
    up, down = sum(v == 1 for v in tr.values()), sum(v == -1 for v in tr.values())
    d = 1 if up >= cfg["trend"]["minAgree"] else -1 if down >= cfg["trend"]["minAgree"] else 0
    buy = d == 1
    out = {"T": T, "trend": tr, "dir": d, "price": x.close, "aoi": None, "pattern": None, "h4": {}, "items": [], "touchedZone": None}
    hi4 = ctx.last_closed("H4", TF["H4"], T)
    li = ctx.last_closed("L", ctx.l_sec, T)
    di = ctx.last_closed("D1", TF["D1"], T)
    if hi4 < 60 or li < 60 or di < cfg["atrPeriod"] + 1:
        out["items"] = []
        return out
    zones = [z for z in ctx.zones_at(T) if z.touches >= A["minTouches"]]
    out["zones"] = zones
    a4, al, ad = ctx.atr_h4[hi4], ctx.atr_l[li], ctx.atr_d1[di]

    # Price at a valid W1 / D1 AOI: buys above the zone after touching it, sells below it
    aoi = None
    if d:
        recent = ctx.h4[max(0, hi4 - A["touchBarsH4"] + 1):hi4 + 1] + [x]
        tol = A["touchTolAtr"] * ad
        ext = min(b.low for b in recent) if buy else max(b.high for b in recent)
        for z in zones:
            touched = (ext <= z.hi + tol and x.close > z.mid) if buy else (ext >= z.lo - tol and x.close < z.mid)
            if touched and (aoi is None or (z.hi > aoi.hi if buy else z.lo < aoi.lo)):
                aoi = z
    out["aoi"] = aoi

    # H4 rejection (last 6 closed H4 candles)
    bars = list(range(max(0, hi4 - H["barsH4"] + 1), hi4 + 1))
    ema_rej = struct_rej = candle_rej = None
    if d:
        for k in bars:
            b, ema = ctx.h4[k], ctx.ema_h4[k]
            if ema == ema and ((b.low <= ema + H["emaTolAtr"] * a4 and b.close > ema) if buy else (b.high >= ema - H["emaTolAtr"] * a4 and b.close < ema)):
                ema_rej = f"H4 {fmt_time(b.time)} {'low' if buy else 'high'} tested EMA{cfg['emaPeriod']} {f(ema)} and closed {'above' if buy else 'below'}"
        ce = bisect.bisect_right([s.confirmedIndex for s in ctx.sw_h4], bars[0] - 1)
        levels = [s.price for s in ctx.sw_h4[:ce] if s.index >= bars[0] - 60]
        for k in bars:
            b = ctx.h4[k]
            for lv in levels:
                if (abs(b.low - lv) <= H["structTolAtr"] * a4 and b.close > lv) if buy else (abs(b.high - lv) <= H["structTolAtr"] * a4 and b.close < lv):
                    struct_rej = f"H4 {fmt_time(b.time)} rejected the H4 structure level {f(lv)}"
        for k in bars[-3:]:
            b = ctx.h4[k]
            kind = _rejection_candle(b, buy, H) or ("engulfing" if k > 0 and _engulfing(ctx.h4[k - 1], b, buy) else None)
            if kind:
                candle_rej = f"H4 {fmt_time(b.time)} {kind}"
    out["h4"] = {"ema": ema_rej, "structure": struct_rej, "candle": candle_rej}

    # Lower timeframe (1H): pattern and 50 EMA rejection
    pattern = _ltf_pattern(ctx, li, buy) if d else None
    out["pattern"] = pattern
    ltf_ema = None
    if d:
        for k in range(max(0, li - L["emaBars"] + 1), li + 1):
            b, ema = ctx.l[k], ctx.ema_l[k]
            if ema == ema and ((b.low <= ema + L["emaTolAtr"] * al and b.close > ema) if buy else (b.high >= ema - L["emaTolAtr"] * al and b.close < ema)):
                ltf_ema = f"{cfg['ltfTf']} {fmt_time(b.time)} rejected EMA{cfg['emaPeriod']} {f(ema)}"

    # 30m engulfing at the London / New York open
    win = active_window(x.time, cfg["sessions"]["windows"])
    engulf = bool(d) and i > 0 and _engulfing(ctx.e[i - 1], x, buy)
    out["engulf"] = engulf and win is not None
    out["session"] = win["name"] if win else None

    side = "bullish" if buy else "bearish"
    word = {1: "bullish", -1: "bearish", 0: "no structure yet"}
    W = cfg["scoring"]["confluenceWeight"]
    out["items"] = [
        item("w1", "Weekly trend in favour", "الاتجاه الأسبوعي مع الصفقة", d != 0 and tr["W1"] == d, f"W1 {word[tr['W1']]}", W, False),
        item("d1", "Daily trend in favour", "الاتجاه اليومي مع الصفقة", d != 0 and tr["D1"] == d, f"D1 {word[tr['D1']]}", W, False),
        item("h4trend", "4H trend in favour", "اتجاه 4 ساعات مع الصفقة", d != 0 and tr["H4"] == d, f"H4 {word[tr['H4']]}", W, False),
        item("aoi", f"Price at a W1 / D1 AOI with ≥ {A['minTouches']} touches", "السعر عند منطقة اهتمام أسبوعية/يومية (3 لمسات+)", aoi is not None,
             f"{aoi.tfs} zone {f(aoi.lo)}–{f(aoi.hi)} · {aoi.touches} touches · price {'above' if buy else 'below'}" if aoi else "Price is not at a valid W1 / D1 zone", W, False),
        item("h4ema", f"4H EMA {cfg['emaPeriod']} rejection", "رفض EMA 50 على 4 ساعات", ema_rej is not None, ema_rej or "No H4 EMA rejection in the last day", W, False),
        item("h4struct", "4H structure rejection", "رفض هيكل 4 ساعات", struct_rej is not None, struct_rej or "No H4 structure rejection", W, False),
        item("h4candle", "4H rejection candle (pin bar / wick / engulfing)", "شمعة رفض 4 ساعات", candle_rej is not None, candle_rej or "No H4 rejection candle", W, False),
        item("pattern", f"{cfg['ltfTf']} H&S / inverse H&S / double top-bottom", "نموذج رأس وكتفين أو قمة/قاع مزدوج", pattern is not None,
             f"{pattern['type']} · neckline {f(pattern['neckline'])}" if pattern else "No pattern on the lower timeframe", W, False),
        item("ltfema", f"{cfg['ltfTf']} EMA {cfg['emaPeriod']} rejection", "رفض EMA 50 على الفريم الصغير", ltf_ema is not None, ltf_ema or "No lower-timeframe EMA rejection", W, False),
        item("engulf", f"{cfg['entryTf']} {side} engulfing at the London / New York open", "شمعة ابتلاعية 30 دقيقة في افتتاح لندن/نيويورك",
             out["engulf"], f"{cfg['entryTf']} {fmt_time(x.time)} {side} engulfing · {win['name']}" if out["engulf"] else
             ("Engulfing outside the London / New York open" if engulf else f"No {cfg['entryTf']} {side} engulfing on the last close"), W, False),
    ]
    out["score"] = score_checklist(out["items"])
    out["h4Rejection"] = bool(ema_rej or struct_rej or candle_rej)
    out["atr"] = {"ltf": al, "h4": a4, "d1": ad}
    out["pip"] = pip
    return out


def _levels(ctx: _Ctx, g: dict, i: int) -> tuple[Optional[dict], Optional[str]]:
    """Entry / SL / TP for an entry candle that passed the triggers, or the reason it cannot be traded."""
    cfg, R = ctx.cfg, ctx.cfg["risk"]
    pip, buy = g["pip"], g["dir"] == 1
    entry = ctx.e[i].close
    li = ctx.last_closed("L", ctx.l_sec, g["T"])
    p = g["pattern"]
    if p:
        ref = p["head"]
    else:
        seg = ctx.l[max(0, li - R["slLookbackLtf"] + 1):li + 1] + [ctx.e[i]]
        ref = min(b.low for b in seg) if buy else max(b.high for b in seg)
    buf = R["slBufferAtr"] * g["atr"]["ltf"]
    sl = ref - buf if buy else ref + buf
    if abs(entry - sl) < R["minSlPips"] * pip:
        sl = entry - R["minSlPips"] * pip if buy else entry + R["minSlPips"] * pip
    if (sl >= entry) if buy else (sl <= entry):
        return None, "Stop would be on the wrong side of the entry"
    if abs(entry - sl) > R["maxSlPips"] * pip:
        return None, f"Stop {to_fixed(abs(entry - sl) / pip, 1)} pips > {R['maxSlPips']} pips"
    # TP at the next W1 / D1 zone in the trade direction
    ahead = [z for z in g["zones"] if (z.lo > entry if buy else z.hi < entry) and z is not g["aoi"]]
    if not ahead:
        return None, "No W1 / D1 zone ahead for the TP"
    z = min(ahead, key=lambda q: q.lo) if buy else max(ahead, key=lambda q: q.hi)
    tp = z.lo - R["tpSpreadPips"] * pip if buy else z.hi + R["tpSpreadPips"] * pip
    step = R["roundStepPips"] * pip
    rnd = math.floor(tp / step + 1e-9) * step if buy else math.ceil(tp / step - 1e-9) * step
    if (0 <= tp - rnd <= R["roundBeforePips"] * pip and rnd > entry) if buy else (0 <= rnd - tp <= R["roundBeforePips"] * pip and rnd < entry):
        tp = rnd - R["roundOffsetPips"] * pip if buy else rnd + R["roundOffsetPips"] * pip
        tp_note = f"next {z.tfs} zone {to_fixed(z.lo, 5)}–{to_fixed(z.hi, 5)} ({z.touches} touches), placed before the round level {to_fixed(rnd, 5)}"
    else:
        tp_note = f"next {z.tfs} zone {to_fixed(z.lo, 5)}–{to_fixed(z.hi, 5)} ({z.touches} touches)"
    reward = abs(tp - entry) / abs(entry - sl)
    cap = R.get("maxRr")
    if cap and reward > cap:  # optional: never aim further than `maxRr` (the rules' "target 1:3")
        tp = entry + cap * abs(entry - sl) if buy else entry - cap * abs(entry - sl)
        tp_note = f"{js_str(cap)}R (the {z.tfs} zone {to_fixed(z.lo, 5)}–{to_fixed(z.hi, 5)} is further)"
        reward = cap
    if reward < R["minRr"] - 1e-9:
        return None, f"R:R 1:{to_fixed(reward, 2)} to the next zone < 1:{js_str(R['minRr'])}"
    return {"entry": entry, "sl": sl, "tp": tp, "tpZone": z, "tpNote": tp_note, "slRef": ref,
            "slNote": f"beyond the {p['type']} head {to_fixed(ref, 5)}" if p else f"beyond the last {R['slLookbackLtf']} {cfg['ltfTf']} candles {to_fixed(ref, 5)}"}, None


def _build_setup(ctx: _Ctx, g: dict, lv: dict, i: int, spread: float, last: int) -> dict:
    cfg, R, FIL, spec = ctx.cfg, ctx.cfg["risk"], ctx.cfg["filters"], ctx.cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    buy = g["dir"] == 1
    c = ctx.e
    entry, sl = round_to(lv["entry"], d), snap_sl(lv["sl"], buy, d)
    unit = abs(entry - sl)
    mark = lambda k: snap_tp(entry + k * unit if buy else entry - k * unit, buy, d)  # noqa: E731
    tp3 = snap_tp(lv["tp"], buy, d)
    tp1, tp2 = mark(R["tp1R"]), mark(R["tp2R"])
    signal_time = c[i].time + ctx.e_sec
    valid_until = signal_time + R["marketValidMin"] * 60
    params = {"side": "BUY" if buy else "SELL", "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
              "expiryTime": None, "marketFillTime": signal_time, "cancelIfTp1BeforeFill": False, "partials": R["partials"],
              "breakeven": R["breakeven"], "spread": spread, "slippage": FIL["slippagePips"] * pip}
    p = g["pattern"]
    return {
        "id": f"{spec['symbol']}-GPA-{c[i].time}", "setup": "GPA", "direction": "BUY" if buy else "SELL", "entryType": "MARKET",
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "tp2Source": f"{js_str(R['tp2R'])}R mark", "tp3Source": lv["tpNote"],
        "rrTp2": rr(entry, sl, tp2), "rrTarget": rr(entry, sl, tp3), "slDistance": round_to(unit, d), "slPips": to_pips(spec, unit),
        "lots": lot_table(spec, entry, sl, R["riskPct"], R["balances"]),
        "signalTime": signal_time, "signalIndex": i, "expiresAt": valid_until,
        "invalidation": f"SL {to_fixed(sl, d)} {lv['slNote']}; set & forget to TP {to_fixed(tp3, d)}; do not enter after {fmt_time(valid_until)}",
        "isFresh": i == len(c) - 1 or i == last, "lifecycle": simulate_lifecycle(c, params, i + 1), "params": params,
        "anchors": {"gpa": {"direction": "BUY" if buy else "SELL", "score": g["score"], "grade": grade_of(g["score"], cfg),
                            "trend": g["trend"], "aoi": {"lo": g["aoi"].lo, "hi": g["aoi"].hi, "touches": g["aoi"].touches, "tfs": g["aoi"].tfs},
                            "tpZone": {"lo": lv["tpZone"].lo, "hi": lv["tpZone"].hi, "touches": lv["tpZone"].touches, "tfs": lv["tpZone"].tfs},
                            "pattern": p, "session": g["session"], "h4": g["h4"], "time": c[i].time}},
    }


def _triggers_ok(g: dict) -> bool:
    """What the entry itself needs (rule 4): a direction, the AOI touched, an H4 rejection and the open-session engulfing."""
    return bool(g["dir"]) and g["aoi"] is not None and g.get("h4Rejection", False) and g.get("engulf", False)


def evaluate_alexg(inp: dict, cfg: dict) -> dict:
    spec = cfg["spec"]
    d, pip = spec["decimals"], spec["pipSize"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    now = inp["nowSec"]
    e_key, l_key = cfg["entryTf"], cfg["ltfTf"]
    e = closed_only(inp["candles"].get(e_key) or [], TF[e_key], now)[-cfg["history"]:]
    ltf = closed_only(inp["candles"].get(l_key) or [], TF[l_key], now)
    h4 = closed_only(inp["candles"].get("H4") or [], TF["H4"], now)
    h1 = closed_only(inp["candles"].get("H1") or [], TF["H1"], now)
    last = len(e) - 1
    price = inp["livePrice"] if inp["livePrice"] > 0 else (e[last].close if e else 0)
    FIL, R = cfg["filters"], cfg["risk"]
    spread = inp["spread"] if inp["spread"] is not None else FIL["assumedSpreadPips"] * pip
    result = new_result(spec, cfg, inp, price)

    # ---- Data quality ----
    min_e, min_h1 = 120, 60 * 120  # ~60 weeks of H1 for the weekly structure and zones
    stale = inp["isMarketOpen"] and len(e) > 0 and now - (e[last].time + TF[e_key]) > max(6 * TF[e_key], 6 * 3600)  # Yahoo leaves late-evening candles empty for a while
    if not inp["isRealData"] or len(e) < min_e or len(h1) < min_h1 or len(h4) < 200 or stale:
        result["dataQuality"] = {
            "ok": False, "source": inp["dataSource"],
            "reason": "Live feed unavailable (synthetic candles): no analysis" if not inp["isRealData"]
            else f"Last {e_key} candle is stale (feed paused)" if stale else f"Not enough history ({e_key} {len(e)}/{min_e}, H1 {len(h1)}/{min_h1}, H4 {len(h4)}/200)",
        }
        result["headline"], result["headlineAr"] = "Data not usable", "البيانات غير صالحة"
        return result

    ctx = _Ctx(e, ltf, h4, h1, cfg)

    # ---- Replay one trade at a time, exactly like the backtest (only open-session engulfings can trigger) ----
    latest: Optional[tuple[dict, dict]] = None
    past: list[dict] = []  # the trades the strategy closed (history list + target odds)
    i = 60
    while i <= last:
        x = e[i]
        if not (active_window(x.time, cfg["sessions"]["windows"]) and (_engulfing(e[i - 1], x, True) or _engulfing(e[i - 1], x, False))):
            i += 1
            continue
        g = _grade(ctx, i)
        if not _triggers_ok(g) or g["score"] < cfg["scoring"]["thresholds"]["watch"]:
            i += 1
            continue
        lv, _why = _levels(ctx, g, i)
        if not lv:
            i += 1
            continue
        s = _build_setup(ctx, g, lv, i, spread, last)
        latest = (g, s)
        lc = s["lifecycle"]
        if lc["state"] == "CLOSED":
            past.append(trade_record(s, ctx.e_sec, e, i))
        if lc["state"] != "CLOSED":
            break
        i = next((j for j in range(i + 1, last + 1) if e[j].time == lc["exitTime"]), last) + 1

    result["history"] = past[-HISTORY_MAX:]
    tp_past = past  # every closed trade feeds the target odds (the list above keeps only the recent ones)

    # ---- Live read on the last closed candle (the 5-part answer: trend, AOI, grade, verdict, levels) ----
    now_g = _grade(ctx, last)
    news = news_block(now, inp["news"]["events"], FIL["news"])
    ev, nxt = news["event"], news["next"]
    ccys = "/".join(FIL["news"]["currencies"])
    result["news"] = {
        "blocked": news["blocked"],
        "detail": f"{ev['currency']} {ev['title']} at {fmt_time(ev['time'])}" if ev else f"No high-impact {ccys} news within ±30 min",
        "next": f"{nxt['currency']} {nxt['title']} {fmt_utc_minute(nxt['time'])} UTC" if nxt else None,
        "source": inp["news"]["source"],
    }
    win = active_window(now, cfg["sessions"]["windows"])
    result["market"]["window"] = win["name"] if win else None
    word = {1: "bullish", -1: "bearish", 0: "none"}
    tr = now_g["trend"]
    trend_detail = f"W1 {word[tr['W1']]} · D1 {word[tr['D1']]} · H4 {word[tr['H4']]}"
    result["bias"] = {"direction": "BULLISH" if now_g["dir"] == 1 else "BEARISH" if now_g["dir"] == -1 else "NEUTRAL",
                      "detail": trend_detail + (f" → {'BUY' if now_g['dir'] == 1 else 'SELL'} only" if now_g["dir"] else " → no majority, no trade")}

    setup = None
    if latest:
        g, s = latest
        if s["lifecycle"]["state"] != "CLOSED" or s["signalIndex"] >= last - R["showLastSetupBars"]:
            setup = s

    g = latest[0] if setup else now_g
    nb = news_block(setup["signalTime"] if setup else now, inp["news"]["events"], FIL["news"])
    day = inp["day"]
    if setup:
        rules = [
            item("majority", "Trend majority (≥ 2 of W1 / D1 / H4)", "أغلبية الاتجاه", True, trend_detail if setup["isFresh"] else f"{setup['direction']} majority at the entry", 0, True),
            item("trigger", "Entry trigger: AOI touched + H4 rejection + open-session engulfing", "شروط الدخول", True,
                 f"{setup['anchors']['gpa']['aoi']['tfs']} AOI · {setup['anchors']['gpa']['session']}", 0, True),
            item("rr", f"Risk : reward ≥ 1:{js_str(R['minRr'])} to the next W1 / D1 zone", "العائد إلى المخاطرة 1:2 على الأقل", True,
                 f"1:{to_fixed(setup['rrTarget'], 2)} · TP {f(setup['tp3'])} · SL {f(setup['sl'])} ({js_str(setup['slPips'])} pips)", 0, True),
        ]
    else:
        rules = [item("majority", "Trend majority (≥ 2 of W1 / D1 / H4)", "أغلبية الاتجاه", now_g["dir"] != 0, trend_detail, 0, True)]
    rules += [
        item("news", f"No high-impact {ccys} news ±30 min", "لا أخبار قوية ±30 دقيقة", not nb["blocked"],
             f"{nb['event']['currency']} {nb['event']['title']} at {fmt_time(nb['event']['time'])}" if nb["event"] else "Clear", 0, True),
        item("spread", f"Spread <= {js_str(FIL['maxSpreadPips'])} pips", "السبريد مقبول", spread <= FIL["maxSpreadPips"] * pip,
             f"Spread {to_fixed(spread / pip, 1)} pips{' (assumed, no live spread in feed)' if inp['spread'] is None else ''}", 0, True),
        item("daily", f"Max {FIL['maxTradesPerDay']} trades / stop after {FIL['maxLossesPerDay']} loss per day", "حد الصفقات اليومي",
             day["trades"] < FIL["maxTradesPerDay"] and day["losses"] < FIL["maxLossesPerDay"], f"{day['trades']} trade(s), {day['losses']} loss(es) today", 0, True),
    ]
    checklist = g["items"] + rules
    result["checklist"] = checklist
    result["setup"] = setup
    result["tpReach"] = tp_options(tp_past, setup, cfg["spec"]["decimals"])
    failed = [c for c in checklist if c["required"] and not c["passed"]]
    score = g.get("score", 0) if g["items"] else 0
    result["score"] = score if setup else 0
    result["grade"] = grade_of(score, cfg)
    result["liveGrade"] = {"score": now_g.get("score", 0), "grade": grade_of(now_g.get("score", 0), cfg)}
    result["rejection"] = f"{failed[0]['rule']}: {failed[0]['detail']}" if failed else None
    result["status"] = classify(score, not failed, cfg["scoring"]["thresholds"]) if setup else "NO_TRADE"
    if setup and result["status"] == "SIGNAL":
        result["signal"] = to_signal_json(spec, cfg["strategy"], setup, score, cfg["timeframes"], checklist)
    result["canNotify"] = bool(result["status"] == "SIGNAL" and setup and setup["isFresh"] and setup["lifecycle"]["state"] == "OPEN" and inp["isMarketOpen"])

    # What is missing right now (the "WAIT / NO TRADE" verdict)
    if not now_g["items"]:
        progress = "Not enough history for the W1 / D1 / H4 structure"
    elif not now_g["dir"]:
        progress = f"{trend_detail}: no majority, stand aside"
    elif not now_g["aoi"]:
        side = "above" if now_g["dir"] == 1 else "below"
        zones = sorted(now_g.get("zones", []), key=lambda z: abs(z.mid - price))
        near = next((z for z in zones if (z.hi < price if now_g["dir"] == 1 else z.lo > price)), None)
        progress = (f"{'BUY' if now_g['dir'] == 1 else 'SELL'} bias: waiting for price to come back to the {near.tfs} AOI {f(near.lo)}–{f(near.hi)} "
                    f"({near.touches} touches) and hold {side} it" if near else f"{'BUY' if now_g['dir'] == 1 else 'SELL'} bias: no valid W1 / D1 AOI {side} price")
    elif not now_g["h4Rejection"]:
        progress = f"At the {now_g['aoi'].tfs} AOI {f(now_g['aoi'].lo)}–{f(now_g['aoi'].hi)}: waiting for an H4 rejection (EMA 50, structure or rejection candle)"
    else:
        progress = (f"At the AOI with an H4 rejection (grade now {now_g['score']}%): waiting for a {cfg['entryTf']} "
                    f"{'bullish' if now_g['dir'] == 1 else 'bearish'} engulfing at the London / New York open")
    result["facts"]["progress"] = progress

    # ---- Drawings: AOI zones (D1 / W1), the pattern, the trade ----
    sym = spec["symbol"]
    zones_now = now_g.get("zones", [])
    t0 = h1[max(0, len(h1) - 24 * 120)].time if h1 else e[0].time
    near_zones = sorted(zones_now, key=lambda z: abs(z.mid - price))[:4]
    drawings = [
        {"id": f"{sym}-AOI-{round(z.mid, 5)}", "layer": "levels", "kind": "box", "tf": "D1", "t1": t0, "t2": None, "p1": z.lo, "p2": z.hi,
         "text": f"{z.tfs} AOI · {z.touches} touches", "color": "bull" if z.mid < price else "bear"}
        for z in near_zones
    ]
    if setup:
        a = setup["anchors"]["gpa"]
        bull = a["direction"] == "BUY"
        if a["pattern"]:
            names = ["LS", "H", "RS"] if len(a["pattern"]["points"]) == 3 else ["1", "2"]
            for nm, (pt, pp) in zip(names, a["pattern"]["points"]):
                drawings.append({"id": f"{sym}-PT-{pt}", "layer": "structure", "kind": "marker", "tf": l_key, "t1": pt, "t2": None, "p1": pp,
                                 "text": nm, "color": "bull" if bull else "bear", "position": "below" if bull else "above"})
            drawings.append({"id": f"{sym}-NECK-{a['time']}", "layer": "structure", "kind": "hline", "tf": l_key, "t1": a["pattern"]["points"][0][0],
                             "t2": a["time"] + ctx.e_sec, "p1": a["pattern"]["neckline"], "text": f"Neckline {a['pattern']['type']}",
                             "color": "entry", "style": "dashed"})
        drawings.append({"id": f"{sym}-ENG-{a['time']}", "layer": "structure", "kind": "marker", "tf": e_key, "t1": a["time"], "t2": None, "p1": setup["entry"],
                         "text": f"{e_key} engulfing · {a['grade']} {a['score']}%", "color": "entry", "position": "below" if bull else "above"})
        drawings.extend(trade_drawings(setup, e_key, ""))
    result["drawings"] = drawings

    result["facts"].update({
        "price": price, "spread": spread, "trendW1": word[tr["W1"]], "trendD1": word[tr["D1"]], "trendH4": word[tr["H4"]],
        "weeklyTrend": word[tr["W1"]], "dailyTrend": word[tr["D1"]], "atrH4": round_to(now_g.get("atr", {}).get("h4", 0) or 0, d),
        "grade": result["grade"], "liveGrade": result["liveGrade"],
        "areasOfInterest": [{"price": round_to(z.mid, d), "lo": round_to(z.lo, d), "hi": round_to(z.hi, d), "touches": z.touches, "tfs": z.tfs,
                             "kind": "support" if z.mid < price else "resistance"} for z in near_zones],
        "lastTrade": ({"id": latest[1]["id"], "state": latest[1]["lifecycle"]["state"], "outcome": latest[1]["lifecycle"]["outcome"],
                       "r": latest[1]["lifecycle"]["rMultiple"]} if latest else None),
    })

    status = result["status"]
    sd = setup["direction"] if setup else ""
    if not setup:
        result["headline"] = progress
    elif status == "SIGNAL" and setup["isFresh"]:
        result["headline"] = f"{sd} market {f(setup['entry'])} · grade {result['grade']} {score}% · 1:{to_fixed(setup['rrTarget'], 1)}"
    elif status == "SIGNAL":
        st = setup["lifecycle"]["state"]
        st = {"TP1_HIT": "running, 1R reached", "TP2_HIT": "running, 2R reached"}.get(st, st)
        result["headline"] = f"{sd} {result['grade']} {score}% · {fmt_time(setup['signalTime'])} · {st}"
    elif status in ("WATCH", "IGNORE"):
        result["headline"] = f"{sd} setup graded {score}% (below C+ 60%): no trade"
    else:
        result["headline"] = f"{sd} setup rejected: {failed[0]['rule']}"
    result["headlineAr"] = (f"إشارة {sd} عند {f(setup['entry'])} · تقييم {result['grade']}" if status == "SIGNAL" else "إعداد موجود لكنه غير مكتمل الشروط") if setup else "لا توجد صفقة حالياً"
    return result
