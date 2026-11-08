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

# The pair profiles (the master spec, 2026-11-08). Kept from the earlier guide, by the user's rule (win rate >= 55 % and
# profitable in both halves of the year test): EUR/USD SnapBack 3σ (SB) and AUD/CAD range reversion (P).
STRATEGIES = {"XAUUSD": ["S1", "S2", "S3", "S4"], "EURUSD": ["S1", "S2", "S3", "S4", "SB"], "GBPUSD": ["S1", "S2", "S3", "S4"],
              "EURCHF": ["S1", "S2", "S3"], "AUDCAD": ["P"], "AUDCHF": ["S1", "S2", "S3", "S4"]}
FAMILY = {"XAUUSD": "GOLD-QUANT S1–S4", "EURUSD": "INST-AMD S1–S4 + SnapBack", "GBPUSD": "CABLE-RAID S1–S4", "EURCHF": "SWISS-REV S1–S3",
          "AUDCAD": "Commodity range reversion", "AUDCHF": "RISK-REGIME S1–S4"}
NAMES = {
    "XAUUSD": {"S1": "Bullish Asian / London low sweep + M5 displacement & FVG", "S2": "Bearish Asian / London high sweep + M5 displacement & FVG",
               "S3": "NY COMEX momentum continuation pullback", "S4": "PDH / PDL rejection + M15 MSS"},
    "EURUSD": {"S1": "Bullish London / NY Judas into discount POI", "S2": "Bearish London / NY Judas into premium POI",
               "S3": "NY raid of the London extremes + OTE", "S4": "Daily VWAP rotation", "SB": "SnapBack 3σ mean reversion (kept)"},
    "GBPUSD": {"S1": "Bullish deep sweep + M15 reclaim + M5 breaker", "S2": "Bearish deep sweep + M15 reclaim + M5 breaker",
               "S3": "London open volatility squeeze", "S4": "NY overlap pullback to the H1 order block"},
    "EURCHF": {"S1": "Bullish extreme discount fade (Z <= -2.2)", "S2": "Bearish extreme premium fade (Z >= +2.2)",
               "S3": "VWAP ± 2.5σ European exhaustion"},
    "AUDCAD": {"P": "Commodity range reversion (kept)"},
    "AUDCHF": {"S1": "Risk-on trend pullback (OTE + H1 OB + M15 BOS)", "S2": "Risk-off trend pullback (OTE + H1 OB + M15 BOS)",
               "S3": "Bullish quiet-regime range fade", "S4": "Bearish quiet-regime range fade"},
}
CLAIMED = {(k, sid): "the spec gives no win rate: measured here" for k, v in STRATEGIES.items() for sid in v}
CLAIMED.update({("EURUSD", "SB"): "62.0 % (SteadyPips, 79 trades, 1:1); 70 % on our 1-year test", ("AUDCAD", "P"): "~60 %+; 59 % on our 1-year test",
                ("XAUUSD", "S1"): "spec example: 61.9 % on 42 setups (90 days)", ("EURCHF", "S1"): "spec example: 68.4 % on 2.2σ fades"})
MIN_RR = {**{("XAUUSD", s): 2.2 for s in ("S1", "S2", "S3")}, ("XAUUSD", "S4"): 2.0,
          **{("EURUSD", s): 2.0 for s in ("S1", "S2", "S3", "S4")}, ("EURUSD", "SB"): 1.0,
          **{("GBPUSD", s): 2.5 for s in ("S1", "S2", "S3", "S4")},
          **{("EURCHF", s): 1.8 for s in ("S1", "S2", "S3")}, ("AUDCAD", "P"): 1.5,
          ("AUDCHF", "S1"): 2.0, ("AUDCHF", "S2"): 2.0, ("AUDCHF", "S3"): 1.5, ("AUDCHF", "S4"): 1.5}
# Turned off on 2026-11-08 at the user's request ("Yes, turn them off"): the sub-strategies that LOST in the one-year
# Dukascopy test (net R <= 0, or a loss in either half). They are still measured by smc/tools/playbook_test.py, never sent.
# CAUTION: chosen on the same data they are measured on; strategies with no trade in the year stay on (nothing to judge).
DISABLED = {("XAUUSD", "S2"), ("XAUUSD", "S3"), ("XAUUSD", "S4"), ("EURUSD", "S3"), ("EURUSD", "S4"), ("GBPUSD", "S1"),
            ("GBPUSD", "S3"), ("GBPUSD", "S4"), ("EURCHF", "S1"), ("EURCHF", "S3")}
RISK_PCT = {**{("XAUUSD", s): 0.75 for s in ("S1", "S2", "S3", "S4")}}  # the spec: gold at most 0.75 %; the others 1 %
MEAN_REVERSION = {("EURUSD", "SB"), ("EURCHF", "S1"), ("EURCHF", "S2"), ("EURCHF", "S3"), ("AUDCAD", "P"), ("AUDCHF", "S3"), ("AUDCHF", "S4")}
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
        exits: Optional[list[int]] = None) -> dict:
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
         macro: Optional[dict] = None, swiss_shock: Optional[list[int]] = None) -> tuple[list, list]:
    """The pair's strategies on its candles: (setups with their result and checklist, what is forming). `news`: the
    red-folder pause times (red_folder + eia_times); `d1`: daily candles for the ADR (built from H1 when not given);
    `macro`: macro_view() for the AUD/CHF gate and its risk-off exits."""
    daily = Daily(d1 if d1 else resample(h1, DAY))
    from . import engines  # the master spec's engines (engines.py)
    cx = engines.Ctx(m5, h1, daily) if key != "AUDCAD" else None
    if key == "XAUUSD":
        parts = [engines.gold(cx, pip, cost)]
    elif key == "EURUSD":
        parts = [engines.amd(cx, pip, cost), snapback(m5, h1, daily, key, pip, cost)]
    elif key == "GBPUSD":
        parts = [engines.cable(cx, pip, cost)]
    elif key == "EURCHF":
        parts = [engines.swiss(cx, pip, cost, swiss_shock)]
    elif key == "AUDCAD":
        parts = [mean_reversion(m5, h1, daily, key, pip, cost)]
    elif key == "AUDCHF":
        parts = [engines.risk_regime(cx, pip, cost)]
    else:
        return [], []
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
                              x["holdUntil"], cost, None, nw if not x["market"] else None, exits)
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

    if key == "XAUUSD":
        session(day, day + 6 * H1S, "Asian")
        session(day + 7 * H1S, day + 10 * H1S + 1800, "London", "liquidity")
        prev_day()
        windows += [{"from": day + 7 * H1S, "to": day + 10 * H1S + 1800, "label": "London killzone"},
                    {"from": day + 12 * H1S + 1800, "to": day + 16 * H1S, "label": "NY / COMEX killzone"}]
    elif key == "EURUSD":
        session(day, day + 7 * H1S, "Asian")
        vwap_lines(1.5)
        bands()
        windows += [{"from": day, "to": day + 7 * H1S, "label": "Accumulation (Asia)"},
                    {"from": day + 7 * H1S, "to": day + 9 * H1S + 1800, "label": "Manipulation: London Judas"},
                    {"from": day + 12 * H1S, "to": day + 14 * H1S + 1800, "label": "Manipulation: NY Judas"}]
    elif key == "GBPUSD":
        session(day, day + 7 * H1S, "Asian")
        prev_day()
        windows += [{"from": day + 7 * H1S, "to": day + 10 * H1S, "label": "London raid"},
                    {"from": day + 12 * H1S + 1800, "to": day + 15 * H1S + 1800, "label": "NY overlap raid"}]
    elif key == "EURCHF":
        from .engines import zscore
        cl = [x.close for x in h1]
        z, mu, sg = zscore(cl, 50)
        n = min(150, len(h1))
        for mult, lab in ((0, "EMA 50 (mean)"), (2.2, "Z ±2.2σ"), (-2.2, "")):
            lines.append({"points": [[h1[i].time + H1S, r(mu[i] + mult * sg[i])] for i in range(len(h1) - n, len(h1)) if mu[i] is not None and sg[i] is not None],
                          "color": "#A78BFA", "label": lab, "dash": mult != 0})
        vwap_lines(2.5)
        dealing(50, "50-candle range")
        windows.append({"from": day + 6 * H1S + 1800, "to": day + 15 * H1S + 1800, "label": "European hours"})
    elif key == "AUDCAD":
        bands()
        a20 = daily.adr(now, 20)
        if a20:
            h4 = resample(h1, H4S)
            for d in (1, -1):
                for v in three_touch(h4, len(h4), d, 0.1 * a20):
                    seg(h4[max(0, len(h4) - 120)].time, end, v, "liquidity", -d, f"3-touch level ({'swing lows' if d > 0 else 'swing highs'})")
        windows.append({"from": day, "to": day + 11 * H1S, "label": "reversion window (Tokyo / London)"})
    elif key == "AUDCHF":
        emas((20, 50, 200))
        dealing(60, "60-candle range")
        windows.append({"from": day + 6 * H1S, "to": day + 15 * H1S, "label": "execution window"})

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
