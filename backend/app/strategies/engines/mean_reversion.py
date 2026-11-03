"""
Agent 3 · AUD/CHF · Mean_Reversion_Range_Engine (H4 range, H1 execution).

  RANGE FILTER (last closed H4): ADX(14) < 28. Channel on the last 60 H4 candles:
        Resistance_Zone_Top = Highest(High, 60), Resistance_Zone_Bottom = Top − 0.8 × ATR_H4(14)
        Support_Zone_Bottom = Lowest(Low, 60),   Support_Zone_Top = Bottom + 0.8 × ATR_H4(14)
  DIVERGENCE (H1, fractal swings): the current swing low lies in the support zone, a previous swing low 5–30 H1 candles
        before it: Low_now ≤ Low_prev, RSI(14)_now > RSI_prev + 3, RSI_prev < 35 (mirror at resistance: RSI_prev > 65)
  TRIGGER: an H1 engulfing candle after the divergence is confirmed (within `maxWait` candles, the swing not broken):
        previous candle red, current green, body covers the previous body, range > 0.7 × ATR_H1(14)
  ORDER: MARKET at the engulfing close. SL = the lowest low − 1.2 × ATR_H1(14).
        TP1 (50 % closed, stop to break-even) = the channel's middle; TP2 (the other 50 %) = the start of the opposite zone;
        the blended R:R (0.5 × TP1 + 0.5 × TP2) must be ≥ 1.8.
"""

from ..pairs.rules import adx, atr
from ..shared.types import Candle
from .primitives import aggregate, rsi, swing_flags

H4 = 14400
PARAMS = {"adxMax": 28, "channel": 60, "zoneAtr": 0.8, "divMin": 5, "divMax": 30, "rsiDiff": 3, "rsiLow": 35, "rsiHigh": 65,
          "engulfAtr": 0.7, "slAtr": 1.2, "minRR": 1.8, "maxWait": 8, "tp1Share": 0.5}


def _h4_frame(c: list[Candle], p: dict) -> dict:
    h4 = aggregate(c, H4)
    return {"c": h4, "adx": adx(h4), "atr": atr(h4)}


def scan(c: list[Candle], ctx: dict) -> dict:
    p, pip = ctx["params"], ctx["pip"]
    f = _h4_frame(c, p)
    h4, ax, a4 = f["c"], f["adx"], f["atr"]
    a1, r1 = atr(c), rsi(c)
    hi_f, lo_f = swing_flags(c)
    n = p["channel"]
    setups: list[dict] = []
    used: set = set()
    j = -1  # last H4 candle closed at the close of H1 candle i
    zones, zj = None, -1
    status = "Not enough history"
    for i in range(len(c)):
        close_t = c[i].time + 3600
        while j + 1 < len(h4) and h4[j + 1].time + H4 <= close_t:
            j += 1
        if j < n + 30 or ax[j] is None or a4[j] is None or a1[i] is None or r1[i] is None:
            continue
        if zj != j:  # the zones change once per H4 close
            top = max(x.high for x in h4[j - n + 1:j + 1])
            bot = min(x.low for x in h4[j - n + 1:j + 1])
            zones = {"rt": top, "rb": top - p["zoneAtr"] * a4[j], "sb": bot, "st": bot + p["zoneAtr"] * a4[j], "mid": (top + bot) / 2,
                     "adx": ax[j], "t1": h4[j - n + 1].time}
            zj = j
        z = zones
        if ax[j] >= p["adxMax"]:
            status = f"H4 ADX {ax[j]:.0f} ≥ {p['adxMax']}: trending, no range trade"
            continue
        status = (f"H4 range (ADX {ax[j]:.0f}): support {z['sb']:.5f}–{z['st']:.5f}, resistance {z['rb']:.5f}–{z['rt']:.5f} · "
                  f"waiting for an RSI divergence and an H1 engulfing in a zone")
        if i < 1:
            continue
        x, y = c[i], c[i - 1]
        bull = y.close < y.open and x.close > x.open and x.close >= y.open and x.open <= y.close
        bear = y.close > y.open and x.close < x.open and x.close <= y.open and x.open >= y.close
        if not (bull or bear) or x.high - x.low <= p["engulfAtr"] * a1[i]:
            continue
        buy = bull
        flags = lo_f if buy else hi_f
        # the latest confirmed swing in the zone, recent enough and not broken since
        for s in range(i - 2, max(-1, i - 2 - p["maxWait"]), -1):
            if not flags[s]:
                continue
            ext = c[s].low if buy else c[s].high
            seg = c[s + 1:i + 1]
            broken = any(k.low < ext for k in seg) if buy else any(k.high > ext for k in seg)
            in_zone = ext <= z["st"] if buy else ext >= z["rb"]
            if broken or not in_zone or (buy, s) in used:
                break
            prev = next((q for q in range(s - p["divMin"], max(-1, s - p["divMax"] - 1), -1)
                         if flags[q] and r1[q] is not None and r1[s] is not None
                         and ((c[s].low <= c[q].low and r1[s] > r1[q] + p["rsiDiff"] and r1[q] < p["rsiLow"]) if buy
                              else (c[s].high >= c[q].high and r1[s] < r1[q] - p["rsiDiff"] and r1[q] > p["rsiHigh"]))), None)
            if prev is None:
                break
            used.add((buy, s))
            extreme = min(k.low for k in c[s:i + 1]) if buy else max(k.high for k in c[s:i + 1])
            entry = x.close
            sl = extreme - p["slAtr"] * a1[i] if buy else extreme + p["slAtr"] * a1[i]
            risk = abs(entry - sl)
            tp1, tp2 = z["mid"], (z["rb"] if buy else z["st"])
            if risk <= 0 or not ((entry < tp1 < tp2) if buy else (tp2 < tp1 < entry)):
                break
            rr1, rr2 = abs(tp1 - entry) / risk, abs(tp2 - entry) / risk
            blended = p["tp1Share"] * rr1 + (1 - p["tp1Share"]) * rr2
            if blended < p["minRR"]:
                break
            setups.append({
                "index": i, "time": x.time, "buy": buy, "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp2,
                "partials": [p["tp1Share"], 0, 1 - p["tp1Share"]], "breakeven": True, "expiryBars": None, "cancelLevel": None,
                "why": [f"H4 ADX {ax[j]:.0f} < {p['adxMax']}: a range",
                        f"{'Support' if buy else 'Resistance'} zone {(z['sb'] if buy else z['rb']):.5f}–{(z['st'] if buy else z['rt']):.5f} (60 H4, 0.8 × ATR)",
                        f"RSI divergence: {'lower' if buy else 'higher'} {'low' if buy else 'high'} {ext:.5f} vs {(c[prev].low if buy else c[prev].high):.5f} "
                        f"{s - prev} H1 earlier, RSI {r1[s]:.1f} vs {r1[prev]:.1f}",
                        f"{'Bullish' if buy else 'Bearish'} engulfing H1, range {(x.high - x.low) / pip:.1f} pips > 0.7 × ATR",
                        f"SL {risk / pip:.1f} pips (1.2 × ATR beyond the {'low' if buy else 'high'}) · TP1 the middle (50 %, then BE) · TP2 the "
                        f"{'resistance' if buy else 'support'} zone · R:R 1:{blended:.2f} blended"],
                "zone": {"top": z["st"] if buy else z["rt"], "bottom": z["sb"] if buy else z["rb"], "time": z["t1"], "label": "Demand" if buy else "Supply"},
                "rr": blended,
            })
            break
    drawings = []
    if zones:
        z = zones
        drawings = [{"kind": "box", "t1": z["t1"], "t2": None, "p1": z["rt"], "p2": z["rb"], "text": "H4 resistance zone", "color": "bear", "faded": True},
                    {"kind": "box", "t1": z["t1"], "t2": None, "p1": z["st"], "p2": z["sb"], "text": "H4 support zone", "color": "bull", "faded": True},
                    {"kind": "hline", "t1": z["t1"], "p1": z["mid"], "text": "Range 50 %", "color": "muted", "style": "dashed"}]
    return {"setups": setups, "status": status, "drawings": drawings}
