"""
AGENT 4 · XAUUSD_Sovereign_SMC_Agent (XAU/USD spot gold) · M15 session liquidity, M5 MSS + FVG + OTE · UTC+1.
1 pip = $0.10 (pips_to_price("XAUUSD", 10) = $1.00).

  STEP 1 · liquidity pools
    07:30  Asian_High / Asian_Low (00:00–07:30) and PDH / PDL locked. Asian range > 180 pips ($18): gold already expanded
           overnight → the London killzone is skipped, only the New York reset is traded.
    13:15  London_High / London_Low (08:00–13:15) locked; New York targets {London H/L, Asian H/L, PDH, PDL}.
  STEP 2 · killzone sweep + wick rejection (London 08:00–11:00 · New York 13:30–16:30)
    short: price above a high pool by 8–65 pips ($0.80–$6.50) and, within 1–3 M5 candles of the first breach, an M5
    close back below the level; gold_sweep_peak = the highest high, protected_m5_low = the last confirmed M5 swing low
    before the sweep. Long: the mirror at a low pool.
  STEP 3 · M5 displacement MSS + FVG + OTE
    an M5 close below protected_m5_low; the displacement peak → displacement_low ≥ 25 pips ($2.50) holding a bearish
    FVG ≥ 6 pips ($0.60) or a bearish order block. OTE of the leg: 0.618 / 0.705 / 0.786.
    entry = max(fvg.bottom, ote_618) when the FVG overlaps the OTE zone; else fvg.ce_50 when it sits in the premium
    (≥ the leg's 50 %); else the 0.705 sweet spot when the order block overlaps the OTE zone; else no order.
  STEP 4 · execution
    LIMIT, cancelled after 12 M5 candles or once price reaches 50 % of the way to TP2 before the fill.
    SL = peak + $0.50 (trough − $0.50), at least 25 pips ($2.50), more than 65 pips ($6.50) → skipped.
    TP1 (close 50 %, stop to entry + 2 pips): +1.5R or the swept session's midpoint, whichever comes first, at least 1.3R.
    TP2 (the runner): the opposite session pool (Asian / London low for a short) beyond TP1, else 3.0R.

Draws on the XAU/USD chart: ASIAN_BOX (gold tint), LONDON_BOX (cyan tint), PDH / PDL / Asian / London lines, the
"XAU LIQUIDITY SWEEP + REJECTION" badge, the OTE_GOLD_ZONE (61.8–78.6 %, dotted 70.5 %), FVG / OB boxes, MSS_BREAK and
the trade projection (ENTRY, SL, TP1 50 % + BE, TP2 runner).
"""

from typing import Optional

from ..core.quant_primitives import fingerprint, gaps, hm, in_window, last_swing, mt, order_block, ote, swing_flags, trading_days
from .base import PairAgent, context, line, marker, zone

ASIA = (0, 7 * 60 + 30)
LONDON = (8 * 60, 13 * 60 + 15)
KILLZONES = (("London", 8 * 60, 11 * 60), ("New York", 13 * 60 + 30, 16 * 60 + 30))
NAMES = {"AH": "Asian high", "AL": "Asian low", "LH": "London high", "LL": "London low", "PDH": "PDH", "PDL": "PDL"}


class XAUUSDAgent(PairAgent):
    symbol = "XAUUSD"
    agent_id = "XAUUSD_Sovereign_SMC_Agent"
    name = "Sovereign_SMC"
    tf = "M5"
    windows = [(8 * 60, 11 * 60), (13 * 60 + 30, 16 * 60 + 30)]
    target_range = (1.3, 30.0)
    entry_types = ("LIMIT",)
    timeframes = {"bias": "M15", "setup": "M15", "entry": "M5"}
    params = {"asiaMaxPips": 180.0, "sweepMinPips": 8.0, "sweepMaxPips": 65.0, "rejectBars": 3, "dispMinPips": 25.0, "minFvgPips": 6.0,
              "slBufferPips": 5.0, "slMinPips": 25.0, "slMaxPips": 65.0, "tp1R": 1.5, "tp1MinR": 1.3, "tp2R": 3.0, "beOffsetPips": 2.0,
              "expiryBars": 12, "obLookback": 10, "minAsiaBars": 60}
    why = ("Spot gold runs violent stop hunts at the London open and the New York COMEX open, often overshooting with long wicks. "
           "The agent waits for a session high / low to be swept and closed back inside, an M5 break of structure, and enters "
           "where an FVG meets the Fibonacci OTE (61.8–78.6 %) of the displacement.")
    steps = ["07:30 UTC+1: Asian high / low (00:00–07:30) + PDH / PDL; Asia > 180 pips ($18) → New York only",
             "13:15: London high / low (08:00–13:15) added to the New York pools",
             "Killzones 08:00–11:00 / 13:30–16:30: a pool swept by 8–65 pips and closed back inside within 3 M5 candles",
             "M5 MSS, displacement ≥ 25 pips with an FVG ≥ 6 pips or an OB; entry at the FVG ∩ OTE (61.8–78.6 %)",
             "LIMIT (12 M5 bars) · SL sweep ± $0.50 (25–65 pips) · TP1 1.5R or session 50 % (≥ 1.3R, 50 % + BE+2) · TP2 opposite pool or 3R"]

    def session_name(self, minute: int) -> str:
        if ASIA[0] <= minute < ASIA[1]:
            return "Asian range"
        for name, a, b in KILLZONES:
            if a <= minute < b:
                return f"{name} killzone"
        return "Off-killzone"

    def _day(self, c, prev: Optional[tuple[int, int]], a: int, b: int) -> dict:
        p, P = self.params, self.p2p
        last_minute = mt(c[b].time)[1]
        t_day = c[a].time - mt(c[a].time)[1] * 60
        day_end = t_day + 86400
        zones, lines, markers = [], [], []
        pools: dict[str, float] = {}
        mids: dict[str, float] = {}
        if prev:
            seg = c[prev[0]:prev[1] + 1]
            pools["PDH"], pools["PDL"] = max(x.high for x in seg), min(x.low for x in seg)
            mids["PD"] = (pools["PDH"] + pools["PDL"]) / 2
            lines += [line(f"XU-PDH-{t_day}", "PDH", t_day, day_end, pools["PDH"], None, "PDH"),
                      line(f"XU-PDL-{t_day}", "PDL", t_day, day_end, pools["PDL"], None, "PDL")]
        asia = in_window(c, a, b, *ASIA)
        out = {"setups": [], "ctx": context("IDLE", "Mapping the Asian liquidity (00:00–07:30 UTC+1)", self.session_name(last_minute), "", zones, lines)}
        if len(asia) < p["minAsiaBars"]:
            return out
        ah, al = max(c[i].high for i in asia), min(c[i].low for i in asia)
        asia_pips = self.pips(ah - al)
        zones.append(zone(f"XU-ASIA-{t_day}", "ASIAN_BOX", t_day, t_day + ASIA[1] * 60, ah, al, f"ASIAN RANGE ${ah - al:.2f}"))
        lines += [line(f"XU-AH-{t_day}", "SESSION_HIGH", t_day + ASIA[1] * 60, day_end, ah, None, "ASIAN HIGH"),
                  line(f"XU-AL-{t_day}", "SESSION_LOW", t_day + ASIA[1] * 60, day_end, al, None, "ASIAN LOW")]
        if last_minute < ASIA[1]:
            out["ctx"] = context("IDLE", f"Asian range forming: {asia_pips:.0f} pips (${ah - al:.2f})", "Asian range", "", zones, lines)
            return out
        pools["AH"], pools["AL"] = ah, al
        mids["A"] = (ah + al) / 2
        lon = in_window(c, a, b, *LONDON)
        lh = ll = None
        if lon:
            lh, ll = max(c[i].high for i in lon), min(c[i].low for i in lon)
            zones.append(zone(f"XU-LON-{t_day}", "LONDON_BOX", t_day + LONDON[0] * 60, t_day + LONDON[1] * 60, lh, ll, "LONDON SESSION"))
            if last_minute >= LONDON[1]:
                lines += [line(f"XU-LH-{t_day}", "SESSION_HIGH", t_day + LONDON[1] * 60, day_end, lh, None, "LONDON HIGH", color="#38BDF8"),
                          line(f"XU-LL-{t_day}", "SESSION_LOW", t_day + LONDON[1] * 60, day_end, ll, None, "LONDON LOW", color="#38BDF8")]
        hi_f, lo_f = swing_flags(c[a:b + 1])
        rel = lambda k: k - a  # noqa: E731
        london_ok = asia_pips <= p["asiaMaxPips"]
        state = "ARMED"
        banner = (f"Pools locked (Asia {asia_pips:.0f} pips): waiting for a killzone sweep" if london_ok
                  else f"Asia {asia_pips:.0f} pips > {p['asiaMaxPips']:g}: London skipped, waiting for the New York reset")
        tag = "SESSION LIQUIDITY"
        for kz, w0, w1 in KILLZONES:
            if kz == "London" and not london_ok:
                continue
            active = dict(pools)
            if kz == "New York" and lh is not None:
                active["LH"], active["LL"] = lh, ll
                mids["L"] = (lh + ll) / 2
            win = in_window(c, a, b, w0, w1)
            st = {k: {"first": None, "ext": None, "dead": False, "rejected": False} for k in active}
            done = False
            for i in win:
                x = c[i]
                for k, lvl in active.items():
                    s = st[k]
                    if s["dead"] or done:
                        continue
                    buy = k in ("AL", "LL", "PDL")
                    beyond = (lvl - x.low) if buy else (x.high - lvl)
                    if beyond > 0:
                        if s["first"] is None:
                            ref = last_swing(hi_f if buy else lo_f, rel(i), rel(i))
                            if ref is None:
                                s["dead"] = True
                                continue
                            s.update(first=i, ref=ref + a, refPrice=c[ref + a].high if buy else c[ref + a].low)
                        e = x.low if buy else x.high
                        if s["ext"] is None or ((e < s["ext"]) if buy else (e > s["ext"])):
                            s["ext"], s["extIdx"] = e, i
                        if self.pips(s["ext"] - lvl) > p["sweepMaxPips"]:
                            s["dead"] = True
                            markers.append(marker(f"XU-BO-{k}-{x.time}", x.time, s["ext"], not buy, f"{NAMES[k]}: real breakout", "#D4AF37", "circle"))
                            continue
                    if s["first"] is None:
                        continue
                    pen = self.pips(s["ext"] - lvl)
                    back = x.close > lvl if buy else x.close < lvl
                    if not s["rejected"]:
                        if back and pen >= p["sweepMinPips"] and i - s["first"] <= p["rejectBars"] - 1:
                            s["rejected"] = True
                            s["sweepMk"] = marker(f"XU-SW-{c[s['extIdx']].time}", c[s["extIdx"]].time, s["ext"], not buy,
                                                  "XAU LIQUIDITY SWEEP + REJECTION", "#D4AF37")
                            state, banner = "LIQUIDITY_SWEPT", f"{kz}: {NAMES[k]} swept by {pen:.0f} pips (${pen * self.pip:.2f}) and rejected: waiting for the M5 MSS"
                        elif i - s["first"] >= p["rejectBars"] - 1:
                            s["dead"] = True  # no close back inside within 3 candles: accepted beyond the level
                            continue
                    if not s["rejected"]:
                        continue
                    if not (x.close > s["refPrice"] if buy else x.close < s["refPrice"]):
                        continue
                    s["dead"] = True
                    markers.append(s["sweepMk"])
                    mss_line = line(f"XU-MSS-{x.time}", "MSS_BREAK", c[s["ref"]].time, x.time, s["refPrice"], None, "MSS")
                    leg = c[s["extIdx"]:i + 1]
                    disp_end = max(q.high for q in leg) if buy else min(q.low for q in leg)
                    disp = self.pips(disp_end - s["ext"])
                    fvgs = gaps(c, s["extIdx"] + 2, i, buy, P(p["minFvgPips"]))
                    ob = order_block(c, i, buy, p["obLookback"])
                    if disp < p["dispMinPips"] or not (fvgs or ob):
                        lines.append(mss_line)
                        state, banner = "ARMED", f"{kz}: MSS but displacement {disp:.0f} pips < {p['dispMinPips']:g} or no FVG / OB"
                        continue
                    o = ote(s["ext"], disp_end)
                    entry, how, fvg = None, "", None
                    for g in fvgs:
                        if g.bottom <= o.top and g.top >= o.bottom:  # the FVG overlaps the OTE zone
                            fvg = g
                            entry = min(g.top, o.ote_618) if buy else max(g.bottom, o.ote_618)
                            how, tag = "FVG ∩ OTE", "OTE + FVG"
                            break
                    if entry is None and fvgs:
                        g = fvgs[-1]
                        if (g.ce_50 <= o.eq_50) if buy else (g.ce_50 >= o.eq_50):
                            fvg, entry, how, tag = g, g.ce_50, "FVG ce_50 in the discount / premium", "FVG CE"
                    if entry is None and ob is not None and ob.bottom <= o.top and ob.top >= o.bottom:
                        entry, how, tag = o.ote_705, "OB ∩ OTE: the 0.705 sweet spot", "OTE + OB"
                    if entry is None or ((entry >= x.close) if buy else (entry <= x.close)):
                        lines.append(mss_line)
                        state, banner = "ARMED", f"{kz}: MSS without an entry in the OTE / premium-discount"
                        continue
                    sl = s["ext"] - P(p["slBufferPips"]) if buy else s["ext"] + P(p["slBufferPips"])
                    risk_p = self.pips(entry - sl)
                    if risk_p > p["slMaxPips"]:
                        lines.append(mss_line)
                        state, banner = "ARMED", f"{kz}: SL {risk_p:.0f} pips > {p['slMaxPips']:g}: skipped to protect the R:R"
                        continue
                    sl_txt = f"SL {risk_p:.0f} pips (${risk_p * self.pip:.2f})"
                    if risk_p < p["slMinPips"]:
                        sl = entry - P(p["slMinPips"]) if buy else entry + P(p["slMinPips"])
                        sl_txt = f"SL widened to {p['slMinPips']:g} pips (${p['slMinPips'] * self.pip:.2f})"
                    risk = abs(entry - sl)
                    sgn = 1 if buy else -1
                    r15, rmin = entry + sgn * p["tp1R"] * risk, entry + sgn * p["tp1MinR"] * risk
                    smid = mids.get("L" if k in ("LH", "LL") else "A" if k in ("AH", "AL") else "PD")
                    tp1 = r15
                    if smid is not None and ((entry < smid < r15) if buy else (r15 < smid < entry)):
                        tp1 = smid  # the session midpoint comes first
                    if (tp1 < rmin) if buy else (tp1 > rmin):
                        tp1 = rmin
                    opp = [active[q] for q in (("AH", "LH") if buy else ("AL", "LL")) if q in active]
                    beyond_tp1 = [v for v in opp if ((v > tp1) if buy else (v < tp1))]
                    tp2 = (min(beyond_tp1) if buy else max(beyond_tp1)) if beyond_tp1 else entry + sgn * p["tp2R"] * risk
                    tp2_txt = "the opposite session pool" if beyond_tp1 else f"{p['tp2R']:g}R"
                    half = entry + sgn * 0.5 * abs(tp2 - entry)
                    t_exp = x.time + 300 + p["expiryBars"] * 300
                    zs = [zone(f"XU-OTE-{x.time}", "OTE_GOLD_ZONE", c[s["extIdx"]].time, t_exp, o.top, o.bottom, "OTE GOLDEN ZONE (61.8% - 78.6%)", o.ote_705)]
                    if fvg:
                        zs.append(zone(f"XU-FVG-{c[fvg.index].time}", "FVG_BULL" if buy else "FVG_BEAR", c[fvg.index - 2].time, t_exp, fvg.top, fvg.bottom,
                                       "FVG", fvg.ce_50))
                    if ob:
                        zs.append(zone(f"XU-OB-{c[ob.index].time}", "OB_BULL" if buy else "OB_BEAR", c[ob.index].time, t_exp, ob.top, ob.bottom, "OB", ob.mean))
                    out["setups"].append({
                        "index": i, "time": x.time, "buy": buy, "entryType": "LIMIT", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp2,
                        "partials": [0.5, 0, 0.5], "breakeven": True, "beOffset": P(p["beOffsetPips"]), "expiryBars": p["expiryBars"], "cancelLevel": half,
                        "session": f"{kz} killzone", "tag": tag, "draw": {"zones": zs, "priceLines": [mss_line], "markers": [s["sweepMk"]]},
                        "why": [f"{kz} killzone: {NAMES[k]} {lvl:.2f} swept by {pen:.0f} pips (${pen * self.pip:.2f}), closed back inside within 3 M5 candles",
                                f"MSS: M5 close {x.close:.2f} {'above' if buy else 'below'} the protected swing {s['refPrice']:.2f}",
                                f"Displacement {disp:.0f} pips (${disp * self.pip:.2f}) with {'an FVG' if fvgs else ''}{' and ' if fvgs and ob else ''}{'an OB' if ob else ''}",
                                f"OTE {o.bottom:.2f} – {o.top:.2f} (0.705 at {o.ote_705:.2f}): entry {entry:.2f} by {how}",
                                f"{sl_txt} · TP1 {tp1:.2f} (50 % + BE+2 pips) · TP2 {tp2:.2f} ({tp2_txt})"],
                    })
                    state, banner = "MSS_CONFIRMED", f"{kz}: sweep + rejection + MSS → {'BUY' if buy else 'SELL'} LIMIT {entry:.2f} ({tag})"
                    done = True
        if state in ("ARMED", "LIQUIDITY_SWEPT") and last_minute >= KILLZONES[-1][2]:
            state, banner = "COOLDOWN", "Killzones over: no gold setup today"
        out["ctx"] = context(state, banner + f" · killzones {', '.join(f'{n} {hm(x)}–{hm(y)}' for n, x, y in KILLZONES)}",
                             self.session_name(last_minute), tag, zones, lines, markers)
        return out

    def scan(self, c, peer=None, memo_key: str = "") -> dict:
        days = trading_days(c)
        setups, ctx = [], context("IDLE", "Not enough history")
        for n, (d, a, b) in enumerate(days):
            prev = (days[n - 1][1], days[n - 1][2]) if n else None
            sig = (fingerprint(c, a, b), prev and fingerprint(c, *prev))
            res = self.cached_day(memo_key or "main", d, sig, lambda a=a, b=b, prev=prev: self._day(c, prev, a, b))
            setups.extend(res["setups"])
            ctx = res["ctx"]
        return {"setups": setups, "context": ctx}
