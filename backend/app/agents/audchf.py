"""
AGENT 3 · AUDCHF_MeanReversion_Range_Agent (AUD/CHF) · H4 ADX filter & channel, H1 RSI divergence & engulfing trigger.

  COOLDOWN  ADX_H4(14) ≥ 28: the market trends, no range trade
  ARMED     ADX_H4(14) < 28, the 60-bar H4 range:
              Supply  res_top = max(High_H4[-60:]) → res_bottom = res_top − 0.8 × ATR_H4(14)
              Demand  sup_bottom = min(Low_H4[-60:]) → sup_top = sup_bottom + 0.8 × ATR_H4(14)
              Equilibrium (res_top + sup_bottom) / 2
  LIQUIDITY_SWEPT  an H1 candle in a zone (Low ≤ sup_top / High ≥ res_bottom)
  MSS_CONFIRMED    RSI(14) divergence between two H1 swings 5–30 bars apart:
              demand: Low_2 ≤ Low_1 + 2 pips, RSI_2 ≥ RSI_1 + 3, RSI_1 < 35 · supply: High_2 ≥ High_1 − 2 pips, RSI_2 ≤ RSI_1 − 3, RSI_1 > 65
  IN_TRADE  a closed H1 engulfing candle in the reversal direction, range ≥ 0.7 × ATR_H1(14) → MARKET at its close
              SL 1.2 × ATR_H1(14) beyond the divergence extreme (20–35 pips), TP1 the equilibrium (50 % + break-even),
              TP2 the opposite zone boundary (res_bottom for a long, sup_top for a short)

Draws on the AUD/CHF chart: SUPPLY_BAND, DEMAND_BAND, the EQUILIBRIUM line, the sloped "H1 RSI DIVERGENCE" line between
the two pivots, the "ENGULFING TRIGGER" arrow and the trade projection.
"""

from ..core.quant_primitives import adx, aggregate, atr, rsi, swing_flags
from .base import PairAgent, clamp_stop, context, line, marker, zone

H4 = 14400


class AUDCHFAgent(PairAgent):
    symbol = "AUDCHF"
    agent_id = "AUDCHF_MeanReversion_Range_Agent"
    name = "MeanReversion_Range"
    tf = "H1"
    history = 12500
    min_bars = 1200
    windows = None
    target_range = (0.5, 40.0)
    entry_types = ("MARKET",)
    timeframes = {"bias": "H4", "setup": "H4", "entry": "H1"}
    params = {"adxMax": 28.0, "channel": 60, "zoneAtr": 0.8, "divMin": 5, "divMax": 30, "priceTolPips": 2.0, "rsiDiff": 3.0, "rsiLow": 35.0,
              "rsiHigh": 65.0, "engulfAtr": 0.7, "slAtr": 1.2, "slMinPips": 20.0, "slMaxPips": 35.0, "maxWait": 8}
    why = ("AUD/CHF does not run in one direction: it bounces between the top and the bottom of its range. At a wall the agent "
           "does not guess: it waits for an RSI divergence (the sellers or buyers tiring) and a strong H1 engulfing candle, then "
           "trades back to the middle and the other wall.")
    steps = ["H4: ADX(14) < 28 (else COOLDOWN) · Supply / Demand = the 60-bar H4 extremes ∓ 0.8 × ATR_H4(14)",
             "H1 in a zone: RSI(14) divergence between two swings 5–30 bars apart (Low_2 ≤ Low_1 + 2 pips, RSI_2 ≥ RSI_1 + 3, RSI_1 < 35)",
             "H1 engulfing candle, range ≥ 0.7 × ATR_H1(14): MARKET at its close",
             "SL 1.2 × ATR_H1 beyond the divergence extreme (20–35 pips)",
             "TP1 the equilibrium (close 50 % + break-even) · TP2 the opposite zone boundary"]

    def session_name(self, minute: int) -> str:
        return "H4 range regime"

    def scan(self, c, peer=None, memo_key: str = "") -> dict:
        p, P = self.params, self.p2p
        h4 = aggregate(c, H4)
        ax, a4 = adx(h4), atr(h4)
        a1, r1 = atr(c), rsi(c)
        hi_f, lo_f = swing_flags(c)
        n = p["channel"]
        setups: list[dict] = []
        used: set = set()
        j, zj, z = -1, -1, None
        pending_div: dict = {}
        ctx = context("IDLE", "Not enough H4 history")
        for i in range(len(c)):
            close_t = c[i].time + 3600
            while j + 1 < len(h4) and h4[j + 1].time + H4 <= close_t:
                j += 1
            if j < n + 30 or ax[j] is None or a4[j] is None or a1[i] is None or r1[i] is None:
                continue
            if zj != j:
                top = max(x.high for x in h4[j - n + 1:j + 1])
                bot = min(x.low for x in h4[j - n + 1:j + 1])
                z = {"rt": top, "rb": top - p["zoneAtr"] * a4[j], "sb": bot, "st": bot + p["zoneAtr"] * a4[j], "eq": (top + bot) / 2,
                     "t1": h4[j - n + 1].time, "adx": ax[j]}
                zj = j
            x = c[i]
            if ax[j] >= p["adxMax"]:
                ctx = ("COOLDOWN", f"H4 ADX {ax[j]:.1f} ≥ {p['adxMax']:g}: trending, no range trade", z, None)
                continue
            in_demand, in_supply = x.low <= z["st"], x.high >= z["rb"]
            state = "LIQUIDITY_SWEPT" if (in_demand or in_supply) else "ARMED"
            banner = (f"H4 range (ADX {ax[j]:.1f}): {'price in DEMAND' if in_demand else 'price in SUPPLY' if in_supply else 'waiting for a zone touch'}")
            # the divergence confirmed on this candle (its second swing is known now)
            s = i - 2
            for buy, flags in ((True, lo_f), (False, hi_f)):
                if s < 0 or not flags[s]:
                    continue
                ext = c[s].low if buy else c[s].high
                if not ((ext <= z["st"]) if buy else (ext >= z["rb"])):
                    continue
                q = next((q for q in range(s - p["divMin"], max(-1, s - p["divMax"] - 1), -1)
                          if flags[q] and r1[q] is not None and r1[s] is not None and (
                              (c[s].low <= c[q].low + P(p["priceTolPips"]) and r1[s] >= r1[q] + p["rsiDiff"] and r1[q] < p["rsiLow"]) if buy else
                              (c[s].high >= c[q].high - P(p["priceTolPips"]) and r1[s] <= r1[q] - p["rsiDiff"] and r1[q] > p["rsiHigh"]))), None)
                if q is not None:
                    pending_div[buy] = {"s": s, "q": q, "ext": ext, "until": i + p["maxWait"]}
            for buy in (True, False):
                dv = pending_div.get(buy)
                if not dv:
                    continue
                broken = (x.low < dv["ext"]) if buy else (x.high > dv["ext"])
                if i > dv["until"] or (broken and i > dv["s"] + 2):
                    pending_div.pop(buy)
            live = next((b for b in (True, False) if b in pending_div), None)
            if live is not None:
                state, banner = "MSS_CONFIRMED", f"H1 RSI divergence in {'DEMAND' if live else 'SUPPLY'}: waiting for the engulfing trigger"
            y = c[i - 1]
            bull = y.close < y.open and x.close > x.open and x.close >= y.open and x.open <= y.close
            bear = y.close > y.open and x.close < x.open and x.close <= y.open and x.open >= y.close
            fired = None
            if (bull or bear) and x.high - x.low >= p["engulfAtr"] * a1[i]:
                buy = bull
                dv = pending_div.get(buy)
                if dv and (buy, dv["s"]) not in used:
                    used.add((buy, dv["s"]))
                    pending_div.pop(buy)
                    extreme = min(k.low for k in c[dv["s"]:i + 1]) if buy else max(k.high for k in c[dv["s"]:i + 1])
                    entry = x.close
                    sl0 = extreme - p["slAtr"] * a1[i] if buy else extreme + p["slAtr"] * a1[i]
                    sl, sl_txt = clamp_stop(self, entry, sl0, buy, p["slMinPips"], p["slMaxPips"])
                    tp1, tp2 = z["eq"], (z["rb"] if buy else z["st"])
                    if sl is None:
                        banner = f"Engulfing, but {sl_txt}"
                    elif not ((entry < tp1 < tp2) if buy else (tp2 < tp1 < entry)):
                        banner = "Engulfing closed beyond the equilibrium: no room to TP1"
                    else:
                        risk = abs(entry - sl)
                        qd, sd = dv["q"], dv["s"]
                        div_line = line(f"AC-DIV-{c[sd].time}", "DIVERGENCE_LINE", c[qd].time, c[sd].time,
                                        c[qd].low if buy else c[qd].high, c[sd].low if buy else c[sd].high, "H1 RSI DIVERGENCE")
                        trig = marker(f"AC-ENG-{x.time}", x.time, x.low if buy else x.high, not buy, "ENGULFING TRIGGER")
                        setups.append({
                            "index": i, "time": x.time, "buy": buy, "entryType": "MARKET", "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp2,
                            "partials": [0.5, 0, 0.5], "breakeven": True, "beOffset": 0, "expiryBars": None, "cancelLevel": None,
                            "session": "H4 range regime", "tag": "H4 RANGE + RSI DIV", "draw": {"zones": [], "priceLines": [div_line], "markers": [trig]},
                            "why": [f"H4 ADX {ax[j]:.1f} < {p['adxMax']:g}: a range",
                                    f"{'Demand' if buy else 'Supply'} zone {(z['sb'] if buy else z['rb']):.5f} – {(z['st'] if buy else z['rt']):.5f}",
                                    f"H1 RSI divergence: {'low' if buy else 'high'} {c[sd].low if buy else c[sd].high:.5f} vs {c[qd].low if buy else c[qd].high:.5f} "
                                    f"({sd - qd} bars), RSI {r1[sd]:.1f} vs {r1[qd]:.1f}",
                                    f"H1 engulfing, range {self.pips(x.high - x.low):.1f} pips ≥ 0.7 × ATR ({self.pips(a1[i]):.1f})",
                                    f"SL {self.pips(risk):.1f} pips ({sl_txt}) · TP1 equilibrium {tp1:.5f} (50 % + BE) · TP2 {tp2:.5f}"],
                        })
                        fired = (buy, entry)
            if fired:
                state, banner = "MSS_CONFIRMED", f"Engulfing trigger → {'BUY' if fired[0] else 'SELL'} MARKET {fired[1]:.5f}"
            ctx = (state, banner, z, pending_div.get(True) or pending_div.get(False))
        if isinstance(ctx, dict):
            return {"setups": setups, "context": ctx}
        state, banner, z, dv = ctx
        end = c[-1].time + 3600 * 24
        zones = [zone(f"AC-SUP-{z['t1']}", "SUPPLY_BAND", z["t1"], end, z["rt"], z["rb"], "SUPPLY ZONE (H4)"),
                 zone(f"AC-DEM-{z['t1']}", "DEMAND_BAND", z["t1"], end, z["st"], z["sb"], "DEMAND ZONE (H4)")]
        lines = [line(f"AC-EQ-{z['t1']}", "EQUILIBRIUM", z["t1"], end, z["eq"], None, "EQUILIBRIUM 50%", color="#D4AF37")]
        if dv:
            buy = dv["ext"] <= z["st"]
            q, s = dv["q"], dv["s"]
            lines.append(line(f"AC-DIV-{c[s].time}", "DIVERGENCE_LINE", c[q].time, c[s].time, c[q].low if buy else c[q].high,
                              c[s].low if buy else c[s].high, "H1 RSI DIVERGENCE"))
        tag = "H4 RANGE + RSI DIV" if dv else "H4 RANGE" if state != "COOLDOWN" else "TRENDING (ADX)"
        return {"setups": setups, "context": context(state, f"{banner} · ADX {z['adx']:.1f}", "H4 range regime", tag, zones, lines)}
