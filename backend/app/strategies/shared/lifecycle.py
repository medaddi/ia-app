"""
Order lifecycle simulator. The live status shown in the app, the daily trade/loss limits and
the backtester all use this one function, so they can never disagree.

Price model: candles are bid prices. A BUY fills at ask (bid + spread) and exits at bid;
a SELL fills at bid and exits at ask. Stops get extra slippage. When one candle touches both
SL and a target, SL is assumed first (conservative).

`params` keys (camelCase, stored with the setup): side, entryType, entry, sl, tp1, tp2,
tp3 (None = trail only), expiryTime, marketFillTime, cancelIfTp1BeforeFill, partials, spread, slippage,
breakeven (optional, default True: stop to entry at TP1; False = set & forget), maxBars (optional time exit).
"""

from typing import Callable, Optional

from .jsnum import js_div, round_to
from .types import Candle


def simulate_lifecycle(c: list[Candle], p: dict, start_index: int,
                       trail_level: Optional[Callable[[int], Optional[float]]] = None,
                       upto_index: Optional[int] = None,
                       exit_when: Optional[Callable[[int], bool]] = None) -> dict:
    """`exit_when(i)`: the strategy's own exit (e.g. RSI(2): the close crosses back over EMA5) → closed at that candle's close."""
    if upto_index is None:
        upto_index = len(c) - 1
    buy = p["side"] == "BUY"
    risk = abs(p["entry"] - p["sl"])
    spread, slippage = p["spread"], p["slippage"]
    partials = p["partials"]
    res = {"state": "PENDING" if p["entryType"] == "LIMIT" else "OPEN", "events": [], "fillTime": None, "fillPrice": None,
           "exitTime": None, "rMultiple": None, "outcome": None}
    events = res["events"]
    acc = {"realised": 0.0, "remaining": 1.0}
    stop = p["sl"]
    stage = 0  # 0 = before TP1, 1 = after TP1, 2 = after TP2

    def r(exit_price: float) -> float:
        return js_div((exit_price - res["fillPrice"]) if buy else (res["fillPrice"] - exit_price), risk)

    def close(t: int, exit_price: float, kind: str) -> dict:
        acc["realised"] += acc["remaining"] * r(exit_price)
        acc["remaining"] = 0
        res["state"] = "CLOSED"
        res["exitTime"] = t
        events.append({"time": t, "type": kind, "price": exit_price})
        realised = acc["realised"]
        res["rMultiple"] = round_to(realised, 3)
        res["outcome"] = "WIN" if realised > 0.05 else "LOSS" if realised < -0.05 else "BREAKEVEN"
        return res

    i = start_index
    if p["entryType"] == "MARKET":
        fill = p["entry"] + spread + slippage if buy else p["entry"] - slippage
        res["fillPrice"] = fill
        mft = p.get("marketFillTime")
        res["fillTime"] = mft if mft is not None else (c[i].time if 0 <= i < len(c) else None)  # filled as the confirmation candle closes
        events.append({"time": res["fillTime"] if res["fillTime"] is not None else 0, "type": "FILL", "price": fill})

    end = min(upto_index + 1, len(c))
    while i < end:
        x = c[i]
        if res["state"] == "PENDING":
            if p["expiryTime"] is not None and x.time >= p["expiryTime"]:
                res["state"] = "EXPIRED"
                events.append({"time": x.time, "type": "EXPIRE", "price": x.open})
                return res
            touched = (x.low + spread <= p["entry"]) if buy else (x.high >= p["entry"])
            tp1_first = p["cancelIfTp1BeforeFill"] and ((x.high >= p["tp1"]) if buy else (x.low + spread <= p["tp1"]))
            if not touched and tp1_first:
                res["state"] = "CANCELLED"
                events.append({"time": x.time, "type": "CANCEL", "price": p["tp1"]})
                return res
            if not touched:
                i += 1
                continue
            res["state"] = "OPEN"
            res["fillPrice"] = p["entry"]  # limit fills at its price
            res["fillTime"] = x.time
            events.append({"time": x.time, "type": "FILL", "price": p["entry"]})
            # Stop on the fill candle itself (worst case)
            if (x.low <= stop) if buy else (x.high + spread >= stop):
                return close(x.time, stop - slippage if buy else stop + slippage, "SL")
            i += 1
            continue

        stop_hit = (x.low <= stop) if buy else (x.high + spread >= stop)
        if stop_hit:
            original = stop == p["sl"]  # set & forget keeps the original stop after TP1/TP2
            slip = slippage if original else 0
            return close(x.time, stop - slip if buy else stop + slip, "SL" if original else "BE_EXIT" if stage == 1 else "TRAIL_EXIT")

        def reached(tp: float) -> bool:
            return x.high >= tp if buy else x.low + spread <= tp

        if stage == 0 and reached(p["tp1"]):
            acc["realised"] += partials[0] * r(p["tp1"])
            acc["remaining"] -= partials[0]
            stage = 1
            if p.get("breakeven", True):
                stop = res["fillPrice"]
            res["state"] = "TP1_HIT"
            events.append({"time": x.time, "type": "TP1", "price": p["tp1"]})
            if p.get("breakeven", True):
                events.append({"time": x.time, "type": "BE", "price": stop})
        if stage == 1 and reached(p["tp2"]):
            acc["realised"] += partials[1] * r(p["tp2"])
            acc["remaining"] -= partials[1]
            stage = 2
            res["state"] = "TP2_HIT"
            events.append({"time": x.time, "type": "TP2", "price": p["tp2"]})
        if stage == 2 and p.get("tp3") is not None and reached(p["tp3"]):
            return close(x.time, p["tp3"], "TP3")
        if stage == 2 and trail_level:
            t = trail_level(i)
            if t is not None and (t > stop if buy else t < stop):
                stop = t
        # Strategy exit at the close (buy at bid, sell at ask)
        if exit_when and exit_when(i):
            return close(x.time, x.close if buy else x.close + spread, "SIGNAL_EXIT")
        # Optional time exit: close at the close of the `maxBars`-th candle after the entry (buy at bid, sell at ask)
        if p.get("maxBars") and i - start_index + 1 >= p["maxBars"]:
            return close(x.time, x.close if buy else x.close + spread, "TIME_EXIT")
        i += 1
    return res
