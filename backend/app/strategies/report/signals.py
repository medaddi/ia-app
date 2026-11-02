"""
The strategy report's per-pair strategies ("Anja7 Stratigiyat Trading F Forex"), as signal rules on closed candles.
Each rule has `prep(c, p)` → indicators and `at(c, i, ind, p)` → a setup at candle i or None. A setup gives the side, the
entry (the close of candle i), the stop and the reasons, so the engine can build, replay and explain it.
"""

import math
from typing import Optional

from ..shared.types import Candle


def _hour(t: int) -> int:
    return (t // 3600) % 24


# ---------------------------------------------------------------- indicators (None until defined)
def ema(v: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    k, e = 2 / (n + 1), None
    for i, x in enumerate(v):
        e = x if e is None else x * k + e * (1 - k)
        out[i] = e if i >= n - 1 else None
    return out


def sma(v: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    s = 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n:
            s -= v[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def stdev(v: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    for i in range(n - 1, len(v)):
        w = v[i - n + 1:i + 1]
        m = sum(w) / n
        out[i] = math.sqrt(sum((x - m) ** 2 for x in w) / n)
    return out


def atr(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    a = None
    for i in range(len(c)):
        tr = c[i].high - c[i].low if i == 0 else max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close)
        a = tr if a is None else (a * (n - 1) + tr) / n
        out[i] = a if i >= n else None
    return out


def rsi(v: list[float], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(v)
    g = l_ = 0.0
    for i in range(1, len(v)):
        d = v[i] - v[i - 1]
        up, dn = max(d, 0), max(-d, 0)
        if i <= n:
            g += up / n
            l_ += dn / n
        else:
            g = (g * (n - 1) + up) / n
            l_ = (l_ * (n - 1) + dn) / n
        if i >= n:
            out[i] = 100 if l_ == 0 else 100 - 100 / (1 + g / l_)
    return out


def stoch_k(c: list[Candle], n: int = 14, k: int = 3) -> list[Optional[float]]:
    raw: list[Optional[float]] = [None] * len(c)
    for i in range(n - 1, len(c)):
        hh = max(x.high for x in c[i - n + 1:i + 1])
        ll = min(x.low for x in c[i - n + 1:i + 1])
        raw[i] = 50 if hh == ll else (c[i].close - ll) / (hh - ll) * 100
    out: list[Optional[float]] = [None] * len(c)
    for i in range(k - 1, len(c)):
        w = raw[i - k + 1:i + 1]
        if None not in w:
            out[i] = sum(w) / k  # type: ignore[arg-type]
    return out


def adx(c: list[Candle], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    tr_s = pdm_s = ndm_s = None
    dxs: list[float] = []
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
        if tr_s:
            pdi, ndi = 100 * pdm_s / tr_s, 100 * ndm_s / tr_s
            dx = 0 if pdi + ndi == 0 else 100 * abs(pdi - ndi) / (pdi + ndi)
            dxs.append(dx)
            a = sum(dxs) / n if len(dxs) == n else (a * (n - 1) + dx) / n if len(dxs) > n else None
            if i >= 2 * n:
                out[i] = a
    return out


def _bands(c: list[Candle], n: int, dev: float):
    cl = [x.close for x in c]
    mid, sd = sma(cl, n), stdev(cl, n)
    up = [None if m is None else m + dev * s for m, s in zip(mid, sd)]
    lo = [None if m is None else m - dev * s for m, s in zip(mid, sd)]
    return mid, up, lo, sd


# ---------------------------------------------------------------- 1. mean reversion: Bollinger + Stochastic (range pairs)
def mr_prep(c, p):
    mid, up, lo, _ = _bands(c, p["bbPeriod"], p["bbDev"])
    return {"mid": mid, "up": up, "lo": lo, "k": stoch_k(c, p["stochPeriod"], p["stochSmooth"]), "atr": atr(c), "adx": adx(c)}


def mr_at(c, i, ind, p) -> Optional[dict]:
    """The candle before closed outside the Bollinger band with the Stochastic at its extreme, this one closes back
    inside, ADX shows no trend (and, if set, inside the session hours)."""
    if i < 2 or None in (ind["mid"][i], ind["mid"][i - 1], ind["k"][i - 1], ind["atr"][i], ind["adx"][i]):
        return None
    s = p.get("sessionHours")
    if s and not (s[0] <= _hour(c[i].time) < s[1]):
        return None
    if ind["adx"][i] >= p["adxMax"]:
        return None
    a = ind["atr"][i]
    prev, x = c[i - 1], c[i]
    why_adx = f"ADX {ind['adx'][i]:.0f} < {p['adxMax']}: no trend"
    if prev.close < ind["lo"][i - 1] and ind["k"][i - 1] < p["stochLow"] and x.close > ind["lo"][i]:
        sl = min(prev.low, x.low) - p["slAtr"] * a
        if x.close - sl >= p["minRiskAtr"] * a:
            return {"buy": True, "entry": x.close, "sl": sl, "why": [
                f"Close below the Bollinger ({p['bbPeriod']}, {p['bbDev']:g}) band, then back inside", f"Stochastic {ind['k'][i - 1]:.0f} < {p['stochLow']}", why_adx]}
    if prev.close > ind["up"][i - 1] and ind["k"][i - 1] > 100 - p["stochLow"] and x.close < ind["up"][i]:
        sl = max(prev.high, x.high) + p["slAtr"] * a
        if sl - x.close >= p["minRiskAtr"] * a:
            return {"buy": False, "entry": x.close, "sl": sl, "why": [
                f"Close above the Bollinger ({p['bbPeriod']}, {p['bbDev']:g}) band, then back inside", f"Stochastic {ind['k'][i - 1]:.0f} > {100 - p['stochLow']}", why_adx]}
    return None


def mr_draw(c, ind, p, last):
    if ind["up"][last] is None:
        return []
    t1 = c[max(0, last - 30)].time
    return [{"kind": "hline", "t1": t1, "p1": ind["up"][last], "text": f"Bollinger {p['bbDev']:g}σ upper", "color": "bear", "style": "dotted"},
            {"kind": "hline", "t1": t1, "p1": ind["mid"][last], "text": "Bollinger middle", "color": "muted", "style": "dotted"},
            {"kind": "hline", "t1": t1, "p1": ind["lo"][last], "text": f"Bollinger {p['bbDev']:g}σ lower", "color": "bull", "style": "dotted"}]


def mr_now(c, ind, p, last) -> str:
    if ind["adx"][last] is not None and ind["adx"][last] >= p["adxMax"]:
        return f"ADX {ind['adx'][last]:.0f} ≥ {p['adxMax']}: the pair is trending, the range rule waits"
    return (f"Waiting for a close outside the Bollinger band ({ind['lo'][last]:.5g} – {ind['up'][last]:.5g}) with the Stochastic beyond "
            f"{p['stochLow']} / {100 - p['stochLow']}, then a close back inside") if ind["up"][last] is not None else "Not enough history"


# ---------------------------------------------------------------- 2. New York trend with ADX (USD/CAD)
def ny_prep(c, p):
    cl = [x.close for x in c]
    return {"fast": ema(cl, p["emaFast"]), "slow": ema(cl, p["emaSlow"]), "adx": adx(c), "atr": atr(c)}


def ny_at(c, i, ind, p) -> Optional[dict]:
    """New York session, ADX above the threshold, EMA fast vs slow trend, a pullback to the fast EMA that closes back
    in the trend; stop at slAtr × ATR."""
    if None in (ind["fast"][i], ind["slow"][i], ind["adx"][i], ind["atr"][i]):
        return None
    s = p["sessionHours"]
    if not (s[0] <= _hour(c[i].time) < s[1]) or ind["adx"][i] <= p["adxMin"]:
        return None
    x, f, a = c[i], ind["fast"][i], ind["atr"][i]
    trend = f"EMA{p['emaFast']} {'>' if f > ind['slow'][i] else '<'} EMA{p['emaSlow']}, ADX {ind['adx'][i]:.0f} > {p['adxMin']}"
    if f > ind["slow"][i] and x.low <= f < x.close and x.close > x.open:
        return {"buy": True, "entry": x.close, "sl": x.close - p["slAtr"] * a, "why": [trend, f"Pullback to EMA{p['emaFast']} and a bullish close", "New York session"]}
    if f < ind["slow"][i] and x.high >= f > x.close and x.close < x.open:
        return {"buy": False, "entry": x.close, "sl": x.close + p["slAtr"] * a, "why": [trend, f"Pullback to EMA{p['emaFast']} and a bearish close", "New York session"]}
    return None


def ny_draw(c, ind, p, last):
    t1 = c[max(0, last - 30)].time
    return [{"kind": "hline", "t1": t1, "p1": ind["fast"][last], "text": f"EMA{p['emaFast']} (pullback)", "color": "entry", "style": "dotted"}] if ind["fast"][last] else []


def ny_now(c, ind, p, last) -> str:
    a = ind["adx"][last]
    return (f"ADX {a:.0f}: waiting for ADX > {p['adxMin']} and a pullback to EMA{p['emaFast']} in New York ({p['sessionHours'][0]:02d}:00–{p['sessionHours'][1]:02d}:00 GMT)"
            if a is not None else "Not enough history")


# ---------------------------------------------------------------- 3. MACD + RSI (H4 swing)
def macd_prep(c, p):
    cl = [x.close for x in c]
    f, s = ema(cl, p["macdFast"]), ema(cl, p["macdSlow"])
    m = [None if a is None or b is None else a - b for a, b in zip(f, s)]
    sig: list[Optional[float]] = [None] * len(m)
    e, k = None, 2 / (p["macdSignal"] + 1)
    for i, x in enumerate(m):
        if x is None:
            continue
        e = x if e is None else x * k + e * (1 - k)
        sig[i] = e
    return {"macd": m, "signal": sig, "rsi": rsi(cl, p["rsiPeriod"]), "atr": atr(c)}


def macd_at(c, i, ind, p) -> Optional[dict]:
    """MACD crosses its signal line with RSI on the same side of 50; stop at slAtr × ATR."""
    m, s, r, a = ind["macd"], ind["signal"], ind["rsi"][i], ind["atr"][i]
    if i < 1 or None in (m[i], m[i - 1], s[i], s[i - 1], r, a):
        return None
    x = c[i]
    if m[i - 1] <= s[i - 1] and m[i] > s[i] and r > 50:
        return {"buy": True, "entry": x.close, "sl": x.close - p["slAtr"] * a, "why": ["MACD crosses above its signal line", f"RSI(14) {r:.0f} > 50"]}
    if m[i - 1] >= s[i - 1] and m[i] < s[i] and r < 50:
        return {"buy": False, "entry": x.close, "sl": x.close + p["slAtr"] * a, "why": ["MACD crosses below its signal line", f"RSI(14) {r:.0f} < 50"]}
    return None


def macd_now(c, ind, p, last) -> str:
    m, s = ind["macd"][last], ind["signal"][last]
    return (f"MACD {'above' if m > s else 'below'} its signal line, RSI(14) {ind['rsi'][last]:.0f}: waiting for the next cross with RSI on its side of 50"
            if m is not None and s is not None and ind["rsi"][last] is not None else "Not enough history")


# ---------------------------------------------------------------- 4. Bollinger squeeze breakout (gold)
def sq_prep(c, p):
    mid, up, lo, sd = _bands(c, p["bbPeriod"], p["bbDev"])
    bw = [None if m is None or not m else 2 * p["bbDev"] * s / m for m, s in zip(mid, sd)]
    avg: list[Optional[float]] = [None] * len(c)
    n = p["squeezeLookback"]
    for i in range(n, len(c)):
        w = bw[i - n:i]
        if None not in w:
            avg[i] = sum(w) / n  # type: ignore[arg-type]
    return {"mid": mid, "up": up, "lo": lo, "bw": bw, "avg": avg, "atr": atr(c)}


def sq_at(c, i, ind, p) -> Optional[dict]:
    """The bands squeeze (width below squeezePct of its average) then a close outside them; stop at the middle band
    (at least one ATR)."""
    if i < 1 or None in (ind["bw"][i - 1], ind["avg"][i - 1], ind["mid"][i], ind["atr"][i]) or ind["bw"][i - 1] >= p["squeezePct"] * ind["avg"][i - 1]:
        return None
    x, mid, a = c[i], ind["mid"][i], ind["atr"][i]
    sq = f"Squeeze: band width {ind['bw'][i - 1] / ind['avg'][i - 1] * 100:.0f}% of its average"
    if x.close > ind["up"][i]:
        return {"buy": True, "entry": x.close, "sl": x.close - max(x.close - mid, a), "why": [sq, "Close above the upper band"]}
    if x.close < ind["lo"][i]:
        return {"buy": False, "entry": x.close, "sl": x.close + max(mid - x.close, a), "why": [sq, "Close below the lower band"]}
    return None


def sq_now(c, ind, p, last) -> str:
    bw, avg = ind["bw"][last], ind["avg"][last]
    if bw is None or avg is None:
        return "Not enough history"
    return (f"Bands squeezed ({bw / avg * 100:.0f}% of their average): waiting for a close outside them" if bw < p["squeezePct"] * avg
            else f"No squeeze (band width {bw / avg * 100:.0f}% of its average, needs < {p['squeezePct'] * 100:.0f}%)")


# ---------------------------------------------------------------- 5. session range breakout (NZD/USD: Sydney open)
def sess_prep(c, p):
    rng: dict[int, dict] = {}
    for x in c:
        h = _hour(x.time)
        if p["rangeHours"][0] <= h < p["rangeHours"][1]:
            key = (x.time + p["dayShift"] * 3600) // 86400
            r = rng.setdefault(key, {"hi": x.high, "lo": x.low, "t0": x.time})
            r["hi"], r["lo"] = max(r["hi"], x.high), min(r["lo"], x.low)
    return {"ranges": rng, "atr": atr(c)}


def sess_at(c, i, ind, p) -> Optional[dict]:
    """The first strong close beyond the quiet late-New-York range after the Sydney open; stop at the other side."""
    x = c[i]
    h = _hour(x.time)
    b0, b1 = p["breakHours"]
    if not (h >= b0 or h < b1) or ind["atr"][i] is None:
        return None
    r = ind["ranges"].get((x.time + p["dayShift"] * 3600) // 86400)
    span = x.high - x.low
    if not r or r["hi"] <= r["lo"] or r["hi"] - r["lo"] > p["maxRangeAtr"] * ind["atr"][i] or span <= 0 or abs(x.close - x.open) < p["minBodyPct"] * span:
        return None
    why = [f"Late New York range {r['lo']:.5f} – {r['hi']:.5f}", "Strong H1 close beyond it after the Sydney open"]
    if x.close > r["hi"] and (x.close - x.low) / span >= p["closeOuterThird"]:
        return {"buy": True, "entry": x.close, "sl": r["lo"], "why": why, "oncePer": (x.time + p["dayShift"] * 3600) // 86400}
    if x.close < r["lo"] and (x.high - x.close) / span >= p["closeOuterThird"]:
        return {"buy": False, "entry": x.close, "sl": r["hi"], "why": why, "oncePer": (x.time + p["dayShift"] * 3600) // 86400}
    return None


def sess_draw(c, ind, p, last):
    r = ind["ranges"].get((c[last].time + p["dayShift"] * 3600) // 86400)
    return [{"kind": "box", "t1": r["t0"], "p1": r["hi"], "p2": r["lo"], "text": "Late New York range", "color": "liquidity"}] if r else []


def sess_now(c, ind, p, last) -> str:
    r = ind["ranges"].get((c[last].time + p["dayShift"] * 3600) // 86400)
    return (f"Waiting for a strong H1 close beyond {r['lo']:.5f} – {r['hi']:.5f} between {p['breakHours'][0]:02d}:00 and {p['breakHours'][1]:02d}:00 GMT"
            if r else f"The range builds {p['rangeHours'][0]:02d}:00–{p['rangeHours'][1]:02d}:00 GMT")


RULES = {
    "mean_reversion": {"prep": mr_prep, "at": mr_at, "draw": mr_draw, "now": mr_now},
    "ny_adx_trend": {"prep": ny_prep, "at": ny_at, "draw": ny_draw, "now": ny_now},
    "macd_rsi": {"prep": macd_prep, "at": macd_at, "draw": lambda c, ind, p, last: [], "now": macd_now},
    "bb_squeeze": {"prep": sq_prep, "at": sq_at, "draw": mr_draw, "now": sq_now},
    "session_breakout": {"prep": sess_prep, "at": sess_at, "draw": sess_draw, "now": sess_now},
}
