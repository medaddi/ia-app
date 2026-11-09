"""
EUR/USD — the user's spec "eur_usd_multi_agent_quantitative_strategy_claude_prompt.md" (2026-11-09), applied to the
letter. It replaces everything earlier for EUR/USD (SnapBack 3σ included: git history keeps it).

Strategy: "London-NY Killzone VWAP Orderblock & SMT Divergence".
  Scenario A  London open manipulation sweep + VWAP-band order block (sweep 06:45-09:30, entries in 07:00-10:00 UTC)
  Scenario B  NY overlap trend continuation pullback to the session VWAP (12:00-14:30, entries until 15:00 UTC)
  Scenario C  ECB / Fed / NFP protocol: new orders suspended 20 min before, the first M15 after the release must close,
              then only Scenario B, and only when the post-news move respects the H4 structure
  Scenario D  after 16:30 UTC or today's range >= 0.85 ADR 14: hard NO_TRADE

Section 3 math: the session VWAP reset at 00:00 UTC (and a NY VWAP from 12:00) with volume-weighted σ bands ±1.0 / 1.5 /
2.0 / 2.5 (weights = volumes; a feed without volume weighs every candle the same, CHOICE); SMT against GBP/USD (the
product of the two normalised swing changes < 0); the M15 order block [L_ob, O_ob] (the last bearish candle before an
upward displacement that breaks a fractal swing high) with an adjacent unmitigated FVG >= 0.20 ATR 14 M15; the Asian
range ratio γ = R_Asia / ADR 14 <= 0.38. The Risk Manager: a 2.0-pip buffer, SL 6-28 pips, RR >= 2.4, 1 % (0.5 % when
over 65 % of ADR is used). The Devil: a hard veto at >= 65 %. The Lead: consensus >= 78 in a killzone, no hard veto.
"""

from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from typing import Optional

from .gold import G, badge, hm, structure
from .playbook import DAY, H1S, M5S, M15S, Daily, _make, body, hilo, m5_index_at_close, resample, run, span

PIP = 0.0001
STRATEGY_NAME = "London-NY Killzone VWAP Orderblock & SMT Divergence"
NAMES = {"A": "Scenario A · London manipulation sweep + VWAP-band OB", "B": "Scenario B · NY overlap pullback to the session VWAP"}
SCEN = {"A": "SCENARIO_A_LONDON_SWEEP_OB", "B": "SCENARIO_B_NY_VWAP_CONTINUATION"}
BASELINE = {"A": {"trades": 382, "winRate": 61.2, "avgWin": 2.60, "expectancyR": 1.20, "pf": 2.98, "mdd": -4.8},
            "B": {"trades": 310, "winRate": 56.8, "avgWin": 2.45, "expectancyR": 0.96, "pf": 2.52, "mdd": -5.9}}
MACRO = {("EUR", "Main Refinancing Rate"), ("EUR", "Monetary Policy Statement"), ("EUR", "ECB Press Conference"), ("EUR", "CPI Flash Estimate y/y"),
         ("EUR", "Core CPI Flash Estimate y/y"), ("USD", "Non-Farm Employment Change"), ("USD", "CPI m/m"), ("USD", "CPI y/y"),
         ("USD", "Core CPI m/m"), ("USD", "Core CPI y/y"), ("USD", "Federal Funds Rate"), ("USD", "FOMC Statement"), ("USD", "FOMC Press Conference")}


def macro_times(events) -> list[int]:
    """Scenario C's events: ECB rate decision, Eurozone flash CPI, NFP, US CPI, FOMC."""
    return sorted({int(e["time"]) for e in (events or []) if (e.get("currency"), e.get("title")) in MACRO})


def vwap_anchored(m5, anchor_hour: int) -> tuple[list, list]:
    """VWAP_t and σ_t (section 3.1) reset each UTC day at `anchor_hour`: σ² = Σ V (TP - VWAP_t)² / Σ V, computed with the
    identity Σ V TP² / Σ V - VWAP_t². Before the anchor the value is None."""
    vw: list[Optional[float]] = [None] * len(m5)
    sd: list[Optional[float]] = [None] * len(m5)
    cur, sw, s1, s2 = None, 0.0, 0.0, 0.0
    for i, x in enumerate(m5):
        a = x.time - x.time % DAY + anchor_hour * H1S
        if x.time < a:
            continue
        if cur != a:
            cur, sw, s1, s2 = a, 0.0, 0.0, 0.0
        v = x.volume if getattr(x, "volume", 0) and x.volume > 0 else 1.0
        tp = (x.high + x.low + x.close) / 3
        sw, s1, s2 = sw + v, s1 + v * tp, s2 + v * tp * tp
        m = s1 / sw
        vw[i], sd[i] = m, max(s2 / sw - m * m, 0.0) ** 0.5
    return vw, sd


class F(G):
    def __init__(self, m5, h1, daily: Daily, gbp_m5=None):
        super().__init__(m5, h1, daily)
        self.vw0, self.sd0 = vwap_anchored(m5, 0)
        self.vw12, self.sd12 = vwap_anchored(m5, 12)
        self.gbp = None
        if gbp_m5:
            g15 = resample(gbp_m5, M15S)
            from .playbook import atr
            self.gbp = ({x.time: x for x in g15}, atr(g15, 14), [x.time for x in g15])

    def gamma(self, D: int) -> Optional[tuple[float, float, float]]:
        """(L_Asia, H_Asia, γ) over 00:00-06:00 UTC."""
        hl = hilo(span(self.m5, self.t5, D, D + 6 * H1S))
        adr = self.daily.adr(D, 14)
        return (hl[1], hl[0], (hl[0] - hl[1]) / adr) if hl and adr else None

    def smt(self, j_t1: int, j_t2: int, d: int) -> Optional[bool]:
        """Section 3.2 against GBP/USD on M15 swing points t1 (the earlier swing) and t2 (the sweep candle): bullish SMT
        when (ΔL_EUR / ATR_EUR) × (ΔL_GBP / ATR_GBP) < 0, the mirror on highs. None without GBP data."""
        if not self.gbp:
            return None
        gm, gat, gt = self.gbp
        a, b = self.m15[j_t1], self.m15[j_t2]
        ga, gb = gm.get(a.time), gm.get(b.time)
        if ga is None or gb is None:
            return None
        k = bisect_left(gt, b.time)
        g_atr = gat[k] if k < len(gat) else None
        e_atr = self.at15[j_t2]
        if not g_atr or not e_atr:
            return None
        de = ((b.low - a.low) if d > 0 else (b.high - a.high)) / e_atr
        dg = ((gb.low - ga.low) if d > 0 else (gb.high - ga.high)) / g_atr
        return de * dg < 0

    def ob_fvg(self, j_from: int, j_to: int, d: int, until_j: int):
        """Section 3.3 on M15: the last opposite candle before a displacement that closes beyond the last fractal swing
        (the MSS), zone [L_ob, O_ob] (bull) / [O_ob, H_ob] (bear), with an adjacent FVG >= 0.20 ATR M15 (between the OB and
        the 2nd candle after it, or the 1st and 3rd, CHOICE) not mitigated up to until_j. Returns dict or None."""
        m = self.m15
        hi_f, lo_f = self.f15
        for t in range(max(j_from, 3), min(j_to, len(m))):
            ref = next((q for q in range(t - 3, max(t - 40, 0), -1) if (hi_f[q] if d > 0 else lo_f[q])), None)
            if ref is None:
                continue
            lvl = m[ref].high if d > 0 else m[ref].low
            if not ((m[t].close > lvl) if d > 0 else (m[t].close < lvl)):
                continue
            ob = next((q for q in range(t - 1, max(t - 6, 0), -1) if ((m[q].close < m[q].open) if d > 0 else (m[q].close > m[q].open))), None)
            if ob is None:
                return None
            at = self.at15[t] or 0
            fvg = None
            for a_, c_ in ((ob, ob + 2), (ob + 1, ob + 3)):
                if c_ >= len(m):
                    continue
                if d > 0 and m[c_].low - m[a_].high >= 0.20 * at:
                    fvg = (m[a_].high, m[c_].low, c_)
                    break
                if d < 0 and m[a_].low - m[c_].high >= 0.20 * at:
                    fvg = (m[c_].high, m[a_].low, c_)
                    break
            if not fvg:
                return None
            zone = (m[ob].low, m[ob].open) if d > 0 else (m[ob].open, m[ob].high)
            j_known = max(t, fvg[2])
            mitig = any(((m[q].low <= zone[1]) if d > 0 else (m[q].high >= zone[0])) for q in range(j_known + 1, min(until_j + 1, len(m))))
            if mitig:
                return None
            return {"ob": zone, "fvg": fvg[:2], "t_set": m[j_known].time + M15S, "mss": lvl, "j_ob": ob, "j_mss": t}
        return None


def _risk(entry: float, sl: float, d: int, tps: list, need: float):
    """The Risk Manager: SL < 6 pips widened to 6; > 28 pips rejected; the nearest TP2 at `need` R or more."""
    dist = abs(entry - sl) / PIP
    if dist < 6.0:
        sl = entry - d * 6.0 * PIP
    elif dist > 28.0:
        return None, f"SL {dist:.1f} pips > 28 (inefficient structure)"
    risk = abs(entry - sl)
    good = sorted([(n, p) for n, p in tps if p is not None and (p - entry) * d >= need * risk], key=lambda t: abs(t[1] - entry))
    return (sl, (good[0][1], good[0][0])) if good else (None, f"no TP2 at {need:g} R or more")


def _days(m5) -> list[int]:
    return sorted({x.time - x.time % DAY for x in m5 if datetime.fromtimestamp(x.time, timezone.utc).weekday() < 5})


def _adr_used(f: F, D: int, t: int) -> float:
    adr = f.daily.adr(D, 14)
    day = hilo(span(f.m5, f.t5, D, t))
    return (day[0] - day[1]) / adr if adr and day else 0.0


def scenario_a(f: F, cost: float, out: list, watch: list) -> None:
    """γ_Asia <= 0.38; 06:45-09:30 UTC an M15 candle takes L_Asia (H1 bullish) / H_Asia (H1 bearish) and touches the
    session VWAP ∓ 1.5σ; then the M15 MSS with an unmitigated OB + FVG; the limit at the OB's proximal edge (O_ob), or the
    FVG's 50 % when it lies inside the OB (CHOICE: "OB / 50 % FVG overlap"); longs only under the H1 E_eq. SL = L_sweep -
    max(2.0 pips, 0.30 ATR M15). TP1 the session VWAP (40 % closed, the stop stays: the spec moves it nowhere), TP2 the
    opposing Asian boundary or PDH / PDL at >= 2.8 R. Entries in the London killzone 07:00-10:00 only."""
    m15 = f.m15
    for D in _days(f.m5):
        gm = f.gamma(D)
        if not gm or gm[2] > 0.38:
            continue
        la, ha, gamma = gm
        i1 = f.i1(D + 7 * H1S)
        if i1 < 1:
            continue
        bias = f.s1["trend"][i1]
        if not bias:
            continue
        d = bias
        lvl = la if d > 0 else ha
        pd = hilo(span(f.m5, f.t5, D - DAY, D)) or hilo(span(f.m5, f.t5, D - 3 * DAY, D - 2 * DAY + 1))
        j0, j1 = f.j15(D + 6 * H1S + 2700) + 1, f.j15(D + 9 * H1S + 1800) + 1
        for j in range(max(j0, 3), min(j1, len(m15))):
            x = m15[j]
            if not ((x.low < lvl) if d > 0 else (x.high > lvl)):
                continue
            k = m5_index_at_close(f.t5, x.time + M15S)
            if k is None or f.vw0[k] is None:
                continue
            band = f.vw0[k] - d * 1.5 * f.sd0[k]
            touched = (x.low <= band) if d > 0 else (x.high >= band)
            t1 = next((q for q in range(j - 3, max(j - 40, 0), -1) if (f.f15[1][q] if d > 0 else f.f15[0][q])), None)
            smt = f.smt(t1, j, d) if t1 is not None else None
            steps = [(f"γ_Asia {gamma:.2f} <= 0.38", True, f"{la:.5f} - {ha:.5f}"), (f"H1 {'bullish' if d > 0 else 'bearish'}", True, ""),
                     (f"Sweep of {'L' if d > 0 else 'H'}_Asia 06:45-09:30", True, f"{lvl:.5f}"),
                     (f"Touches VWAP {'-' if d > 0 else '+'}1.5σ", touched, f"{band:.5f}"),
                     ("SMT vs GBP/USD", bool(smt), "divergence" if smt else ("none" if smt is False else "no GBP data"))]
            if not touched:
                continue
            ext = x.low if d > 0 else x.high
            z = f.ob_fvg(j, min(j + 8, len(m15)), d, 0)  # fresh at the setup's close: nothing after it is known yet
            if not z:
                watch.append({"sid": "A", "time": x.time + M15S, "dir": d, "steps": steps + [("M15 MSS + unmitigated OB + FVG >= 0.20 ATR", False, "waiting")]})
                break
            t_set = z["t_set"]
            if not (D + 7 * H1S <= t_set < D + 10 * H1S):
                watch.append({"sid": "A", "time": t_set, "dir": d, "steps": steps + [("Inside the London killzone 07:00-10:00", False, hm(t_set))]})
                break
            ce = (z["fvg"][0] + z["fvg"][1]) / 2
            entry = ce if z["ob"][0] <= ce <= z["ob"][1] else z["ob"][1] if d > 0 else z["ob"][0]
            dr = f.dealing(t_set)
            if dr and ((entry > dr[2]) if d > 0 else (entry < dr[2])):
                watch.append({"sid": "A", "time": t_set, "dir": d, "steps": steps + [("Entry in the H1 discount / premium", False, f"E_eq {dr[2]:.5f}")]})
                break
            j_set = f.j15(t_set)
            sl = ext - d * max(2.0 * PIP, 0.30 * (f.at15[j_set] or 0))
            sl2, tp2 = _risk(entry, sl, d, [("the opposing Asian boundary", ha if d > 0 else la), ("PD" + ("H" if d > 0 else "L"), (pd[0] if d > 0 else pd[1]) if pd else None)], 2.8)
            steps += [("M15 MSS + unmitigated OB + FVG >= 0.20 ATR", True, f"OB {z['ob'][0]:.5f} - {z['ob'][1]:.5f}"), ("Limit at the OB proximal edge / 50 % FVG", True, f"{entry:.5f}")]
            if sl2 is None:
                watch.append({"sid": "A", "time": t_set, "dir": d, "steps": steps + [("Risk Manager", False, tp2)]})
                break
            k0 = m5_index_at_close(f.t5, t_set)
            if k0 is None:
                break
            vw = f.vw0[k0]
            used = _adr_used(f, D, t_set)
            s = _make("EURUSD", "A", d, f.m5, k0, entry, sl2, vw, tp2[0], 0.4, False, max(1, (D + 10 * H1S - t_set) // M5S), D + 16 * H1S + 1800, steps,
                      {"levels": {"Asia high": ha, "Asia low": la, **({"PDH": pd[0], "PDL": pd[1]} if pd else {})}, "fvg": (z["fvg"][0], z["fvg"][1], m15[z["j_ob"]].time),
                       "ob": (z["ob"][1], z["ob"][0], m15[z["j_ob"]].time), "sweep": (ext, x.time), "mss": (z["mss"], m15[z["j_mss"]].time)}, cost,
                      zone=(min(z["ob"]), max(z["ob"])), be_off=None)
            if s:
                s.update(riskPct=0.5 if used > 0.65 else 1.0, tp2Name=tp2[1], smt=smt, gamma=gamma, scenario="A", adrUsed=used, newsMin=20)
                out.append(s)
            break


def scenario_b(f: F, cost: float, out: list, watch: list) -> None:
    """London (07:00-12:00 UTC) moved >= 35 pips with an H1 BOS that way; 12:00-14:30 UTC the NY pullback reaches the H1
    discount (long) and tests the session VWAP AND a London-session M15 OB (unmitigated until then); an M5 rejection candle
    (WDR >= 0.40) there: entry at its close (CHOICE: the confluence entry after the rejection). SL the rejection extreme -
    2.0 pips; TP the 1.272 (else 1.618) Fibonacci extension of the NY pullback toward the London high, at RR >= 2.4. Entries
    until 15:00 UTC. Risk 1 % (0.5 % over 65 % ADR)."""
    m5 = f.m5
    for D in _days(m5):
        lon = hilo(span(m5, f.t5, D + 7 * H1S, D + 12 * H1S))
        if not lon or (lon[0] - lon[1]) / PIP < 35:
            continue
        i_a, i_b = f.i1(D + 8 * H1S), f.i1(D + 12 * H1S)
        evs = [f.s1["event"][q] for q in range(max(i_a, 1), i_b + 1) if f.s1["event"][q] != f.s1["event"][q - 1]]
        if not evs or evs[-1][0] != "BOS":
            continue
        d = evs[-1][1]
        obs = []
        for jj in range(f.j15(D + 7 * H1S) + 1, f.j15(D + 12 * H1S) + 1):
            z = f.ob_fvg(jj, jj + 1, d, f.j15(D + 12 * H1S))
            if z:
                obs.append(z)
        if not obs:
            continue
        ks, ke = bisect_left(f.t5, D + 12 * H1S), bisect_left(f.t5, D + 14 * H1S + 1800)
        for k in range(ks, ke):
            x = m5[k]
            v = f.vw0[k]
            dr = f.dealing(x.time + M5S)
            if v is None or not dr:
                continue
            disc = (x.low <= dr[2]) if d > 0 else (x.high >= dr[2])
            at_v = x.low <= v <= x.high
            ob = next((z for z in obs if ((z["ob"][0] <= x.low <= z["ob"][1] + 2 * PIP) if d > 0 else (z["ob"][0] - 2 * PIP <= x.high <= z["ob"][1]))), None)
            rng = x.high - x.low
            wdr = ((min(x.open, x.close) - x.low) if d > 0 else (x.high - max(x.open, x.close))) / rng if rng > 0 else 0
            if not (disc and at_v and ob and wdr >= 0.40):
                continue
            entry = x.close
            ext = x.low if d > 0 else x.high
            sl = ext - d * 2.0 * PIP
            start = lon[0] if d > 0 else lon[1]
            ext1272 = ext + d * 1.272 * abs(start - ext)
            ext1618 = ext + d * 1.618 * abs(start - ext)
            sl2, tp2 = _risk(entry, sl, d, [("Fib 1.272 extension", ext1272), ("Fib 1.618 extension", ext1618)], 2.4)
            steps = [(f"London impulse {(lon[0] - lon[1]) / PIP:.0f} pips (>= 35) with an H1 BOS", True, ""),
                     ("NY pullback into the H1 discount" if d > 0 else "NY pullback into the H1 premium", True, f"E_eq {dr[2]:.5f}"),
                     ("Tests the session VWAP + a London M15 OB", True, f"VWAP {v:.5f}"), (f"M5 rejection candle (WDR {wdr:.2f} >= 0.40)", True, "")]
            if sl2 is None:
                watch.append({"sid": "B", "time": x.time + M5S, "dir": d, "steps": steps + [("Risk Manager", False, tp2)]})
                break
            if x.time + M5S >= D + 15 * H1S:
                break
            used = _adr_used(f, D, x.time + M5S)
            s = _make("EURUSD", "B", d, m5, k, entry, sl2, None, tp2[0], 1.0, True, 0, D + 16 * H1S + 1800, steps,
                      {"ob": (ob["ob"][1], ob["ob"][0], f.m15[ob["j_ob"]].time), "sweep": (ext, x.time), "levels": {"London high": lon[0], "London low": lon[1]}}, cost,
                      be_off=None)
            if s:
                s.update(riskPct=0.5 if used > 0.65 else 1.0, tp2Name=tp2[1], scenario="B", adrUsed=used, newsMin=20)
                out.append(s)
            break


def devil(f: F, s: dict) -> tuple[float, list[str]]:
    """Failure probability (CHOICE: the weights): γ_Asia > 0.50 +35 · GBP/USD failing to confirm (no SMT) +25 · after
    15:30 UTC +30 · an unmitigated opposing H4 order block before 1.5 R +30. Hard veto >= 65 %."""
    t, d = s["time"], s["dir"]
    D = t - t % DAY
    p, worries = 0.0, []
    gm = f.gamma(D)
    if gm and gm[2] > 0.50:
        p += 35
        worries.append(f"Asia already used {gm[2] * 100:.0f}% of ADR: chop risk")
    if s["sid"] == "A" and s.get("smt") is False:
        p += 25
        worries.append("GBP/USD does not confirm (no SMT)")
    if t % DAY > 15 * H1S + 1800:
        p += 30
        worries.append("after 15:30 UTC: London liquidity dries up")
    r15 = s["entry"] + d * 1.5 * abs(s["entry"] - s["sl"])
    i4 = f.i4(t)
    for q in range(max(1, i4 - 30), i4 + 1):
        ev = f.s4["event"][q]
        if ev and ev[1] == -d and f.s4["event"][q - 1] != ev:
            ob = next((f.h4[r] for r in range(q - 1, max(q - 6, 0), -1) if ((f.h4[r].close > f.h4[r].open) if d > 0 else (f.h4[r].close < f.h4[r].open))), None)
            if ob and ((s["entry"] < ob.low < r15) if d > 0 else (r15 < ob.high < s["entry"])) and \
               not any(((x.high >= ob.low) if d > 0 else (x.low <= ob.high)) for x in f.h4[q + 1:i4 + 1]):
                p += 30
                worries.append(f"H4 {'supply' if d > 0 else 'demand'} at {(ob.low if d > 0 else ob.high):.5f} before 1.5R")
                break
    return min(p, 100.0), worries


def scan(m5, h1, cost: float, news_events=None, d1=None, gbp_m5=None) -> tuple[list, list]:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    f = F(m5, h1, daily, gbp_m5)
    out, watch = [], []
    scenario_a(f, cost, out, watch)
    scenario_b(f, cost, out, watch)
    out.sort(key=lambda x: x["time"])
    seen = set()
    out = [x for x in out if not ((x["sid"], x["time"], x["dir"]) in seen or seen.add((x["sid"], x["time"], x["dir"])))]
    nw = macro_times(news_events) if news_events is not None else []
    for s in out:
        t = s["time"]
        D = t - t % DAY
        before = [n for n in nw if n - 20 * 60 <= t < n + 15 * 60]  # suspended 20 min before until the first M15 after closes
        window = [n for n in nw if n - 30 * 60 <= t <= n + 30 * 60]
        c_ok = not window or (s["sid"] == "B" and not before and f.s4["trend"][f.i4(t)] == s["dir"])
        if nw and not s["market"]:
            s["result"] = run(m5, s["index"], s["dir"], s["entry"], s["sl"], s["tp1"], s["tp"], s["part"], False, s["expiry"], s["holdUntil"], cost,
                              None, nw, None, None, None, 20)
        late = t % DAY > 16 * H1S + 1800
        used = _adr_used(f, D, t)
        p, worries = devil(f, s)
        sl_p = abs(s["entry"] - s["sl"]) / PIP
        s["devilP"], s["worries"] = p, worries
        s["checklist"] = [
            (f"1 · {NAMES[s['sid']]}", True, STRATEGY_NAME),
            ("2 · Scenario C: no ECB / Fed / NFP / CPI within ±30 min (else B only, after the first M15, with H4)", c_ok,
             "not checked (no news history)" if news_events is None else ("news at " + ", ".join(hm(n) for n in window) + " UTC" if window else "clear")),
            (f"3 · Scenario D: not after 16:30 UTC, today < 85 % of ADR ({used * 100:.0f} %)", not late and used < 0.85, ""),
            (f"4 · Risk Manager: SL 6-28 pips ({sl_p:.1f}), RR >= 2.4 ({s['rr']:.2f})", 6.0 - 1e-6 <= sl_p <= 28.0 and s["rr"] >= 2.4, s.get("tp2Name", "")),
            (f"5 · Lot for {s.get('riskPct', 1.0):g} % risk ($10 / pip / lot)", True, ""),
            (f"6 · Devil's Advocate: failure probability {p:.0f} % (< 65 %)", p < 65, "; ".join(worries) or "no trap found"),
        ]
        s["pass"] = all(ok for _, ok, _ in s["checklist"])
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("7 · One EUR/USD trade at a time", False, "the previous setup is still pending or open"))
            continue
        r = s["result"]
        busy = m5[r["at"]].time + M5S if "at" in r else 1 << 62
    for w in watch:
        w.setdefault("sid", "A")
    return out, sorted(watch, key=lambda w: w["time"])


UI = {"VALID": "ok", "WAIT": "wait", "WARNING": "warn", "VETO": "veto", "STANDBY": "wait"}
ROLE = {"lead_strategist": ("lead", "Lead Strategist"), "structure_analyst": ("structure", "Structure Analyst"),
        "liquidity_session_analyst": ("liquidity", "Liquidity & Session Analyst"), "entry_specialist": ("entry", "Entry Specialist"),
        "risk_manager": ("risk", "Risk Manager"), "backtest_engineer": ("backtest", "Backtest Engineer"), "devils_advocate": ("devil", "Devil's Advocate")}


def report(m5, h1, now: int, setups: list, watch: list, research: Optional[dict], news_events, d1=None, gbp_m5=None) -> dict:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    f = F(m5, h1, daily, gbp_m5)
    t = m5[-1].time + M5S
    price = m5[-1].close
    D = t - t % DAY
    k = len(m5) - 1
    i1, i4 = f.i1(t), f.i4(t)
    h1t, h4t = f.s1["trend"][i1], (f.s4["trend"][i4] if i4 >= 0 else 0)
    dr = f.dealing(t)
    tod = t % DAY
    sess = ("LONDON_KILLZONE" if 7 * H1S <= tod < 10 * H1S else "NY_OVERLAP" if 12 * H1S <= tod < 15 * H1S else
            "INACTIVE" if not (6 * H1S + 2700 <= tod < 16 * H1S) else "BETWEEN_KILLZONES")
    killzone = 7 * H1S <= tod < 10 * H1S or 12 * H1S <= tod < 15 * H1S + 1800
    gm = f.gamma(D)
    used = _adr_used(f, D, t)
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE")]
    cand = next((s for s in reversed(live) if s["pass"]), live[-1] if live else None)
    w = watch[-1] if watch and watch[-1]["time"] >= now - 3 * H1S else None
    nw = macro_times(news_events) if news_events is not None else None
    nxt = next((n for n in (nw or []) if n >= now - 30 * 60), None)
    in_c = nxt is not None and abs(nxt - now) <= 30 * 60
    vw, sd = f.vw0[k], f.sd0[k]
    smt = cand.get("smt") if cand else None
    pos = None if vw is None or not sd else (price - vw) / sd
    structure_a = {"ui_badge_summary": badge(f"H1 {'bullish' if h1t > 0 else 'bearish' if h1t < 0 else 'neutral'} | " +
                                             (f"{'Above' if price > vw else 'Below'} VWAP {vw:.4f}" if vw else "no VWAP") +
                                             f" | SMT {'bullish' if smt and (cand['dir'] > 0) else 'bearish' if smt else 'neutral'}"),
                   "status": "VALID" if h1t and h1t == h4t else "WAIT", "h4_bias": {1: "BULLISH", -1: "BEARISH"}.get(h4t, "NEUTRAL"),
                   "h1_bias": {1: "BULLISH", -1: "BEARISH"}.get(h1t, "NEUTRAL"), "vwap_session": vw,
                   "vwap_bands": {"plus_1_5_sigma": vw + 1.5 * sd, "minus_1_5_sigma": vw - 1.5 * sd, "plus_2_0_sigma": vw + 2 * sd, "minus_2_0_sigma": vw - 2 * sd} if vw else None,
                   "vwap_ny": f.vw12[k], "price_sigma": pos, "smt_divergence": ("BULLISH" if cand["dir"] > 0 else "BEARISH") if smt else "NONE",
                   "dealing_range": {"low": dr[0], "high": dr[1], "equilibrium": dr[2]} if dr else None}
    lv_pd = hilo(span(m5, f.t5, D - DAY, D)) or hilo(span(m5, f.t5, D - 3 * DAY, D - 2 * DAY + 1))
    lon = hilo(span(m5, f.t5, D + 7 * H1S, min(t, D + 12 * H1S))) if t > D + 7 * H1S else None
    asia = (gm[1], gm[0]) if gm else None
    bsl = sorted({round(v, 5) for v in [lv_pd and lv_pd[0], asia and asia[0], lon and lon[0]] + f.eq_levels(t, -1) if v and v > price})
    ssl = sorted({round(v, 5) for v in [lv_pd and lv_pd[1], asia and asia[1], lon and lon[1]] + f.eq_levels(t, 1) if v and v < price}, reverse=True)
    swept = cand is not None or bool(w and any("Sweep" in s_[0] and s_[1] for s_ in w["steps"]))
    if nw is None:
        lq_s, lq_b = "WARNING", "News feed down: ECB / Fed not checked"
    elif in_c:
        lq_s, lq_b = "WARNING", f"Scenario C: macro release {hm(nxt)} UTC"
    elif sess == "INACTIVE":
        lq_s, lq_b = "WAIT", f"Off-hours | ADR used: {used * 100:.0f}% | Next: Asia 00:00 UTC"
    else:
        lq_s = "VALID" if swept and killzone else "WAIT"
        lq_b = (f"{'Asia Low' if (cand or w or {'dir': 1})['dir'] > 0 else 'Asia High'} swept | " if swept else f"γ_Asia {gm[2]:.2f} | " if gm else "") + sess.replace("_", " ").title()
    liquidity_a = {"ui_badge_summary": badge(lq_b), "status": lq_s, "active_session": "OFF_HOURS" if sess == "INACTIVE" else sess,
                   "asia_range_ratio_adr": round(gm[2], 2) if gm else None, "prime_manipulation": bool(gm and gm[2] <= 0.38),
                   "bsl_targets": bsl[:4], "ssl_targets": ssl[:4], "sweep_detected": swept, "adr_used": round(used, 2)}
    sid = cand["sid"] if cand else (w["sid"] if w else "A")
    meas = (((research or {}).get("strategies") or {}).get(sid) or {}).get("all")
    base = BASELINE[sid]
    # the rolling check: of the last 10 London sweeps of the Asian range, how many reached the session VWAP the same day
    tests, hits = 0, 0
    for Dd in reversed(_days(m5)[:-1]):
        g2 = f.gamma(Dd)
        if not g2:
            continue
        ks, ke = bisect_left(f.t5, Dd + 6 * H1S + 2700), bisect_left(f.t5, Dd + 9 * H1S + 1800)
        kk = next((q for q in range(ks, ke) if m5[q].low < g2[0] or m5[q].high > g2[1]), None)
        if kk is None:
            continue
        tests += 1
        hits += any(f.vw0[q] is not None and m5[q].low <= f.vw0[q] <= m5[q].high for q in range(kk + 1, min(bisect_left(f.t5, Dd + 16 * H1S), len(m5))))
        if tests == 10:
            break
    if meas and meas.get("trades", 0) >= 30:
        bt_b, bt_s = f"Data VERIFIED: {meas['winRate']}% WR | {meas['expectancyR']:+.2f}R EV", "VALID"
    else:
        bt_b, bt_s = f"Data LIMITED: N={(meas or {}).get('trades', 0)} · {hits}/{tests} sweeps hit VWAP", "WARNING"
    backtest_a = {"ui_badge_summary": badge(bt_b), "status": bt_s, "historical_win_rate": base["winRate"] / 100, "expected_value_r": base["expectancyR"],
                  "measured": meas, "spec_benchmark": base, "last_10_sweeps_to_vwap": f"{hits}/{tests}"}
    if cand:
        zl, zh = min(cand["zone"]), max(cand["zone"])
        entry_a = {"ui_badge_summary": badge(f"M15 OB {zl:.5f}-{zh:.5f} | limit {cand['entry']:.5f}" if not cand["market"] else f"VWAP+OB rejection | {cand['entry']:.5f}"),
                   "status": "VALID", "entry_valid": True, "order_block": [zl, zh]}
        rk = cand.get("riskPct", 1.0)
        rd = abs(cand["entry"] - cand["sl"]) / PIP
        lots = int(10000 * rk / 100 / (rd * 10) * 100) / 100 if rd else 0
        ok = 6.0 - 1e-6 <= rd <= 28.0 and cand["rr"] >= 2.4
        risk_a = {"ui_badge_summary": badge(f"Risk {rk:g}% | SL {rd:.1f}p | {lots} lot/$10k | RR {cand['rr']:.1f}" if ok else f"Rejected: SL {rd:.1f}p / RR {cand['rr']:.1f}"),
                  "status": "VALID" if ok else "VETO", "risk_percent": rk, "position_size_lots": lots}
    else:
        entry_a = {"ui_badge_summary": "No clean zone: " + ("session filter inactive" if sess == "INACTIVE" else "waiting for M15 OB+FVG"), "status": "WAIT", "entry_valid": False}
        risk_a = {"ui_badge_summary": "Nothing to size", "status": "STANDBY", "risk_percent": 0.0, "position_size_lots": 0.0}
    if cand:
        p, worries = cand["devilP"], cand["worries"]
    else:
        p, worries = 0.0, []
        if sess == "INACTIVE" or tod > 15 * H1S + 1800:
            p, worries = 85.0, ["Off-session liquidity trap & wide spreads"]
        elif gm and gm[2] > 0.50:
            p, worries = 35.0, [f"Asia used {gm[2] * 100:.0f}% of ADR: chop risk"]
    devil_a = {"ui_badge_summary": badge("My worry: " + (worries[0] if worries else "nothing fatal found")), "status": "VETO" if p >= 65 else "WARNING" if p else "VALID",
               "failure_probability": round(p / 100, 2), "veto_active": p >= 65, "worries": worries}
    st = 100 if structure_a["status"] == "VALID" else 50 if h1t else 0
    lq = 100 if lq_s == "VALID" else 50 if killzone else 0
    en = 100 if cand else 0
    bt = 100 if bt_s == "VALID" else 0
    score = round(0.25 * st + 0.25 * lq + 0.20 * en + 0.15 * bt + 0.15 * (100 - p), 1)
    execute = bool(cand and cand["pass"] and killzone and score >= 78 and not devil_a["veto_active"] and risk_a["status"] == "VALID")
    late = tod > 16 * H1S + 1800 or used >= 0.85
    if execute:
        decision = ("BUY_LIMIT" if cand["dir"] > 0 else "SELL_LIMIT") if not cand["market"] else ("BUY_MARKET" if cand["dir"] > 0 else "SELL_MARKET")
        lead_b = f"{decision.split('_')[0]} {decision.split('_')[1]} {cand['entry']:.5f} | SL {cand['sl']:.5f} | TP {cand['tp']:.5f}"
        plan = {"order_type": decision, "entry_price": cand["entry"], "stop_loss": cand["sl"], "tp1_price": cand.get("tp1"), "tp2_price": cand["tp"],
                "scenario_id": SCEN[cand["sid"]]}
        scen = SCEN[cand["sid"]]
    else:
        decision, plan = "NO_TRADE", None
        if late:
            scen, lead_b = "SCENARIO_D_OFF_SESSION", "No trade: dead zone / ADR > 85% used"
        elif in_c:
            scen, lead_b = "SCENARIO_C_MACRO_PROTOCOL", f"No trade: macro release {hm(nxt)} UTC"
        elif cand:
            scen, lead_b = SCEN[cand["sid"]], f"No trade: consensus {score:.0f} < 78" if score < 78 else "No trade: a veto is active"
        elif sess == "INACTIVE":
            scen, lead_b = "SCENARIO_D_OFF_SESSION", "No trade: I wait for London Open & Asia range"
        else:
            scen = "SCENARIO_A_LONDON_SWEEP_OB" if tod < 10 * H1S else "SCENARIO_B_NY_VWAP_CONTINUATION"
            tgt = (ssl[0] if h1t >= 0 and ssl else bsl[0] if bsl else price)
            lead_b = f"No trade: I wait for {'London' if tod < 10 * H1S else 'NY'} sweep of {tgt:.4f}"
    lead_a = {"ui_badge_summary": badge(lead_b), "status": "VALID" if execute else "VETO" if devil_a["veto_active"] and cand else "WAIT",
              "reasoning": f"H1 {structure_a['h1_bias']}, H4 {structure_a['h4_bias']}, {sess}; consensus {score} (CHOICE: the gold spec's weights)",
              "execution_plan": plan}
    agents = {"lead_strategist": lead_a, "structure_analyst": structure_a, "liquidity_session_analyst": liquidity_a, "entry_specialist": entry_a,
              "risk_manager": risk_a, "backtest_engineer": backtest_a, "devils_advocate": devil_a}
    contract = {"pair": "EUR/USD", "strategy_name": STRATEGY_NAME, "timestamp_utc": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scenario_active": scen, "consensus_score": score, "final_decision": decision, "agents": agents}
    ui = []
    for kk in ("lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager", "backtest_engineer", "devils_advocate"):
        a = agents[kk]
        key, role = ROLE[kk]
        lines = [f"{x}: {y}" for x, y in a.items() if x not in ("ui_badge_summary", "status") and y not in (None, [], {})]
        ui.append({"key": key, "role": role, "status": UI[a["status"]], "finding": a["ui_badge_summary"], "lines": lines, "statusMd": a["status"]})
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand}
