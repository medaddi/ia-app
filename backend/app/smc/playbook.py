"""
The shared pieces of the desk: candles and indicators, the trade followed on M5 (run), and the registry of what each
pair's team trades. Since 2026-11-10 (the user's spec "FXAlexG Set & Forget — redesigned 5-agent architecture") every
instrument runs ONE engine, alexg.py; every earlier strategy and the 7-agent team were purged (git history keeps them).

Every trade is followed on M5, the stop before the target inside a candle, spread + slippage included.
"""

from bisect import bisect_left, bisect_right
from typing import Optional

from ..market.pairs import PAIRS as _FX

M5S, M15S, H1S, H4S, DAY = 300, 900, 3600, 14400, 86400
NEWS_MIN = 30  # the spec: no entry and no pending limit within 30 min of a high-impact release of the pair's currencies

ALEXG_PAIRS = ["XAUUSD", *(p.replace("/", "") for p in _FX)]  # gold + the 28 forex pairs
SETUP_NAMES = {"SF_BR": "Set & Forget — Break & Retest Continuation", "SF_BOUNCE": "Set & Forget — Direct AOI Structure Bounce",
               "SF_COUNTER": "Set & Forget — Weekly Retracement Intraday Swing"}
STRATEGIES = {k: list(SETUP_NAMES) for k in ALEXG_PAIRS}
STRATEGY_NAME = "FXAlexG Set & Forget"
NAMES = {k: dict(SETUP_NAMES) for k in ALEXG_PAIRS}
CLAIMED = {(k, s): "the spec gives no benchmark; see the measured test" for k in ALEXG_PAIRS for s in SETUP_NAMES}


def team_name(key: str) -> str:
    return STRATEGY_NAME


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


def body(x) -> float:
    return abs(x.close - x.open)


def m5_index_at_close(m5_times: list[int], t_close: int) -> Optional[int]:
    """The M5 candle whose close is t_close or the last one closed before it."""
    k = bisect_right(m5_times, t_close - M5S) - 1
    return k if k >= 0 else None


def run(m5, k0: int, d: int, entry: float, sl: float, tp1: Optional[float], tp: float, part: float, market: bool,
        expiry: int, hold_until: int, cost: float, events: Optional[list] = None, news: Optional[list[int]] = None,
        exits: Optional[list[int]] = None, be_off: Optional[float] = 0.0, miss_px: Optional[float] = None, news_min: int = 0,
        friday_exit: bool = False) -> dict:
    """A limit (or a market order at the close of candle k0) followed candle by candle on M5:
    PENDING → FILLED → TP1 (close `part`, stop to entry) → TP / STOP / BE_STOP / TIME, or EXPIRED / MISSED (target first).
    `hold_until`: unix time the rest is closed at market. `be_off`: the break-even stop sits be_off beyond the entry
    (gold: + $0.50). `miss_px`: a pending limit is cancelled when price reaches it first (gold: 1.5 R without a fill).
    `friday_exit`: a trade not in profit at the first candle of Friday 20:00 UTC or later is closed there (TIME).
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
                nm = news_min or NEWS_MIN
                j = bisect_left(news, x.time - nm * 60)
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
    stop, banked, left, tp1_done, fri_seen = sl, 0.0, 1.0, False, set()
    t_fill = m5[fill].time + M5S
    nxt = next((e for e in (exits or []) if e >= t_fill), None)  # a macro risk-off close after the fill (AUD/CHF)
    for j in range(start, n):
        x = m5[j]
        if nxt is not None and x.time >= nxt:
            r = banked + left * (x.open - entry) / risk * d - cost / risk
            log.append((j, "RISK_OFF", x.open))
            return {"state": "WIN" if r > 0.05 else "LOSS" if r < -0.05 else "BE", "fill": fill, "at": j, "r": r, "riskOff": True}
        if friday_exit and j > fill:
            wd = (x.time // 86400 + 3) % 7  # Monday = 0
            wk = (x.time // 86400 + 3) // 7
            if wd == 4 and x.time % 86400 >= 20 * 3600 and wk not in fri_seen:
                fri_seen.add(wk)
                if (x.open - entry) * d <= 0:  # not in profit: closed at once
                    r = banked + left * (x.open - entry) / risk * d - cost / risk
                    log.append((j, "TIME", x.open))
                    return {"state": "WIN" if r > 0.05 else "LOSS" if r < -0.05 else "BE", "fill": fill, "at": j, "r": r, "fridayExit": True}
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
            if tp1 is not None and not tp1_done and ((d > 0 and x.high >= tp1) or (d < 0 and x.low <= tp1)):
                tp1_done = True
                banked, left = part * abs(tp1 - entry) / risk, 1 - part
                if be_off is not None:  # None: the stop stays (EUR/USD's spec moves it nowhere)
                    stop = entry + d * be_off
                log.append((j, "TP1", tp1))
                if be_off is not None:
                    log.append((j, "BE", stop))
    return {"state": "ACTIVE", "fill": fill, "stop": stop, "banked": banked}


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


def scan(key: str, m5, h1, cost: float, events=None, d1=None, research=None, spread: Optional[float] = None) -> tuple[list, list]:
    """The pair's FXAlexG setups on its candles: (setups with their result and checklist, what is forming)."""
    from . import alexg
    return alexg.scan(key, m5, h1, cost, events, d1, research, spread)
