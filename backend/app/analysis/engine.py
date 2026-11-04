"""
The "Analyse" button: the pair read now (trend, volatility, the SMC view) and every library strategy checked on the
latest CLOSED candles (library.py):

  SETUP    the strategy fired on a recent candle, its trade has hit neither the stop nor the target, its time limit is
           not over and less than half the move to the target is done: it can still be taken (entry, SL, TP, lots)
  LATE     it fired, but more than half of the move to the target is done: too late to enter
  WAITING  no setup: what it waits for (the channel level and its distance, the hours, ADX / RSI / trend side)

One request per press, nothing polled: the candles come from the feed's cache (refreshed at most once a minute).
"""

import time
from typing import Optional

from ..agents.registry import AGENT_CONFIGS
from ..agents.smc import smc_view
from ..core.quant_primitives import adx, atr, ema, rsi
from ..market.data import fetch_candle_series, fetch_live_price, market_session_status
from ..strategies.shared.jsnum import fmt_utc_minute, round_to
from ..strategies.shared.risk import lot_table
from ..strategies.shared.types import TF_SEC, closed_only
from .library import LIBRARY

PROVIDER = {"H1": ("1H", 12500), "H4": ("4H", 3200)}


def in_hours(t: int, hours) -> bool:
    if not hours:
        return True
    h, (a, b) = (t // 3600) % 24, hours
    return a <= h < b if a < b else (h >= a or h < b)


class _Ind:
    """The indicators of one timeframe, computed once for every strategy that reads it."""

    def __init__(self, c):
        cl = [x.close for x in c]
        self.c, self.a, self.ax, self.r = c, atr(c), adx(c), rsi(c)
        self.e50, self.e200 = ema(cl, 50), ema(cl, 200)
        self._ch: dict[int, tuple[list, list]] = {}

    def channel(self, n: int, i: int) -> tuple[Optional[float], Optional[float]]:
        if i < n:
            return None, None
        w = self.c[i - n:i]
        return max(x.high for x in w), min(x.low for x in w)


def _signal(ind: _Ind, s: dict, i: int) -> Optional[int]:
    """+1 buy / −1 sell when the strategy fires on candle i (its rules exactly as tested), else None."""
    c, p = ind.c, s["p"]
    hi, lo = ind.channel(p["n"], i)
    a = ind.a[i]
    if hi is None or a is None or not in_hours(c[i].time, p.get("hours")):
        return None
    x = c[i]
    if s["fam"] == "breakout":
        if ind.e50[i] is None or ind.e200[i] is None or (p.get("adx") and (ind.ax[i] is None or ind.ax[i] < p["adx"])):
            return None
        if x.close > hi and ind.e50[i] > ind.e200[i]:
            return 1
        if x.close < lo and ind.e50[i] < ind.e200[i]:
            return -1
        return None
    if p.get("adx") and (ind.ax[i] is None or ind.ax[i] >= p["adx"]):
        return None
    d = -1 if x.close > hi else 1 if x.close < lo else 0
    if not d:
        return None
    r = ind.r[i]
    if p.get("rsi") and (r is None or (d > 0 and r > p["rsi"]) or (d < 0 and r < 100 - p["rsi"])):
        return None
    if p.get("trend") and (ind.e200[i] is None or (d > 0) != (x.close > ind.e200[i])):
        return None
    return d


def _waiting(ind: _Ind, s: dict, last: int, pip: float, now: int) -> str:
    """What the strategy waits for on the next candle, in plain words."""
    c, p = ind.c, s["p"]
    hi, lo = ind.channel(p["n"], last + 1 if last + 1 <= len(c) else last)
    if hi is None:
        return "Not enough history"
    px = c[last].close
    up, dn = (hi - px) / pip, (px - lo) / pip
    if p.get("hours") and not in_hours(c[last].time + TF_SEC[s["tf"]], p["hours"]):
        return f"Trades only {p['hours'][0]:02d}:00–{p['hours'][1]:02d}:00 GMT: waiting for the window"
    if s["fam"] == "breakout":
        e50, e200 = ind.e50[last], ind.e200[last]
        if e50 is None or e200 is None:
            return "Not enough history"
        if p.get("adx") and (ind.ax[last] or 0) < p["adx"]:
            return f"ADX {ind.ax[last] or 0:.0f} < {p['adx']}: no momentum for a breakout yet"
        return (f"Uptrend: a {s['tf']} close above {hi:.5g} ({up:.0f} pips away) buys" if e50 > e200
                else f"Downtrend: a {s['tf']} close below {lo:.5g} ({dn:.0f} pips away) sells")
    if p.get("adx") and (ind.ax[last] or 0) >= p["adx"]:
        return f"ADX {ind.ax[last]:.0f} ≥ {p['adx']}: a strong trend, no fade"
    side = ""
    if p.get("trend") and ind.e200[last] is not None:
        side = " (buy side only: price above EMA200)" if px > ind.e200[last] else " (sell side only: price below EMA200)"
    rsi_txt = f", RSI(14) beyond {p['rsi']} / {100 - p['rsi']}" if p.get("rsi") else ""
    return f"A {s['tf']} close below {lo:.5g} ({dn:.0f} pips) buys / above {hi:.5g} ({up:.0f} pips) sells{rsi_txt}{side}"


def _check(ind: _Ind, s: dict, spec: dict, price: float, now: int) -> dict:
    c = ind.c
    last = len(c) - 1
    pip = spec["pipSize"]
    d = spec["decimals"]
    out = {"id": s["id"], "name": s["name"], "timeframe": s["tf"], "family": s["fam"], "targetR": s["rr"], "maxBars": s["mb"], "test": s["test"]}
    # the most recent signal whose trade could still be running (within its time limit)
    for i in range(last, max(210, last - s["mb"] + 1) - 1, -1):  # entered at the close of i, out by the close of i + mb
        sd = _signal(ind, s, i)
        if not sd:
            continue
        e = c[i].close
        risk = s["p"]["sl"] * ind.a[i]
        sl, tp = e - sd * risk, e + sd * s["rr"] * risk
        hit = None
        for x in c[i + 1:]:
            if (sd > 0 and x.low <= sl) or (sd < 0 and x.high >= sl):
                hit = "SL"
                break
            if (sd > 0 and x.high >= tp) or (sd < 0 and x.low <= tp):
                hit = "TP"
                break
        when = c[i].time + TF_SEC[s["tf"]]
        if hit:
            out.update(status="WAITING", reason=_waiting(ind, s, last, pip, now),
                       last={"direction": "BUY" if sd > 0 else "SELL", "at": when, "result": hit})
            return out
        done = (price - e) / risk * sd if risk else 0  # R already made from the entry
        setup = {"direction": "BUY" if sd > 0 else "SELL", "entry": round_to(e, d), "sl": round_to(sl, d), "tp": round_to(tp, d), "rr": s["rr"],
                 "since": when, "closeBy": when + s["mb"] * TF_SEC[s["tf"]], "rNow": round(done, 2),
                 "slPips": round(risk / pip, 1), "lots": lot_table(spec, e, sl, 1, [500, 1000, 5000, 10000])}
        late = done > 0.5 * s["rr"]
        out.update(status="LATE" if late else "SETUP", setup=setup,
                   reason=(f"Fired {fmt_utc_minute(when)} UTC, {done:+.2f}R already: most of the move is done" if late
                           else f"Fired {fmt_utc_minute(when)} UTC · now {done:+.2f}R from the entry · closed at market by {fmt_utc_minute(setup['closeBy'])} UTC"))
        return out
    out.update(status="WAITING", reason=_waiting(ind, s, last, pip, now))
    return out


async def analyse(pair: str) -> dict:
    """The pair now: price, trend, volatility, the SMC read, and every library strategy's state."""
    now = int(time.time())
    spec = AGENT_CONFIGS[pair]["spec"]
    live = await fetch_live_price(pair)
    price = live.get("price") or 0
    inds: dict[str, _Ind] = {}
    for tf in sorted({s["tf"] for s in LIBRARY[pair]}):
        code, n = PROVIDER[tf]
        series = await fetch_candle_series(pair, code, n, price)
        inds[tf] = _Ind(closed_only(series["candles"], TF_SEC[tf], now))
    main = inds["H1"] if "H1" in inds else next(iter(inds.values()))
    if len(main.c) < 260:
        return {"success": False, "symbol": pair, "error": "Not enough history from the feed"}
    last = len(main.c) - 1
    price = price or main.c[last].close
    a_now = main.a[last]
    usual = sorted(v for v in main.a[-200:] if v)
    ratio = a_now / usual[len(usual) // 2] if a_now and usual else 1
    trend = "bullish" if (main.e50[last] or 0) > (main.e200[last] or 0) else "bearish"
    smc = smc_view(main.c, spec["symbol"], TF_SEC["H1" if "H1" in inds else "H4"])
    rows = [_check(inds[s["tf"]], s, spec, price, now) for s in LIBRARY[pair]]
    order = {"SETUP": 0, "LATE": 1, "WAITING": 2}
    rows.sort(key=lambda r: (order[r["status"]], -r["test"]["unseen"]["winRate"]))
    setups = [r for r in rows if r["status"] == "SETUP"]
    return {
        "success": True, "symbol": pair, "price": price, "priceSource": live.get("source"), "quoteTime": live.get("quoteTime"), "at": now,
        "marketOpen": market_session_status(pair)["isOpen"], "decimals": spec["decimals"],
        "read": {"trend": trend, "volatility": "high" if ratio > 1.5 else "low" if ratio < 0.7 else "normal", "atrRatio": round(ratio, 2),
                 "atrPips": round(a_now / spec["pipSize"], 1) if a_now else None, "smc": smc["summary"]},
        "verdict": (f"{len(setups)} setup(s) can be taken now" if setups else "No setup right now: every strategy is waiting"),
        "strategies": rows,
    }
