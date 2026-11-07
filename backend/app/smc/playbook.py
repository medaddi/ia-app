"""
Each pair's strategies, from the user's guide "Istratijiyat Tadawoul L-Azwaj O D-Dhab" (دليل التداول المؤسسي والكمي
للأزواج الستة, data to early November 2026), section 6a "the master execution table", coded rule by rule. They replace
every earlier strategy (the SMC S1–S4 and the first playbook): each team trades only its pair's strategies below.

  XAU/USD  P   ICT Silver Bullet / NY killzone: 09:30-10:15 NY sweep of the Asian / London / 9:30 levels, M5 MSS,
               FVG formed 10:00-11:00 NY, limit at its start, stop $1 beyond the sweep, TP the opposite pool (>= 1:2)
  EUR/USD  P1  London Judas swing: H1 bias, false break of the NY midnight open and the Asian range 02:00-05:00 NY,
               M5 MSS + FVG, limit at the FVG, stop beyond the false move, TP the Asian opposite side (1:2)
           P2  SnapBack 3σ: H1 close outside Bollinger (16, 3.0) with RSI 14 < 30 / > 70, SL = TP = 2 ATR 14 (1:1)
  GBP/USD  P1  London / overlap sweep: Asian high / low taken 07:00-09:00 or 12:00-14:00 UTC, MSS + FVG, stop >= 0.45
               ADR20, TP 1.0 ADR20
           P2  EMA pullback: price > EMA 20 > 50 > 200 rising on H1 and H4, ADX > 25, pullback to EMA 20 / 50 at a
               flipped swing, RSI back to the middle, reversal candle 08:00-15:00 UTC, stop >= 0.45 ADR20, TP 1.0 ADR20
  EUR/CHF  P   time-filtered 3σ mean reversion: ADR regime + ADX < 30, a 3-touch H4 level, H1 close outside BB (16, 3)
               with RSI 30 / 70, only 07:00-13:00 or 15:30-18:00 UTC; stop 0.5 ADR20, TP the mean (1:1 to 1:1.5)
  AUD/CAD  P   commodity range reversion: the same at a 3-touch H4 range edge, only 00:00-11:00 UTC (never 14:00),
               stop 0.5 ADR20, TP 0.8 ADR20
  AUD/CHF  P   risk-on carry swing (longs, the guide's preferred side): above a rising EMA 200 on H4 and H1, pullback
               to EMA 20 / 50 on a higher low, bullish reversal close 06:00-15:00 UTC; stop 0.7 ADR20, TP1 1.0 ADR20
               (half), TP2 2.0 ADR20. The guide's macro gate (S&P 500, VIX, iron ore) is NOT checked: no such data here.

The guide's own risk rules (section 6b) are the checklist: 1 % per trade, no red-folder news around the entry, the
reward each strategy asks, the correlation cap (no full-risk trades the same way on EUR/USD + GBP/USD, AUD/CAD + AUD/CHF,
EUR/CHF + AUD/CHF: checked across the six teams before any alert) and the ADR regime (mean reversion stops when the range
expands: ADR20 / ADR250 >= 1.40 or ADR5 / ADR20 > 1.40; sweeps and trends skip a compressed market, ADR5 / ADR20 < 0.60).

The win rates quoted in the guide (SnapBack 62 % / 61.5 % documented by SteadyPips; ICT 75-80 % "not guaranteed") are its
claims: smc/tools/playbook_test.py measures every strategy on stored Dukascopy candles with costs, shown next to them.

Rules of the code: a candle only knows the candles before it; a swing exists from the candle that confirms it (2 later);
a setup is dated at the close of the last candle it needs; every trade is followed on M5, the stop before the target
inside a candle. New York times follow New York daylight saving (zoneinfo). Where the guide leaves a choice, the code
says "CHOICE" next to it.
"""

from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

M5S, M15S, H1S, H4S, DAY = 300, 900, 3600, 14400, 86400
NY = ZoneInfo("America/New_York")

STRATEGIES = {"XAUUSD": ["P"], "EURUSD": ["P1", "P2"], "GBPUSD": ["P1", "P2"], "EURCHF": ["P"], "AUDCAD": ["P"], "AUDCHF": ["P"]}
NAMES = {
    "XAUUSD": {"P": "ICT Silver Bullet / NY killzone sweep + FVG / OTE"},
    "EURUSD": {"P1": "London Judas swing", "P2": "SnapBack 3σ mean reversion"},
    "GBPUSD": {"P1": "London / NY overlap liquidity sweep", "P2": "EMA 20/50/200 trend pullback"},
    "EURCHF": {"P": "Time-filtered 3σ mean reversion"},
    "AUDCAD": {"P": "Commodity range reversion"},
    "AUDCHF": {"P": "Risk-on carry swing pullback"},
}
CLAIMED = {  # what the guide says, word for word in substance (HYPOTHESIS until measured)
    ("XAUUSD", "P"): "75-80 % in ICT studies (not guaranteed); R:R 1:2 to 1:4",
    ("EURUSD", "P1"): "no win rate given; R:R 1:2 (up to 1:3)",
    ("EURUSD", "P2"): "62.0 % (SteadyPips, 79 trades, 1:1, Jan 2024 - Mar 2026)",
    ("GBPUSD", "P1"): "no win rate given; R:R 1:2 to 1:3",
    ("GBPUSD", "P2"): "no win rate given (plain EMA crossovers: 26.2 %); R:R 1:2",
    ("EURCHF", "P"): "~60 %+ in ranges (from the 3σ model); R:R 1:1 to 1:1.5",
    ("AUDCAD", "P"): "~60 %+ in calm sessions; R:R 1:1.5 to 1:2",
    ("AUDCHF", "P"): "high when VIX, iron ore and rates agree (no number); R:R 1:2.5 to 1:3",
}
MIN_RR = {("XAUUSD", "P"): 2.0, ("EURUSD", "P1"): 2.0, ("EURUSD", "P2"): 1.0, ("GBPUSD", "P1"): 2.0, ("GBPUSD", "P2"): 2.0,
          ("EURCHF", "P"): 1.0, ("AUDCAD", "P"): 1.5, ("AUDCHF", "P"): 2.0}
MEAN_REVERSION = {("EURUSD", "P2"), ("EURCHF", "P"), ("AUDCAD", "P")}
NEWS_MIN = 15  # CHOICE: no red-folder release from 15 min before to 15 min after the entry (the guide: wait 10-15 min)


def team_name(key: str) -> str:
    return " + ".join(NAMES[key].values())


# ---------------------------------------------------------------- indicators (each value uses candles up to i only)
class _Bar:
    __slots__ = ("time", "open", "high", "low", "close")

    def __init__(self, t, o, h, lo, c):
        self.time, self.open, self.high, self.low, self.close = t, o, h, lo, c


def resample(c, step: int) -> list:
    """Bigger candles from smaller ones (UTC slots). A slot is returned once it has its last candle (closed)."""
    out, cur = [], None
    for x in c:
        t = x.time - x.time % step
        if cur is None or cur.time != t:
            cur = _Bar(t, x.open, x.high, x.low, x.close)
            out.append(cur)
        else:
            cur.high, cur.low, cur.close = max(cur.high, x.high), min(cur.low, x.low), x.close
    return out


def ema(vals: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(vals)
    if len(vals) < n:
        return out
    k, e = 2 / (n + 1), sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out


def sma_std(vals: list[float], n: int) -> tuple[list, list]:
    m: list[Optional[float]] = [None] * len(vals)
    s: list[Optional[float]] = [None] * len(vals)
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        mu = sum(w) / n
        m[i], s[i] = mu, (sum((v - mu) ** 2 for v in w) / n) ** 0.5
    return m, s


def rsi(vals: list[float], n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(vals)
    if len(vals) <= n:
        return out
    g = sum(max(vals[i] - vals[i - 1], 0) for i in range(1, n + 1)) / n
    lo = sum(max(vals[i - 1] - vals[i], 0) for i in range(1, n + 1)) / n
    for i in range(n, len(vals)):
        if i > n:
            ch = vals[i] - vals[i - 1]
            g, lo = (g * (n - 1) + max(ch, 0)) / n, (lo * (n - 1) + max(-ch, 0)) / n
        out[i] = 100.0 if lo == 0 else 100 - 100 / (1 + g / lo)
    return out


def atr(c, n: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(c)
    tr = [c[0].high - c[0].low] + [max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close) for i in range(1, len(c))]
    if len(c) < n:
        return out
    a = sum(tr[:n]) / n
    out[n - 1] = a
    for i in range(n, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def adx(c, n: int = 14) -> list[Optional[float]]:
    """Wilder's ADX."""
    out: list[Optional[float]] = [None] * len(c)
    if len(c) < 2 * n + 1:
        return out
    tr, pdm, mdm = [], [], []
    for i in range(1, len(c)):
        up, dn = c[i].high - c[i - 1].high, c[i - 1].low - c[i].low
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
        tr.append(max(c[i].high, c[i - 1].close) - min(c[i].low, c[i - 1].close))
    s_tr, s_p, s_m = sum(tr[:n]), sum(pdm[:n]), sum(mdm[:n])
    dxs = []
    for k in range(n, len(tr) + 1):
        if k > n:
            s_tr, s_p, s_m = s_tr - s_tr / n + tr[k - 1], s_p - s_p / n + pdm[k - 1], s_m - s_m / n + mdm[k - 1]
        pdi, mdi = (100 * s_p / s_tr, 100 * s_m / s_tr) if s_tr else (0.0, 0.0)
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
        if len(dxs) == n:
            a = sum(dxs) / n
            out[k] = a
        elif len(dxs) > n:
            a = (a * (n - 1) + dxs[-1]) / n
            out[k] = a
    return out


def fractals(c, w: int = 2) -> tuple[list, list]:
    """Swing highs / lows (w candles each side). The swing at j is KNOWN only at candle j + w."""
    n = len(c)
    hi: list[bool] = [False] * n
    lo: list[bool] = [False] * n
    for j in range(w, n - w):
        if all(c[j].high > c[j - k].high and c[j].high >= c[j + k].high for k in range(1, w + 1)):
            hi[j] = True
        if all(c[j].low < c[j - k].low and c[j].low <= c[j + k].low for k in range(1, w + 1)):
            lo[j] = True
    return hi, lo


def body(x) -> float:
    return abs(x.close - x.open)


def m5_index_at_close(m5_times: list[int], t_close: int) -> Optional[int]:
    """The M5 candle whose close is t_close or the last one closed before it."""
    k = bisect_right(m5_times, t_close - M5S) - 1
    return k if k >= 0 else None


# ---------------------------------------------------------------- the trade, followed on M5
def run(m5, k0: int, d: int, entry: float, sl: float, tp1: Optional[float], tp: float, part: float, market: bool,
        expiry: int, hold_until: int, cost: float, events: Optional[list] = None, news: Optional[list[int]] = None) -> dict:
    """A limit (or a market order at the close of candle k0) followed candle by candle on M5:
    PENDING → FILLED → TP1 (close `part`, stop to entry) → TP / STOP / BE_STOP / TIME, or EXPIRED / MISSED (target first).
    `hold_until`: unix time the rest is closed at market. Returns state, fill, at, r (in R, cost included)."""
    log = events if events is not None else []
    n = len(m5)
    risk = abs(entry - sl)
    if risk <= 0:
        return {"state": "INVALID"}
    if market:
        fill, start = k0, k0 + 1
        log.append((k0, "FILLED", entry))
    else:
        fill, end = None, min(n, k0 + 1 + expiry)
        for i in range(k0 + 1, end):
            x = m5[i]
            if news:  # the guide's news rule: a pending limit is pulled from 15 min before a red-folder release to 15 min after
                j = bisect_left(news, x.time - NEWS_MIN * 60)
                if j < len(news) and news[j] < x.time + M5S + NEWS_MIN * 60:
                    log.append((i, "EXPIRED", entry))
                    return {"state": "EXPIRED", "at": i, "news": news[j]}
            if (d > 0 and x.low <= entry) or (d < 0 and x.high >= entry):
                fill = i
                break
            if (d > 0 and x.high >= tp) or (d < 0 and x.low <= tp):
                log.append((i, "MISSED", entry))
                return {"state": "MISSED", "at": i}
        if fill is None:
            if end == n and n - 1 - k0 < expiry:
                return {"state": "PENDING"}
            log.append((end - 1, "EXPIRED", entry))
            return {"state": "EXPIRED", "at": end - 1}
        log.append((fill, "FILLED", entry))
        start = fill
    stop, banked, left = sl, 0.0, 1.0
    for j in range(start, n):
        x = m5[j]
        if x.time >= hold_until:
            r = banked + left * (x.open - entry) / risk * d - cost / risk
            log.append((j, "TIME", x.open))
            return {"state": "WIN" if r > 0.05 else "LOSS" if r < -0.05 else "BE", "fill": fill, "at": j, "r": r}
        if (d > 0 and x.low <= stop) or (d < 0 and x.high >= stop):
            r = banked + left * (stop - entry) / risk * d - cost / risk
            log.append((j, "STOP" if stop == sl else "BE_STOP", stop))
            return {"state": "WIN" if r > 0.05 else "LOSS" if r < -0.05 else "BE", "fill": fill, "at": j, "r": r}
        if j > fill or market:
            if (d > 0 and x.high >= tp) or (d < 0 and x.low <= tp):
                r = banked + left * abs(tp - entry) / risk - cost / risk
                log.append((j, "TP", tp))
                return {"state": "WIN", "fill": fill, "at": j, "r": r}
            if tp1 is not None and left == 1.0 and ((d > 0 and x.high >= tp1) or (d < 0 and x.low <= tp1)):
                banked, left, stop = part * abs(tp1 - entry) / risk, 1 - part, entry
                log.append((j, "TP1", tp1))
                log.append((j, "BE", entry))
    return {"state": "ACTIVE", "fill": fill, "stop": stop, "banked": banked}


# ---------------------------------------------------------------- shared pieces
def ny(d: date, h: int, m: int = 0) -> int:
    """Unix time of h:m New York local time on the New York date d (daylight saving included)."""
    return int(datetime(d.year, d.month, d.day, h, m, tzinfo=NY).timestamp())


def ny_dates(c) -> list[date]:
    return sorted({datetime.fromtimestamp(x.time, NY).date() for x in c})


class Daily:
    """Daily ranges for the ADR: only the days BEFORE a moment count (the day in progress is not known yet)."""

    def __init__(self, d1):
        self.t = [x.time for x in d1]
        self.r = [x.high - x.low for x in d1]

    def adr(self, t: int, n: int) -> Optional[float]:
        k = bisect_left(self.t, t - t % DAY)  # days strictly before t's day
        if k < max(3, min(n, 10)):
            return None
        w = self.r[max(0, k - n):k]
        return sum(w) / len(w)


def span(c, times: list[int], a: int, b: int) -> list:
    """The candles whose open is in [a, b)."""
    return c[bisect_left(times, a):bisect_left(times, b)]


def hilo(c) -> Optional[tuple[float, float]]:
    return (max(x.high for x in c), min(x.low for x in c)) if c else None


def median_body(c, k: int, n: int = 20) -> float:
    w = sorted(body(x) for x in c[max(0, k - n):k])
    return w[len(w) // 2] if w else 0.0


def _make(key, sid, d, m5, k0, entry, sl, tp1, tp, part, market, expiry_m5, hold_until, steps, geo, cost, zone=None) -> Optional[dict]:
    risk = abs(entry - sl)
    if risk <= 0 or (d > 0 and not (sl < entry < tp)) or (d < 0 and not (tp < entry < sl)):
        return None
    if tp1 is not None and not ((d > 0 and entry < tp1 < tp) or (d < 0 and tp < tp1 < entry)):
        tp1 = None
    s = {"sid": sid, "pair": key, "dir": d, "index": k0, "time": m5[k0].time + M5S, "entry": entry, "sl": sl, "tp1": tp1, "tp": tp,
         "part": part if tp1 is not None else 1.0, "market": market, "expiry": expiry_m5, "holdUntil": hold_until,
         "rr": abs(tp - entry) / risk, "zone": zone or (entry, entry), "steps": steps, "geo": geo}
    s["result"] = run(m5, k0, d, entry, sl, tp1, tp, s["part"], market, expiry_m5, hold_until, cost)
    return s


def _mss_fvg(m5, k_from: int, k_to: int, d: int, ext_k: int, lo_f, hi_f, t_fvg0: int = 0, t_fvg1: int = 1 << 62):
    """After a sweep whose extreme is candle ext_k, the first candle k in [k_from, k_to) that closes beyond the last swing
    formed before the extreme (the MSS) with displacement (CHOICE: body >= 1.5x the median body of the 20 before), then the
    last 3-candle FVG of the move whose 3rd candle opens in [t_fvg0, t_fvg1) up to 2 candles after k.
    Returns (k_mss, level, k_fvg, (bottom, top)) or a partial tuple with None."""
    ref = next((j for j in range(ext_k - 1, max(ext_k - 80, 0), -1) if (hi_f[j] if d > 0 else lo_f[j])), None)
    if ref is None:
        return None, None, None, None
    lvl = m5[ref].high if d > 0 else m5[ref].low
    for k in range(max(k_from, ref + 2), k_to):  # the swing is known 2 candles after it
        x = m5[k]
        if not ((d > 0 and x.close > lvl) or (d < 0 and x.close < lvl)):
            continue
        if body(x) < 1.5 * median_body(m5, k):
            continue
        fvg, kf = None, None
        for j in range(ext_k + 2, min(k + 3, len(m5))):
            a, b = m5[j - 2], m5[j]
            if not (t_fvg0 <= b.time < t_fvg1):
                continue
            if d > 0 and b.low > a.high:
                fvg, kf = (a.high, b.low), j
            if d < 0 and b.high < a.low:
                fvg, kf = (b.high, a.low), j
        return k, lvl, kf, fvg
    return None, lvl, None, None


def _regime(daily: "Daily", t: int, mr: bool) -> tuple[bool, str]:
    a5, a20, a250 = daily.adr(t, 5), daily.adr(t, 20), daily.adr(t, 250)
    if not a5 or not a20:
        return True, "not enough daily history"
    if mr:
        ok = a5 / a20 <= 1.40 and (a250 is None or a20 / a250 < 1.40)
        return ok, f"ADR5/20 {a5 / a20:.2f}" + (f" · ADR20/250 {a20 / a250:.2f}" if a250 else "") + (" (mean reversion allowed)" if ok else " (expansion: mean reversion off)")
    ok = a5 / a20 >= 0.60
    return ok, f"ADR5/20 {a5 / a20:.2f}" + ("" if ok else " (compressed: targets unlikely)")


# ---------------------------------------------------------------- XAU/USD · ICT Silver Bullet / NY killzone
def xau(m5, h1, daily: Daily, pip: float, cost: float) -> tuple[list, list]:
    """Levels before 10:00 NY: the Asian range (20:00-00:00 NY, CHOICE: ICT's Asian range), the London killzone range
    (02:00-05:00 NY) and the 9:30 equity-open range (09:30-10:00 NY; CHOICE: its first half hour). Sweep: 09:30-10:15 NY,
    a candle trades beyond one of them (the 9:30 range only from 10:00). MSS on M5 with displacement, by 11:00 NY. FVG:
    3-candle, its 3rd candle inside 10:00-11:00 NY. Entry: limit at the FVG's start, valid until 11:00 NY (never extended).
    Stop: $1.00 beyond the sweep extreme (CHOICE: the guide's worked example, 2,342.50 → 2,343.50). Target: the nearest
    opposite level (Asian / London / 9:30 range) giving at least 1:2, else the nearest (then question 3 says no).
    OTE (62-79 % of the displacement leg) is preferred by the guide, not required: shown as a step. Closed at 16:00 NY."""
    out, watch = [], []
    if len(m5) < 300:
        return out, watch
    times = [x.time for x in m5]
    hi_f, lo_f = fractals(m5)
    for D in ny_dates(m5):
        if D.weekday() > 4:
            continue
        prev = D - timedelta(days=1)
        asia = hilo(span(m5, times, ny(prev, 20), ny(D, 0)))
        lon = hilo(span(m5, times, ny(D, 2), ny(D, 5)))
        eq = hilo(span(m5, times, ny(D, 9, 30), ny(D, 10)))
        t930, t1000, t1015, t1100, t1600 = ny(D, 9, 30), ny(D, 10), ny(D, 10, 15), ny(D, 11), ny(D, 16)
        if not asia or not lon:
            continue
        ks, ke = bisect_left(times, t930), bisect_left(times, t1100)
        if ke - ks < 6:
            continue
        for d in (-1, 1):  # -1: buy-side liquidity taken (highs) → sell · +1: sell-side taken (lows) → buy
            lv = {"Asian high": asia[0], "London high": lon[0]} if d < 0 else {"Asian low": asia[1], "London low": lon[1]}
            k_sw, name = None, None
            for k in range(ks, ke):
                x = m5[k]
                if x.time >= t1015:
                    break
                cand = dict(lv)
                if eq and x.time >= t1000:
                    cand["9:30 high" if d < 0 else "9:30 low"] = eq[0] if d < 0 else eq[1]
                hit = [n for n, v in cand.items() if (x.high > v if d < 0 else x.low < v)]
                if hit:
                    k_sw, name = k, hit[0]
                    break
            if k_sw is None:
                continue
            steps = [(f"Sweep 09:30-10:15 NY of the {name}", True, f"{cand[name]:.2f}")]
            ext_k = k_sw
            for k in range(k_sw, ke):  # the sweep's extreme until the MSS
                if (d < 0 and m5[k].high > m5[ext_k].high) or (d > 0 and m5[k].low < m5[ext_k].low):
                    ext_k = k
                k_m, lvl, kf, fvg = _mss_fvg(m5, k, k + 1, d, ext_k, lo_f, hi_f, t1000, t1100)
                if k_m is not None:
                    break
            else:
                k_m = None
            if k_m is None:
                watch.append({"time": m5[k_sw].time + M5S, "dir": d, "steps": steps + [("M5 MSS with displacement by 11:00 NY", False, "waiting")]})
                continue
            steps.append(("M5 MSS: body close beyond the swing, with displacement", True, f"{lvl:.2f}"))
            if fvg is None:
                watch.append({"time": m5[k_m].time + M5S, "dir": d, "steps": steps + [("FVG formed 10:00-11:00 NY", False, "none in the move")]})
                continue
            sx = m5[ext_k].high if d < 0 else m5[ext_k].low
            k0 = max(k_m, kf)
            t_set = m5[k0].time + M5S
            if t_set >= t1100:
                continue
            entry = fvg[0] if d < 0 else fvg[1]  # the FVG's start: the edge price reaches first on the way back
            sl = sx + 1.0 if d < 0 else sx - 1.0
            move = m5[k0].low if d < 0 else m5[k0].high
            leg = abs(sx - move)
            ote = (sx - 0.79 * leg, sx - 0.62 * leg) if d < 0 else (sx + 0.62 * leg, sx + 0.79 * leg)
            in_ote = min(fvg) <= max(ote) and max(fvg) >= min(ote)
            opp = {"Asian low": asia[1], "London low": lon[1]} if d < 0 else {"Asian high": asia[0], "London high": lon[0]}
            if eq:
                opp["9:30 low" if d < 0 else "9:30 high"] = eq[1] if d < 0 else eq[0]
            risk = abs(entry - sl)
            tgt = sorted(((n, v) for n, v in opp.items() if (v < entry if d < 0 else v > entry)), key=lambda nv: abs(nv[1] - entry))
            if not tgt:
                continue
            good = [nv for nv in tgt if abs(nv[1] - entry) >= 2 * risk]
            tn, tp = (good or tgt)[0]
            steps += [("FVG formed 10:00-11:00 NY", True, f"{fvg[0]:.2f} - {fvg[1]:.2f}"),
                      ("FVG inside the OTE 62-79 % (preferred, not required)", in_ote, f"{min(ote):.2f} - {max(ote):.2f}"),
                      (f"Target: the {tn}", True, f"{tp:.2f}")]
            s = _make("XAUUSD", "P", d, m5, k0, entry, sl, None, tp, 1.0, False,
                      max(1, (t1100 - t_set) // M5S), t1600, steps,
                      {"levels": {**lv, **opp}, "window": (t1000, t1100), "fvg": (fvg[0], fvg[1], m5[kf - 2].time),
                       "sweep": (sx, m5[ext_k].time), "mss": (lvl, m5[k_m].time), "ote": ote}, cost, zone=fvg)
            if s:
                out.append(s)
    return out, watch


# ---------------------------------------------------------------- EUR/USD P1 · London Judas swing
def _h1_bias(h1, h1_times: list[int], hhi, hlo, t: int) -> int:
    """H1 structure at time t: +1 higher highs AND higher lows (the last two confirmed swings), -1 the mirror, 0 neither."""
    i = bisect_right(h1_times, t - H1S) - 1  # the last H1 candle closed at t
    highs = [j for j in range(i - 2, max(i - 200, 0), -1) if hhi[j]][:2]
    lows = [j for j in range(i - 2, max(i - 200, 0), -1) if hlo[j]][:2]
    if len(highs) < 2 or len(lows) < 2:
        return 0
    if h1[highs[0]].high > h1[highs[1]].high and h1[lows[0]].low > h1[lows[1]].low:
        return 1
    if h1[highs[0]].high < h1[highs[1]].high and h1[lows[0]].low < h1[lows[1]].low:
        return -1
    return 0


def judas(m5, h1, pip: float, cost: float) -> tuple[list, list]:
    """H1 bias (higher highs / lows) at 02:00 NY. Levels: the NY midnight open (open of the 00:00 NY candle) and the Asian
    range (20:00-00:00 NY, CHOICE as gold). London killzone 02:00-05:00 NY: bullish bias → price trades below the midnight
    open AND below the Asian low (the false move); then on M5 it closes back inside the range and breaks the last minor
    swing high with displacement, leaving an FVG: limit at the FVG's start (CHOICE: the FVG, not the OB), valid until
    07:00 NY (CHOICE). Stop 2 pips beyond the false move's extreme (the guide's example: 1.0842 → 1.0840). Target: the
    Asian range's opposite side. The mirror for a bearish bias. Closed at 12:00 NY (CHOICE)."""
    out, watch = [], []
    if len(m5) < 300 or len(h1) < 60:
        return out, watch
    times = [x.time for x in m5]
    hi_f, lo_f = fractals(m5)
    hhi, hlo = fractals(h1)
    h1_times = [x.time for x in h1]
    for D in ny_dates(m5):
        if D.weekday() > 4:
            continue
        prev = D - timedelta(days=1)
        asia = hilo(span(m5, times, ny(prev, 20), ny(D, 0)))
        k_mo = bisect_left(times, ny(D, 0))
        if not asia or k_mo >= len(m5) or abs(m5[k_mo].time - ny(D, 0)) > 600:
            continue
        mo = m5[k_mo].open
        t2, t5, t7, t12 = ny(D, 2), ny(D, 5), ny(D, 7), ny(D, 12)
        bias = _h1_bias(h1, h1_times, hhi, hlo, t2)
        if bias == 0:
            continue
        d = bias
        level = asia[1] if d > 0 else asia[0]
        ks, ke = bisect_left(times, t2), bisect_left(times, t5)
        k_sw = next((k for k in range(ks, ke) if ((m5[k].low < level and m5[k].low < mo) if d > 0 else (m5[k].high > level and m5[k].high > mo))), None)
        steps = [("H1 bias bullish (higher highs and lows)" if d > 0 else "H1 bias bearish (lower highs and lows)", True, ""),
                 (f"NY midnight open {mo:.5f} · Asian range {asia[1]:.5f} - {asia[0]:.5f}", True, "")]
        if k_sw is None:
            continue
        steps.append((f"Judas swing: false move {'below' if d > 0 else 'above'} the open and the Asian {'low' if d > 0 else 'high'}", True, f"{level:.5f}"))
        ext_k, k_m = k_sw, None
        for k in range(k_sw, ke):
            if (d > 0 and m5[k].low < m5[ext_k].low) or (d < 0 and m5[k].high > m5[ext_k].high):
                ext_k = k
            back = (m5[k].close > level) if d > 0 else (m5[k].close < level)
            if not back:
                continue
            k_m, lvl, kf, fvg = _mss_fvg(m5, k, k + 1, d, ext_k, lo_f, hi_f)
            if k_m is not None:
                break
        if k_m is None:
            watch.append({"time": m5[k_sw].time + M5S, "dir": d, "steps": steps + [("Back inside + M5 MSS", False, "waiting")]})
            continue
        steps.append(("Back inside the range + M5 MSS with displacement", True, f"{lvl:.5f}"))
        if fvg is None:
            watch.append({"time": m5[k_m].time + M5S, "dir": d, "steps": steps + [("FVG in the move", False, "none")]})
            continue
        k0 = max(k_m, kf)
        t_set = m5[k0].time + M5S
        sx = m5[ext_k].low if d > 0 else m5[ext_k].high
        entry = fvg[1] if d > 0 else fvg[0]
        sl = sx - 2 * pip if d > 0 else sx + 2 * pip
        tp = asia[0] if d > 0 else asia[1]
        steps += [("FVG left by the move", True, f"{fvg[0]:.5f} - {fvg[1]:.5f}"), (f"Target: the Asian {'high' if d > 0 else 'low'}", True, f"{tp:.5f}")]
        s = _make("EURUSD", "P1", d, m5, k0, entry, sl, None, tp, 1.0, False, max(1, (t7 - t_set) // M5S), t12, steps,
                  {"levels": {"Asian high": asia[0], "Asian low": asia[1], "NY midnight open": mo}, "window": (t2, t5),
                   "fvg": (fvg[0], fvg[1], m5[kf - 2].time), "sweep": (sx, m5[ext_k].time), "mss": (lvl, m5[k_m].time)}, cost, zone=fvg)
        if s:
            out.append(s)
    return out, watch


# ---------------------------------------------------------------- EUR/USD P2 · SnapBack 3σ
def snapback(m5, h1, daily: Daily, key: str, pip: float, cost: float) -> tuple[list, list]:
    """H1: a candle closes below the lower Bollinger band (16, 3.0) with RSI 14 under 30 → buy at that close; above the
    upper band with RSI over 70 → sell. SL and TP both 2.0 × ATR 14 (1:1). One trade at a time: no new signal while the
    previous one is still open. Held at most 5 days (CHOICE)."""
    out, watch = [], []
    if len(h1) < 40:
        return out, watch
    cl = [x.close for x in h1]
    mid, sd = sma_std(cl, 16)
    r, at = rsi(cl, 14), atr(h1, 14)
    m5_times = [x.time for x in m5]
    busy_until = 0
    for i in range(20, len(h1)):
        x = h1[i]
        if None in (mid[i], sd[i], r[i], at[i]):
            continue
        t_close = x.time + H1S
        if t_close < busy_until:
            continue
        up, lo = mid[i] + 3 * sd[i], mid[i] - 3 * sd[i]
        d = 1 if (x.close < lo and r[i] < 30) else -1 if (x.close > up and r[i] > 70) else 0
        if not d:
            continue
        k0 = m5_index_at_close(m5_times, t_close)
        if k0 is None or m5[k0].time + M5S != t_close:
            continue
        entry = m5[k0].close
        steps = [(f"H1 close {'under' if d > 0 else 'over'} Bollinger (16, 3.0)", True, f"{lo if d > 0 else up:.5f}"),
                 (f"RSI 14 {r[i]:.0f} {'< 30' if d > 0 else '> 70'}", True, ""), (f"SL = TP = 2.0 × ATR 14 ({2 * at[i] / pip:.1f} pips)", True, "")]
        s = _make(key, "P2", d, m5, k0, entry, entry - d * 2 * at[i], None, entry + d * 2 * at[i], 1.0, True, 0, t_close + 5 * DAY, steps,
                  {"bands": True}, cost)
        if s:
            out.append(s)
            res = s["result"]
            busy_until = m5[res["at"]].time + M5S if "at" in res else 1 << 62
    return out, watch


# ---------------------------------------------------------------- GBP/USD P1 · London / NY overlap sweep
def gbp_sweep(m5, daily: Daily, pip: float, cost: float) -> tuple[list, list]:
    """The Asian range (00:00-07:00 UTC, CHOICE: up to London's open). In 07:00-09:00 or 12:00-14:00 UTC price takes the
    Asian high or low; then the M5 MSS with displacement inside the window, with an FVG: limit at its start, valid 2 hours
    (CHOICE). Stop 2 pips beyond the sweep wick, and at least 0.45 × ADR20 from the entry (the guide: 0.4-0.5). Target
    1.0 × ADR20 (the guide: 0.8-1.0). Closed at 20:00 UTC (CHOICE)."""
    out, watch = [], []
    if len(m5) < 300:
        return out, watch
    times = [x.time for x in m5]
    hi_f, lo_f = fractals(m5)
    for day in sorted({x.time - x.time % DAY for x in m5}):
        if datetime.fromtimestamp(day, timezone.utc).weekday() > 4:
            continue
        asia = hilo(span(m5, times, day, day + 7 * H1S))
        a20 = daily.adr(day + 7 * H1S, 20)
        if not asia or not a20:
            continue
        taken = set()
        for w0, w1 in ((day + 7 * H1S, day + 9 * H1S), (day + 12 * H1S, day + 14 * H1S)):
            ks, ke = bisect_left(times, w0), bisect_left(times, w1)
            for d in (1, -1):  # +1: the Asian LOW taken → buy · -1: the HIGH taken → sell
                if d in taken:
                    continue
                level = asia[1] if d > 0 else asia[0]
                k_sw = next((k for k in range(ks, ke) if (m5[k].low < level if d > 0 else m5[k].high > level)), None)
                if k_sw is None:
                    continue
                taken.add(d)
                steps = [(f"Asian {'low' if d > 0 else 'high'} taken in the {'London open' if w0 % DAY == 7 * H1S else 'NY overlap'} window", True, f"{level:.5f}")]
                ext_k, k_m = k_sw, None
                for k in range(k_sw, ke):
                    if (d > 0 and m5[k].low < m5[ext_k].low) or (d < 0 and m5[k].high > m5[ext_k].high):
                        ext_k = k
                    k_m, lvl, kf, fvg = _mss_fvg(m5, k, k + 1, d, ext_k, lo_f, hi_f)
                    if k_m is not None:
                        break
                if k_m is None:
                    watch.append({"time": m5[k_sw].time + M5S, "dir": d, "steps": steps + [("M5 MSS with displacement", False, "waiting")]})
                    continue
                steps.append(("M5 MSS with displacement", True, f"{lvl:.5f}"))
                if fvg is None:
                    watch.append({"time": m5[k_m].time + M5S, "dir": d, "steps": steps + [("FVG in the move", False, "none")]})
                    continue
                k0 = max(k_m, kf)
                t_set = m5[k0].time + M5S
                sx = m5[ext_k].low if d > 0 else m5[ext_k].high
                entry = fvg[1] if d > 0 else fvg[0]
                sl = min(sx - 2 * pip, entry - 0.45 * a20) if d > 0 else max(sx + 2 * pip, entry + 0.45 * a20)
                tp = entry + d * 1.0 * a20
                steps += [("FVG left by the move", True, f"{fvg[0]:.5f} - {fvg[1]:.5f}"),
                          (f"Stop >= 0.45 ADR20, target 1.0 ADR20 (ADR20 {a20 / pip:.0f} pips)", True, "")]
                s = _make("GBPUSD", "P1", d, m5, k0, entry, sl, None, tp, 1.0, False, 24, day + 20 * H1S, steps,
                          {"levels": {"Asian high": asia[0], "Asian low": asia[1]}, "window": (w0, w1), "fvg": (fvg[0], fvg[1], m5[kf - 2].time),
                           "sweep": (sx, m5[ext_k].time), "mss": (lvl, m5[k_m].time)}, cost, zone=fvg)
                if s:
                    out.append(s)
    return out, watch


# ---------------------------------------------------------------- GBP/USD P2 · EMA 20/50/200 trend pullback
def ema_pullback(m5, h1, daily: Daily, pip: float, cost: float) -> tuple[list, list]:
    """BUY: on H1 and on H4 (built from H1) price > EMA 20 > EMA 50 > EMA 200, each EMA rising (over 5 candles, CHOICE),
    and ADX 14 (H1) over 25. The H1 candle pulls back to EMA 20 or EMA 50 (its low reaches EMA 20) at a swing high that
    price had broken (the flip: within 0.3 ATR, CHOICE), RSI 14 back in the middle (40-60, CHOICE), and closes as a reversal
    (pin bar or bullish engulfing) above EMA 20, its close between 08:00 and 15:00 UTC: buy at the close. Stop 2 pips under
    the pullback low and at least 0.45 × ADR20 away; target 1.0 × ADR20. The mirror for a SELL. Held 48 hours (CHOICE)."""
    out, watch = [], []
    if len(h1) < 260:
        return out, watch
    cl = [x.close for x in h1]
    e20, e50, e200 = ema(cl, 20), ema(cl, 50), ema(cl, 200)
    a = adx(h1, 14)
    r, at = rsi(cl, 14), atr(h1, 14)
    h4 = resample(h1, H4S)
    c4 = [x.close for x in h4]
    f20, f50, f200 = ema(c4, 20), ema(c4, 50), ema(c4, 200)
    t4 = [x.time for x in h4]
    hhi, hlo = fractals(h1)
    m5_times = [x.time for x in m5]

    def aligned(v, a20, a50, a200, i, d):
        if None in (a20[i], a50[i], a200[i], a20[i - 5], a50[i - 5], a200[i - 5]):
            return False
        order = (v > a20[i] > a50[i] > a200[i]) if d > 0 else (v < a20[i] < a50[i] < a200[i])
        rising = all(((s[i] - s[i - 5]) * d) > 0 for s in (a20, a50, a200))
        return order and rising

    for i in range(210, len(h1)):
        x = h1[i]
        t_close = x.time + H1S
        if not (8 * H1S < t_close % DAY <= 15 * H1S) or None in (a[i], r[i], at[i]):
            continue
        j4 = bisect_right(t4, t_close - H4S) - 1  # the last CLOSED H4 candle
        if j4 < 205:
            continue
        for d in (1, -1):
            if not aligned(h1[i - 1].close, e20, e50, e200, i - 1, d) or not aligned(h4[j4].close, f20, f50, f200, j4, d) or a[i] <= 25:
                continue
            touch = (x.low <= e20[i]) if d > 0 else (x.high >= e20[i])
            if not touch:
                continue
            flips = [j for j in range(i - 3, max(i - 80, 0), -1) if (hhi[j] if d > 0 else hlo[j]) and j + 2 <= i]
            lvl = next((h1[j].high if d > 0 else h1[j].low for j in flips
                        if abs((h1[j].high if d > 0 else h1[j].low) - (x.low if d > 0 else x.high)) <= 0.3 * at[i]
                        and any(((h1[q].close - (h1[j].high if d > 0 else h1[j].low)) * d) > 0 for q in range(j + 1, i))), None)
            prev = h1[i - 1]
            pin = (min(x.open, x.close) - x.low >= 2 * body(x)) if d > 0 else (x.high - max(x.open, x.close) >= 2 * body(x))
            engulf = (x.close > x.open and prev.close < prev.open and x.close > prev.open) if d > 0 else (x.close < x.open and prev.close > prev.open and x.close < prev.open)
            close_ok = (x.close > e20[i]) if d > 0 else (x.close < e20[i])
            mid_rsi = 40 <= r[i] <= 60
            steps = [("H1 and H4: price > EMA 20 > 50 > 200, all rising" if d > 0 else "H1 and H4: price < EMA 20 < 50 < 200, all falling", True, ""),
                     (f"ADX {a[i]:.0f} > 25", True, ""), ("Pullback to EMA 20 / 50", True, f"{e20[i]:.5f}"),
                     ("At a flipped swing (old high now support)" if d > 0 else "At a flipped swing (old low now resistance)", lvl is not None, f"{lvl:.5f}" if lvl else "none"),
                     (f"RSI {r[i]:.0f} back to the middle (40-60)", mid_rsi, ""), ("Reversal candle closing beyond EMA 20", (pin or engulf) and close_ok, "")]
            if not (lvl is not None and mid_rsi and (pin or engulf) and close_ok):
                if lvl is not None:
                    watch.append({"time": t_close, "dir": d, "steps": steps})
                continue
            a20 = daily.adr(t_close, 20)
            k0 = m5_index_at_close(m5_times, t_close)
            if not a20 or k0 is None or m5[k0].time + M5S != t_close:
                continue
            entry = m5[k0].close
            sl = min(x.low - 2 * pip, entry - 0.45 * a20) if d > 0 else max(x.high + 2 * pip, entry + 0.45 * a20)
            s = _make("GBPUSD", "P2", d, m5, k0, entry, sl, None, entry + d * a20, 1.0, True, 0, t_close + 48 * H1S, steps,
                      {"emas": True, "flip": (lvl, x.time)}, cost)
            if s:
                out.append(s)
    return out, watch


# ---------------------------------------------------------------- EUR/CHF and AUD/CAD · time-filtered 3σ mean reversion
def three_touch(h4, upto: int, d: int, tol: float, back: int = 120) -> list[float]:
    """The guide's mechanical swing levels: H4 swing lows (d=+1) or highs (d=-1), N = 2 each side, confirmed before
    candle `upto`; a level is 3 or more of them within `tol` of each other (CHOICE: 0.1 ADR20, the last 120 H4 = 20 days).
    Returns the levels (the mean of each cluster)."""
    hi_f, lo_f = _fr_cache(h4)
    pts = sorted((h4[j].low if d > 0 else h4[j].high) for j in range(max(0, upto - back), upto - 2) if (lo_f[j] if d > 0 else hi_f[j]))
    out, k = [], 0
    while k < len(pts):
        grp = [p for p in pts if abs(p - pts[k]) <= tol]
        if len(grp) >= 3:
            lv = sum(grp) / len(grp)
            if not out or abs(out[-1] - lv) > tol:
                out.append(lv)
        k += 1
    return out


_FR: dict = {}


def _fr_cache(c):
    k = (id(c), len(c))
    if k not in _FR:
        _FR.clear()
        _FR[k] = fractals(c)
    return _FR[k]


def mean_reversion(m5, h1, daily: Daily, key: str, pip: float, cost: float) -> tuple[list, list]:
    """Regime: ADR20 / ADR250 < 1.40 and ADR5 / ADR20 <= 1.40 (question 6), ADX 14 on H1 under 30 (the guide: 30-35, off
    over 40). Level: a 3-touch H4 swing level (support for a buy, resistance for a sell). Signal: an H1 candle reaching the
    level (within the tolerance) closes outside Bollinger (16, 3.0) with RSI 14 under 30 (buy) / over 70 (sell), its close
    in the pair's window: EUR/CHF 07:00-13:00 or 15:30-18:00 UTC, AUD/CAD 00:00-11:00 UTC; never 14:00 or 21:00-23:00 UTC.
    (The guide's other trigger, an RSI divergence at the level, is not coded: CHOICE.) Entry at the close. Stop 0.5 ×
    ADR20 from the entry and beyond the level. Target: EUR/CHF the mean (the band's middle line, 1:1 to 1:1.5), AUD/CAD
    0.8 × ADR20. Held 24 hours (CHOICE)."""
    out, watch = [], []
    if len(h1) < 60:
        return out, watch
    cl = [x.close for x in h1]
    mid, sd = sma_std(cl, 16)
    r, a = rsi(cl, 14), adx(h1, 14)
    h4 = resample(h1, H4S)
    t4 = [x.time for x in h4]
    m5_times = [x.time for x in m5]

    def window(t: int) -> bool:
        m = (t % DAY) // 60  # minutes after 00:00 UTC of the close
        if key == "EURCHF":
            return 7 * 60 < m <= 13 * 60 or 15 * 60 + 30 < m <= 18 * 60
        return 0 < m <= 11 * 60

    for i in range(20, len(h1)):
        x = h1[i]
        t_close = x.time + H1S
        if None in (mid[i], sd[i], r[i], a[i]) or not window(t_close):
            continue
        up, lo = mid[i] + 3 * sd[i], mid[i] - 3 * sd[i]
        d = 1 if (x.close < lo and r[i] < 30) else -1 if (x.close > up and r[i] > 70) else 0
        if not d:
            continue
        a20 = daily.adr(t_close, 20)
        if not a20:
            continue
        tol = 0.1 * a20
        j4 = bisect_right(t4, t_close - H4S)
        levels = three_touch(h4, j4, d, tol)
        ext = x.low if d > 0 else x.high
        lvl = next((v for v in levels if abs(ext - v) <= tol or ((ext < v) if d > 0 else (ext > v)) and abs(x.close - v) <= 2 * tol), None)
        reg_ok, reg = _regime(daily, t_close, True)
        steps = [(f"ADX {a[i]:.0f} < 30 (no strong trend)", a[i] < 30, ""), (f"Regime: {reg}", reg_ok, ""),
                 (f"At a 3-touch H4 {'support' if d > 0 else 'resistance'}", lvl is not None, f"{lvl:.5f}" if lvl else f"{len(levels)} level(s), none here"),
                 (f"H1 close {'under' if d > 0 else 'over'} Bollinger (16, 3.0) + RSI {r[i]:.0f}", True, "")]
        if not (a[i] < 30 and lvl is not None):
            watch.append({"time": t_close, "dir": d, "steps": steps})
            continue
        k0 = m5_index_at_close(m5_times, t_close)
        if k0 is None or m5[k0].time + M5S != t_close:
            continue
        entry = m5[k0].close
        sl = min(entry - 0.5 * a20, lvl - tol) if d > 0 else max(entry + 0.5 * a20, lvl + tol)
        tp = mid[i] if key == "EURCHF" else entry + d * 0.8 * a20
        steps.append((f"Target: {'the mean (band middle)' if key == 'EURCHF' else '0.8 ADR20'}", True, f"{tp:.5f}"))
        s = _make(key, "P", d, m5, k0, entry, sl, None, tp, 1.0, True, 0, t_close + 24 * H1S, steps,
                  {"bands": True, "level": (lvl, x.time)}, cost)
        if s:
            s["regime"] = reg_ok
            out.append(s)
    return out, watch


# ---------------------------------------------------------------- AUD/CHF · risk-on carry swing
def carry_swing(m5, h1, daily: Daily, pip: float, cost: float) -> tuple[list, list]:
    """Longs only (the guide's preferred side; the sell side needs its macro gate, not available). On H4 and H1 price
    is above EMA 200 and EMA 200 is rising (over 5 candles, CHOICE). An H1 candle pulls back to the EMA 20 / EMA 50 zone
    (its low between EMA 50 - 0.2 ATR and EMA 20, CHOICE) on a higher low (above the last confirmed H1 swing low) and
    closes as a bullish reversal (pin bar or engulfing, above EMA 20), its close in 06:00-15:00 UTC (never 21:00-22:00):
    buy at the close. Stop 0.7 × ADR20 from the entry (the guide: 0.6-0.8), or 2 pips under the pullback low if that is
    lower. TP1 1.0 × ADR20 (half, stop to entry, CHOICE: the half), TP2 2.0 × ADR20. Held 5 days (CHOICE).
    The guide's 3-pillar macro gate (S&P 500 up, VIX down, iron ore up) is NOT checked: no such data in the app."""
    out, watch = [], []
    if len(h1) < 260:
        return out, watch
    cl = [x.close for x in h1]
    e20, e50, e200 = ema(cl, 20), ema(cl, 50), ema(cl, 200)
    at = atr(h1, 14)
    h4 = resample(h1, H4S)
    c4 = [x.close for x in h4]
    f200 = ema(c4, 200)
    t4 = [x.time for x in h4]
    hhi, hlo = fractals(h1)
    m5_times = [x.time for x in m5]
    for i in range(210, len(h1)):
        x = h1[i]
        t_close = x.time + H1S
        if not (6 * H1S < t_close % DAY <= 15 * H1S) or None in (e20[i], e50[i], e200[i], e200[i - 5], at[i]):
            continue
        j4 = bisect_right(t4, t_close - H4S) - 1
        if j4 < 206 or f200[j4] is None or f200[j4 - 5] is None:
            continue
        trend = x.close > e200[i] and e200[i] > e200[i - 5] and h4[j4].close > f200[j4] and f200[j4] > f200[j4 - 5]
        if not trend:
            continue
        zone_ok = e50[i] - 0.2 * at[i] <= x.low <= e20[i]
        if not zone_ok:
            continue
        last_low = next((h1[j].low for j in range(i - 3, max(i - 100, 0), -1) if hlo[j] and j + 2 <= i), None)
        higher = last_low is not None and x.low > last_low
        prev = h1[i - 1]
        pin = min(x.open, x.close) - x.low >= 2 * body(x)
        engulf = x.close > x.open and prev.close < prev.open and x.close > prev.open
        rev = (pin or engulf) and x.close > e20[i]
        steps = [("H4 and H1 above a rising EMA 200", True, ""), ("Pullback into EMA 20 / 50", True, f"{e50[i]:.5f} - {e20[i]:.5f}"),
                 ("On a higher low", higher, f"last swing low {last_low:.5f}" if last_low else "none"),
                 ("Bullish reversal candle closing above EMA 20", rev, ""),
                 ("Macro gate (S&P 500, VIX, iron ore)", True, "not checked: no such data in the app (HYPOTHESIS)")]
        if not (higher and rev):
            if higher:
                watch.append({"time": t_close, "dir": 1, "steps": steps})
            continue
        a20 = daily.adr(t_close, 20)
        k0 = m5_index_at_close(m5_times, t_close)
        if not a20 or k0 is None or m5[k0].time + M5S != t_close:
            continue
        entry = m5[k0].close
        sl = min(entry - 0.7 * a20, x.low - 2 * pip)
        s = _make("AUDCHF", "P", 1, m5, k0, entry, sl, entry + 1.0 * a20, entry + 2.0 * a20, 0.5, True, 0, t_close + 5 * DAY, steps,
                  {"emas": True}, cost)
        if s:
            out.append(s)
    return out, watch


# ---------------------------------------------------------------- the checklist (the guide's section 6b) and the entry point
def checklist(key: str, s: dict, news: Optional[list[int]], daily: Optional[Daily] = None) -> list[tuple[str, bool, str]]:
    t, sid = s["time"], s["sid"]
    near = [n for n in (news or []) if t - NEWS_MIN * 60 <= n <= t + NEWS_MIN * 60] if news is not None else []
    need = MIN_RR[(key, sid)]
    mr = (key, sid) in MEAN_REVERSION
    reg_ok, reg = _regime(daily, t, mr) if daily else (True, "not checked")
    hm = lambda n: datetime.fromtimestamp(n, timezone.utc).strftime("%H:%M")  # noqa: E731
    return [
        ("1 · This pair's strategy from the guide", True, NAMES[key][sid]),
        (f"2 · No red-folder news {NEWS_MIN} min around the entry", not near,
         "not checked (no news history)" if news is None else ("news at " + ", ".join(hm(n) for n in near) + " UTC" if near else "none")),
        (f"3 · Reward >= 1:{need:g}", s["rr"] >= need - 1e-9, f"1:{s['rr']:.2f}"),
        ("4 · Lot sized for 1 % risk", True, "risk / (stop pips × pip value)"),
        ("5 · Correlation cap (no full-risk twin trade the same way)", True, "checked across the six teams before any alert"),
        (f"6 · Volatility regime ({'mean reversion' if mr else 'sweep / trend'})", reg_ok, reg),
    ]


def scan(key: str, m5, h1, pip: float, cost: float, news: Optional[list[int]] = None, eur_m5=None, d1=None) -> tuple[list, list]:
    """The pair's strategies on its candles: (setups with their result and checklist, what is forming). `d1`: daily candles
    for the ADR (built from H1 when not given)."""
    daily = Daily(d1 if d1 else resample(h1, DAY))
    if key == "XAUUSD":
        parts = [xau(m5, h1, daily, pip, cost)]
    elif key == "EURUSD":
        parts = [judas(m5, h1, pip, cost), snapback(m5, h1, daily, key, pip, cost)]
    elif key == "GBPUSD":
        parts = [gbp_sweep(m5, daily, pip, cost), ema_pullback(m5, h1, daily, pip, cost)]
    elif key in ("EURCHF", "AUDCAD"):
        parts = [mean_reversion(m5, h1, daily, key, pip, cost)]
    elif key == "AUDCHF":
        parts = [carry_swing(m5, h1, daily, pip, cost)]
    else:
        return [], []
    s = sorted((x for p in parts for x in p[0]), key=lambda x: x["time"])
    w = sorted((x for p in parts for x in p[1]), key=lambda x: x["time"])
    seen = set()
    s = [x for x in s if not ((x["sid"], x["time"], x["dir"]) in seen or seen.add((x["sid"], x["time"], x["dir"])))]
    nw = sorted(news) if news else None
    for x in s:
        if nw and not x["market"]:  # the limit is followed again with the news rule (pulled around a release)
            x["result"] = run(m5, x["index"], x["dir"], x["entry"], x["sl"], x["tp1"], x["tp"], x["part"], False, x["expiry"], x["holdUntil"], cost, None, nw)
        x["checklist"] = checklist(key, x, news, daily)
        x["pass"] = all(ok for _, ok, _ in x["checklist"])
    for x in w:
        x.setdefault("sid", "P")
    return s, w


# ---------------------------------------------------------------- what each pair's chart shows: its own strategy, nothing else
def _line(h1, vals, n: int, color: str, label: str, dash: bool = False, r=lambda v: v) -> dict:
    pts = [[h1[i].time + H1S, r(vals[i])] for i in range(max(0, len(h1) - n), len(h1)) if vals[i] is not None]
    return {"points": pts, "color": color, "label": label, "dash": dash}


def draw(key: str, m5, h1, now: int, shown: Optional[dict], decimals: int, d1=None) -> dict:
    """The chart of the pair's strategy: its levels, its time windows, its indicator lines, and the shown setup's own
    zones (sweep, MSS, FVG, OTE, flipped level). Lines are H1 values at each H1 close."""
    r = lambda v: round(v, decimals)  # noqa: E731
    boxes, segs, labels, lines, windows = [], [], [], [], []
    if not m5:
        return {"boxes": boxes, "segments": segs, "labels": labels, "lines": lines, "windows": windows}
    times = [x.time for x in m5]
    end = m5[-1].time + M5S
    daily = Daily(d1 if d1 else resample(h1, DAY))

    def seg(a, b, p, kind, d, label):
        if p is not None:
            segs.append({"from": a, "to": b, "price": r(p), "kind": kind, "dir": d, "label": label})

    def bands():
        cl = [x.close for x in h1]
        mid, sd = sma_std(cl, 16)
        up = [None if m is None else m + 3 * s for m, s in zip(mid, sd)]
        lo = [None if m is None else m - 3 * s for m, s in zip(mid, sd)]
        lines.extend([_line(h1, up, 150, "#A78BFA", "BB 16, 3σ", True, r), _line(h1, mid, 150, "#A78BFA", "mean (SMA 16)", False, r),
                      _line(h1, lo, 150, "#A78BFA", "", True, r)])

    def emas(which=(20, 50, 200)):
        cl = [x.close for x in h1]
        col = {20: "#38BDF8", 50: "#F59E0B", 200: "#F43F5E"}
        for n in which:
            lines.append(_line(h1, ema(cl, n), 150, col[n], f"EMA {n}", False, r))

    if key in ("XAUUSD", "EURUSD"):
        D = datetime.fromtimestamp(m5[-1].time, NY).date()
        prev = D - timedelta(days=1)
        a0 = ny(prev, 20)
        asia = hilo(span(m5, times, a0, ny(D, 0)))
        if asia:
            seg(a0, end, asia[0], "session", 1, "Asian high")
            seg(a0, end, asia[1], "session", -1, "Asian low")
        if key == "XAUUSD":
            lon = hilo(span(m5, times, ny(D, 2), ny(D, 5)))
            eq = hilo(span(m5, times, ny(D, 9, 30), ny(D, 10)))
            if lon:
                seg(ny(D, 2), end, lon[0], "liquidity", 1, "London high")
                seg(ny(D, 2), end, lon[1], "liquidity", -1, "London low")
            if eq and end > ny(D, 10):
                seg(ny(D, 9, 30), end, eq[0], "liquidity", 1, "9:30 high")
                seg(ny(D, 9, 30), end, eq[1], "liquidity", -1, "9:30 low")
            windows.append({"from": ny(D, 9, 30), "to": ny(D, 10, 15), "label": "sweep 09:30-10:15 NY"})
            windows.append({"from": ny(D, 10), "to": ny(D, 11), "label": "Silver Bullet 10-11 NY"})
        else:
            k_mo = bisect_left(times, ny(D, 0))
            if k_mo < len(m5):
                seg(ny(D, 0), end, m5[k_mo].open, "eq", 0, "NY midnight open")
            windows.append({"from": ny(D, 2), "to": ny(D, 5), "label": "London killzone (Judas)"})
            bands()
    elif key == "GBPUSD":
        day = m5[-1].time - m5[-1].time % DAY
        asia = hilo(span(m5, times, day, day + 7 * H1S))
        if asia:
            seg(day, end, asia[0], "session", 1, "Asian high")
            seg(day, end, asia[1], "session", -1, "Asian low")
        windows += [{"from": day + 7 * H1S, "to": day + 9 * H1S, "label": "London open sweep"},
                    {"from": day + 12 * H1S, "to": day + 14 * H1S, "label": "NY overlap sweep"}]
        emas()
    elif key in ("EURCHF", "AUDCAD"):
        bands()
        a20 = daily.adr(now, 20)
        if a20:
            h4 = resample(h1, H4S)
            for d in (1, -1):
                for v in three_touch(h4, len(h4), d, 0.1 * a20):
                    seg(h4[max(0, len(h4) - 120)].time, end, v, "liquidity", -d, f"3-touch level ({'swing lows' if d > 0 else 'swing highs'})")
        day = m5[-1].time - m5[-1].time % DAY
        windows += ([{"from": day + 7 * H1S, "to": day + 13 * H1S, "label": "reversion window"},
                     {"from": day + 15 * H1S + 1800, "to": day + 18 * H1S, "label": "reversion window"}] if key == "EURCHF"
                    else [{"from": day, "to": day + 11 * H1S, "label": "reversion window (Tokyo / London)"}])
    elif key == "AUDCHF":
        emas()
        day = m5[-1].time - m5[-1].time % DAY
        windows.append({"from": day + 6 * H1S, "to": day + 15 * H1S, "label": "entry window 06-15 UTC"})

    g = (shown or {}).get("geo") or {}
    d = (shown or {}).get("dir", 1)
    if g.get("sweep"):
        p, t = g["sweep"]
        labels.append({"time": t, "price": r(p), "text": "Liquidity sweep", "above": d < 0, "kind": "sweep"})
    if g.get("mss"):
        p, t = g["mss"]
        seg(t - 6 * M5S, t, p, "choch", d, "MSS")
    if g.get("fvg"):
        a, b, t = g["fvg"]
        boxes.append({"from": t, "to": end + 2 * H1S, "top": r(max(a, b)), "bottom": r(min(a, b)), "kind": "fvg", "dir": d, "label": "FVG"})
    if g.get("ote") and g.get("fvg"):
        a, b = g["ote"]
        boxes.append({"from": g["fvg"][2], "to": end + 2 * H1S, "top": r(max(a, b)), "bottom": r(min(a, b)), "kind": "ob", "dir": d, "label": "OTE 62-79 %"})
    if g.get("flip") and g["flip"][0] is not None:
        p, t = g["flip"]
        seg(t - 12 * H1S, end, p, "liquidity", d, "flipped swing")
    if g.get("level") and g["level"][0] is not None:
        p, t = g["level"]
        seg(t - 24 * H1S, end, p, "liquidity", -d, "the 3-touch level")
    return {"boxes": boxes, "segments": segs, "labels": labels, "lines": lines, "windows": windows}
