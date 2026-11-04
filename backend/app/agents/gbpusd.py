"""
AGENT 2 · GBPUSD_LondonJudas_SMT_Agent (GBP/USD) · D1 / M15 key levels, M5 SMT + MSS + order block · UTC+1.
Reads GBP/USD and EUR/USD M5 at the same time.

  IDLE      before 07:45: the levels are not locked
  ARMED     07:45: PDH / PDL and Asian high / low (00:00–07:30) of GBPUSD and EURUSD locked
  LIQUIDITY_SWEPT  08:00–10:30, the London Judas fakeout with SMT, at PDH / Asian high (short) or PDL / Asian low (long):
             A. GBPUSD takes its level by 4–30 pips while EURUSD does NOT take its matching level, or
             B. EURUSD takes its level while GBPUSD fails within 5 pips of its own
  MSS_CONFIRMED    GBPUSD closes back inside the level and beyond the last M5 swing, with a 3-candle displacement
             (open of [-3] → close of [-1]) ≥ 1.5 × ATR_M5(14); the originating M5 order block
  PENDING_ORDER    LIMIT at OB_Mean (50 % of the OB body), cancelled after 90 min (or if 3R trades first)
             SL 4 pips beyond the Judas extreme (15–28 pips), TP 3R, stop to break-even at +1.5R
  COOLDOWN  after 10:30 without a setup, or after the day's order.

Draws on the GBP/USD chart: PDH / PDL solid lines, Asian SESSION_HIGH / LOW dashed lines, the "JUDAS TRAP + SMT vs EURUSD"
badge, the OB box with its "OB 50% ENTRY" midline, the MSS_BREAK line and the trade projection.
"""

from typing import Optional

from ..core.quant_primitives import atr, fingerprint, in_window, last_swing, mt, order_block, swing_flags, trading_days
from .base import PairAgent, clamp_stop, context, line, marker, zone

ASIA = (0, 7 * 60 + 30)
LOCK = 7 * 60 + 45
WINDOW = (8 * 60, 10 * 60 + 30)
NAMES = {"PDH": "PDH", "PDL": "PDL", "AH": "Asian high", "AL": "Asian low"}


def levels(c, prev: Optional[tuple[int, int]], a: int, b: int, min_asia: int) -> dict:
    out = {}
    if prev:
        seg = c[prev[0]:prev[1] + 1]
        out["PDH"], out["PDL"] = max(x.high for x in seg), min(x.low for x in seg)
    asia = in_window(c, a, b, *ASIA)
    if len(asia) >= min_asia:
        out["AH"], out["AL"] = max(c[i].high for i in asia), min(c[i].low for i in asia)
    return out


class GBPUSDAgent(PairAgent):
    symbol = "GBPUSD"
    agent_id = "GBPUSD_LondonJudas_SMT_Agent"
    name = "LondonJudas_SMT"
    tf = "M5"
    peer = "EUR/USD"
    windows = [WINDOW]
    target_range = (3.0, 3.0)
    entry_types = ("LIMIT",)
    timeframes = {"bias": "D1", "setup": "M15", "entry": "M5"}
    params = {"penMinPips": 4.0, "penMaxPips": 30.0, "failWithinPips": 5.0, "dispAtr": 1.5, "slBufferPips": 4.0, "slMinPips": 15.0,
              "slMaxPips": 28.0, "targetR": 3.0, "breakevenR": 1.5, "expiryMin": 90, "obLookback": 10, "minAsiaBars": 60}
    why = ("Cable fakes a breakout at the London open (the Judas swing) and then runs the other way. The agent reads EUR/USD "
           "at the same moment: GBP/USD takes its high while EUR/USD fails to take its own (or the reverse), and that SMT "
           "divergence marks the trap. It works the order block of the displacement that breaks the structure back.")
    steps = ["07:45 UTC+1: PDH / PDL and the Asian high / low (00:00–07:30) of GBPUSD and EURUSD",
             "08:00–10:30: GBPUSD takes a level by 4–30 pips while EURUSD fails (or EURUSD takes it and GBPUSD fails within 5 pips)",
             "M5 close back inside + beyond the last swing, 3-candle displacement ≥ 1.5 × ATR_M5(14)",
             "LIMIT at the M5 order block's 50 % (OB_Mean), cancelled after 90 min",
             "SL Judas extreme ± 4 pips (15–28) · TP 3R · BE at +1.5R"]

    def session_name(self, minute: int) -> str:
        if ASIA[0] <= minute < ASIA[1]:
            return "Asian range"
        if WINDOW[0] <= minute < WINDOW[1]:
            return "London Judas window"
        return "Off-window"

    def _day(self, c, prev, a, b, peer: Optional[dict]) -> dict:
        p, P = self.params, self.p2p
        last_minute = mt(c[b].time)[1]
        day_end = c[a].time + 86400
        L = levels(c, prev, a, b, p["minAsiaBars"])
        E = levels(peer["c"], peer["prev"], peer["a"], peer["b"], p["minAsiaBars"]) if peer and peer.get("a") is not None else ({} if peer else None)
        out = {"setups": [], "ctx": context("IDLE", "Locking the key levels at 07:45 UTC+1", self.session_name(last_minute))}
        lines = []
        t_day = c[a].time
        for k, v in L.items():
            cat = "PDH" if k == "PDH" else "PDL" if k == "PDL" else "SESSION_HIGH" if k == "AH" else "SESSION_LOW"
            t_from = t_day if k in ("PDH", "PDL") else t_day + ASIA[1] * 60
            lines.append(line(f"GU-{k}-{t_day}", cat, t_from, day_end, v, None, NAMES[k].upper()))
        if not L or last_minute < LOCK:
            out["ctx"] = context("IDLE", "Locking the key levels at 07:45 UTC+1", self.session_name(last_minute), "", [], lines)
            return out
        lo = max(prev[0] if prev else a, a - 300)
        seg = c[lo:b + 1]
        hi_f, lo_f = swing_flags(seg)
        at = atr(seg)
        rel = lambda k: k - lo  # noqa: E731
        win = in_window(c, a, b, *WINDOW)
        eur = {x.time: x for x in peer["c"][peer["a"]:peer["b"] + 1]} if peer and peer.get("a") is not None else {}
        eur_hi = eur_lo = None
        gb_hi = gb_lo = None  # GBP window extremes (for variant B)
        st = {k: {"ext": None, "dead": False, "variant": None} for k in L}
        state, banner, tag = "ARMED", "Key levels locked: waiting for the London Judas fakeout with SMT vs EURUSD", "PDH/PDL + ASIA"
        markers, zones = [], []
        done = False
        for i in win:
            x = c[i]
            ex = eur.get(x.time)
            if ex is not None:
                eur_hi = ex.high if eur_hi is None else max(eur_hi, ex.high)
                eur_lo = ex.low if eur_lo is None else min(eur_lo, ex.low)
            if gb_hi is None or x.high > c[gb_hi].high:
                gb_hi = i
            if gb_lo is None or x.low < c[gb_lo].low:
                gb_lo = i
            for k, lvl in L.items():
                s = st[k]
                if s["dead"] or done:
                    continue
                buy = k in ("PDL", "AL")
                beyond = (lvl - x.low) if buy else (x.high - lvl)
                el = (E or {}).get(k)
                eur_took = None if E is None else (el is not None and ((eur_lo is not None and eur_lo < el) if buy else (eur_hi is not None and eur_hi > el)))
                if beyond > 0:  # A: GBPUSD takes its level
                    if s["ext"] is None or s["variant"] == "B":
                        ref = last_swing(hi_f if buy else lo_f, rel(i), rel(i))
                        if ref is None:
                            s["dead"] = True
                            continue
                        s.update(ref=ref + lo, refPrice=seg[ref].high if buy else seg[ref].low, ext=x.low if buy else x.high, extIdx=i, variant="A")
                    elif (x.low < s["ext"]) if buy else (x.high > s["ext"]):
                        s["ext"], s["extIdx"] = (x.low if buy else x.high), i
                    if abs(s["ext"] - lvl) > P(p["penMaxPips"]):
                        s["dead"] = True
                        markers.append(marker(f"GU-BO-{k}-{x.time}", x.time, s["ext"], not buy, f"{NAMES[k]}: real breakout", "#D4AF37", "circle"))
                        continue
                    state, banner = "LIQUIDITY_SWEPT", f"Judas fakeout at the {NAMES[k]}: waiting for the M5 MSS"
                elif s["ext"] is None and eur_took is not False:
                    # B: EURUSD took its level while GBPUSD stays within 5 pips under its own (None = EURUSD not read: superset)
                    g = gb_lo if buy else gb_hi
                    near = (c[g].low - lvl) if buy else (lvl - c[g].high)
                    if 0 <= near <= P(p["failWithinPips"]) and (eur_took is None or eur_took):
                        ref = last_swing(hi_f if buy else lo_f, rel(g), rel(i))
                        if ref is not None:
                            s.update(ref=ref + lo, refPrice=seg[ref].high if buy else seg[ref].low, ext=c[g].low if buy else c[g].high, extIdx=g, variant="B")
                            state, banner = "LIQUIDITY_SWEPT", f"SMT: EURUSD took its {NAMES[k]}, GBPUSD failed: waiting for the M5 MSS"
                if s["ext"] is None:
                    continue
                if s["variant"] == "B" and ((x.low < s["ext"]) if buy else (x.high > s["ext"])):
                    s["ext"], s["extIdx"] = (x.low if buy else x.high), i
                    if (s["ext"] < lvl) if buy else (s["ext"] > lvl):  # GBPUSD took it after all: now variant A
                        s["variant"] = "A"
                inside = x.close > lvl if buy else x.close < lvl
                mss = x.close > s["refPrice"] if buy else x.close < s["refPrice"]
                if not (inside and mss):
                    continue
                s["dead"] = True  # one decision per fakeout
                pen = (lvl - s["ext"]) / self.pip if buy else (s["ext"] - lvl) / self.pip
                if s["variant"] == "A":
                    if pen < p["penMinPips"]:
                        banner = f"{NAMES[k]} taken by {pen:.1f} pips only (< {p['penMinPips']:g})"
                        continue
                    if E is not None and eur_took:
                        banner = f"No SMT: EURUSD took its {NAMES[k]} too"
                        continue
                    if E is not None and (E or {}).get(k) is None:
                        banner = "No EURUSD level for the SMT check"
                        continue
                    smt = (f"SMT: GBPUSD took its {NAMES[k]} by {pen:.1f} pips, EURUSD did not take its own" if E is not None
                           else "SMT not read (pre-filter)")
                else:
                    smt = f"SMT: EURUSD took its {NAMES[k]}, GBPUSD failed {abs(pen):.1f} pips from its own"
                a_i = at[rel(i)]
                disp = (c[i - 2].open - x.close) if not buy else (x.close - c[i - 2].open)
                if a_i is None or disp < p["dispAtr"] * a_i:
                    banner = f"Displacement {self.pips(disp):.1f} pips < {p['dispAtr']:g} × ATR"
                    continue
                ob = order_block(c, i, buy, p["obLookback"])
                if ob is None:
                    banner = "No order block before the break"
                    continue
                entry = ob.mean
                if (entry >= x.close) if buy else (entry <= x.close):
                    banner = "Order block already traded through"
                    continue
                sl0 = s["ext"] - P(p["slBufferPips"]) if buy else s["ext"] + P(p["slBufferPips"])
                sl, sl_txt = clamp_stop(self, entry, sl0, buy, p["slMinPips"], p["slMaxPips"])
                mss_line = line(f"GU-MSS-{x.time}", "MSS_BREAK", c[s["ref"]].time, x.time, s["refPrice"], None, "MSS")
                trap = marker(f"GU-JT-{c[s['extIdx']].time}", c[s["extIdx"]].time, s["ext"], not buy, "JUDAS TRAP + SMT vs EURUSD")
                if sl is None:
                    banner = sl_txt
                    lines.append(mss_line)
                    markers.append(trap)
                    continue
                risk = abs(entry - sl)
                sign = 1 if buy else -1
                tp, be = entry + sign * p["targetR"] * risk, entry + sign * p["breakevenR"] * risk
                bars = p["expiryMin"] // 5
                t_exp = x.time + 300 + bars * 300
                draw = {"zones": [zone(f"GU-OB-{c[ob.index].time}", "OB_BULL" if buy else "OB_BEAR", c[ob.index].time, t_exp, ob.top, ob.bottom,
                                       "OB 50% ENTRY", ob.mean)],
                        "priceLines": [mss_line], "markers": [trap]}
                out["setups"].append({
                    "index": i, "time": x.time, "buy": buy, "entryType": "LIMIT", "entry": entry, "sl": sl, "tp1": be, "tp2": tp, "tp3": tp,
                    "partials": [0, 0, 1], "breakeven": True, "beOffset": 0, "expiryBars": bars, "cancelLevel": tp,
                    "session": "London Judas window", "tag": "SMT CONFIRMED", "draw": draw,
                    "why": [f"London Judas at the {NAMES[k]} {lvl:.5f} ({'GBPUSD took it' if s['variant'] == 'A' else 'GBPUSD failed it'})", smt,
                            f"MSS: M5 close {x.close:.5f} back inside and {'above' if buy else 'below'} the swing {s['refPrice']:.5f}",
                            f"3-candle displacement {self.pips(disp):.1f} pips ≥ {p['dispAtr']:g} × ATR ({self.pips(a_i):.1f} pips)",
                            f"M5 order block {ob.bottom:.5f} – {ob.top:.5f}: LIMIT at OB_Mean {ob.mean:.5f}",
                            f"SL {self.pips(risk):.1f} pips ({sl_txt}) · TP 3R · BE at +1.5R"],
                })
                state, banner, tag = "MSS_CONFIRMED", f"Judas + SMT + MSS → {'BUY' if buy else 'SELL'} LIMIT {entry:.5f} at the OB 50 %", "SMT CONFIRMED"
                done = True
        if state in ("ARMED", "LIQUIDITY_SWEPT") and last_minute >= WINDOW[1]:
            state, banner = "COOLDOWN", f"{banner} · Judas window closed (10:30): no trade today"
        out["ctx"] = context(state, banner, self.session_name(last_minute), tag, zones, lines, markers)
        return out

    def scan(self, c, peer=None, memo_key: str = "") -> dict:
        days = trading_days(c)
        pdays = {d: (a, b) for d, a, b in trading_days(peer)} if peer is not None else {}
        pkeys = sorted(pdays)
        setups, ctx = [], context("IDLE", "Not enough history")
        for n, (d, a, b) in enumerate(days):
            prev = (days[n - 1][1], days[n - 1][2]) if n else None
            pinfo, psig = None, None
            if peer is not None:
                pa = pdays.get(d)
                earlier = [k for k in pkeys if k < d]
                pprev = pdays[earlier[-1]] if earlier else None
                pinfo = {"c": peer, "a": pa[0] if pa else None, "b": pa[1] if pa else None, "prev": pprev}
                psig = (fingerprint(peer, *pa) if pa else None, fingerprint(peer, *pprev) if pprev else None)
            sig = (fingerprint(c, a, b), prev and fingerprint(c, *prev), peer is not None, psig)
            res = self.cached_day(f"{memo_key or 'main'}|{peer is not None}", d, sig, lambda a=a, b=b, prev=prev, pinfo=pinfo: self._day(c, prev, a, b, pinfo))
            setups.extend(res["setups"])
            ctx = res["ctx"]
        return {"setups": setups, "context": ctx}
