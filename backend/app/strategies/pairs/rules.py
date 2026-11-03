"""
The pair strategies' rules on closed candles. Each rule has `prep(c, p)` → indicators and `at(c, i, ind, p)` → a setup at
candle i or None; a setup gives the side, the entry (the close of candle i), the stop and the reasons, so the engine can
build, replay and explain it. `draw` gives the rule's levels for the chart, `now` what the rule is waiting for.
"""

from typing import Optional

from ..shared.types import Candle


def hour(t: int) -> int:
    return (t // 3600) % 24


def in_hours(t: int, hours: Optional[list[int]]) -> bool:
    """The candle opened inside [start, end) GMT; a window may wrap midnight (22 → 5)."""
    if not hours:
        return True
    h, (a, b) = hour(t), hours
    return a <= h < b if a < b else (h >= a or h < b)


# ---------------------------------------------------------------- indicators (None until defined)
def ema(v: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    k, e = 2 / (n + 1), None
    for i, x in enumerate(v):
        e = x if e is None else x * k + e * (1 - k)
        out[i] = e if i >= n - 1 else None
    return out


def atr(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    a = None
    for i in range(len(c)):
        tr = c[i].high - c[i].low if i == 0 else max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close)
        a = tr if a is None else (a * (n - 1) + tr) / n
        out[i] = a if i >= n else None
    return out


def adx(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    tr_s = pdm_s = ndm_s = None
    a = None
    for i in range(1, len(c)):
        up, dn = c[i].high - c[i - 1].high, c[i - 1].low - c[i].low
        pdm = up if up > dn and up > 0 else 0
        ndm = dn if dn > up and dn > 0 else 0
        tr = max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close)
        if tr_s is None:
            tr_s, pdm_s, ndm_s = tr, pdm, ndm
        else:
            tr_s, pdm_s, ndm_s = tr_s - tr_s / n + tr, pdm_s - pdm_s / n + pdm, ndm_s - ndm_s / n + ndm
        if i < n or not tr_s:
            continue
        pdi, ndi = 100 * pdm_s / tr_s, 100 * ndm_s / tr_s
        dx = 0 if pdi + ndi == 0 else 100 * abs(pdi - ndi) / (pdi + ndi)
        a = dx if a is None else (a * (n - 1) + dx) / n
        if i >= 2 * n:
            out[i] = a
    return out


def channel(c: list[Candle], n: int) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """The highest high / lowest low of the n candles BEFORE each candle."""
    hi: list[Optional[float]] = [None] * len(c)
    lo: list[Optional[float]] = [None] * len(c)
    for i in range(n, len(c)):
        w = c[i - n:i]
        hi[i], lo[i] = max(x.high for x in w), min(x.low for x in w)
    return hi, lo


def _prep(c, p):
    cl = [x.close for x in c]
    hi, lo = channel(c, p["channel"])
    return {"hi": hi, "lo": lo, "atr": atr(c), "adx": adx(c), "e50": ema(cl, 50), "e200": ema(cl, 200)}


def _draw(c, ind, p, last):
    if ind["hi"][last] is None:
        return []
    t1, n = c[max(0, last - p["channel"])].time, p["channel"]
    return [{"kind": "hline", "t1": t1, "p1": ind["hi"][last], "text": f"{n}-candle high", "color": "liquidity", "style": "dotted"},
            {"kind": "hline", "t1": t1, "p1": ind["lo"][last], "text": f"{n}-candle low", "color": "liquidity", "style": "dotted"}]


# ---------------------------------------------------------------- 1. channel breakout in the trend (trending pairs: gold)
def bo_at(c, i, ind, p) -> Optional[dict]:
    """A close beyond the high (low) of the last `channel` candles, with EMA50 above (below) EMA200: buy (sell) at that
    close, stop `slAtr` × ATR away. Trending markets carry a breakout further than the stop more often than not."""
    hi, lo, a, e50, e200, ax = ind["hi"][i], ind["lo"][i], ind["atr"][i], ind["e50"][i], ind["e200"][i], ind["adx"][i]
    if None in (hi, lo, a, e50, e200) or (p.get("adxMin") and (ax is None or ax < p["adxMin"])):
        return None
    x = c[i]
    if x.close > hi and e50 > e200:
        return {"buy": True, "entry": x.close, "sl": x.close - p["slAtr"] * a,
                "why": [f"Uptrend: EMA50 {e50:.5g} > EMA200 {e200:.5g}", f"Close {x.close:.5g} above the {p['channel']}-candle high {hi:.5g}",
                        f"Stop {p['slAtr']:g} × ATR below the entry"]}
    if x.close < lo and e50 < e200:
        return {"buy": False, "entry": x.close, "sl": x.close + p["slAtr"] * a,
                "why": [f"Downtrend: EMA50 {e50:.5g} < EMA200 {e200:.5g}", f"Close {x.close:.5g} below the {p['channel']}-candle low {lo:.5g}",
                        f"Stop {p['slAtr']:g} × ATR above the entry"]}
    return None


def bo_now(c, ind, p, last) -> str:
    hi, lo, e50, e200 = ind["hi"][last], ind["lo"][last], ind["e50"][last], ind["e200"][last]
    if None in (hi, lo, e50, e200):
        return "Not enough history"
    return (f"Uptrend (EMA50 > EMA200): waiting for a close above the {p['channel']}-candle high {hi:.5g}" if e50 > e200
            else f"Downtrend (EMA50 < EMA200): waiting for a close below the {p['channel']}-candle low {lo:.5g}")


# ---------------------------------------------------------------- 2. channel fade (reverting pairs)
def fade_at(c, i, ind, p) -> Optional[dict]:
    """A close beyond the high (low) of the last `channel` candles — inside the session hours and without a strong trend
    when set — is faded at that close: sell (buy), stop `slAtr` × ATR beyond the entry. On a reverting pair such a close
    comes back more often than it runs."""
    hi, lo, a, ax = ind["hi"][i], ind["lo"][i], ind["atr"][i], ind["adx"][i]
    x = c[i]
    if None in (hi, lo, a) or not in_hours(x.time, p.get("hours")):
        return None
    if p.get("adxMax") and (ax is None or ax >= p["adxMax"]):
        return None
    why = []
    if p.get("hours"):
        why.append(f"Inside the {p['hours'][0]:02d}:00–{p['hours'][1]:02d}:00 GMT window")
    if p.get("adxMax"):
        why.append(f"ADX {ax:.0f} < {p['adxMax']}: no strong trend")
    if x.close > hi:
        return {"buy": False, "entry": x.close, "sl": x.close + p["slAtr"] * a,
                "why": [f"Close {x.close:.5g} above the {p['channel']}-candle high {hi:.5g}: stretched, faded", *why, f"Stop {p['slAtr']:g} × ATR above"]}
    if x.close < lo:
        return {"buy": True, "entry": x.close, "sl": x.close - p["slAtr"] * a,
                "why": [f"Close {x.close:.5g} below the {p['channel']}-candle low {lo:.5g}: stretched, faded", *why, f"Stop {p['slAtr']:g} × ATR below"]}
    return None


def fade_now(c, ind, p, last) -> str:
    hi, lo = ind["hi"][last], ind["lo"][last]
    if hi is None:
        return "Not enough history"
    when = f" between {p['hours'][0]:02d}:00 and {p['hours'][1]:02d}:00 GMT" if p.get("hours") else ""
    trend = f", ADX below {p['adxMax']}" if p.get("adxMax") else ""
    return f"Waiting for a close outside {lo:.5g} – {hi:.5g} (the {p['channel']}-candle channel){when}{trend}, to fade it"


RULES = {
    "channel_breakout": {"prep": _prep, "at": bo_at, "draw": _draw, "now": bo_now},
    "channel_fade": {"prep": _prep, "at": fade_at, "draw": _draw, "now": fade_now},
}
