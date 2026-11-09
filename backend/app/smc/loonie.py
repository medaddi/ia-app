"""
AUD/CAD — the user's spec "aud_cad_multi_agent_quantitative_strategy_claude_prompt.md" (2026-11-09), applied to the
letter. It replaces everything earlier for AUD/CAD (the commodity range reversion "P": git history keeps it).

Strategy: "Cointegrated Regression Channel & VPOC Supply/Demand Reversion".
  Scenario A  channel boundary liquidity sweep + return to VPOC (|β~| <= 1.25, |Z_reg| >= 1.90 outside the 70 % VA,
              a swing swept into a fresh S/D zone, M15 CHoCH + FVG toward VPOC)
  Scenario B  sloping channel trend pullback (0.60 < |β~| <= 1.60) to the ∓1.75 σ_e line + an H1 zone, M15 MSS,
              12:30-16:00 or 23:00-04:00 UTC, target the opposite ±1.75 σ_e line at >= 2.8 R
  Scenario C  RBA / BOC / CAD employment / AUD CPI: no execution 20 min before to 20 min after; nothing in the rollover
  Scenario D  |Z_reg| < 1.10 (at the VPOC magnet): NO_TRADE

Section 3 math as written: the OLS line over N = 100 H1 closes, e_N, σ_e (N - 2), Z_reg = e_N / σ_e, β~ = 24 β / ATR 14
H1; the 100-bar H1 volume profile in K = 40 bins (VPOC, the narrowest contiguous 70 % value area around it); fresh
S/D zones (departure >= 2.0 ATR H1 with a BOS, tested <= 1 time).

Every number the spec leaves open is marked CHOICE and was fixed before any result was seen.
"""

from bisect import bisect_left
from datetime import datetime, timezone
from typing import Optional

from .fiber import F
from .gold import badge, hm
from .playbook import DAY, H1S, M5S, M15S, Daily, _make, hilo, m5_index_at_close, resample, run, span

PIP = 0.0001
STRATEGY_NAME = "Cointegrated Regression Channel & VPOC Supply/Demand Reversion"
NAMES = {"A": "Scenario A · channel boundary sweep back to VPOC", "B": "Scenario B · sloping channel trend pullback"}
SCEN = {"A": "SCENARIO_A_CHANNEL_SWEEP_VPOC", "B": "SCENARIO_B_SLOPING_CHANNEL_PULLBACK", "C": "SCENARIO_C_NEWS_ROLLOVER_LOCKOUT", "D": "SCENARIO_D_AT_VPOC"}
BASELINE = {"A": {"trades": 328, "winRate": 64.6, "avgWin": 2.25, "expectancyR": 1.10, "pf": 2.92, "mdd": -4.4},
            "B": {"trades": 244, "winRate": 59.8, "avgWin": 2.65, "expectancyR": 1.18, "pf": 2.84, "mdd": -5.2}}
EVENTS_C = {("CAD", "Overnight Rate"), ("CAD", "BOC Rate Statement"), ("CAD", "Employment Change"), ("AUD", "Cash Rate"),
            ("AUD", "RBA Rate Statement"), ("AUD", "CPI m/m"), ("AUD", "CPI y/y"), ("AUD", "Trimmed Mean CPI m/m")}
N_REG, K_BINS, LOCK_MIN = 100, 40, 20
MAX_SPREAD_PIPS = 1.5


def news_times(events) -> list[int]:
    return sorted({int(e["time"]) for e in (events or []) if (e.get("currency"), e.get("title")) in EVENTS_C})


def rollover(t: int) -> bool:
    """20:45-22:30 UTC: the Liquidity Analyst's ROLLOVER_LOCKOUT (it holds Scenario C's 21:00-22:30)."""
    tod = t % DAY
    return 20 * H1S + 2700 <= tod < 22 * H1S + 1800


def channel(closes: list[float], i: int, n: int = N_REG) -> Optional[dict]:
    """3.1 over the n closes ending at i (bar index 1..n): β, α, the line at N, σ_e (N - 2), Z_reg, R²."""
    if i < n - 1:
        return None
    c = closes[i - n + 1:i + 1]
    ib = (n + 1) / 2
    cb = sum(c) / n
    sxx = sum((k - ib) ** 2 for k in range(1, n + 1))
    b = sum((k - ib) * (v - cb) for k, v in zip(range(1, n + 1), c)) / sxx
    a = cb - b * ib
    res = [v - (a + b * k) for k, v in zip(range(1, n + 1), c)]
    se = (sum(r * r for r in res) / (n - 2)) ** 0.5
    sst = sum((v - cb) ** 2 for v in c)
    line = a + b * n
    return {"beta": b, "alpha": a, "line": line, "se": se, "z": (c[-1] - line) / se if se > 0 else 0.0,
            "r2": 1 - sum(r * r for r in res) / sst if sst > 0 else 0.0}


def profile(h1, i: int, n: int = N_REG, k: int = K_BINS) -> Optional[dict]:
    """3.2 over the n H1 candles ending at i: K equal bins of [L_min, H_max]; each candle's volume goes to the bin of its
    typical price (H + L + C) / 3 (CHOICE); a feed without volume counts 1 per candle (a TPO profile, CHOICE). VPOC =
    the fullest bin's midpoint; VAL / VAH = the narrowest contiguous bins around it holding >= 70 % (ties: more volume)."""
    if i < n - 1:
        return None
    w = h1[i - n + 1:i + 1]
    lo, hi = min(x.low for x in w), max(x.high for x in w)
    if hi <= lo:
        return None
    step = (hi - lo) / k
    v = [0.0] * k
    for x in w:
        tp = (x.high + x.low + x.close) / 3
        q = min(int((tp - lo) / step), k - 1)
        v[q] += x.volume if getattr(x, "volume", 0) and x.volume > 0 else 1.0
    poc = max(range(k), key=lambda q: v[q])
    tot = sum(v)
    best = None
    for a in range(poc + 1):
        s = sum(v[a:poc + 1])
        for b in range(poc, k):
            if b > poc:
                s += v[b]
            if s >= 0.70 * tot:
                cand = (b - a, -s, a, b)
                if best is None or cand < best:
                    best = cand
                break
    _, _, a, b = best
    return {"vpoc": lo + (poc + 0.5) * step, "val": lo + a * step, "vah": lo + (b + 1) * step, "low": lo, "high": hi}


def zones(h1, at1, fr) -> list[dict]:
    """3.3: an H1 demand zone = the last bearish H1 candle (the base) before an up move that, within 3 candles (CHOICE),
    travels >= 2.0 ATR 14 H1 from the base's low AND closes above the last confirmed H1 fractal high (the BOS); zone =
    the base's [low, high] (CHOICE), known at the close of the BOS candle. The mirror for supply."""
    hi_f, lo_f = fr
    out = []
    for t in range(20, len(h1)):
        for d in (1, -1):
            base = t - 1
            x = h1[base]
            if not ((x.close < x.open) if d > 0 else (x.close > x.open)) or not at1[base]:
                continue
            for e in range(base + 1, min(base + 4, len(h1))):
                ref = next((q for q in range(e - 3, max(e - 40, 0), -1) if (hi_f[q] if d > 0 else lo_f[q])), None)
                if ref is None:
                    break
                lvl = h1[ref].high if d > 0 else h1[ref].low
                move = (max(y.high for y in h1[base + 1:e + 1]) - x.low) if d > 0 else (x.high - min(y.low for y in h1[base + 1:e + 1]))
                if move >= 2.0 * at1[base] and ((h1[e].close > lvl) if d > 0 else (h1[e].close < lvl)):
                    out.append({"dir": d, "lo": x.low, "hi": x.high, "base": base, "known": h1[e].time + H1S, "t0": x.time})
                    break
    return out


def tests_of(h1, z: dict, upto_t: int, times: Optional[list[int]] = None) -> int:
    """Touches of a zone after it was made (an H1 candle entering it after one outside it), before upto_t."""
    n, inside = 0, True
    k = bisect_left(times if times is not None else [y.time for y in h1], z["known"])
    for y in h1[k:]:
        if y.time + H1S > upto_t:
            break
        touch = (y.low <= z["hi"]) if z["dir"] > 0 else (y.high >= z["lo"])
        if touch and not inside:
            n += 1
        inside = touch
    return n


class L(F):
    def __init__(self, m5, h1, daily: Daily):
        super().__init__(m5, h1, daily, None)
        self.c1 = [x.close for x in h1]
        self.zs = zones(h1, self.at1, self.f1)
        self._ch, self._pr = {}, {}

    def ch(self, i: int) -> Optional[dict]:
        if i not in self._ch:
            c = channel(self.c1, i)
            if c and self.at1[i]:
                c["slope"] = 24 * c["beta"] / self.at1[i]
            self._ch[i] = c if c and "slope" in c else None
        return self._ch[i]

    def pr(self, i: int) -> Optional[dict]:
        if i not in self._pr:
            self._pr[i] = profile(self.h1, i)
        return self._pr[i]

    def fresh_zone(self, t: int, d: int, ext: float) -> Optional[tuple[dict, int]]:
        """The zone of direction d known at t that the extreme reaches (inside or through it), tested <= 1 time before."""
        best = None
        for z in self.zs:
            if z["dir"] != d or z["known"] > t or t - z["known"] > 30 * DAY:  # zones up to 30 days old (CHOICE)
                continue
            reach = (ext <= z["hi"]) if d > 0 else (ext >= z["lo"])
            if not reach:
                continue
            n = tests_of(self.h1, z, t - M15S, self.t1)
            if n <= 1 and (best is None or z["known"] > best[0]["known"]):
                best = (z, n)
        return best


def _session_b(tc: int) -> bool:
    tod = tc % DAY
    return 12 * H1S + 1800 < tod <= 16 * H1S or tod > 23 * H1S or tod <= 4 * H1S


def _swing_swept(l: L, j: int, d: int, ext: float) -> Optional[tuple[str, float]]:
    m15 = l.m15
    hi_f, lo_f = l.f15
    for q in range(j - 3, max(j - 48, 0), -1):
        if not (lo_f[q] if d > 0 else hi_f[q]):
            continue
        lv = m15[q].low if d > 0 else m15[q].high
        if all(((m15[r].low >= lv) if d > 0 else (m15[r].high <= lv)) for r in range(q + 1, j)) and ((ext < lv) if d > 0 else (ext > lv)):
            return "M15 swing", lv
    i1 = l.i1(m15[j].time + M15S)
    sw = (l.s1["sl"] if d > 0 else l.s1["sh"])[i1] if i1 >= 0 else None
    if sw and ((ext < sw[0]) if d > 0 else (ext > sw[0])) and ((m15[j - 1].low >= sw[0]) if d > 0 else (m15[j - 1].high <= sw[0])):
        return "H1 swing", sw[0]
    return None


def _entry(l: L, j: int, d: int, end: int):
    z = l.ob_fvg(j, min(j + 8, len(l.m15)), d, 0)
    if not z or z["t_set"] > end:
        return None
    ce = (z["fvg"][0] + z["fvg"][1]) / 2
    entry = ce if z["ob"][0] <= ce <= z["ob"][1] else z["ob"][1] if d > 0 else z["ob"][0]
    return z, entry


def scenario_a(l: L, cost: float, out: list, watch: list) -> None:
    """A: at an M15 close (any hour but the rollover), on the last closed H1: |β~| <= 1.25; the candle's extreme at
    |Z_reg| >= 1.90 against the H1 line, beyond VAL / VAH, sweeping an intact M15 / H1 swing into a fresh zone (tested
    <= 1); then the M15 MSS + OB + FVG toward VPOC within 8 candles (EUR/USD's definition, as the CHoCH with displacement).
    Limit at the OB proximal edge / the 50 % FVG inside it, valid 8 M15 (CHOICE). SL = the zone's distal edge (or the
    sweep extreme when it went further, CHOICE) ∓ 0.30 ATR 14 M15. TP1 VPOC (50 % closed, CHOICE), TP2 the opposite VA
    boundary at RR >= 2.4. Held 48 h (CHOICE)."""
    m15, m5 = l.m15, l.m5
    end = m5[-1].time + M5S
    used = set()
    for j in range(60, len(m15)):
        x = m15[j]
        tc = x.time + M15S
        if tc > end or rollover(tc):
            continue
        i1 = l.i1(tc)
        c = l.ch(i1)
        if not c or abs(c["slope"]) > 1.25:
            continue
        for d in (1, -1):
            ext = x.low if d > 0 else x.high
            zx = (ext - c["line"]) / c["se"]
            if not ((zx <= -1.90) if d > 0 else (zx >= 1.90)):
                continue
            p = l.pr(i1)
            if not p or not ((ext < p["val"]) if d > 0 else (ext > p["vah"])):
                continue
            sw = _swing_swept(l, j, d, ext)
            fz = l.fresh_zone(tc, d, ext)
            steps = [(f"Structured channel |β~| {abs(c['slope']):.2f} <= 1.25", True, ""),
                     (f"Z_reg {zx:+.2f} beyond ±1.90, {'below VAL' if d > 0 else 'above VAH'}", True, f"VAL {p['val']:.5f} · VAH {p['vah']:.5f}"),
                     ("Swept a prior swing", bool(sw), f"{sw[0]} {sw[1]:.5f}" if sw else "none"),
                     ("Into a fresh H1 " + ("demand" if d > 0 else "supply") + " zone (tested <= 1)", bool(fz),
                      f"{fz[0]['lo']:.5f}-{fz[0]['hi']:.5f} · {fz[1]} tests" if fz else "none")]
            if not (sw and fz):
                watch.append({"sid": "A", "time": tc, "dir": d, "steps": steps})
                continue
            zone = fz[0]
            if (id(zone), d) in used:
                continue
            used.add((id(zone), d))
            e = _entry(l, j, d, end)
            if not e:
                watch.append({"sid": "A", "time": tc, "dir": d, "steps": steps + [("M15 CHoCH + displacement + FVG toward VPOC", False, "waiting")]})
                continue
            z, entry = e
            j_set = l.j15(z["t_set"])
            far = min(zone["lo"], ext) if d > 0 else max(zone["hi"], ext)
            sl = far - d * 0.30 * (l.at15[j_set] or 0)
            tp1, tp2 = p["vpoc"], (p["vah"] if d > 0 else p["val"])
            k0 = m5_index_at_close(l.t5, z["t_set"])
            if k0 is None:
                continue
            steps += [("M15 CHoCH + displacement + FVG toward VPOC", True, f"OB {z['ob'][0]:.5f}-{z['ob'][1]:.5f}")]
            s = _make("AUDCAD", "A", d, m5, k0, entry, sl, tp1, tp2, 0.5, False, 24, z["t_set"] + 48 * H1S, steps,
                      {"ob": (z["ob"][1], z["ob"][0], m15[z["j_ob"]].time), "zone": (zone["lo"], zone["hi"], zone["t0"]), "sweep": (ext, x.time),
                       "levels": {"VPOC": p["vpoc"], "VAH": p["vah"], "VAL": p["val"]}}, cost, zone=(min(z["ob"]), max(z["ob"])), be_off=None)
            if s:
                s.update(scenario="A", tp2Name="VAH" if d > 0 else "VAL", slope=c["slope"], zreg=zx, zoneTests=fz[1], needRR=2.4)
                out.append(s)


def scenario_b(l: L, cost: float, out: list, watch: list) -> None:
    """B: 0.60 < |β~| <= 1.60 (d = the slope's sign); an M15 close in 12:30-16:00 or 23:00-04:00 UTC whose extreme
    reaches the line ∓ 1.75 σ_e AND an H1 zone of direction d (fresh: tested <= 1, the 3.3 rule, CHOICE); then the M15
    MSS + OB + FVG with the trend within 8 candles: a limit as in A. SL the zone's distal edge ∓ 0.30 ATR M15 (the Risk
    Manager); TP the line ± 1.75 σ_e at the setup (CHOICE: not projected forward) at >= 2.8 R. Held 48 h (CHOICE)."""
    m15, m5 = l.m15, l.m5
    end = m5[-1].time + M5S
    used = set()
    for j in range(60, len(m15)):
        x = m15[j]
        tc = x.time + M15S
        if tc > end or not _session_b(tc) or rollover(tc):
            continue
        i1 = l.i1(tc)
        c = l.ch(i1)
        if not c or not (0.60 < abs(c["slope"]) <= 1.60):
            continue
        d = 1 if c["slope"] > 0 else -1
        band = c["line"] - d * 1.75 * c["se"]
        ext = x.low if d > 0 else x.high
        if not ((ext <= band) if d > 0 else (ext >= band)):
            continue
        fz = l.fresh_zone(tc, d, ext)
        steps = [(f"Sloping channel β~ {c['slope']:+.2f} (0.60-1.60)", True, ""), (f"Pullback to the {'-' if d > 0 else '+'}1.75 σ_e line", True, f"{band:.5f}"),
                 ("At an H1 " + ("demand" if d > 0 else "supply") + " zone (tested <= 1)", bool(fz), f"{fz[0]['lo']:.5f}-{fz[0]['hi']:.5f}" if fz else "none")]
        if not fz:
            watch.append({"sid": "B", "time": tc, "dir": d, "steps": steps})
            continue
        zone = fz[0]
        if (id(zone), d) in used:
            continue
        used.add((id(zone), d))
        e = _entry(l, j, d, end)
        if not e:
            watch.append({"sid": "B", "time": tc, "dir": d, "steps": steps + [("M15 MSS with the trend", False, "waiting")]})
            continue
        z, entry = e
        j_set = l.j15(z["t_set"])
        far = min(zone["lo"], ext) if d > 0 else max(zone["hi"], ext)
        sl = far - d * 0.30 * (l.at15[j_set] or 0)
        tp = c["line"] + d * 1.75 * c["se"]
        k0 = m5_index_at_close(l.t5, z["t_set"])
        if k0 is None:
            continue
        steps.append(("M15 MSS + OB + FVG with the trend", True, f"OB {z['ob'][0]:.5f}-{z['ob'][1]:.5f}"))
        s = _make("AUDCAD", "B", d, m5, k0, entry, sl, None, tp, 1.0, False, 24, z["t_set"] + 48 * H1S, steps,
                  {"ob": (z["ob"][1], z["ob"][0], m15[z["j_ob"]].time), "zone": (zone["lo"], zone["hi"], zone["t0"]), "sweep": (ext, x.time)}, cost,
                  zone=(min(z["ob"]), max(z["ob"])), be_off=None)
        if s:
            s.update(scenario="B", tp2Name=f"the {'+' if d > 0 else '-'}1.75 σ_e line", slope=c["slope"], zreg=(ext - c["line"]) / c["se"], zoneTests=fz[1], needRR=2.8)
            out.append(s)


def devil(l: L, s: dict) -> tuple[float, list[str]]:
    """Failure probability (CHOICE: the weights): |β~| > 1.60 against the trade +45 · the zone tapped >= 2 times +40 ·
    within 2 h before the 21:00 rollover +30. Hard veto >= 65 %."""
    t, d = s["time"], s["dir"]
    p, w = 0.0, []
    sl_ = s.get("slope")
    if sl_ is not None and abs(sl_) > 1.60 and (sl_ > 0) != (d > 0):
        p += 45
        w.append(f"Channel slope {sl_:+.2f} > 1.60 against us: a macro trend")
    if s.get("zoneTests", 0) >= 2:
        p += 40
        w.append(f"Zone tapped {s['zoneTests']} times: resting orders used up")
    if 19 * H1S <= t % DAY < 21 * H1S:
        p += 30
        w.append("Within 2 h of the 21:00 rollover spread blowout")
    return min(p, 100.0), w


def scan(m5, h1, cost: float, news_events=None, d1=None, spread_pips: Optional[float] = None) -> tuple[list, list]:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    l = L(m5, h1, daily)
    out, watch = [], []
    if len(h1) < 160 or len(l.m15) < 120:
        return out, watch
    scenario_a(l, cost, out, watch)
    scenario_b(l, cost, out, watch)
    out.sort(key=lambda x: x["time"])
    nw = news_times(news_events) if news_events is not None else None
    for s in out:
        t = s["time"]
        if nw and not s["market"]:  # Scenario C: a pending limit is pulled 20 min before a release
            s["result"] = run(m5, s["index"], s["dir"], s["entry"], s["sl"], s["tp1"], s["tp"], s["part"], False, s["expiry"], s["holdUntil"], cost,
                              None, nw, None, None, None, LOCK_MIN)
        p, worries = devil(l, s)
        s["devilP"], s["worries"] = p, worries
        near = [n for n in (nw or []) if abs(n - t) <= LOCK_MIN * 60]
        sp = spread_pips
        need = s.get("needRR", 2.4)
        s["checklist"] = [
            (f"1 · {NAMES[s['sid']]}", True, STRATEGY_NAME),
            ("2 · Scenario C: no RBA / BOC / CAD jobs / AUD CPI ±20 min, not in the 20:45-22:30 rollover", not near and not rollover(t),
             "not checked (no news history)" if nw is None else (", ".join(hm(n) for n in near) + " UTC" if near else "clear")),
            (f"3 · Risk Manager: RR {s['rr']:.2f} (>= {need:g}, never under 2.20)", s["rr"] >= max(need, 2.2) - 1e-9, s.get("tp2Name", "")),
            (f"4 · Risk Manager: spread <= {MAX_SPREAD_PIPS:g} pips", sp is None or sp <= MAX_SPREAD_PIPS, "not known" if sp is None else f"{sp:g} pips"),
            ("5 · Lot for 1 % risk (CAD pip value in USD)", True, ""),
            (f"6 · Devil's Advocate: failure probability {p:.0f} % (< 65 %)", p < 65, "; ".join(worries) or "no trap found"),
        ]
        s["pass"] = all(ok for _, ok, _ in s["checklist"])
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["checklist"].append(("7 · One AUD/CAD trade at a time", False, "the previous setup is still pending or open"))
            continue
        r = s["result"]
        busy = m5[r["at"]].time + M5S if "at" in r else 1 << 62
    return out, sorted(watch, key=lambda w: w["time"])


UI = {"VALID": "ok", "WAIT": "wait", "WARNING": "warn", "VETO": "veto", "STANDBY": "wait"}
ROLE = {"lead_strategist": ("lead", "Lead Strategist"), "structure_analyst": ("structure", "Structure Analyst"),
        "liquidity_session_analyst": ("liquidity", "Liquidity & Session Analyst"), "entry_specialist": ("entry", "Entry Specialist"),
        "risk_manager": ("risk", "Risk Manager"), "backtest_engineer": ("backtest", "Backtest Engineer"), "devils_advocate": ("devil", "Devil's Advocate")}


def _session(t: int) -> str:
    tod = t % DAY
    if rollover(t):
        return "ROLLOVER_LOCKOUT"
    if tod >= 23 * H1S or tod < 5 * H1S:
        return "SYDNEY_TOKYO"
    if 12 * H1S + 1800 <= tod < 16 * H1S + 1800:
        return "TORONTO_NY"
    return "LATE_NY" if tod >= 16 * H1S + 1800 else "LONDON" if tod >= 7 * H1S else "PRE_LONDON"


def report(m5, h1, now: int, setups: list, watch: list, research: Optional[dict], news_events, d1=None,
           usd_per_pip: Optional[float] = None, spread_pips: Optional[float] = None) -> dict:
    daily = Daily(d1 if d1 else resample(h1, DAY))
    l = L(m5, h1, daily)
    t = m5[-1].time + M5S
    price = m5[-1].close
    D = t - t % DAY
    i1 = l.i1(t)
    c = l.ch(i1) if i1 >= 0 else None
    p = l.pr(i1) if i1 >= 0 else None
    zr = (price - c["line"]) / c["se"] if c and c["se"] else None
    where = "n/a" if not p else "Below VAL" if price < p["val"] else "Above VAH" if price > p["vah"] else "Balanced"
    zs_now = [z for z in l.zs if z["known"] <= t and t - z["known"] <= 30 * DAY and tests_of(h1, z, t, l.t1) <= 1 and
              (z["hi"] < p["val"] if z["dir"] > 0 else z["lo"] > p["vah"]) ] if p else []
    at_zone = next((z for z in zs_now if z["lo"] <= price <= z["hi"]), None)
    if zr is not None and at_zone:
        sb = f"H1 Channel Z={zr:+.2f} | {where} | At H1 {'Demand' if at_zone['dir'] > 0 else 'Supply'}"
    elif zr is not None:
        sb = f"H1 Channel Z={zr:+.2f} | VPOC: {p['vpoc']:.4f} | {where}" if p else f"H1 Channel Z={zr:+.2f}"
    else:
        sb = "H1 Channel: not enough candles"
    st_ok = zr is not None and abs(zr) >= 1.85 and where != "Balanced"
    structure_a = {"ui_badge_summary": badge(sb), "status": "VALID" if st_ok else "WAIT",
                   "channel_z_score": None if zr is None else round(zr, 2), "channel_slope_normalized": None if not c else round(c["slope"], 2),
                   "channel_r_squared": None if not c else round(c["r2"], 2), "regression_midline": None if not c else c["line"],
                   "channel_175": {"upper": c["line"] + 1.75 * c["se"], "lower": c["line"] - 1.75 * c["se"]} if c else None,
                   "vpoc": p and p["vpoc"], "vah": p and p["vah"], "val": p and p["val"],
                   "fresh_zones": [{"type": "DEMAND" if z["dir"] > 0 else "SUPPLY", "low": z["lo"], "high": z["hi"]} for z in zs_now[-4:]]}
    sess = _session(t)
    asia = hilo(span(m5, l.t5, D, min(t, D + 6 * H1S)))
    pd = hilo(span(m5, l.t5, D - DAY, D)) or hilo(span(m5, l.t5, D - 3 * DAY, D - 2 * DAY + 1))
    bsl = sorted({round(v, 5) for v in [pd and pd[0], asia and asia[0], c and c["line"] + 1.9 * c["se"], p and p["vah"]] + l.eq_levels(t, -1) if v and v > price})
    ssl = sorted({round(v, 5) for v in [pd and pd[1], asia and asia[1], c and c["line"] - 1.9 * c["se"], p and p["val"]] + l.eq_levels(t, 1) if v and v < price}, reverse=True)
    live = [s for s in setups if s["result"]["state"] in ("PENDING", "ACTIVE")]
    cand = next((s for s in reversed(live) if s["pass"]), live[-1] if live else None)
    w = watch[-1] if watch and watch[-1]["time"] >= now - 3 * H1S else None
    swept = cand is not None or bool(w and any(s_[0].startswith("Swept") and s_[1] for s_ in w["steps"]))
    sname = {"ROLLOVER_LOCKOUT": "Rollover lockout", "SYDNEY_TOKYO": "Sydney/Tokyo AUD", "TORONTO_NY": "Toronto CAD Session", "LATE_NY": "Pre-Rollover caution",
             "LONDON": "London (off-window)", "PRE_LONDON": "Off-window"}[sess]
    if swept:
        ext = cand["geo"]["sweep"][0] if cand else ""
        lq_b = f"{'Low' if (cand or w)['dir'] > 0 else 'High'} swept at {ext if isinstance(ext, str) else f'{ext:.4f}'} | {sname}"
    else:
        lq_b = (f"BSL at {bsl[0]:.4f} | SSL at {ssl[0]:.4f} | " if bsl and ssl else "") + sname
    liquidity_a = {"ui_badge_summary": badge(lq_b), "status": "VETO" if sess == "ROLLOVER_LOCKOUT" else "VALID" if swept else "WAIT",
                   "active_session": sess, "asia_range": {"high": asia[0], "low": asia[1]} if asia else None,
                   "bsl_targets": bsl[:4], "ssl_targets": ssl[:4], "sweep_detected": swept}
    if cand:
        entry_a = {"ui_badge_summary": badge(f"{'Buy' if cand['dir'] > 0 else 'Sell'} limit {cand['entry']:.5f} | TP1 {(cand['tp1'] or cand['tp']):.5f}"),
                   "status": "VALID", "entry_valid": True, "zone": [min(cand["zone"]), max(cand["zone"])], "tp1": cand.get("tp1"), "tp2": cand["tp"]}
        rd = abs(cand["entry"] - cand["sl"]) / PIP
        pv = usd_per_pip or 7.3
        lots = int(10000 * 0.01 / (rd * pv) * 100) / 100 if rd else 0
        ok = cand["checklist"][2][1] and cand["checklist"][3][1]
        risk_a = {"ui_badge_summary": badge(f"Risk 1% | SL {rd:.1f}p | {lots} lot/$10k | RR {cand['rr']:.1f}" if ok else f"Rejected: RR {cand['rr']:.1f} / spread"),
                  "status": "VALID" if ok else "VETO", "risk_percent": 1.0, "position_size_lots": lots, "usd_per_pip_per_lot": pv, "spread_pips": spread_pips}
    else:
        if zr is not None and abs(zr) < 1.50:
            eb = "No clean zone: price at VPOC magnet" if p and abs(price - p["vpoc"]) <= 0.25 * (p["vah"] - p["val"]) else "No clean zone: price inside Value Area equilibrium"
        else:
            eb = "No clean zone: awaiting M15 CHoCH toward VPOC"
        entry_a = {"ui_badge_summary": eb, "status": "WAIT", "entry_valid": False}
        risk_a = {"ui_badge_summary": "Nothing to size", "status": "STANDBY", "risk_percent": 0.0, "position_size_lots": 0.0}
    sid = cand["sid"] if cand else "A"
    meas = (((research or {}).get("strategies") or {}).get(sid) or {}).get("all")
    base = BASELINE[sid]
    old = l.ch(i1 - 50) if i1 >= 50 else None
    stab = (c["se"] / old["se"]) if c and old and old["se"] else None
    stable = stab is not None and 0.67 <= stab <= 1.5  # CHOICE: σ_e within ±50 % of 50 H1 bars ago
    if meas and meas.get("trades", 0) >= 30:
        bt_b, bt_s = f"Data READY: Channel VPOC reversion WR {meas['winRate']}%", "VALID" if stable else "WARNING"
    else:
        bt_b, bt_s = f"Data LIMITED: N={(meas or {}).get('trades', 0)} · R²={c['r2']:.2f}" if c else "Data LIMITED: no channel", "WARNING"
    backtest_a = {"ui_badge_summary": badge(bt_b), "status": bt_s, "historical_win_rate": base["winRate"] / 100, "expected_value_r": base["expectancyR"],
                  "channel_r_squared": None if not c else round(c["r2"], 3), "residual_stability": None if stab is None else round(stab, 2),
                  "residuals_stable": stable, "measured": meas, "spec_benchmark": base}
    nw = news_times(news_events) if news_events is not None else None
    near = [n for n in (nw or []) if abs(n - now) <= LOCK_MIN * 60]
    if cand:
        pf, worries = cand["devilP"], cand["worries"]
    else:
        pf, worries = 0.0, []
        if sess == "ROLLOVER_LOCKOUT":
            pf, worries = 90.0, ["Rollover: AUD/CAD spreads 4-10 pips"]
        elif near:
            pf, worries = 90.0, [f"Scenario C: release at {hm(near[0])} UTC"]
        elif zr is not None and abs(zr) < 1.10:
            pf, worries = 79.0, ["Entering near VPOC has 50/50 coin-flip odds"]
        elif c and abs(c["slope"]) > 1.60:
            pf, worries = 70.0, [f"Slope {c['slope']:+.2f}: a macro trend, not a channel"]
        elif 19 * H1S <= t % DAY < 21 * H1S:
            pf, worries = 30.0, ["Within 2 h of the 21:00 rollover"]
    devil_a = {"ui_badge_summary": badge("My worry: " + (worries[0] if worries else "nothing fatal found")), "status": "VETO" if pf >= 65 else "WARNING" if pf else "VALID",
               "failure_probability": round(pf / 100, 2), "veto_active": pf >= 65, "worries": worries}
    st = 100 if st_ok else 50 if zr is not None and abs(zr) >= 1.10 else 0
    lq = 100 if liquidity_a["status"] == "VALID" else 0 if sess == "ROLLOVER_LOCKOUT" else 50
    en = 100 if cand else 0
    bt = 100 if bt_s == "VALID" else 0
    score = round(0.25 * st + 0.25 * lq + 0.20 * en + 0.15 * bt + 0.15 * (100 - pf), 1)
    execute = bool(cand and cand["pass"] and score >= 78 and not devil_a["veto_active"] and risk_a["status"] == "VALID" and sess != "ROLLOVER_LOCKOUT" and not near)
    if execute:
        decision = "BUY_LIMIT" if cand["dir"] > 0 else "SELL_LIMIT"
        lead_b = f"{decision.replace('_', ' ')} {cand['entry']:.5f} | SL {cand['sl']:.5f} | TP {cand['tp']:.5f}"
        plan = {"order_type": decision, "entry_price": cand["entry"], "stop_loss": cand["sl"], "tp1_price": cand.get("tp1"),
                "tp1_close": cand["part"] if cand.get("tp1") else None, "tp2_price": cand["tp"], "scenario_id": SCEN[cand["sid"]]}
        scen = SCEN[cand["sid"]]
    else:
        decision, plan = "NO_TRADE", None
        if sess == "ROLLOVER_LOCKOUT" or near:
            scen, lead_b = SCEN["C"], "No trade: rollover lockout" if sess == "ROLLOVER_LOCKOUT" else f"No trade: release {hm(near[0])} UTC"
        elif cand:
            scen, lead_b = SCEN[cand["sid"]], f"No trade: consensus {score:.0f} < 78" if score < 78 else "No trade: a veto is active"
        elif zr is None or abs(zr) < 1.10:
            scen = SCEN["D"]
            lead_b = f"No trade: Price at VPOC {p['vpoc']:.4f} (wait for channel edge)" if p else "No trade: no channel yet"
        else:
            scen = SCEN["B"] if c and 0.60 < abs(c["slope"]) <= 1.60 else SCEN["A"]
            lead_b = f"No trade: Z={zr:+.2f}, I wait for the channel edge + M15 CHoCH"
    lead_a = {"ui_badge_summary": badge(lead_b), "status": "VALID" if execute else "VETO" if devil_a["veto_active"] and cand else "WAIT",
              "reasoning": (f"Z_reg {structure_a['channel_z_score']}, slope {structure_a['channel_slope_normalized']} ATR/24h, VPOC "
                            f"{p['vpoc']:.5f} (VAL {p['val']:.5f} · VAH {p['vah']:.5f}), {sess}" if p else sess) +
                           f"; consensus {score} (CHOICE: the gold spec's weights, >= 78)",
              "execution_plan": plan}
    agents = {"lead_strategist": lead_a, "structure_analyst": structure_a, "liquidity_session_analyst": liquidity_a, "entry_specialist": entry_a,
              "risk_manager": risk_a, "backtest_engineer": backtest_a, "devils_advocate": devil_a}
    contract = {"pair": "AUD/CAD", "strategy_name": STRATEGY_NAME, "timestamp_utc": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scenario_active": scen, "consensus_score": score, "final_decision": decision, "agents": agents}
    ui = []
    for kk in ("lead_strategist", "structure_analyst", "liquidity_session_analyst", "entry_specialist", "risk_manager", "backtest_engineer", "devils_advocate"):
        ag = agents[kk]
        key, role = ROLE[kk]
        lines = [f"{x}: {y}" for x, y in ag.items() if x not in ("ui_badge_summary", "status") and y not in (None, [], {})]
        ui.append({"key": key, "role": role, "status": UI[ag["status"]], "finding": ag["ui_badge_summary"], "lines": lines, "statusMd": ag["status"]})
    return {"contract": contract, "agents": ui, "execute": execute, "candidate": cand}
