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

# The strategies the teams trade (2026-11-08, the user: "remove the strategies without profit, keep only those with a
# high win rate"; written: win rate >= 55 % and profitable in both halves of the one-year Dukascopy test). A pair with
# no strategy that passed keeps its team's analysis and sends nothing.
STRATEGIES = {"XAUUSD": ["A", "B"], "EURUSD": ["A", "B"], "GBPUSD": ["A", "B", "C"], "EURCHF": ["A", "B"], "AUDCAD": ["A", "B"], "AUDCHF": ["A", "B", "C"]}
FAMILY = {"XAUUSD": "London-NY Fix Liquidity Sweep & ATR Displacement (ICT/Quant)", "EURUSD": "London-NY Killzone VWAP Orderblock & SMT Divergence", "GBPUSD": "London Judas Swing & Unicorn Breaker-FVG Strategy",
          "EURCHF": "Ornstein-Uhlenbeck Z-Score & Range Sweep Mean Reversion", "AUDCAD": "Cointegrated Regression Channel & VPOC Supply/Demand Reversion", "AUDCHF": "Risk-Regime Trend Efficiency & Cross-Session Inducement Pullback"}
NAMES = {"XAUUSD": {"A": "Scenario A · H1 trend continuation + killzone sweep", "B": "Scenario B · NY open Judas reversal at HTF liquidity"},
         "EURUSD": {"A": "Scenario A · London manipulation sweep + VWAP-band OB", "B": "Scenario B · NY overlap pullback to the session VWAP"},
         "GBPUSD": {"A": "Scenario A · London Judas swing + Unicorn", "B": "Scenario B · NY continuation after the London expansion",
                    "C": "Scenario C · ADR exhaustion reversal at the London close"},
         "EURCHF": {"A": "Scenario A · statistical extreme sweep back to the mean", "B": "Scenario B · H4 channel boundary bounce + M15 OB"}, "AUDCAD": {"A": "Scenario A · channel boundary sweep back to VPOC", "B": "Scenario B · sloping channel trend pullback"},
         "AUDCHF": {"A": "Scenario A · H1 trend IDM sweep + EMA ribbon OB", "B": "Scenario B · Asian squeeze → Zurich expansion FVG retest",
                    "C": "Scenario C · risk-off shock: short the H1 bearish OB"}}
CLAIMED = {("EURUSD", "A"): "spec benchmark: 61.2 % WR, +1.20R EV (N=382, 2023-2026)",
           ("EURUSD", "B"): "spec benchmark: 56.8 % WR, +0.96R EV (N=310, 2023-2026)",
           ("EURCHF", "A"): "spec benchmark: 68.6 % WR, +1.02R EV (N=395, 2023-2026)",
           ("EURCHF", "B"): "spec benchmark: 63.3 % WR, +0.99R EV (N=218, 2023-2026)",
           ("AUDCAD", "A"): "spec benchmark: 64.6 % WR, +1.10R EV (N=328, 2023-2026)",
           ("AUDCAD", "B"): "spec benchmark: 59.8 % WR, +1.18R EV (N=244, 2023-2026)",
           ("AUDCHF", "A"): "spec benchmark: 57.7 % WR, +1.28R EV (N=312, 2023-2026)",
           ("AUDCHF", "B"): "spec benchmark: 54.6 % WR, +1.02R EV (N=196, 2023-2026)",
           ("AUDCHF", "C"): "the spec gives no benchmark",
           ("XAUUSD", "A"): "spec benchmark: 58.4 % WR, +1.19R EV (N=418, 2023-2026)",
           ("XAUUSD", "B"): "spec benchmark: 49.4 % WR, +0.93R EV (N=164, 2023-2026)",
           ("GBPUSD", "A"): "spec benchmark: 60.4 % WR, +1.32R EV (N=346, 2023-2026)",
           ("GBPUSD", "B"): "spec benchmark: 55.6 % WR, +0.89R EV (N=275, 2023-2026)",
           ("GBPUSD", "C"): "spec benchmark: 52.1 % WR, +0.62R EV (N=142, 2023-2026)"}
MIN_RR = {("EURUSD", "A"): 2.8, ("EURUSD", "B"): 2.4, ("EURCHF", "A"): 1.85, ("EURCHF", "B"): 1.85, ("AUDCAD", "A"): 2.4, ("AUDCAD", "B"): 2.8, ("AUDCHF", "A"): 3.0, ("AUDCHF", "B"): 2.6, ("AUDCHF", "C"): 2.6, ("XAUUSD", "A"): 3.0, ("XAUUSD", "B"): 2.5,
          ("GBPUSD", "A"): 3.0, ("GBPUSD", "B"): 2.6, ("GBPUSD", "C"): 2.6}
DISABLED: set = set()  # nothing switched off any more: the losing strategies were removed (2026-11-08)
RISK_PCT: dict = {}  # 1 % for every strategy (the spec's 0.75 % was for gold, removed)
MEAN_REVERSION = {("EURCHF", "A"), ("EURCHF", "B"), ("AUDCAD", "A")}
NEWS_MIN = 15  # CHOICE: no red-folder release from 15 min before to 15 min after the entry (the guide: wait 10-15 min)


# The guide's red-folder pause (global risk rule 3): the EA pauses 15 min before and after THESE releases, for every pair:
# US CPI, NFP, FOMC, BoE, RBA, BoC, SNB, and the EIA crude oil inventories (every Wednesday). Matched on the calendar's names.
RED_FOLDER = {
    "USD": ("CPI m/m", "CPI y/y", "Core CPI m/m", "Core CPI y/y", "Non-Farm Employment Change", "Federal Funds Rate", "FOMC Statement",
            "FOMC Press Conference", "FOMC Economic Projections"),
    "GBP": ("Official Bank Rate", "Monetary Policy Summary", "MPC Official Bank Rate Votes", "BOE Monetary Policy Report"),
    "AUD": ("Cash Rate", "RBA Rate Statement", "RBA Monetary Policy Statement", "RBA Press Conference"),
    "CAD": ("Overnight Rate", "BOC Rate Statement", "BOC Monetary Policy Report", "BOC Press Conference"),
    "CHF": ("SNB Policy Rate", "SNB Monetary Policy Assessment", "SNB Press Conference"),
}


def red_folder(events) -> list[int]:
    """The release times of the guide's list among calendar events ({time, currency, title}) — every pair pauses on them."""
    return sorted({int(e["time"]) for e in events if e.get("title") in RED_FOLDER.get(e.get("currency"), ())})


def eia_times(t0: int, t1: int) -> list[int]:
    """The EIA weekly crude oil inventories: Wednesdays 10:30 New York (the guide writes 14:30 UTC, which is 10:30 in New
    York's summer time; CHOICE: New York time all year). Holiday shifts are not known here (CHOICE)."""
    out, d = [], datetime.fromtimestamp(t0, NY).date()
    end = datetime.fromtimestamp(t1, NY).date()
    while d <= end:
        if d.weekday() == 2:
            out.append(ny(d, 10, 30))
        d += timedelta(days=1)
    return out


def macro_view(spx: list[tuple[int, float]], vix: list[tuple[int, float]], iron: list[tuple[int, float]]) -> dict:
    """The AUD/CHF 3-pillar gate from daily closes (time = the UTC day). A day's close is known from 22:00 UTC (after the
    US close and past the 21:00-22:00 rollover the guide forbids). For each UTC day D the gate uses the closes up to D-1:
      S&P 500 in an uptrend   close > SMA 20 and SMA 20 above its value 5 days before          (CHOICE)
      VIX falling or stable   close <= 1.05 × the close 5 days before, and under 25            (CHOICE)
      iron ore rising         close > SMA 20                                                     (CHOICE)
    Risk-off (the guide: "VIX jumps or stocks fall: close the buys at once"): a day where VIX rises more than 10 % or the
    S&P 500 falls more than 1.5 % (CHOICE): every AUD/CHF long is closed at 22:00 UTC that day.
    Returns {"gate": {day: (open, detail)}, "exits": [times]}."""
    def sma(v, i, n):
        return sum(x for _, x in v[i - n + 1:i + 1]) / n if i >= n - 1 else None

    def at(v, day):  # index of the last close BEFORE `day`
        return bisect_left([t for t, _ in v], day) - 1

    gate, exits = {}, []
    days = sorted({t for t, _ in spx} | {t for t, _ in vix})
    for D in (range(days[0], days[-1] + 2 * DAY, DAY) if days else []):  # every calendar day (FX trades on US holidays too)
        i, j, k = at(spx, D), at(vix, D), at(iron, D)
        if min(i, j, k) < 25:
            continue
        s20, s20b, i20 = sma(spx, i, 20), sma(spx, i - 5, 20), sma(iron, k, 20)
        up = spx[i][1] > s20 and s20 > s20b
        calm = vix[j][1] <= 1.05 * vix[j - 5][1] and vix[j][1] < 25
        ore = iron[k][1] > i20
        gate[D] = (up and calm and ore, f"S&P 500 {'up' if up else 'not up'} · VIX {vix[j][1]:.1f} {'calm' if calm else 'rising / high'} · iron ore {'rising' if ore else 'not rising'}")
    for v, lim, name in ((vix, 0.10, "VIX"), (spx, -0.015, "SPX")):
        for a, b in zip(v, v[1:]):
            ch = b[1] / a[1] - 1
            if (name == "VIX" and ch > lim) or (name == "SPX" and ch < lim):
                exits.append(b[0] + 22 * H1S)
    return {"gate": gate, "exits": sorted(set(exits))}


def team_name(key: str) -> str:
    return FAMILY[key]


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
        expiry: int, hold_until: int, cost: float, events: Optional[list] = None, news: Optional[list[int]] = None,
        exits: Optional[list[int]] = None, be_off: Optional[float] = 0.0, miss_px: Optional[float] = None, news_min: int = 0) -> dict:
    """A limit (or a market order at the close of candle k0) followed candle by candle on M5:
    PENDING → FILLED → TP1 (close `part`, stop to entry) → TP / STOP / BE_STOP / TIME, or EXPIRED / MISSED (target first).
    `hold_until`: unix time the rest is closed at market. `be_off`: the break-even stop sits be_off beyond the entry
    (gold: + $0.50). `miss_px`: a pending limit is cancelled when price reaches it first (gold: 1.5 R without a fill).
    Returns state, fill, at, r (in R, cost included)."""
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
                nm = news_min or NEWS_MIN  # EUR/USD: orders suspended 20 min before (its spec)
                j = bisect_left(news, x.time - NEWS_MIN * 60)
                if j < len(news) and news[j] < x.time + M5S + nm * 60:
                    log.append((i, "EXPIRED", entry))
                    return {"state": "EXPIRED", "at": i, "news": news[j]}
            if (d > 0 and x.low <= entry) or (d < 0 and x.high >= entry):
                fill = i
                break
            if (d > 0 and x.high >= tp) or (d < 0 and x.low <= tp) or \
               (miss_px is not None and ((d > 0 and x.high >= miss_px) or (d < 0 and x.low <= miss_px))):
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
    t_fill = m5[fill].time + M5S
    nxt = next((e for e in (exits or []) if e >= t_fill), None)  # a macro risk-off close after the fill (AUD/CHF)
    for j in range(start, n):
        x = m5[j]
        if nxt is not None and x.time >= nxt:
            r = banked + left * (x.open - entry) / risk * d - cost / risk
            log.append((j, "RISK_OFF", x.open))
            return {"state": "WIN" if r > 0.05 else "LOSS" if r < -0.05 else "BE", "fill": fill, "at": j, "r": r, "riskOff": True}
        if x.time >= hold_until:
            r = banked + left * (x.open - entry) / risk * d - cost / risk
            log.append((j, "TIME", x.open))
            return {"state": "WIN" if r > 0.05 else "LOSS" if r < -0.05 else "BE", "fill": fill, "at": j, "r": r}
        if (d > 0 and x.low <= stop) or (d < 0 and x.high >= stop):
            r = banked + left * (stop - entry) / risk * d - cost / risk
            log.append((j, "STOP" if stop == sl else "BE_STOP", stop))  # BE_STOP: the stop moved after TP1
            return {"state": "WIN" if r > 0.05 else "LOSS" if r < -0.05 else "BE", "fill": fill, "at": j, "r": r}
        if j > fill or market:
            if (d > 0 and x.high >= tp) or (d < 0 and x.low <= tp):
                r = banked + left * abs(tp - entry) / risk - cost / risk
                log.append((j, "TP", tp))
                return {"state": "WIN", "fill": fill, "at": j, "r": r}
            if tp1 is not None and left == 1.0 and ((d > 0 and x.high >= tp1) or (d < 0 and x.low <= tp1)):
                banked, left = part * abs(tp1 - entry) / risk, 1 - part
                if be_off is not None:  # None: the stop stays (EUR/USD's spec moves it nowhere)
                    stop = entry + d * be_off
                log.append((j, "TP1", tp1))
                if be_off is not None:
                    log.append((j, "BE", stop))
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


def _make(key, sid, d, m5, k0, entry, sl, tp1, tp, part, market, expiry_m5, hold_until, steps, geo, cost, zone=None,
          be_off: float = 0.0, miss_px: Optional[float] = None) -> Optional[dict]:
    risk = abs(entry - sl)
    if risk <= 0 or (d > 0 and not (sl < entry < tp)) or (d < 0 and not (tp < entry < sl)):
        return None
    if tp1 is not None and not ((d > 0 and entry < tp1 < tp) or (d < 0 and tp < tp1 < entry)):
        tp1 = None
    s = {"sid": sid, "pair": key, "dir": d, "index": k0, "time": m5[k0].time + M5S, "entry": entry, "sl": sl, "tp1": tp1, "tp": tp,
         "part": part if tp1 is not None else 1.0, "market": market, "expiry": expiry_m5, "holdUntil": hold_until,
         "rr": abs(tp - entry) / risk, "zone": zone or (entry, entry), "steps": steps, "geo": geo, "beOff": be_off, "missPx": miss_px}
    s["result"] = run(m5, k0, d, entry, sl, tp1, tp, s["part"], market, expiry_m5, hold_until, cost, None, None, None, be_off, miss_px)
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
    return True, f"ADR5/20 {a5 / a20:.2f}" + (" (compressed: targets cut)" if a5 / a20 < 0.70 else "")


# ---------------------------------------------------------------- the H1 bias (used by the engines)
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


# ---------------------------------------------------------------- EUR/USD SB · SnapBack 3σ (kept)
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
        s = _make(key, "SB", d, m5, k0, entry, entry - d * 2 * at[i], None, entry + d * 2 * at[i], 1.0, True, 0, t_close + 5 * DAY, steps,
                  {"bands": True}, cost)
        if s:
            out.append(s)
            res = s["result"]
            busy_until = m5[res["at"]].time + M5S if "at" in res else 1 << 62
    return out, watch


# ---------------------------------------------------------------- AUD/CAD · time-filtered 3σ mean reversion (kept)
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
    The other trigger: an RSI divergence AT the level (the guide: in the middle of the range it is noise): two H1 swing
    lows 5-40 candles apart, the second as low or lower while RSI 14 is higher (the mirror for highs), taken at the close
    of the candle that confirms the second swing (2 candles after it). EUR/CHF levels also include the daily pivots
    (P, S1, S2, R1, R2 from the previous day: the guide's "or Daily Pivots"). Entry at the close. Stop 0.5 × ADR20 from
    the entry and beyond the level. Target: EUR/CHF the mean (the band's middle line, 1:1 to 1:1.5), AUD/CAD 0.8 × ADR20.
    Held 24 hours (CHOICE)."""
    out, watch = [], []
    if len(h1) < 60:
        return out, watch
    cl = [x.close for x in h1]
    mid, sd = sma_std(cl, 16)
    r, a = rsi(cl, 14), adx(h1, 14)
    h4 = resample(h1, H4S)
    t4 = [x.time for x in h4]
    m5_times = [x.time for x in m5]
    hi_f, lo_f = fractals(h1)
    d1 = resample(h1, DAY)
    t1 = [x.time for x in d1]

    def pivots(t: int) -> list[float]:
        k = bisect_left(t1, t - t % DAY) - 1  # the previous (closed) day
        if key != "EURCHF" or k < 0:
            return []
        H, L, C = d1[k].high, d1[k].low, d1[k].close
        P = (H + L + C) / 3
        return [P, 2 * P - L, 2 * P - H, P + (H - L), P - (H - L)]

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
        trig, ext = "bands", (x.low if d > 0 else x.high)
        if not d:  # the other trigger: an RSI divergence whose second swing is confirmed by this candle
            j2 = i - 2
            for dd in (1, -1):
                if j2 < 1 or not (lo_f[j2] if dd > 0 else hi_f[j2]) or r[j2] is None:
                    continue
                j1 = next((j for j in range(j2 - 5, max(j2 - 40, 0), -1) if (lo_f[j] if dd > 0 else hi_f[j]) and r[j] is not None), None)
                if j1 is None:
                    continue
                p1, p2 = (h1[j1].low, h1[j2].low) if dd > 0 else (h1[j1].high, h1[j2].high)
                if ((p2 <= p1 and r[j2] > r[j1]) if dd > 0 else (p2 >= p1 and r[j2] < r[j1])):
                    d, trig, ext = dd, f"RSI divergence ({r[j1]:.0f} → {r[j2]:.0f})", p2
                    break
        if not d:
            continue
        a20 = daily.adr(t_close, 20)
        if not a20:
            continue
        tol = 0.1 * a20
        j4 = bisect_right(t4, t_close - H4S)
        levels = three_touch(h4, j4, d, tol)
        piv = pivots(t_close)
        lvl = next((v for v in levels + piv if abs(ext - v) <= tol or ((ext < v) if d > 0 else (ext > v)) and abs(x.close - v) <= 2 * tol), None)
        kind = "daily pivot" if lvl is not None and lvl in piv and lvl not in levels else "3-touch H4 level"
        reg_ok, reg = _regime(daily, t_close, True)
        steps = [(f"ADX {a[i]:.0f} < 30 (no strong trend)", a[i] < 30, ""), (f"Regime: {reg}", reg_ok, ""),
                 (f"At a {'support' if d > 0 else 'resistance'} ({kind})", lvl is not None,
                  f"{lvl:.5f}" if lvl else f"{len(levels)} level(s)" + (" + pivots" if piv else "") + ", none here"),
                 (f"Trigger: H1 close {'under' if d > 0 else 'over'} Bollinger (16, 3.0) + RSI {r[i]:.0f}" if trig == "bands" else f"Trigger: {trig}", True, "")]
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
        (f"2 · Red-folder pause: no CPI / NFP / FOMC / BoE / RBA / BoC / SNB / EIA {NEWS_MIN} min around the entry", not near,
         "not checked (no news history)" if news is None else ("news at " + ", ".join(hm(n) for n in near) + " UTC" if near else "none")),
        (f"3 · Reward >= 1:{need:g}", s["rr"] >= need - 1e-9, f"1:{s['rr']:.2f}"),
        (f"4 · Lot sized for {RISK_PCT.get((key, sid), 1.0):g} % risk", True, "risk / (stop pips × pip value)"),
        ("5 · Correlation cap (EUR/USD + GBP/USD: 0.5 % each · AUD/CAD + AUD/CHF: not both)", True, "checked across the six teams before any alert"),
        (f"6 · Volatility regime ({'mean reversion' if mr else 'sweep / trend'})", reg_ok,
         reg + (f" · targets cut to {s['cut'] * 100:.0f} % (compressed range)" if s.get("cut") else "")),
    ]


def scan(key: str, m5, h1, pip: float, cost: float, news: Optional[list[int]] = None, eur_m5=None, d1=None,
         macro: Optional[dict] = None, swiss_shock: Optional[list[int]] = None, events=None, research=None,
         spread_pips: Optional[float] = None) -> tuple[list, list]:
    """The pair's strategies on its candles: (setups with their result and checklist, what is forming). `news`: the
    red-folder pause times (red_folder + eia_times); `d1`: daily candles for the ADR (built from H1 when not given);
    `macro`: macro_view() for the AUD/CHF gate and its risk-off exits."""
    daily = Daily(d1 if d1 else resample(h1, DAY))
    from . import engines  # what is left of the master spec's engines (engines.py)
    if key == "XAUUSD":  # gold: its own spec and pipeline (gold.py): its news protocol, Devil, consensus
        from . import gold
        return gold.scan(m5, h1, cost, events, d1, macro, research)
    if key == "EURUSD":  # EUR/USD: its own spec and pipeline (fiber.py); eur_m5 carries GBP/USD here (the SMT)
        from . import fiber
        return fiber.scan(m5, h1, cost, events, d1, eur_m5)
    if key == "AUDCAD":  # AUD/CAD: its own spec and pipeline (loonie.py): regression channel, VPOC, S/D zones
        from . import loonie
        return loonie.scan(m5, h1, cost, events, d1, spread_pips)
    if key == "AUDCHF":  # AUD/CHF: its own spec and pipeline (aussie.py); eur_m5 carries (AUD/CAD, EUR/CHF) M5 here
        from . import aussie
        return aussie.scan(m5, h1, cost, events, d1, eur_m5)
    if key == "EURCHF":  # EUR/CHF: its own spec and pipeline (swissy.py): OU Z-score, Hurst, half-life
        from . import swissy
        return swissy.scan(m5, h1, cost, events, d1)
    if key == "GBPUSD":  # Cable: its own spec and pipeline (cable.py)
        from . import cable
        return cable.scan(m5, h1, cost, events, d1, eur_m5)
    if False:  # every pair now runs its own spec module above
        parts = [mean_reversion(m5, h1, daily, key, pip, cost)]
    else:
        return [], []  # no strategy passed the user's rule for this pair
    s = sorted((x for p in parts for x in p[0]), key=lambda x: x["time"])
    w = sorted((x for p in parts for x in p[1]), key=lambda x: x["time"])
    seen = set()
    s = [x for x in s if not ((x["sid"], x["time"], x["dir"]) in seen or seen.add((x["sid"], x["time"], x["dir"])))]
    nw = sorted(news) if news else None
    exits = None  # the macro risk-off exit belonged to the replaced AUD/CHF carry swing
    for x in s:
        a5, a20 = daily.adr(x["time"], 5), daily.adr(x["time"], 20)
        again = bool(nw and not x["market"]) or bool(exits)
        if (key, x["sid"]) not in MEAN_REVERSION and a5 and a20 and a5 / a20 < 0.70:
            # the guide's rescaling: a compressed range (ADR5 / ADR20 under 0.70) cuts the targets to the same share (CHOICE)
            f = a5 / a20
            x["cut"] = f
            x["tp"] = x["entry"] + (x["tp"] - x["entry"]) * f
            if x["tp1"] is not None:
                x["tp1"] = x["entry"] + (x["tp1"] - x["entry"]) * f
            x["rr"] = abs(x["tp"] - x["entry"]) / abs(x["entry"] - x["sl"])
            again = True
        if again:  # followed again with the news pause, the cut targets and the macro exits
            x["result"] = run(m5, x["index"], x["dir"], x["entry"], x["sl"], x["tp1"], x["tp"], x["part"], x["market"], x["expiry"],
                              x["holdUntil"], cost, None, nw if not x["market"] else None, exits, x.get("beOff", 0.0), x.get("missPx"))
        x["checklist"] = checklist(key, x, news, daily)
        x["pass"] = all(ok for _, ok, _ in x["checklist"])
    for x in s:  # a strategy turned off never passes (still measured)
        if (key, x["sid"]) in DISABLED:
            x["pass"] = False
            x["checklist"].append(("0 · Strategy switched on", False, "turned off: it lost in the one-year test"))
    # one trade per pair at a time (the portfolio check's rule, no stacking): a setup while the pair's last taken one is
    # still pending or open is not taken
    busy = 0
    for x in s:
        if not x["pass"]:
            continue
        if x["time"] < busy:
            x["pass"] = False
            x["checklist"].append(("7 · One trade per pair at a time", False, "the pair's previous setup is still pending or open"))
            continue
        r = x["result"]
        busy = m5[r["at"]].time + M5S if "at" in r else 1 << 62
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

    day = m5[-1].time - m5[-1].time % DAY

    def session(a0, a1, name, kind="session"):
        hl = hilo(span(m5, times, a0, a1))
        if hl:
            seg(a0, end, hl[0], kind, 1, f"{name} high")
            seg(a0, end, hl[1], kind, -1, f"{name} low")
        return hl

    def prev_day():
        hl = hilo(span(m5, times, day - DAY, day)) or hilo(span(m5, times, day - 3 * DAY, day - 2 * DAY + 1))
        if hl:
            seg(day - DAY, end, hl[0], "liquidity", 1, "PDH")
            seg(day - DAY, end, hl[1], "liquidity", -1, "PDL")

    def vwap_lines(k_sig):
        from .engines import vwap
        vw, sd = vwap(m5)
        k0 = bisect_left(times, day)
        pts = range(k0, len(m5), 3)
        for mult, lab in ((0, "daily VWAP"), (k_sig, f"VWAP ±{k_sig:g}σ"), (-k_sig, "")):
            lines.append({"points": [[m5[k].time + M5S, r(vw[k] + mult * sd[k])] for k in pts if vw[k] is not None],
                          "color": "#22D3EE", "label": lab, "dash": mult != 0})

    def dealing(n, label="dealing range"):
        if len(h1) >= n:
            lo, hi = min(x.low for x in h1[-n:]), max(x.high for x in h1[-n:])
            t0 = h1[-n].time
            seg(t0, end, hi, "liquidity", 1, f"{label} high")
            seg(t0, end, lo, "liquidity", -1, f"{label} low")
            seg(t0, end, (hi + lo) / 2, "eq", 0, "EQ 50 %")
            return lo, hi
        return None

    if key == "XAUUSD":  # the spec's pools, dealing range, OTE and killzones
        session(day, day + 6 * H1S, "Asia")
        session(day + 7 * H1S, day + 11 * H1S + 1800, "London", "liquidity")
        prev_day()
        from .gold import G as _G
        gx = _G(m5, h1, daily)
        for d_, lab in ((1, "EQL"), (-1, "EQH")):
            for v in gx.eq_levels(now, d_):
                seg(now - 12 * H1S, end, v, "liquidity", -d_, lab)
        dr = gx.dealing(now)
        if dr:
            seg(now - 24 * H1S, end, dr[1], "liquidity", 1, "H1 dealing high")
            seg(now - 24 * H1S, end, dr[0], "liquidity", -1, "H1 dealing low")
            seg(now - 24 * H1S, end, dr[2], "eq", 0, "E_eq 50 %")
            lo, hi = dr[0], dr[1]
            boxes.append({"from": now - 12 * H1S, "to": end + 2 * H1S, "top": r(hi - 0.618 * (hi - lo)), "bottom": r(hi - 0.786 * (hi - lo)),
                          "kind": "fvg", "dir": 1, "label": "OTE 61.8-78.6 % (long)"})
        windows += [{"from": day + 7 * H1S, "to": day + 9 * H1S + 1800, "label": "London killzone (A)"},
                    {"from": day + 12 * H1S + 1800, "to": day + 15 * H1S, "label": "NY / COMEX killzone (A)"},
                    {"from": day + 12 * H1S + 1800, "to": day + 14 * H1S + 900, "label": "NY Judas (B)"}]
    elif key == "EURUSD":  # the EUR/USD spec: the session VWAP ±1.5σ / ±2.0σ, the NY VWAP, the pools and killzones
        from .fiber import vwap_anchored
        session(day, day + 6 * H1S, "Asia")
        session(day + 7 * H1S, day + 12 * H1S, "London", "liquidity")
        prev_day()
        vw0, sd0 = vwap_anchored(m5, 0)
        vw12, _ = vwap_anchored(m5, 12)
        k0_ = bisect_left(times, day)
        pts_ = range(k0_, len(m5), 3)
        for mult, lab, dash in ((0, "session VWAP", False), (1.5, "VWAP ±1.5σ", True), (-1.5, "", True), (2.0, "VWAP ±2.0σ", True), (-2.0, "", True)):
            lines.append({"points": [[m5[q].time + M5S, r(vw0[q] + mult * sd0[q])] for q in pts_ if vw0[q] is not None], "color": "#22D3EE", "label": lab, "dash": dash})
        lines.append({"points": [[m5[q].time + M5S, r(vw12[q])] for q in pts_ if vw12[q] is not None], "color": "#F59E0B", "label": "NY VWAP", "dash": False})
        dealing(48, "H1 dealing range")
        windows += [{"from": day + 7 * H1S, "to": day + 10 * H1S, "label": "London killzone (A)"},
                    {"from": day + 12 * H1S, "to": day + 15 * H1S, "label": "NY overlap (B)"},
                    {"from": day + 16 * H1S + 1800, "to": day + 23 * H1S, "label": "dead zone (D)"}]
    elif key == "GBPUSD":  # the Cable spec: the Asian box, the Judas window, the ADR projections
        session(day, day + 6 * H1S + 1800, "Asia box")
        prev_day()
        tdy = hilo(span(m5, times, day, end))
        a14 = daily.adr(now, 14)
        if tdy and a14:
            for frac, lab in ((0.75, "75 % ADR"), (1.0, "100 % ADR")):
                seg(now - 6 * H1S, end, tdy[1] + frac * a14, "liquidity", 1, f"{lab} from the low")
                seg(now - 6 * H1S, end, tdy[0] - frac * a14, "liquidity", -1, f"{lab} from the high")
        dealing(48, "H1 dealing range")
        windows += [{"from": day + 6 * H1S + 2700, "to": day + 9 * H1S + 900, "label": "Judas window (A)"},
                    {"from": day + 12 * H1S + 1800, "to": day + 15 * H1S + 1800, "label": "NY continuation (B)"},
                    {"from": day + 15 * H1S, "to": day + 16 * H1S, "label": "London close (C)"}]
    elif key == "EURCHF":  # the EUR/CHF spec: the M15 50-bar mean with its ±1.25 / 2.0 / 2.2σ bands, the H4 channel, PDH / PDL
        from .swissy import E as _E
        ex = _E(m5, h1, daily)
        n = min(192, len(ex.m15))
        for mult, lab, col in ((0, "μ 50 (M15 mean)", "#A78BFA"), (2.0, "±2.0σ", "#A78BFA"), (-2.0, "", "#A78BFA"), (2.2, "±2.2σ (pierce)", "#F43F5E"),
                               (-2.2, "", "#F43F5E"), (1.25, "±1.25σ (TP2)", "#22D3EE"), (-1.25, "", "#22D3EE")):
            lines.append({"points": [[ex.m15[q].time + M15S, r(ex.mu[q] + mult * ex.sd[q])] for q in range(len(ex.m15) - n, len(ex.m15))
                                     if ex.mu[q] is not None and ex.m15[q].time + M15S <= end], "color": col, "label": lab, "dash": mult != 0})
        ch = ex.channel(now)
        if ch:
            t0 = ex.h4[max(0, ex.i4(now) - 29)].time
            seg(t0, end, ch[1], "liquidity", 1, f"H4 channel high ({ch[3]} touches)")
            seg(t0, end, ch[0], "liquidity", -1, f"H4 channel low ({ch[2]} touches)")
            seg(t0, end, (ch[0] + ch[1]) / 2, "eq", 0, "H4 midpoint (B target)")
        prev_day()
        windows.append({"from": day + 6 * H1S + 1800, "to": day + 15 * H1S + 1800, "label": "Zurich / Frankfurt / London (A, B)"})
    elif key == "AUDCAD":  # the AUD/CAD spec: the 100-bar H1 regression channel, VPOC / VAH / VAL, fresh S/D zones
        from .loonie import L as _L
        lx = _L(m5, h1, daily)
        i_ = lx.i1(now)
        c_ = lx.ch(i_) if i_ >= 0 else None
        if c_:
            k0_ = i_ - 99
            for mult, lab, col in ((0, "regression midline", "#A78BFA"), (1.75, "±1.75 σ_e", "#22D3EE"), (-1.75, "", "#22D3EE"), (1.9, "±1.90 σ_e (A)", "#F43F5E"), (-1.9, "", "#F43F5E")):
                lines.append({"points": [[h1[k0_ + q - 1].time + H1S, r(c_["alpha"] + c_["beta"] * q + mult * c_["se"])] for q in range(1, 101)],
                              "color": col, "label": lab, "dash": mult != 0})
        p_ = lx.pr(i_) if i_ >= 0 else None
        if p_:
            t0 = h1[max(0, i_ - 99)].time
            seg(t0, end, p_["vpoc"], "eq", 0, "VPOC (TP1)")
            seg(t0, end, p_["vah"], "liquidity", 1, "VAH 70 %")
            seg(t0, end, p_["val"], "liquidity", -1, "VAL 70 %")
            from .loonie import tests_of as _tests
            for z in [z for z in lx.zs if z["known"] <= now and now - z["known"] <= 30 * DAY and _tests(h1, z, now, lx.t1) <= 1][-6:]:
                boxes.append({"from": z["t0"], "to": end + 2 * H1S, "top": r(z["hi"]), "bottom": r(z["lo"]), "kind": "ob", "dir": z["dir"],
                              "label": f"fresh H1 {'demand' if z['dir'] > 0 else 'supply'}"})
        session(day, day + 6 * H1S, "Asia")
        windows += [{"from": day - H1S, "to": day + 5 * H1S, "label": "Sydney / Tokyo AUD"},
                    {"from": day + 12 * H1S + 1800, "to": day + 16 * H1S + 1800, "label": "Toronto / NY CAD"},
                    {"from": day + 20 * H1S + 2700, "to": day + 22 * H1S + 1800, "label": "rollover lockout"}]
    elif key == "AUDCHF":  # the AUD/CHF spec: the EMA 21 / 55 / 200 ribbon, the impulse leg's 50-78.6 %, the Asian box, the sessions
        from .aussie import A as _A
        ax = _A(m5, h1, daily)
        cl = [x.close for x in h1]
        col = {21: "#38BDF8", 55: "#F59E0B", 200: "#F43F5E"}
        for n_ in (21, 55, 200):
            lines.append(_line(h1, ema(cl, n_), 150, col[n_], f"EMA {n_}", False, r))
        i_ = ax.i1(now)
        d_ = ax.trend(i_) or ax.s1["trend"][i_] or 1
        im = ax.impulse(i_, d_) if i_ >= 0 else None
        if im:
            lo_, hi_, ilo, ihi = im
            leg = hi_ - lo_
            a_, b_ = (hi_ - 0.5 * leg, hi_ - 0.786 * leg) if d_ > 0 else (lo_ + 0.5 * leg, lo_ + 0.786 * leg)
            t0 = h1[min(ilo, ihi)].time
            boxes.append({"from": t0, "to": end + 2 * H1S, "top": r(max(a_, b_)), "bottom": r(min(a_, b_)), "kind": "fvg", "dir": d_,
                          "label": f"Pullback 50-78.6 % ({'long' if d_ > 0 else 'short'})"})
            seg(t0, end, hi_, "liquidity", 1, "SH_imp (TP1 long)")
            seg(t0, end, lo_, "liquidity", -1, "SL_imp (TP1 short)")
        session(day, day + 6 * H1S, "Asia box")
        prev_day()
        windows += [{"from": day - H1S, "to": day + 5 * H1S, "label": "Sydney / Tokyo (A)"},
                    {"from": day + 6 * H1S + 1800, "to": day + 10 * H1S + 1800, "label": "Zurich / London open (A, B)"},
                    {"from": day + 20 * H1S + 2700, "to": day + 22 * H1S + 1800, "label": "rollover lockout (D)"}]

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
    if g.get("ob"):
        hi, lo, t = g["ob"]
        boxes.append({"from": t, "to": end + 2 * H1S, "top": r(hi), "bottom": r(lo), "kind": "ob", "dir": d, "label": "Order block / breaker"})
    if g.get("fib"):
        o62, o79, _x, B, A, t = g["fib"]
        boxes.append({"from": t, "to": end + 2 * H1S, "top": r(max(o62, o79)), "bottom": r(min(o62, o79)), "kind": "ob", "dir": d, "label": "OTE 61.8-78.6 %"})
    return {"boxes": boxes, "segments": segs, "labels": labels, "lines": lines, "windows": windows}
