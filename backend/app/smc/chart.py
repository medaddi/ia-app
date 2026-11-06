"""
What a pair's team draws on its chart: its own read of the market, from the same engine objects the strategies use
(engine.Structure, engine.fvgs, engine._h1_pois on CLOSED candles). Every object carries the times of the candles it
starts and ends on, so the chart anchors it there and nothing slides between two refreshes.

  boxes     the nearest valid H1 order block on each side (FVG after it, IDM in front, not closed through), labelled
            "Bullish / Bearish Order Block" · the nearest unfilled H1 FVG on each side · the setup's trade (TP and SL areas)
  segments  each BOS / CHoCH from the broken swing to the candle that closed through it · the OB's IDM · the swept level
            of each liquidity sweep · the H1 equilibrium (50 %) · PDH / PDL · the Asian high / low
  labels    "Liquidity Sweep" at the wick tip of each sweep
"""

from . import engine

DAY, H1S, M5S = engine.DAY, engine.H1S, engine.M5S
KEEP_BREAKS, KEEP_SWEEPS = 4, 2


def _ob_alive(c, p: dict) -> bool:
    """An OB is still valid when no candle since its break closed through it (Definitions: unmitigated)."""
    lo, hi = p["zone"]
    for x in c[p["break"] + 1:]:
        if (p["dir"] > 0 and x.close < lo) or (p["dir"] < 0 and x.close > hi):
            return False
    return True


def _fvg_open(c, k: int, g: tuple) -> bool:
    """An H1 FVG is open while no later candle has traded through it entirely."""
    d, bot, top = g
    for x in c[k + 1:]:
        if (d > 0 and x.low <= bot) or (d < 0 and x.high >= top):
            return False
    return True


def analysis(m5, h1v, decimals: int, now: int, setup: dict | None = None) -> dict:
    c, st = h1v.c, h1v.st
    i = len(c) - 1
    r = lambda v: round(v, decimals)  # noqa: E731
    price = m5[-1].close if m5 else c[-1].close
    end = max(c[-1].time + H1S, m5[-1].time + M5S if m5 else 0)  # the right edge: the last closed candle
    boxes, segments, labels = [], [], []

    # structure: each BOS / CHoCH from the swing it broke to the candle that closed through it; each sweep
    breaks, sweeps = [], []
    for k in range(max(0, i - 200), i + 1):
        for e in st.ev[k]:
            (sweeps if e[0] == "SWEEP" else breaks).append((k, e))
    for k, e in breaks[-KEEP_BREAKS:]:
        segments.append({"from": c[e[3]].time, "to": c[k].time + H1S, "price": r(e[2]), "kind": "bos" if e[0] == "BOS" else "choch",
                         "dir": e[1], "label": "BOS" if e[0] == "BOS" else "CHoCH"})
    for k, e in sweeps[-KEEP_SWEEPS:]:
        tip = c[k].high if e[1] > 0 else c[k].low
        segments.append({"from": c[e[3]].time, "to": c[k].time + H1S, "price": r(e[2]), "kind": "sweep", "dir": e[1], "label": ""})
        labels.append({"time": c[k].time, "price": r(tip), "text": "Liquidity Sweep", "above": e[1] > 0, "kind": "sweep"})

    # the nearest valid order block on each side, with its IDM
    pois = [p for p in engine._h1_pois(h1v, "A") if p["break"] >= i - 300 and p["from"] <= i and _ob_alive(c, p)]
    for d in (1, -1):
        side = [p for p in pois if p["dir"] == d and ((d > 0 and p["zone"][1] <= price) or (d < 0 and p["zone"][0] >= price))]
        if not side:
            continue
        p = min(side, key=lambda p: abs((p["zone"][1] if d > 0 else p["zone"][0]) - price))
        boxes.append({"from": c[p["ob"]].time, "to": end, "top": r(p["zone"][1]), "bottom": r(p["zone"][0]), "kind": "ob", "dir": d,
                      "label": "Bullish Order Block" if d > 0 else "Bearish Order Block"})
        swept = next((k for k in range(p["idm"] + 1, i + 1) if (d > 0 and c[k].low < p["idmLevel"]) or (d < 0 and c[k].high > p["idmLevel"])), None)
        segments.append({"from": c[p["idm"]].time, "to": c[swept].time + H1S if swept is not None else end, "price": r(p["idmLevel"]), "kind": "idm",
                         "dir": d, "label": "IDM" + (" ✓" if swept is not None else "")})
    # the nearest unfilled FVG on each side
    for d in (1, -1):
        gaps = [(k, g) for k, g in enumerate(h1v.fv) if g and g[0] == d and k >= i - 300 and _fvg_open(c, k, g)
                and ((d > 0 and g[2] <= price) or (d < 0 and g[1] >= price))]
        if gaps:
            k, g = min(gaps, key=lambda kg: abs((kg[1][2] if d > 0 else kg[1][1]) - price))
            boxes.append({"from": c[k - 2].time, "to": end, "top": r(g[2]), "bottom": r(g[1]), "kind": "fvg", "dir": d, "label": "FVG"})

    # the dealing range's equilibrium, the previous day, the Asian range
    rng = h1v.range_mid(i)
    if rng:
        t0 = c[min(st.last_sh[i][1], st.last_sl[i][1])].time
        segments.append({"from": t0, "to": end, "price": r(rng[1]), "kind": "eq", "dir": 0, "label": "EQ 50 %"})
    if m5:
        day = m5[-1].time // DAY
        prev = [x for x in m5 if x.time // DAY == day - 1] or [x for x in m5 if x.time // DAY < day][-288:]
        if prev:
            hi_x = max(prev, key=lambda x: x.high)
            lo_x = min(prev, key=lambda x: x.low)
            segments += [{"from": hi_x.time, "to": end, "price": r(hi_x.high), "kind": "liquidity", "dir": 1, "label": "PDH"},
                         {"from": lo_x.time, "to": end, "price": r(lo_x.low), "kind": "liquidity", "dir": -1, "label": "PDL"}]
        a0, a1 = engine.SESSIONS["asia"]
        asia = [x for x in m5 if x.time // DAY == day and a0 * H1S <= x.time % DAY < a1 * H1S]
        if asia and m5[-1].time % DAY >= a1 * H1S:  # known once the session is over
            segments += [{"from": asia[0].time, "to": end, "price": r(max(x.high for x in asia)), "kind": "session", "dir": 1, "label": "Asian high"},
                         {"from": asia[0].time, "to": end, "price": r(min(x.low for x in asia)), "kind": "session", "dir": -1, "label": "Asian low"}]

    # the setup that passed the 7 questions: its trade, as TP and SL areas from the signal on
    trade = None
    if setup:
        t0 = setup["time"]
        t1 = max(setup["validUntil"] + 4 * H1S, end)
        trade = {"from": t0, "to": t1, "entry": setup["entry"], "sl": setup["sl"], "tp": setup["tp"], "dir": 1 if setup["direction"] == "BUY" else -1,
                 "label": f"{setup['strategy']} {setup['direction']} · 1:{setup['rr']}"}
    return {"trend": {1: "BULLISH", -1: "BEARISH"}.get(st.trend[i], "UNDEFINED"), "premium": bool(rng and price > rng[1]),
            "boxes": boxes, "segments": segments, "labels": labels, "trade": trade}
