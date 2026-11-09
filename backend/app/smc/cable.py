"""
GBP/USD ("Cable") — the user's spec "gbp_usd_multi_agent_quantitative_strategy_claude_prompt.md" (2026-11-09), applied
to the letter. It replaces everything earlier for GBP/USD.

Strategy: "London Judas Swing & Unicorn Breaker-FVG Strategy".
  Scenario A  London open Judas swing + Unicorn (breaker block ∩ FVG) reversal, 06:45-10:00 UTC
  Scenario B  NY trend continuation after the London expansion, 12:30-15:30 UTC
  Scenario C  full ADR exhaustion reversal at the NY option cut / London close, 14:30-16:15 UTC (risk 0.5 %)
  Scenario D  a wide Asian blowout (> 55 pips) or UK CPI / BOE MPC within ±30 min: NO_TRADE

Section 3 math: the Asian box 00:00-06:30 UTC (valid when 15 <= W <= 48 pips and W <= 0.42 ADR 14); the Judas
penetration 0.20-0.85 ATR 14 H1 in 06:45-09:15; the Unicorn = the breaker block ∩ the FVG of the impulse that broke
SH_pre; TP_ADR = L_Judas + 0.75 ADR 14 (bull) / H_Judas - 0.75 ADR 14 (bear). The Risk Manager: SL 8-32 pips, 1 % (A, B)
or 0.5 % (C), RR >= 2.60 to TP2. The Devil: a hard veto at failure probability >= 65 %. The Lead: never a trade under a
Devil or Risk veto. Where the spec leaves something open the code says "CHOICE".
"""

from bisect import bisect_left
from datetime import datetime, timezone
from typing import Optional

from .gold import G, avg_body, badge, hm, order_block, structure
from .playbook import DAY, H1S, M5S, M15S, Daily, _make, body, hilo, m5_index_at_close, resample, run, span

PIP = 0.0001
STRATEGY_NAME = "London Judas Swing & Unicorn Breaker-FVG Strategy"
NAMES = {"A": "Scenario A · London Judas swing + Unicorn", "B": "Scenario B · NY continuation after the London expansion",
         "C": "Scenario C · ADR exhaustion reversal at the London close"}
SCEN = {"A": "SCENARIO_A_JUDAS_UNICORN", "B": "SCENARIO_B_NY_CONTINUATION", "C": "SCENARIO_C_ADR_EXHAUSTION"}
BASELINE = {"A": {"trades": 346, "winRate": 60.4, "avgWin": 2.85, "expectancyR": 1.32, "pf": 3.18, "mdd": -4.6},
            "B": {"trades": 275, "winRate": 55.6, "avgWin": 2.40, "expectancyR": 0.89, "pf": 2.41, "mdd": -6.2},
            "C": {"trades": 142, "winRate": 52.1, "avgWin": 2.10, "expectancyR": 0.62, "pf": 1.94, "mdd": -6.9}}
RISK = {"A": 1.0, "B": 1.0, "C": 0.5}
UK_LOCK = {("GBP", "CPI y/y"), ("GBP", "Official Bank Rate"), ("GBP", "Monetary Policy Summary"), ("GBP", "MPC Official Bank Rate Votes"),
           ("GBP", "BOE Monetary Policy Report")}


def uk_lock(events) -> list[int]:
    """Scenario D's lockout: UK CPI and the Bank of England MPC announcement."""
    return sorted({int(e["time"]) for e in (events or []) if (e.get("currency"), e.get("title")) in UK_LOCK})


def asia_box(g: G, D: int):
    """[L_Asia, H_Asia] over 00:00-06:30 UTC and W_Asia in pips."""
    hl = hilo(span(g.m5, g.t5, D, D + 6 * H1S + 1800))
    return (hl[1], hl[0], (hl[0] - hl[1]) / PIP) if hl else None


def _fvg_in(c, a: int, b: int, d: int) -> Optional[tuple[float, float, int]]:
    """The 3-candle FVG [H_{t-2}, L_t] (bull) / [H_t, L_{t-2}] (bear) whose 3rd candle t is in [a, b]: the last one."""
    out = None
    for t in range(max(a, 2), min(b + 1, len(c))):
        if d > 0 and c[t].low > c[t - 2].high:
            out = (c[t - 2].high, c[t].low, t)
        if d < 0 and c[t].high < c[t - 2].low:
            out = (c[t].high, c[t - 2].low, t)
    return out


def _risk(entry: float, sl: float, d: int, tps: list[tuple[str, float]], need: float):
    """The Risk Manager: SL 8.0-32.0 pips (under 8: widened to 8, CHOICE; over 32: rejected); TP2 the nearest target at
    `need` R or more. Returns (sl, (tp2, name)) or (None, why)."""
    dist = abs(entry - sl) / PIP
    if dist < 8.0:
        sl = entry - d * 8.0 * PIP
    elif dist > 32.0:
        return None, f"SL {dist:.1f} pips > 32.0"
    risk = abs(entry - sl)
    good = sorted([(n, p) for n, p in tps if p is not None and (p - entry) * d >= need * risk], key=lambda t: abs(t[1] - entry))
    if not good:
        return None, f"no TP2 at {need:g} R or more"
    return sl, (good[0][1], good[0][0])


def _days(m5) -> list[int]:
    return sorted({x.time - x.time % DAY for x in m5 if datetime.fromtimestamp(x.time, timezone.utc).weekday() < 5})


# ---------------------------------------------------------------- Scenario A · London Judas + Unicorn
def scenario_a(g: G, cost: float, out: list, watch: list) -> None:
    """The Asian box valid (15-48 pips, <= 0.42 ADR 14; > 55 pips is Scenario D). 06:45-09:15 UTC: price takes one side by
    0.20-0.85 ATR 14 H1 into an H1 POI (CHOICE: the H1 discount < 50 % of the dealing range for a long, or the PDL), then a
    displacement candle (body >= 1.35 x the 20-candle average body, CHOICE: the gold spec's measure) closes back inside the
    box AND beyond SH_pre (the last swing high before the final leg down to L_Judas), on M15 or M5. The breaker block = the
    last bullish candle before that leg [L_bb, H_bb]; the impulse's FVG [H_{t-2}, L_t]; Z_Unicorn = their intersection
    (else a clean M15 OB + FVG in the discount). Entry: a limit at Z's proximal edge until 10:00 UTC. SL L_Judas - 3 pips
    (the breaker's distal edge - 0.25 ATR M15 when the Judas wick is over 35 pips). TP1 the opposite box edge (half, SL to
    breakeven); TP2 TP_ADR = L_Judas + 0.75 ADR 14 or PDH, at >= 3.0 R. Risk 1 %. Closed at 20:00 UTC (CHOICE)."""
    m5 = g.m5
    for D in _days(m5):
        box = asia_box(g, D)
        adr = g.daily.adr(D, 14)
        if not box or not adr:
            continue
        la, ha, w = box
        if not (15 <= w <= 48 and w * PIP <= 0.42 * adr):
            continue
        i1 = g.i1(D + 6 * H1S + 2700)
        a1 = g.at1[i1] if i1 >= 0 else None
        pd = hilo(span(m5, g.t5, D - DAY, D)) or hilo(span(m5, g.t5, D - 3 * DAY, D - 2 * DAY + 1))
        if not a1:
            continue
        w0, w1 = D + 6 * H1S + 2700, D + 9 * H1S + 900
        ks, ke = bisect_left(g.t5, w0), bisect_left(g.t5, w1)
        for d in (1, -1):
            lvl = la if d > 0 else ha
            k_sw = next((k for k in range(ks, ke) if ((m5[k].low < lvl) if d > 0 else (m5[k].high > lvl))), None)
            if k_sw is None:
                continue
            ext_k, done = k_sw, False
            for k in range(k_sw, min(len(m5), bisect_left(g.t5, D + 10 * H1S))):
                if m5[k].time < w1 and ((d > 0 and m5[k].low < m5[ext_k].low) or (d < 0 and m5[k].high > m5[ext_k].high)):
                    ext_k = k
                ext = m5[ext_k].low if d > 0 else m5[ext_k].high
                dep = (lvl - ext) if d > 0 else (ext - lvl)
                if dep > 0.85 * a1:
                    break  # deeper than 0.85 ATR H1: a breakout, not a Judas
                if dep < 0.20 * a1:
                    continue
                x = m5[k]
                back = (x.close > lvl) if d > 0 else (x.close < lvl)
                ab = avg_body(m5, k + 1)
                disp = ab and body(x) >= 1.35 * ab and (x.close - x.open) * d > 0
                hi_f, lo_f = g.f5
                ref = next((q for q in range(ext_k - 1, max(ext_k - 60, 0), -1) if (hi_f[q] if d > 0 else lo_f[q])), None)
                if ref is None or k < ref + 2:
                    continue
                pre = m5[ref].high if d > 0 else m5[ref].low
                if not (back and disp and ((x.close > pre) if d > 0 else (x.close < pre))):
                    continue
                dr = g.dealing(x.time + M5S)
                poi = (dr is not None and ((ext <= dr[2]) if d > 0 else (ext >= dr[2]))) or (pd is not None and ((ext <= pd[1]) if d > 0 else (ext >= pd[0])))
                bb = next(((m5[q].low, m5[q].high, q) for q in range(ext_k - 1, max(ref - 1, 0), -1) if ((m5[q].close > m5[q].open) if d > 0 else (m5[q].close < m5[q].open))), None)
                fvg = _fvg_in(m5, ext_k + 2, min(k + 2, len(m5) - 1), d)
                uni = None
                if bb and fvg:
                    lo, hi = max(bb[0], fvg[0]), min(bb[1], fvg[1])
                    if lo < hi:
                        uni = (lo, hi)
                zone, kind = uni, "Unicorn (breaker ∩ FVG)"
                if not zone and fvg:
                    ob = order_block(m5, fvg[2], d)
                    zone, kind = ((fvg[0], fvg[1]), "M15/M5 OB + FVG") if ob else (None, "")
                steps = [(f"Asian box {w:.0f} pips (15-48, <= 0.42 ADR)", True, f"{la:.5f} - {ha:.5f}"),
                         (f"Judas sweep of the Asian {'low' if d > 0 else 'high'}: {dep / a1:.2f} ATR H1 (0.20-0.85)", True, f"{ext:.5f}"),
                         ("Into an H1 POI (discount / PDL)" if d > 0 else "Into an H1 POI (premium / PDH)", poi, ""),
                         ("Displacement back inside the box, beyond SH_pre" if d > 0 else "Displacement back inside the box, beyond SL_pre", True, f"{pre:.5f}"),
                         (f"Entry zone: {kind or 'none'}", zone is not None, f"{zone[0]:.5f} - {zone[1]:.5f}" if zone else "")]
                done = True
                if not (poi and zone):
                    watch.append({"sid": "A", "time": x.time + M5S, "dir": d, "steps": steps})
                    break
                entry = zone[1] if d > 0 else zone[0]
                wick = abs(lvl - ext) / PIP
                j15 = g.j15(x.time + M5S)
                sl = (bb[0] - 0.25 * (g.at15[j15] or 0) if d > 0 else bb[1] + 0.25 * (g.at15[j15] or 0)) if (wick > 35 and bb) else ext - d * 3 * PIP
                tp_adr = ext + d * 0.75 * adr
                sl2, tp2 = _risk(entry, sl, d, [("TP_ADR 75 %", tp_adr), ("PD" + ("H" if d > 0 else "L"), (pd[0] if d > 0 else pd[1]) if pd else None)], 3.0)
                if sl2 is None:
                    watch.append({"sid": "A", "time": x.time + M5S, "dir": d, "steps": steps + [("Risk Manager", False, tp2)]})
                    break
                kz = max(k, fvg[2] if fvg else k)
                k0 = kz if kz < len(m5) else k
                tp1 = ha if d > 0 else la
                s = _make("GBPUSD", "A", d, m5, k0, entry, sl2, tp1, tp2[0], 0.5, False, max(1, (D + 10 * H1S - (m5[k0].time + M5S)) // M5S), D + 20 * H1S,
                          steps, {"levels": {"Asia high": ha, "Asia low": la, **({"PDH": pd[0], "PDL": pd[1]} if pd else {})}, "fvg": (zone[0], zone[1], m5[k0].time),
                                  "ob": (bb[1], bb[0], m5[bb[2]].time) if bb else None, "sweep": (ext, m5[ext_k].time), "mss": (pre, x.time),
                                  "window": (w0, w1), "tpAdr": tp_adr}, cost, zone=zone)
                if s:
                    s.update(riskPct=RISK["A"], tp2Name=tp2[1], judasPips=wick, unicorn=uni is not None, scenario="A")
                    out.append(s)
                break
            if not done:
                watch.append({"sid": "A", "time": m5[k_sw].time + M5S, "dir": d, "steps": [
                    (f"Asian box {w:.0f} pips", True, ""), (f"Asian {'low' if d > 0 else 'high'} taken", True, f"{lvl:.5f}"),
                    ("Judas depth 0.20-0.85 ATR H1 + displacement beyond SH_pre", False, "waiting")]})


# ---------------------------------------------------------------- Scenario B · NY continuation
def scenario_b(g: G, cost: float, out: list, watch: list) -> None:
    """London (07:00-12:00 UTC, CHOICE) broke out with an H1 BOS and the day used 45-68 % of ADR 14 by 12:00; in 12:00-13:45
    an M15 pullback sweeps an internal London swing (an M15 swing formed in London) into the 50-70.5 % retracement of the
    London leg; then an M5 / M15 MSS + FVG: a limit at the FVG's proximal edge until 15:30. SL the pullback extreme - 3
    pips (CHOICE, as in A); TP1 the London high (half, breakeven), TP2 the remaining ADR expansion: the day's low + 0.85
    ADR 14 (CHOICE: from the day's extreme), at RR >= 2.60. Risk 1 %."""
    m5, m15 = g.m5, g.m15
    for D in _days(m5):
        adr = g.daily.adr(D, 14)
        lon = hilo(span(m5, g.t5, D + 7 * H1S, D + 12 * H1S))
        day = hilo(span(m5, g.t5, D, D + 12 * H1S))
        if not adr or not lon or not day:
            continue
        used = (day[0] - day[1]) / adr
        if not (0.45 <= used <= 0.68):
            continue
        i_a, i_b = g.i1(D + 8 * H1S), g.i1(D + 12 * H1S)
        evs = [g.s1["event"][q] for q in range(max(i_a, 1), i_b + 1) if g.s1["event"][q] != g.s1["event"][q - 1]]
        last = evs[-1] if evs else None
        if not last or last[0] != "BOS":
            continue
        d = last[1]
        k_lh = max(range(bisect_left(g.t5, D + 7 * H1S), bisect_left(g.t5, D + 12 * H1S)), key=lambda q: m5[q].high if d > 0 else -m5[q].low)
        leg_lo = hilo(span(m5, g.t5, D + 7 * H1S, m5[k_lh].time + 1))
        lo, hi = (leg_lo[1], lon[0]) if d > 0 else (lon[1], leg_lo[0])
        z50, z705 = (hi - 0.5 * (hi - lo), hi - 0.705 * (hi - lo)) if d > 0 else (lo + 0.5 * (hi - lo), lo + 0.705 * (hi - lo))
        zl, zh = min(z50, z705), max(z50, z705)
        hi_f, lo_f = g.f15
        internal = [m15[q].low if d > 0 else m15[q].high for q in range(g.j15(D + 7 * H1S) + 1, g.j15(D + 12 * H1S)) if (lo_f[q] if d > 0 else hi_f[q])]
        j0, j1 = g.j15(D + 12 * H1S) + 1, g.j15(D + 13 * H1S + 2700) + 1
        for j in range(max(j0, 2), min(j1, len(m15))):
            y = m15[j]
            ext = y.low if d > 0 else y.high
            took = any((ext < v) if d > 0 else (ext > v) for v in internal)
            if not (took and zl <= ext <= zh):
                continue
            k5 = bisect_left(g.t5, y.time)
            found = None
            for k in range(k5, min(k5 + 24, len(m5))):
                if m5[k].time >= D + 15 * H1S + 1800:
                    break
                ref = next((q for q in range(k - 2, max(k - 40, 0), -1) if (g.f5[0][q] if d > 0 else g.f5[1][q])), None)
                if ref is None:
                    continue
                if (m5[k].close > m5[ref].high) if d > 0 else (m5[k].close < m5[ref].low):
                    fvg = _fvg_in(m5, k - 1, min(k + 2, len(m5) - 1), d)
                    if fvg:
                        found = (k, fvg, m5[ref].high if d > 0 else m5[ref].low)
                    break
            steps = [(f"London broke out with an H1 BOS, the day used {used * 100:.0f} % of ADR (45-68 %)", True, ""),
                     ("NY pullback swept an internal London swing", True, f"{ext:.5f}"), ("Into the 50-70.5 % of the London leg", True, f"{zl:.5f} - {zh:.5f}"),
                     ("M5 MSS + FVG", found is not None, "")]
            if not found:
                watch.append({"sid": "B", "time": y.time + M15S, "dir": d, "steps": steps})
                break
            k, fvg, mss = found
            entry = fvg[1] if d > 0 else fvg[0]
            sl = ext - d * 3 * PIP
            tp_rem = (day[1] + 0.85 * adr) if d > 0 else (day[0] - 0.85 * adr)
            sl2, tp2 = _risk(entry, sl, d, [("remaining ADR (0.85)", tp_rem)], 2.6)
            if sl2 is None:
                watch.append({"sid": "B", "time": m5[k].time + M5S, "dir": d, "steps": steps + [("Risk Manager", False, tp2)]})
                break
            k0 = min(fvg[2], len(m5) - 1)
            k0 = max(k0, k)
            s = _make("GBPUSD", "B", d, m5, k0, entry, sl2, lon[0] if d > 0 else lon[1], tp2[0], 0.5, False,
                      max(1, (D + 15 * H1S + 1800 - (m5[k0].time + M5S)) // M5S), D + 20 * H1S, steps,
                      {"levels": {"London high": lon[0], "London low": lon[1]}, "fvg": (fvg[0], fvg[1], m5[k0].time), "sweep": (ext, y.time), "mss": (mss, m5[k].time)},
                      cost, zone=(fvg[0], fvg[1]))
            if s:
                s.update(riskPct=RISK["B"], tp2Name=tp2[1], scenario="B")
                out.append(s)
            break


# ---------------------------------------------------------------- Scenario C · ADR exhaustion reversal
def scenario_c(g: G, cost: float, out: list, watch: list) -> None:
    """The day already spans >= 105 % of ADR 14 in one direction and, in 15:00-16:00 UTC, sweeps a major H4 / D1 swing
    level (CHOICE: the last confirmed H4 swing, the PDH / PDL); then an M5 CHoCH + FVG (in 14:30-16:15): a limit at the
    FVG's proximal edge; target the 38.2 % retracement of the day; SL the sweep extreme +/- 3 pips (CHOICE); risk 0.5 %;
    RR >= 2.60 (the Risk Manager)."""
    m5 = g.m5
    for D in _days(m5):
        adr = g.daily.adr(D, 14)
        pd = hilo(span(m5, g.t5, D - DAY, D)) or hilo(span(m5, g.t5, D - 3 * DAY, D - 2 * DAY + 1))
        if not adr:
            continue
        ks, ke = bisect_left(g.t5, D + 15 * H1S), bisect_left(g.t5, D + 16 * H1S)
        k0d = bisect_left(g.t5, D)
        if ke - ks < 3 or k0d >= len(m5):
            continue
        for k in range(ks, ke):
            day = hilo(m5[k0d:k + 1])
            if not day or (day[0] - day[1]) < 1.05 * adr:
                continue
            open_ = m5[k0d].open
            d = -1 if m5[k].close > open_ else 1  # the reversal of the day's direction
            ext = m5[k].high if d < 0 else m5[k].low
            if ext != (day[0] if d < 0 else day[1]):
                continue
            i4 = g.i4(m5[k].time + M5S)
            h4lvl = g.s4["sh"][i4][0] if d < 0 and g.s4["sh"][i4] else (g.s4["sl"][i4][0] if d > 0 and g.s4["sl"][i4] else None)
            walls = [v for v in (h4lvl, (pd[0] if d < 0 else pd[1]) if pd else None) if v is not None and ((ext > v) if d < 0 else (ext < v))]
            if not walls:
                continue
            hi_f, lo_f = g.f5
            ref = next((q for q in range(k - 1, max(k - 40, 0), -1) if (lo_f[q] if d < 0 else hi_f[q])), None)
            found = None
            for q in range(k + 1, min(k + 16, len(m5))):
                if m5[q].time >= D + 16 * H1S + 900 or ref is None:
                    break
                if (m5[q].close < m5[ref].low) if d < 0 else (m5[q].close > m5[ref].high):
                    fvg = _fvg_in(m5, k + 2, min(q + 2, len(m5) - 1), d)
                    if fvg:
                        found = (q, fvg)
                    break
            steps = [(f"Day {100 * (day[0] - day[1]) / adr:.0f} % of ADR (>= 105 %)", True, ""), ("Sweep of a major H4 / D1 level, 15:00-16:00", True, f"{ext:.5f}"),
                     ("M5 CHoCH + FVG", found is not None, "")]
            if not found:
                watch.append({"sid": "C", "time": m5[k].time + M5S, "dir": d, "steps": steps})
                break
            q, fvg = found
            entry = fvg[0] if d < 0 else fvg[1]
            r38 = (day[0] - 0.382 * (day[0] - day[1])) if d < 0 else (day[1] + 0.382 * (day[0] - day[1]))
            sl2, tp2 = _risk(entry, ext - d * 3 * PIP, d, [("38.2 % retracement", r38)], 2.6)
            if sl2 is None:
                watch.append({"sid": "C", "time": m5[q].time + M5S, "dir": d, "steps": steps + [("Risk Manager", False, tp2)]})
                break
            k0 = max(q, fvg[2])
            s = _make("GBPUSD", "C", d, m5, min(k0, len(m5) - 1), entry, sl2, None, tp2[0], 1.0, False, max(1, (D + 16 * H1S + 900 - (m5[k0].time + M5S)) // M5S),
                      D + 20 * H1S, steps, {"fvg": (fvg[0], fvg[1], m5[k0].time), "sweep": (ext, m5[k].time)}, cost, zone=(fvg[0], fvg[1]))
            if s:
                s.update(riskPct=RISK["C"], tp2Name=tp2[1], scenario="C")
                out.append(s)
            break


# ---------------------------------------------------------------- the Devil and the pipeline
def devil(g: G, s: dict, eur_m5) -> tuple[float, list[str]]:
    """Failure probability (CHOICE: the weights): the Asian box too wide (> 48 pips or > 42 % of ADR) +40 · two
    consecutive M15 full-body closes outside the box without rejecting (a true breakout) +45 · EUR/GBP cross-flow against
    the GBP bias (EUR/GBP = EUR/USD / GBP/USD over the last 4 hours, a move over 0.15 %, CHOICE) +25. Hard veto >= 65 %."""
    t, d = s["time"], s["dir"]
    D = t - t % DAY
    p, worries = 0.0, []
    box = asia_box(g, D)
    adr = g.daily.adr(D, 14)
    if box and adr and (box[2] > 48 or box[2] * PIP > 0.42 * adr):
        p += 40
        worries.append(f"Asian box {box[2]:.0f}p too wide: a real trend, not a Judas")
    if box and s["sid"] == "A":
        j0, j1 = g.j15(D + 6 * H1S + 2700) + 1, g.j15(t) + 1
        run_ = 0
        for j in range(j0, j1):
            y = g.m15[j]
            outside = (y.close < box[0] and y.open < box[0]) if d > 0 else (y.close > box[1] and y.open > box[1])
            full = (y.high - y.low) > 0 and body(y) / (y.high - y.low) >= 0.6
            run_ = run_ + 1 if (outside and full) else 0
            if run_ >= 2:
                p += 45
                worries.append("two M15 full-body closes outside the box: a true breakout")
                break
    if eur_m5:
        te = {x.time: x.close for x in eur_m5}
        k = m5_index_at_close(g.t5, t)
        if k is not None and k > 48:
            a, b = g.m5[k - 48], g.m5[k]
            if a.time in te and b.time in te:
                eg0, eg1 = te[a.time] / a.close, te[b.time] / b.close
                ch = (eg1 / eg0 - 1) * 100
                if (d > 0 and ch > 0.15) or (d < 0 and ch < -0.15):
                    p += 25
                    worries.append(f"EUR/GBP {'up' if ch > 0 else 'down'} {abs(ch):.2f} % against the GBP {'long' if d > 0 else 'short'}")
    return min(p, 100.0), worries


def scan(m5, h1, cost: float, news_events=None, d1=None, eur_m5=None) -> tuple[list, list]:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    g = G(m5, h1, daily)
    out, watch = [], []
    for f in (scenario_a, scenario_b, scenario_c):
        f(g, cost, out, watch)
    out.sort(key=lambda x: x["time"])
    seen = set()
    out = [x for x in out if not ((x["sid"], x["time"], x["dir"]) in seen or seen.add((x["sid"], x["time"], x["dir"])))]
    lock = uk_lock(news_events) if news_events is not None else []
    for s in out:
        t = s["time"]
        near = [n for n in lock if abs(n - t) <= 30 * 60]
        if lock and not s["market"]:
            s["result"] = run(m5, s["index"], s["dir"], s["entry"], s["sl"], s["tp1"], s["tp"], s["part"], False, s["expiry"], s["holdUntil"], cost,
                              None, lock, None, 0.0, None)
        box = asia_box(g, t - t % DAY)
        wide = box is not None and box[2] > 55
        p, worries = devil(g, s, eur_m5)
        sl_p = abs(s["entry"] - s["sl"]) / PIP
        s["devilP"], s["worries"] = p, worries
        s["checklist"] = [
            (f"1 · {NAMES[s['sid']]}", True, STRATEGY_NAME),
            ("2 · Scenario D: UK CPI / BOE MPC not within ±30 min", not near,
             "not checked (no news history)" if news_events is None else ("news at " + ", ".join(hm(n) for n in near) + " UTC" if near else "clear")),
            ("2b · Scenario D: the Asian box not over 55 pips", not (wide and s["sid"] == "A"), f"{box[2]:.0f} pips" if box else ""),
            (f"3 · Risk Manager: SL 8-32 pips ({sl_p:.1f}), RR to TP2 >= 2.60 ({s['rr']:.2f})", 8.0 - 1e-6 <= sl_p <= 32.0 and s["rr"] >= 2.6, s.get("tp2Name", "")),
            (f"4 · Lot for {s.get('riskPct', 1.0):g} % risk", True, ""),
            (f"5 · Devil's Advocate: failure probability {p:.0f} % (< 65 %)", p < 65, "; ".join(worries) or "no trap found"),
        ]
        s["pass"] = all(ok for _, ok, _ in s["checklist"])
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("6 · One Cable trade at a time", False, "the previous setup is still pending or open"))
            continue
        r = s["result"]
        busy = m5[r["at"]].time + M5S if "at" in r else 1 << 62
    for w in watch:
        w.setdefault("sid", "A")
    return out, sorted(watch, key=lambda w: w["time"])


# ---------------------------------------------------------------- the 7 agents and the JSON contract
UI = {"VALID": "ok", "WAIT": "wait", "WARNING": "warn", "VETO": "veto", "STANDBY": "wait"}
ROLE = {"lead_strategist": ("lead", "Lead Strategist"), "structure_analyst": ("structure", "Structure Analyst"),
        "liquidity_session_analyst": ("liquidity", "Liquidity & Session Analyst"), "entry_specialist": ("entry", "Entry Specialist"),
        "risk_manager": ("risk", "Risk Manager"), "backtest_engineer": ("backtest", "Backtest Engineer"), "devils_advocate": ("devil", "Devil's Advocate")}


def report(m5, h1, now: int, setups: list, watch: list, research: Optional[dict], news_events, d1=None, eur_m5=None) -> dict:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    g = G(m5, h1, daily)
    t = m5[-1].time + M5S
    price = m5[-1].close
    D = t - t % DAY
    i1, i4 = g.i1(t), g.i4(t)
    h1t, h4t = g.s1["trend"][i1], (g.s4["trend"][i4] if i4 >= 0 else 0)
    dr = g.dealing(t)
    adr = daily.adr(D, 14) or 0
    box = asia_box(g, D)
    tod = t % DAY
    sess = ("PRE_ASIA" if tod < 0 else "ASIA" if tod < 6 * H1S + 1800 else "PRE_LONDON" if tod < 6 * H1S + 2700 else
            "FRANKFURT_LONDON_OPEN" if tod < 9 * H1S + 1800 else "LONDON" if tod < 12 * H1S else "NY" if tod < 15 * H1S else
            "LONDON_CLOSE" if tod < 16 * H1S + 900 else "POST_SESSION")
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE")]
    cand = next((s for s in reversed(live) if s["pass"]), live[-1] if live else None)
    w = watch[-1] if watch and watch[-1]["time"] >= now - 3 * H1S else None
    lock = uk_lock(news_events) if news_events is not None else None
    nxt = next((n for n in (lock or []) if n >= now - 30 * 60), None)
    locked = nxt is not None and abs(nxt - now) <= 30 * 60
    # Structure Analyst
    bb_active = bool(cand and cand.get("unicorn"))
    structure_a = {"ui_badge_summary": badge(f"H1 {'bullish' if h1t > 0 else 'bearish' if h1t < 0 else 'neutral'} | " +
                                             (f"Dealing range {dr[0]:.4f} - {dr[1]:.4f}" if dr else "no dealing range")),
                   "status": "VALID" if h1t and h1t == h4t else "WAIT", "h4_bias": {1: "BULLISH", -1: "BEARISH"}.get(h4t, "NEUTRAL"),
                   "h1_bias": {1: "BULLISH", -1: "BEARISH"}.get(h1t, "NEUTRAL"), "breaker_block_active": bb_active,
                   "dealing_range": {"low": dr[0], "high": dr[1], "equilibrium": dr[2]} if dr else None}
    # Liquidity & Session Analyst
    today = hilo(span(m5, g.t5, D, t))
    proj = {"75_up": today[1] + 0.75 * adr, "100_up": today[1] + adr, "75_down": today[0] - 0.75 * adr, "100_down": today[0] - adr} if today and adr else None
    judas = bool(cand and cand["sid"] == "A") or bool(w and w["sid"] == "A" and len(w["steps"]) > 1 and w["steps"][1][1])
    if lock is None:
        lq_s, lq_b = "WARNING", "News feed down: UK CPI / BOE not checked"
    elif locked:
        lq_s, lq_b = "VETO", f"UK CPI / BOE at {hm(nxt)} UTC: lockout"
    elif box and sess not in ("ASIA", "PRE_ASIA"):
        lq_s = "VALID" if judas else "WAIT"
        lq_b = f"Asia Box {box[2]:.0f}p | " + ("Judas sweep detected" if judas else f"ADR14 {adr / PIP:.0f} pips")
    else:
        lq_s, lq_b = "WAIT", f"ADR14: {adr / PIP:.0f} pips | Waiting for Asia Box bounds"
    liquidity_a = {"ui_badge_summary": badge(lq_b), "status": lq_s, "active_session": sess, "adr_14_pips": round(adr / PIP, 1),
                   "asia_box_pips": round(box[2], 1) if box else None, "asia_box_adr_ratio": round(box[2] * PIP / adr, 2) if box and adr else None,
                   "judas_sweep_detected": judas, "adr_projections": proj}
    # Backtest Engineer
    sid = cand["sid"] if cand else (w["sid"] if w else "A")
    meas = (((research or {}).get("strategies") or {}).get(sid) or {}).get("all")
    base = BASELINE[sid]
    if meas and meas.get("trades", 0) >= 30:
        bt_b, bt_s = f"Data READY: measured {meas['winRate']}% WR ({meas['expectancyR']:+.2f}R EV)", "VALID"
    else:
        bt_b, bt_s = f"Data LIMITED: N={(meas or {}).get('trades', 0)} · spec {base['winRate']}% / +{base['expectancyR']}R", "WARNING"
    backtest_a = {"ui_badge_summary": badge(bt_b), "status": bt_s, "historical_win_rate": base["winRate"] / 100, "expected_value_r": base["expectancyR"],
                  "measured": meas, "spec_benchmark": base, "box_rule_holds": bool(box and adr and box[2] * PIP <= 0.42 * adr)}
    # Entry Specialist and Risk Manager
    if cand:
        zl, zh = min(cand["zone"]), max(cand["zone"])
        entry_a = {"ui_badge_summary": badge(f"{'Unicorn' if cand.get('unicorn') else 'OB+FVG'} {zl:.5f}-{zh:.5f} | limit {cand['entry']:.5f}"),
                   "status": "VALID", "entry_valid": True, "unicorn_zone": [zl, zh] if cand.get("unicorn") else None, "fvg_ob_zone": [zl, zh]}
        rk = cand.get("riskPct", 1.0)
        rd = abs(cand["entry"] - cand["sl"]) / PIP
        lots = int(10000 * rk / 100 / (rd * 10) * 100) / 100 if rd else 0
        ok = 8.0 - 1e-6 <= rd <= 32.0 and cand["rr"] >= 2.6
        risk_a = {"ui_badge_summary": badge(f"Risk {rk:g}% | SL {rd:.1f}p | RR 1:{cand['rr']:.1f}" if ok else f"Rejected: SL {rd:.1f}p / RR {cand['rr']:.1f}"),
                  "status": "VALID" if ok else "VETO", "risk_percent": rk, "position_size_lots": lots}
    else:
        entry_a = {"ui_badge_summary": "No clean zone: awaiting Unicorn BB+FVG", "status": "WAIT", "entry_valid": False, "unicorn_zone": None}
        risk_a = {"ui_badge_summary": "Nothing to size", "status": "STANDBY", "risk_percent": 0.0, "position_size_lots": 0.0}
    # Devil's Advocate
    if cand:
        p, worries = cand["devilP"], cand["worries"]
    else:
        p, worries = 0.0, []
        if sess in ("ASIA", "PRE_LONDON") or (sess == "FRANKFURT_LONDON_OPEN" and not judas):
            p, worries = 78.0, ["Entering before London sweep invites stop-hunt"]
        if box and box[2] > 55:
            p, worries = max(p, 70.0), [f"Asian blowout {box[2]:.0f}p: no Judas elasticity"] + worries
        if locked:
            p, worries = max(p, 70.0), [f"UK CPI / BOE at {hm(nxt)} UTC"] + worries
    devil_a = {"ui_badge_summary": badge("My worry: " + (worries[0] if worries else "nothing fatal found")), "status": "VETO" if p >= 65 else "WARNING" if p else "VALID",
               "failure_probability": round(p / 100, 2), "veto_active": p >= 65, "worries": worries}
    # the Lead (consensus: CHOICE, the gold spec's weights; the GBP spec gives none)
    st = 100 if structure_a["status"] == "VALID" else 50 if h1t else 0
    lq = 100 if lq_s == "VALID" else 50 if lq_s == "WAIT" else 0
    en = 100 if cand and cand.get("unicorn") else 80 if cand else 0
    bt = 100 if bt_s == "VALID" else 50
    score = round(0.25 * st + 0.25 * lq + 0.20 * en + 0.15 * bt + 0.15 * (100 - p), 1)
    execute = bool(cand and cand["pass"] and risk_a["status"] == "VALID" and not devil_a["veto_active"] and not locked)
    if execute:
        decision = "BUY_LIMIT" if cand["dir"] > 0 else "SELL_LIMIT"
        plan = {"order_type": decision, "entry_price": cand["entry"], "stop_loss": cand["sl"], "tp1_price": cand.get("tp1"), "tp2_price": cand["tp"],
                "scenario_id": SCEN[cand["sid"]], "invalidation_trigger": f"price through {cand['sl']:.5f} before the fill"}
        lead_b, scen = f"{decision.replace('_', ' ')} {cand['entry']:.5f} | TP2 {cand['tp']:.5f}", SCEN[cand["sid"]]
    else:
        decision, plan = "NO_TRADE", None
        if locked or (box and box[2] > 55):
            scen, lead_b = "SCENARIO_D_NO_TRADE", ("No trade: UK CPI / BOE lockout" if locked else "No trade: Asian blowout, no Judas")
        elif cand:
            scen, lead_b = SCEN[cand["sid"]], "No trade: " + ("Devil's Advocate veto" if devil_a["veto_active"] else "Risk Manager veto")
        else:
            scen = "SCENARIO_A_JUDAS_UNICORN" if tod < 10 * H1S else "SCENARIO_B_NY_CONTINUATION" if tod < 15 * H1S + 1800 else "SCENARIO_D_NO_TRADE"
            lead_b = "No trade: I wait for 07:00 UTC Judas sweep" if tod < 9 * H1S + 900 else "No trade: I wait for the NY pullback" if tod < 13 * H1S + 2700 else "No trade: no Cable setup today"
    lead_a = {"ui_badge_summary": badge(lead_b), "status": "VALID" if execute else "VETO" if (locked or devil_a["veto_active"]) else "WAIT",
              "reasoning": f"H1 {structure_a['h1_bias']}, H4 {structure_a['h4_bias']}, {sess}; consensus {score} (CHOICE weights)", "execution_plan": plan}
    agents = {"lead_strategist": lead_a, "structure_analyst": structure_a, "liquidity_session_analyst": liquidity_a, "entry_specialist": entry_a,
              "risk_manager": risk_a, "backtest_engineer": backtest_a, "devils_advocate": devil_a}
    contract = {"pair": "GBP/USD", "strategy_name": STRATEGY_NAME, "timestamp_utc": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scenario_active": scen, "consensus_score": score, "final_decision": decision, "agents": agents}
    ui = []
    for k in ("lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager", "backtest_engineer", "devils_advocate"):
        a = agents[k]
        key, role = ROLE[k]
        lines = [f"{kk}: {vv}" for kk, vv in a.items() if kk not in ("ui_badge_summary", "status") and vv not in (None, [], {})]
        ui.append({"key": key, "role": role, "status": UI[a["status"]], "finding": a["ui_badge_summary"], "lines": lines, "statusMd": a["status"]})
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand}
