"""
Agent 1 · EUR/USD · Asian_Sweep_FVG_Engine (M5, London clock).

State machine, one London day at a time:
  IDLE ─07:00→ RANGE: Asian_High / Asian_Low of 00:00–07:00 (M5 = the same extremes as M15).
                      Asian_Range_Pips outside [12, 45] → IDLE for the day.
  RANGE ─London 08:00–11:00 / New York 13:30–16:00→ SWEEP WATCH, both sides:
        sell side: High > Asian_High by at most 20 pips (more = a real breakout: that side is dead for the session)
        buy side : Low  < Asian_Low  by at most 20 pips
  SWEPT → MSS: an M5 close beyond the last swing (the other way) formed before the sweep
        → the leg from the sweep extreme to the MSS candle must hold an FVG > 2.5 pips (the last one is used)
  ORDER: LIMIT at the FVG's 50 %, SL = sweep extreme ± 3 pips (≤ 18 pips), TP = the other side of the Asian range
         with R:R ≥ 2; stop to break-even at the Asian 50 % or 1R, whichever comes first; the order is deleted after
         12 M5 candles or if the target is reached first (and 15 min before high-impact news, by the engine).
One setup per session window at most.
"""

from typing import Optional

from ..shared.types import Candle
from .primitives import by_day, fingerprint, gaps, hm, last_swing, london, swing_flags

PARAMS = {
    "asia": [0, 7 * 60],  # London minutes
    "windows": [["London", 8 * 60, 11 * 60], ["New York", 13 * 60 + 30, 16 * 60]],
    "rangeMinPips": 12, "rangeMaxPips": 45, "maxSweepPips": 20, "minFvgPips": 2.5,
    "slBufferPips": 3, "maxSlPips": 18, "minRR": 2.0, "expiryBars": 12, "minAsiaBars": 60,
}


def _day(c: list[Candle], a: int, b: int, p: dict, pip: float) -> dict:
    """The day's range, sweeps and setups on candles a..b (one London date)."""
    hi_f, lo_f = swing_flags(c[a:b + 1])
    rel = lambda k: k - a  # noqa: E731
    minute = [london(c[i].time)[1] for i in range(a, b + 1)]
    asia = [i for i in range(a, b + 1) if p["asia"][0] <= minute[rel(i)] < p["asia"][1]]
    out: dict = {"setups": [], "asia": None, "state": "IDLE", "detail": "Waiting for the Asian range (00:00–07:00 London)", "marks": []}
    if len(asia) < p["minAsiaBars"]:
        return out
    ah, al = max(c[i].high for i in asia), min(c[i].low for i in asia)
    rng = (ah - al) / pip
    out["asia"] = {"high": ah, "low": al, "pips": round(rng, 1), "t1": c[asia[0]].time, "t2": c[asia[-1]].time}
    complete = minute[rel(b)] >= p["asia"][1] - 5
    if not complete:
        out["detail"] = f"Asian range forming: {rng:.1f} pips so far"
        return out
    if not p["rangeMinPips"] <= rng <= p["rangeMaxPips"]:
        out["detail"] = f"Asian range {rng:.1f} pips outside {p['rangeMinPips']}–{p['rangeMaxPips']}: no trade today"
        out["state"] = "IDLE"
        return out
    mid = (ah + al) / 2
    out["state"], out["detail"] = "RANGE", f"Asian range {al:.5f} – {ah:.5f} ({rng:.1f} pips): waiting for a sweep in London or New York"

    for name, w0, w1 in p["windows"]:
        win = [i for i in range(a, b + 1) if w0 <= minute[rel(i)] < w1]
        if not win:
            continue
        # side → {swept, ext, extIdx, ref, dead}
        sides = {True: {"swept": False, "dead": False}, False: {"swept": False, "dead": False}}  # True = buy (sweep of the low)
        done = False
        for i in win:
            x = c[i]
            for buy in (False, True):
                s = sides[buy]
                if s["dead"] or done:
                    continue
                beyond = (al - x.low) if buy else (x.high - ah)
                if beyond > 0:
                    if beyond > p["maxSweepPips"] * pip:
                        s["dead"] = True
                        out["marks"].append({"time": x.time, "text": f"{name}: real breakout {'below' if buy else 'above'} Asia", "buy": buy})
                        continue
                    if not s["swept"]:
                        ref = last_swing(hi_f if buy else lo_f, rel(i), rel(i))
                        if ref is None:
                            s["dead"] = True
                            continue
                        s.update(swept=True, sweepIdx=i, ref=ref + a, refPrice=c[ref + a].high if buy else c[ref + a].low, ext=None)
                    ext = x.low if buy else x.high
                    if s["ext"] is None or (ext < s["ext"] if buy else ext > s["ext"]):
                        s["ext"], s["extIdx"] = ext, i
                if not s["swept"]:
                    continue
                mss = x.close > s["refPrice"] if buy else x.close < s["refPrice"]
                if not mss:
                    continue
                s["dead"] = True  # one decision per sweep
                g = gaps(c, s["extIdx"] + 2, i, buy, p["minFvgPips"] * pip)
                if not g:
                    out["marks"].append({"time": x.time, "text": f"{name}: MSS without an FVG > {p['minFvgPips']} pips", "buy": buy})
                    continue
                fvg = g[-1]
                entry = fvg.mid
                sl = s["ext"] - p["slBufferPips"] * pip if buy else s["ext"] + p["slBufferPips"] * pip
                risk = abs(entry - sl)
                tp = ah if buy else al
                rr = abs(tp - entry) / risk if risk else 0
                why_base = [f"Asian range {rng:.1f} pips ({al:.5f} – {ah:.5f})",
                            f"{name}: {'Asian low' if buy else 'Asian high'} swept by {abs(s['ext'] - (al if buy else ah)) / pip:.1f} pips (≤ {p['maxSweepPips']})",
                            f"MSS: M5 close {x.close:.5f} {'above the swing high' if buy else 'below the swing low'} {s['refPrice']:.5f}",
                            f"{'Bullish' if buy else 'Bearish'} FVG {fvg.bottom:.5f} – {fvg.top:.5f} ({(fvg.top - fvg.bottom) / pip:.1f} pips), limit at its 50 %"]
                if risk / pip > p["maxSlPips"]:
                    out["marks"].append({"time": x.time, "text": f"{name}: stop {risk / pip:.1f} pips > {p['maxSlPips']}", "buy": buy})
                    continue
                if rr < p["minRR"] or (tp <= entry if buy else tp >= entry):
                    out["marks"].append({"time": x.time, "text": f"{name}: R:R 1:{rr:.2f} < 1:{p['minRR']:g}", "buy": buy})
                    continue
                one_r = entry + risk if buy else entry - risk
                be = min(mid, one_r) if buy else max(mid, one_r)  # whichever the price reaches first
                if not (entry < be < tp if buy else tp < be < entry):
                    be = one_r
                out["setups"].append({
                    "index": i, "buy": buy, "entryType": "LIMIT", "entry": entry, "sl": sl, "tp1": be, "tp2": tp, "tp3": tp,
                    "partials": [0, 0, 1], "breakeven": True, "expiryBars": p["expiryBars"], "cancelLevel": tp,
                    "why": [*why_base, f"SL {risk / pip:.1f} pips beyond the sweep, TP the other side of Asia (1:{rr:.2f})",
                            f"Break-even at {'the Asian 50 %' if be == mid else '1R'}"],
                    "zone": {"top": fvg.top, "bottom": fvg.bottom, "time": c[fvg.index - 2].time, "label": "FVG"},
                    "session": name,
                })
                done = True
        if done:
            st = out["setups"][-1]
            out["state"] = "ORDER"
            out["detail"] = (f"{name}: {'Asian low' if st['buy'] else 'Asian high'} swept, MSS + FVG → {'BUY' if st['buy'] else 'SELL'} LIMIT "
                             f"{st['entry']:.5f} (TP the other side of Asia)")
            break
    return out


def scan(c: list[Candle], ctx: dict) -> dict:
    p, pip = ctx["params"], ctx["pip"]
    setups: list[dict] = []
    days = by_day(c)
    last: Optional[dict] = None
    memo = ctx["memo"]
    for n, (d, a, b) in enumerate(days):
        sig = fingerprint(c, a, b)
        hit = memo.get(d)
        if hit is None or hit[0] != sig:  # a finished day is computed once; today again at each new candle
            res = _day(c, a, b, p, pip)
            res = {**res, "setups": [{**s, "time": c[s["index"]].time} for s in res["setups"]]}
            memo[d] = (sig, res)
        else:
            res = hit[1]
        setups.extend(res["setups"])
        last = res
    if len(memo) > 400:
        for k in sorted(memo)[:-300]:
            del memo[k]
    drawings, status = [], "Not enough history"
    if last:
        status = last["detail"]
        if last["asia"]:
            A = last["asia"]
            drawings += [{"kind": "hline", "t1": A["t1"], "p1": A["high"], "text": f"Asian high ({A['pips']} pips)", "color": "liquidity", "style": "dotted"},
                         {"kind": "hline", "t1": A["t1"], "p1": A["low"], "text": "Asian low", "color": "liquidity", "style": "dotted"},
                         {"kind": "hline", "t1": A["t1"], "p1": (A["high"] + A["low"]) / 2, "text": "Asia 50 %", "color": "muted", "style": "dashed"}]
        status += "" if not last["marks"] else f" · {last['marks'][-1]['text']}"
        status += f" · windows {', '.join(f'{w[0]} {hm(w[1])}–{hm(w[2])}' for w in p['windows'])} London"
    return {"setups": setups, "status": status, "drawings": drawings}
