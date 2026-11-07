"""
Trade management from the brief's risk rules, applied to a filled setup (smc.simulate gives the plain result: full size
to TP or SL, closed at market after 4 hours). The same function runs in the backtest and in the live trade manager.

  managed   50 % closed at 1:3 (brief: partials 25-50 % at 1:3; Team interpretation: 50 %)
            stop to break-even only after an M5 BOS (body close) in the trade's direction after the fill
            trailing (brief: "trailing under confirmed higher lows / lower highs"): once at break-even, the stop follows
            each M5 swing low (buy) confirmed after the fill, one cost under it, and only ever moves in favour
            the rest runs to the strategy's TP, closed at market after 4 hours like the plain trade
Costs (spread + slippage) are paid once per trade, as in the plain result. Every step is dated by the candle that makes it
known (a swing is used only from the candle that confirms it: no look-ahead).
"""

from .engine import HOLD


def _confirmations(st5) -> dict:
    """candle index → the swings it confirms (lows for buys, highs for sells), built once per structure."""
    cache = getattr(st5, "_by_confirm", None)
    if cache is None:
        cache = {}
        for j, at in st5.confirmed_at.items():
            cache.setdefault(at, []).append(j)
        st5._by_confirm = cache
    return cache


def managed(m5, st5, s: dict, cost: float, trail: bool = True, events: list | None = None) -> dict:
    """`events` (optional) receives each management step: (candle index, kind, price) — the live trade manager sends them."""
    res = s["result"]
    if "fill" not in res or res["state"] in ("ACTIVE",):
        return res
    d, entry, sl, tp = s["dir"], s["entry"], s["sl"], s["tp"]
    risk = abs(entry - sl)
    p3 = entry + d * 3 * risk
    fill, n = res["fill"], len(m5)
    stop, banked, left = sl, 0.0, 1.0
    end = min(n, fill + HOLD)
    conf = _confirmations(st5) if trail else {}
    lows = set(st5.swing_lows_after) if d > 0 else set(st5.swing_highs_after)
    log = events if events is not None else []
    for j in range(fill, end):
        x = m5[j]
        lo, hi = x.low, x.high
        hit_stop = (d > 0 and lo <= stop) or (d < 0 and hi >= stop)
        if hit_stop:  # the stop first inside a candle (the conservative order)
            r_stop = (stop - entry) / risk * d
            r = banked + left * r_stop - cost / risk
            log.append((j, "STOP" if stop == sl else "BE_STOP" if stop == entry else "TRAIL_STOP", stop))
            return {**res, "state": "WIN" if r > 0 else "LOSS" if r < 0 else "BE", "at": j, "r": r, "managed": True}
        if j > fill and ((d > 0 and hi >= tp) or (d < 0 and lo <= tp)):
            r_tp = abs(tp - entry) / risk
            log.append((j, "TP", tp))
            return {**res, "state": "WIN", "at": j, "r": banked + left * r_tp - cost / risk, "managed": True}
        if left == 1.0 and j > fill and ((d > 0 and hi >= p3) or (d < 0 and lo <= p3)) and abs(tp - entry) > 3 * risk:
            banked, left = 0.5 * 3.0, 0.5  # half closed at 1:3
            log.append((j, "PARTIAL_1_3", p3))
        brk = st5.breaks(j, d)
        if j > fill and brk and brk[0] == "BOS" and (stop - entry) * d < 0:
            stop = entry  # break-even only after a structural BOS in favour, on a body close
            log.append((j, "BE", entry))
        if trail and (stop - entry) * d >= 0:  # at break-even or better: trail under each new confirmed swing
            for k in conf.get(j, ()):
                if k <= fill or k not in lows:
                    continue
                lvl = (m5[k].low - cost) if d > 0 else (m5[k].high + cost)
                if (lvl - stop) * d > 0 and (x.close - lvl) * d > 0:
                    stop = lvl
                    log.append((j, "TRAIL", lvl))
    if end == n and n - fill < HOLD:
        return {**res, "state": "ACTIVE", "stop": stop, "banked": banked}
    r_time = (m5[end - 1].close - entry) / risk * d
    log.append((end - 1, "TIME", m5[end - 1].close))
    return {**res, "state": "TIME", "at": end - 1, "r": banked + left * r_time - cost / risk, "managed": True}
