"""
Trade management from the script's risk rules, applied to a filled setup (smc.simulate gives the plain result: full size
to TP or SL, closed at market after 4 hours).

  managed   50 % closed at 1:3 (Episode on risk: partials 25-50 % at 1:3; Team interpretation: 50 %)
            stop to break-even only after an M5 BOS (body close) in the trade's direction after the fill
            the rest runs to the strategy's TP, closed at market after 4 hours like the plain trade
Costs (spread + slippage) are paid once per trade, as in the plain result.
"""

from .smc import HOLD


def managed(m5, st5, s: dict, cost: float) -> dict:
    res = s["result"]
    if "fill" not in res or res["state"] in ("ACTIVE",):
        return res
    d, entry, sl, tp = s["dir"], s["entry"], s["sl"], s["tp"]
    risk = abs(entry - sl)
    p3 = entry + d * 3 * risk
    fill, n = res["fill"], len(m5)
    stop, banked, left = sl, 0.0, 1.0
    end = min(n, fill + HOLD)
    for j in range(fill, end):
        x = m5[j]
        lo, hi = x.low, x.high
        hit_stop = (d > 0 and lo <= stop) or (d < 0 and hi >= stop)
        if hit_stop:  # the stop first inside a candle (the conservative order)
            r_stop = (stop - entry) / risk * d
            return {**res, "state": "WIN" if banked + left * r_stop > 0 else "LOSS" if banked + left * r_stop < 0 else "BE",
                    "at": j, "r": banked + left * r_stop - cost / risk, "managed": True}
        if j > fill and ((d > 0 and hi >= tp) or (d < 0 and lo <= tp)):
            r_tp = abs(tp - entry) / risk
            return {**res, "state": "WIN", "at": j, "r": banked + left * r_tp - cost / risk, "managed": True}
        if left == 1.0 and j > fill and ((d > 0 and hi >= p3) or (d < 0 and lo <= p3)) and abs(tp - entry) > 3 * risk:
            banked, left = 0.5 * 3.0, 0.5  # half closed at 1:3
        brk = st5.breaks(j, d)
        if j > fill and brk and brk[0] == "BOS" and stop != entry:
            stop = entry  # break-even only after a structural BOS in favour, on a body close
    if end == n and n - fill < HOLD:
        return {**res, "state": "ACTIVE"}
    r_time = (m5[end - 1].close - entry) / risk * d
    return {**res, "state": "TIME", "at": end - 1, "r": banked + left * r_time - cost / risk, "managed": True}
