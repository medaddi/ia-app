"""
AGENT 1 · EURUSD_AsianSweep_FVG_Agent (EUR/USD) · M15 Asian range, M5 sweep / MSS / FVG execution · UTC+1.

  IDLE        00:00–07:00  the Asian range is forming
  COOLDOWN    range outside 12–45 pips → no trade today
  ARMED       07:00 → the killzones London 08:00–11:00 and New York 13:30–16:00
  LIQUIDITY_SWEPT  price takes asian_high (short) / asian_low (long) by 1 to 20 pips (more = a real breakout: dead side)
  MSS_CONFIRMED    an M5 close beyond the last confirmed M5 swing before the sweep, with an M5 FVG ≥ 2.5 pips in the leg
  PENDING_ORDER    LIMIT at the FVG's ce_50, deleted after 12 M5 bars (or if the target trades first)
                   SL 3 pips beyond the sweep wick (6–18 pips), TP1 = stop to break-even at asian_mid or +1R (first),
                   TP2 = the opposite side of Asia, at least 2R
  IN_TRADE / COOLDOWN after the order.

Draws on the EUR/USD chart: ASIAN_BOX + ASIAN HIGH / LOW / EQUILIBRIUM lines, "ASIAN HIGH SWEPT" marker on the sweep wick,
MSS_BREAK dotted line, FVG box with its "50% CE ENTRY" line, and the trade projection.
"""

from ..core.quant_primitives import aggregate, fingerprint, gaps, hm, in_window, last_swing, mt, swing_flags, trading_days
from .base import GOLD, PairAgent, clamp_stop, context, line, marker, zone

ASIA = (0, 7 * 60)
KILLZONES = (("London", 8 * 60, 11 * 60), ("New York", 13 * 60 + 30, 16 * 60))


class EURUSDAgent(PairAgent):
    symbol = "EURUSD"
    agent_id = "EURUSD_AsianSweep_FVG_Agent"
    name = "AsianSweep_FVG"
    tf = "M5"
    windows = [(8 * 60, 11 * 60), (13 * 60 + 30, 16 * 60)]
    target_range = (2.0, 30.0)
    entry_types = ("LIMIT",)
    timeframes = {"bias": "M15", "setup": "M5", "entry": "M5"}
    params = {"rangeMinPips": 12.0, "rangeMaxPips": 45.0, "sweepMinPips": 1.0, "sweepMaxPips": 20.0, "minFvgPips": 2.5,
              "slBufferPips": 3.0, "slMinPips": 6.0, "slMaxPips": 18.0, "minRR": 2.0, "expiryBars": 12, "minAsiaBars": 60}
    why = ("In the Asian hours EUR/USD sleeps in a tight box and the stops pile up just beyond it. In the London or New York "
           "killzone the banks run one side of the box, then turn: the agent waits for the M5 close through the last swing (MSS) "
           "with a fair value gap, and works the gap's 50 % back to the other side of the box.")
    steps = ["00:00–07:00 UTC+1: Asian high / low / 50 % on M15, range 12–45 pips (else COOLDOWN)",
             "Killzones 08:00–11:00 and 13:30–16:00: the Asian high (low) taken by 1–20 pips",
             "M5 close beyond the last confirmed swing (MSS) with an M5 FVG ≥ 2.5 pips",
             "LIMIT at the FVG ce_50, cancelled after 12 M5 bars",
             "SL sweep wick ± 3 pips (6–18) · BE at the Asian 50 % or +1R · TP2 the other side of Asia (≥ 2R)"]

    def session_name(self, minute: int) -> str:
        if ASIA[0] <= minute < ASIA[1]:
            return "Asian range"
        for name, a, b in KILLZONES:
            if a <= minute < b:
                return f"{name} killzone"
        return "Off-killzone"

    # ------------------------------------------------------------------ one day
    def _day(self, c, a: int, b: int) -> dict:
        p, P = self.params, self.p2p
        hi_f, lo_f = swing_flags(c[a:b + 1])
        rel = lambda k: k - a  # noqa: E731
        day_end = c[a].time + 86400
        asia = in_window(c, a, b, *ASIA)
        out = {"setups": [], "ctx": context("IDLE", "Building the Asian range (00:00–07:00 UTC+1)", "Asian range")}
        if len(asia) < p["minAsiaBars"]:
            return out
        m15 = aggregate([c[i] for i in asia], 900, 3600)  # the range on M15 (the same extremes as M5)
        ah, al = max(x.high for x in m15), min(x.low for x in m15)
        mid = (ah + al) / 2
        rng = self.pips(ah - al)
        t0, t1 = c[asia[0]].time, c[asia[-1]].time + 300
        zones = [zone(f"EU-ASIA-{t0}", "ASIAN_BOX", t0, t1, ah, al, f"ASIAN RANGE {rng:.1f} pips", mid)]
        lines = [line(f"EU-AH-{t0}", "SESSION_HIGH", t1, day_end, ah, None, "ASIAN HIGH"),
                 line(f"EU-AL-{t0}", "SESSION_LOW", t1, day_end, al, None, "ASIAN LOW"),
                 line(f"EU-EQ-{t0}", "EQUILIBRIUM", t1, day_end, mid, None, "EQUILIBRIUM 50%")]
        markers: list[dict] = []
        last_minute = mt(c[b].time)[1]
        if last_minute < ASIA[1] - 5:
            out["ctx"] = context("IDLE", f"Asian range forming: {rng:.1f} pips so far", "Asian range", "", zones, lines)
            return out
        if not p["rangeMinPips"] <= rng <= p["rangeMaxPips"]:
            out["ctx"] = context("COOLDOWN", f"Asian range {rng:.1f} pips outside {p['rangeMinPips']:g}–{p['rangeMaxPips']:g}: no trade today",
                                 "", "RANGE FILTER", zones, lines)
            return out
        state, banner, tag = "ARMED", f"Asian range {rng:.1f} pips armed: waiting for a killzone sweep", "ASIAN RANGE"

        for name, w0, w1 in KILLZONES:
            win = in_window(c, a, b, w0, w1)
            if not win:
                continue
            sides = {True: {"swept": False, "dead": False}, False: {"swept": False, "dead": False}}  # True = long (low swept)
            done = False
            for i in win:
                x = c[i]
                for buy in (False, True):
                    s = sides[buy]
                    if s["dead"] or done:
                        continue
                    level = al if buy else ah
                    beyond = (level - x.low) if buy else (x.high - level)
                    if beyond >= P(p["sweepMinPips"]) or (s["swept"] and beyond > 0):
                        if beyond > P(p["sweepMaxPips"]):
                            s["dead"] = True
                            markers.append(marker(f"EU-BO-{x.time}", x.time, x.low if buy else x.high, not buy,
                                                  f"{name}: real breakout ({self.pips(beyond):.0f} pips)", GOLD, "circle"))
                            continue
                        if not s["swept"]:
                            ref = last_swing(hi_f if buy else lo_f, rel(i), rel(i))
                            if ref is None:
                                s["dead"] = True
                                continue
                            s.update(swept=True, ref=ref + a, refPrice=c[ref + a].high if buy else c[ref + a].low, ext=None, extIdx=i)
                        ext = x.low if buy else x.high
                        if s["ext"] is None or (ext < s["ext"] if buy else ext > s["ext"]):
                            s["ext"], s["extIdx"] = ext, i
                        state, banner = "LIQUIDITY_SWEPT", f"{name}: {'Asian low' if buy else 'Asian high'} swept, waiting for the M5 MSS"
                    if not s["swept"]:
                        continue
                    if not (x.close > s["refPrice"] if buy else x.close < s["refPrice"]):
                        continue
                    s["dead"] = True  # one decision per sweep
                    sweep_mk = marker(f"EU-SW-{c[s['extIdx']].time}", c[s["extIdx"]].time, s["ext"], not buy,
                                      "ASIAN LOW SWEPT" if buy else "ASIAN HIGH SWEPT")
                    mss = line(f"EU-MSS-{x.time}", "MSS_BREAK", c[s["ref"]].time, x.time, s["refPrice"], None, "MSS")
                    markers.append(sweep_mk)
                    g = gaps(c, s["extIdx"] + 2, i, buy, P(p["minFvgPips"]))
                    if not g:
                        lines.append(mss)
                        state, banner = "ARMED", f"{name}: MSS without an M5 FVG ≥ {p['minFvgPips']:g} pips, no order"
                        continue
                    fvg = g[-1]
                    entry = fvg.ce_50
                    sl0 = s["ext"] - P(p["slBufferPips"]) if buy else s["ext"] + P(p["slBufferPips"])
                    sl, sl_txt = clamp_stop(self, entry, sl0, buy, p["slMinPips"], p["slMaxPips"])
                    if sl is None:
                        lines.append(mss)
                        state, banner = "ARMED", f"{name}: {sl_txt}"
                        continue
                    risk = abs(entry - sl)
                    tp2 = ah if buy else al
                    rr = abs(tp2 - entry) / risk if risk else 0
                    if (tp2 <= entry if buy else tp2 >= entry) or rr < p["minRR"]:
                        lines.append(mss)
                        state, banner = "ARMED", f"{name}: TP2 at 1:{rr:.2f} < 1:{p['minRR']:g}, no order"
                        continue
                    one_r = entry + risk if buy else entry - risk
                    be = min(mid, one_r) if buy else max(mid, one_r)
                    if not (entry < be < tp2 if buy else tp2 < be < entry):
                        be = one_r
                    t_exp = x.time + 300 + p["expiryBars"] * 300
                    cat = "FVG_BULL" if buy else "FVG_BEAR"
                    draw = {"zones": [zone(f"EU-FVG-{x.time}", cat, c[fvg.index - 2].time, t_exp, fvg.top, fvg.bottom, "50% CE ENTRY", fvg.ce_50)],
                            "priceLines": [mss], "markers": [sweep_mk]}
                    out["setups"].append({
                        "index": i, "time": x.time, "buy": buy, "entryType": "LIMIT", "entry": entry, "sl": sl, "tp1": be, "tp2": tp2, "tp3": tp2,
                        "partials": [0, 0, 1], "breakeven": True, "beOffset": 0, "expiryBars": p["expiryBars"], "cancelLevel": tp2,
                        "session": f"{name} killzone", "tag": "ASIAN SWEEP + FVG", "draw": draw,
                        "why": [f"Asian range {rng:.1f} pips ({al:.5f} – {ah:.5f})",
                                f"{name}: {'Asian low' if buy else 'Asian high'} swept by {self.pips(s['ext'] - (al if buy else ah)):.1f} pips (1–20)",
                                f"MSS: M5 close {x.close:.5f} {'above' if buy else 'below'} the swing {s['refPrice']:.5f}",
                                f"M5 FVG {fvg.bottom:.5f} – {fvg.top:.5f} ({self.pips(fvg.top - fvg.bottom):.1f} pips): LIMIT at ce_50",
                                f"SL {self.pips(risk):.1f} pips ({sl_txt}) · BE at {'the Asian 50 %' if be == mid else '+1R'} · TP2 {tp2:.5f} (1:{rr:.2f})"],
                    })
                    state, banner, tag = "MSS_CONFIRMED", f"{name}: sweep + MSS + FVG → {'BUY' if buy else 'SELL'} LIMIT {entry:.5f}", "ASIAN SWEEP + FVG"
                    done = True
            if done:
                break
        if state in ("ARMED", "LIQUIDITY_SWEPT") and last_minute >= KILLZONES[-1][2]:
            state, banner = "COOLDOWN", "Killzones over: no setup today"
        out["ctx"] = context(state, banner, self.session_name(last_minute), tag, zones, lines, markers)
        return out

    def scan(self, c, peer=None, memo_key: str = "") -> dict:
        setups, ctx = [], context("IDLE", "Not enough history")
        for d, a, b in trading_days(c):
            res = self.cached_day(memo_key or "main", d, fingerprint(c, a, b), lambda a=a, b=b: self._day(c, a, b))
            setups.extend(res["setups"])
            ctx = res["ctx"]
        if ctx["state"] != "IDLE" or ctx["banner"] != "Not enough history":
            ctx = {**ctx, "banner": ctx["banner"] + f" · killzones {', '.join(f'{n} {hm(a)}–{hm(b)}' for n, a, b in KILLZONES)}"}
        return {"setups": setups, "context": ctx}
