"""
Agent 2 · GBP/USD · London_Judas_SMT_Engine (M5, London clock, reads EUR/USD M5 at the same time).

State machine, one London day at a time:
  LEVELS (before 08:00): PDH / PDL of the previous day and Asian_High / Asian_Low of 00:00–07:30, for GBP/USD and EUR/USD.
  JUDAS WATCH 08:00–10:00, each key level on its own:
        sell side: GBP/USD trades above PDH (or the Asian high) by 5 to 30 pips (more than 30 = a real breakout: dead)
        buy side : GBP/USD trades below PDL (or the Asian low) by 5 to 30 pips
  SMT: in the same window EUR/USD has NOT traded beyond its own matching level (the divergence that marks the trap)
  MSS on M5: a GBP/USD close back inside the level AND beyond the last swing formed before the fakeout;
        the leg (fakeout extreme → lowest low / highest high up to the MSS) must be longer than 1.5 × ATR(14) M5
  ORDER BLOCK: the last up candle (sell) / down candle (buy) before the leg; LIMIT at its open (or its body's 50 %)
        SL = fakeout extreme ± 4 pips, at least 15 and at most 28 pips (a tighter stop is widened to 15; wider: no trade)
        TP = 3R, stop to break-even at 1.5R; the order is deleted after 12 M5 candles or if 3R is reached first.
The opposite divergence (EUR/USD breaks its level, GBP/USD does not) gives no GBP/USD fakeout to sell: it is not traded here.
"""

from typing import Optional

from ..shared.types import Candle
from .primitives import by_day, fingerprint, hm, last_swing, london, swing_flags
from ..pairs.rules import atr

PARAMS = {
    "asia": [0, 7 * 60 + 30], "window": [8 * 60, 10 * 60],
    "minPenPips": 5, "maxPenPips": 30, "legAtr": 1.5, "slBufferPips": 4, "minSlPips": 15, "maxSlPips": 28,
    "targetR": 3.0, "breakevenR": 1.5, "expiryBars": 12, "obEntry": "open", "minAsiaBars": 60, "obLookback": 12,
}


def _levels(c: list[Candle], prev: Optional[tuple[int, int]], a: int, b: int, p: dict) -> dict:
    out = {}
    if prev:
        out["PDH"], out["PDL"] = max(x.high for x in c[prev[0]:prev[1] + 1]), min(x.low for x in c[prev[0]:prev[1] + 1])
    asia = [x for x in c[a:b + 1] if p["asia"][0] <= london(x.time)[1] < p["asia"][1]]
    if len(asia) >= p["minAsiaBars"]:
        out["AH"], out["AL"] = max(x.high for x in asia), min(x.low for x in asia)
    return out


NAMES = {"PDH": "PDH", "PDL": "PDL", "AH": "Asian high", "AL": "Asian low"}


def _day(c: list[Candle], prev: Optional[tuple[int, int]], a: int, b: int, peer: Optional[dict], p: dict, pip: float) -> dict:
    out: dict = {"setups": [], "levels": {}, "detail": "Waiting for London (08:00–10:00)", "marks": []}
    L = _levels(c, prev, a, b, p)
    out["levels"] = L
    if not L:
        out["detail"] = "No key levels yet (previous day / Asian range)"
        return out
    E = None
    if peer is not None:
        E = _levels(peer["c"], peer["prev"], peer["a"], peer["b"], p) if peer.get("a") is not None else {}
    lo = max(prev[0] if prev else a, a - 300)
    seg = c[lo:b + 1]
    hi_f, lo_f = swing_flags(seg)
    at = atr(seg)
    rel = lambda k: k - lo  # noqa: E731
    w0, w1 = p["window"]
    win = [i for i in range(a, b + 1) if w0 <= london(c[i].time)[1] < w1]
    if not win:
        return out
    eur_by_t = {x.time: x for x in peer["c"][peer["a"]:peer["b"] + 1]} if peer and peer.get("a") is not None else {}
    eur_hi = eur_lo = None
    st = {k: {"ext": None, "dead": False} for k in L}
    done = False
    for i in win:
        x = c[i]
        ex = eur_by_t.get(x.time)
        if ex is not None:
            eur_hi = ex.high if eur_hi is None else max(eur_hi, ex.high)
            eur_lo = ex.low if eur_lo is None else min(eur_lo, ex.low)
        for k, lvl in L.items():
            s = st[k]
            if s["dead"] or done:
                continue
            buy = k in ("PDL", "AL")
            beyond = (lvl - x.low) if buy else (x.high - lvl)
            if beyond > 0:
                if s["ext"] is None:
                    ref = last_swing(hi_f if buy else lo_f, rel(i), rel(i))
                    if ref is None:
                        s["dead"] = True
                        continue
                    s.update(ref=ref + lo, refPrice=seg[ref].high if buy else seg[ref].low, ext=x.low if buy else x.high, extIdx=i)
                elif (x.low < s["ext"]) if buy else (x.high > s["ext"]):
                    s["ext"], s["extIdx"] = (x.low if buy else x.high), i
                if abs(s["ext"] - lvl) > p["maxPenPips"] * pip:
                    s["dead"] = True
                    out["marks"].append(f"{NAMES[k]} broken by more than {p['maxPenPips']} pips: a real breakout")
                    continue
            if s["ext"] is None:
                continue
            pen = abs(s["ext"] - lvl) / pip
            inside = x.close > lvl if buy else x.close < lvl
            mss = x.close > s["refPrice"] if buy else x.close < s["refPrice"]
            if not (inside and mss):
                continue
            s["dead"] = True  # one decision per fakeout
            if pen < p["minPenPips"]:
                out["marks"].append(f"{NAMES[k]} taken by {pen:.1f} pips only (< {p['minPenPips']})")
                continue
            # SMT: EUR/USD failed to take its own matching level in the window (peer None = not checked: a pre-filter)
            smt_txt = "EUR/USD not checked"
            if peer is not None:
                el = E.get(k) if E else None
                eur_x = eur_lo if buy else eur_hi
                if el is None or eur_x is None:
                    out["marks"].append("No EUR/USD data for the SMT check")
                    continue
                broke = eur_x < el if buy else eur_x > el
                if broke:
                    out["marks"].append(f"No SMT: EUR/USD also took its {NAMES[k]}")
                    continue
                smt_txt = f"SMT: EUR/USD {'low' if buy else 'high'} {eur_x:.5f} did not take its {NAMES[k]} {el:.5f}"
            leg_end = min(c[j].low for j in range(s["extIdx"], i + 1)) if not buy else max(c[j].high for j in range(s["extIdx"], i + 1))
            leg = abs(s["ext"] - leg_end)
            a_i = at[rel(i)]
            if a_i is None or leg <= p["legAtr"] * a_i:
                out["marks"].append(f"Leg {leg / pip:.1f} pips ≤ {p['legAtr']} × ATR")
                continue
            ob = next((j for j in range(s["extIdx"], max(lo, s["extIdx"] - p["obLookback"]) - 1, -1)
                       if (c[j].close < c[j].open if buy else c[j].close > c[j].open)), None)
            if ob is None:
                out["marks"].append("No order block before the leg")
                continue
            o = c[ob]
            entry = o.open if p["obEntry"] == "open" else (o.open + o.close) / 2
            if (entry >= x.close) if buy else (entry <= x.close):
                out["marks"].append("Order block already passed by the close")
                continue
            sl = s["ext"] - p["slBufferPips"] * pip if buy else s["ext"] + p["slBufferPips"] * pip
            risk = abs(entry - sl)
            widened = False
            if risk < p["minSlPips"] * pip:
                risk, widened = p["minSlPips"] * pip, True
                sl = entry - risk if buy else entry + risk
            if risk > p["maxSlPips"] * pip + 1e-12:
                out["marks"].append(f"Stop {risk / pip:.1f} pips > {p['maxSlPips']}")
                continue
            sign = 1 if buy else -1
            tp = entry + sign * p["targetR"] * risk
            be = entry + sign * p["breakevenR"] * risk
            out["setups"].append({
                "index": i, "buy": buy, "entryType": "LIMIT", "entry": entry, "sl": sl, "tp1": be, "tp2": tp, "tp3": tp,
                "partials": [0, 0, 1], "breakeven": True, "expiryBars": p["expiryBars"], "cancelLevel": tp,
                "why": [f"London Judas: {NAMES[k]} {lvl:.5f} taken by {pen:.1f} pips ({p['minPenPips']}–{p['maxPenPips']})",
                        smt_txt,
                        f"MSS: M5 close {x.close:.5f} back inside and {'above the swing high' if buy else 'below the swing low'} {s['refPrice']:.5f}",
                        f"Leg {leg / pip:.1f} pips > {p['legAtr']} × ATR(14) ({a_i / pip:.1f} pips)",
                        f"Order block {'down' if buy else 'up'} candle at {hm(london(o.time)[1])}: limit at its {'open' if p['obEntry'] == 'open' else '50 %'}",
                        f"SL {risk / pip:.1f} pips{' (widened to the 15-pip minimum)' if widened else ''} · TP {p['targetR']:g}R · BE at {p['breakevenR']:g}R"],
                "zone": {"top": max(o.open, o.close), "bottom": min(o.open, o.close), "time": o.time, "label": "OB"},
                "level": {"name": NAMES[k], "price": lvl},
            })
            done = True
    if L:
        txt = ", ".join(f"{NAMES[k]} {v:.5f}" for k, v in L.items())
        out["detail"] = f"Key levels {txt}: waiting for a 5–30 pip fakeout {hm(w0)}–{hm(w1)} London with EUR/USD failing (SMT)"
    return out


def scan(c: list[Candle], ctx: dict) -> dict:
    p, pip, memo = ctx["params"], ctx["pip"], ctx["memo"]
    peer_c: Optional[list[Candle]] = ctx.get("peer")
    days = by_day(c)
    pdays = {d: (a, b) for d, a, b in by_day(peer_c)} if peer_c is not None else {}
    pkeys = list(pdays)
    setups: list[dict] = []
    last = None
    for n, (d, a, b) in enumerate(days):
        if london(c[a].time)[2] in (0, 6):  # weekend stubs are not trading days
            continue
        prev_i = next((m for m in range(n - 1, -1, -1) if london(c[days[m][1]].time)[2] not in (0, 6)), None)
        prev = (days[prev_i][1], days[prev_i][2]) if prev_i is not None else None
        peer = None
        psig = None
        if peer_c is not None:
            pa = pdays.get(d)
            pprev = None
            if pa:
                j = pkeys.index(d)
                pp = next((pkeys[m] for m in range(j - 1, -1, -1) if london(peer_c[pdays[pkeys[m]][0]].time)[2] not in (0, 6)), None)
                pprev = pdays[pp] if pp else None
            peer = {"c": peer_c, "a": pa[0] if pa else None, "b": pa[1] if pa else None, "prev": pprev}
            psig = (fingerprint(peer_c, *pa) if pa else None, fingerprint(peer_c, *pprev) if pprev else None)
        sig = (fingerprint(c, a, b), prev and fingerprint(c, *prev), peer_c is not None, psig)
        hit = memo.get(d)
        if hit is None or hit[0] != sig:
            res = _day(c, prev, a, b, peer, p, pip)
            res = {**res, "setups": [{**s, "time": c[s["index"]].time} for s in res["setups"]]}
            memo[d] = (sig, res)
        else:
            res = hit[1]
        setups.extend(res["setups"])
        last = (res, a)
    if len(memo) > 400:
        for k in sorted(memo)[:-300]:
            del memo[k]
    drawings, status = [], "Not enough history"
    if last:
        res, a = last
        status = res["detail"] + (f" · {res['marks'][-1]}" if res["marks"] else "")
        for k, v in res["levels"].items():
            drawings.append({"kind": "hline", "t1": c[a].time, "p1": v, "text": NAMES[k], "color": "liquidity" if k in ("AH", "AL") else "level", "style": "dotted"})
    return {"setups": setups, "status": status, "drawings": drawings}
