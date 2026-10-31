import math
from typing import Optional

from .jsnum import clamp01, iso, round_to
from .liquidity import Level
from .sessions import in_local_window
from .structure import Swing
from .types import Candle


def is_untaken(level: Level, c: list[Candle], upto_index: int) -> bool:
    """A level is still liquidity if no closed candle traded beyond it since it became available."""
    high_side = level.side == "HIGH"
    price, avail = level.price, level.availableFrom
    for i in range(min(upto_index + 1, len(c))):
        x = c[i]
        if x.time <= avail:
            continue
        if (x.high > price) if high_side else (x.low < price):
            return False
    return True


def nearest_swing_beyond(swings: list[Swing], price: float, buy: bool, upto_index: int) -> Optional[Swing]:
    """Nearest untaken swing beyond `price` in the trade direction (opposing liquidity on that timeframe)."""
    kind = "HIGH" if buy else "LOW"
    pool = [s for s in swings if s.kind == kind and s.confirmedIndex <= upto_index and (s.takenIndex is None or s.takenIndex > upto_index)
            and (s.price > price if buy else s.price < price)]
    pool.sort(key=lambda s: s.price if buy else -s.price)
    return pool[0] if pool else None


HISTORY_MAX = 40  # past trades kept for the chart (the most recent; the analysis is polled every second)


REACH_DAYS = 5  # how long a past trade is followed to see how far the market went for it
TP_STEPS = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5]  # R multiples offered as targets


def max_reach_r(c: list, i: int, buy: bool, entry: float, sl: float, tf_sec: int) -> float:
    """How far the market went in the trade's favour (in R) before touching its stop, over the next REACH_DAYS.
    A candle that touches the stop counts for nothing (conservative: the stop may have come first)."""
    risk = abs(entry - sl)
    if risk <= 0:
        return 0.0
    best = 0.0
    for x in c[i + 1:i + 1 + int(REACH_DAYS * 86400 / tf_sec)]:
        if (x.low <= sl) if buy else (x.high >= sl):
            break
        best = max(best, ((x.high - entry) if buy else (entry - x.low)) / risk)
    return round(best, 2)


def tp_options(past: list[dict], setup: Optional[dict], decimals: int) -> dict:
    """Targets the market can reach, measured on this pair's own past trades: for each R multiple, the share of past
    trades whose price got there before the stop. `realistic` = the furthest target reached by at least half of them."""
    reach = [p["reachR"] for p in past if p.get("reachR") is not None]
    n = len(reach)
    steps = [{"r": r, "reach": round(100 * sum(x >= r for x in reach) / n) if n else None} for r in TP_STEPS]
    realistic = max((st["r"] for st in steps if st["reach"] is not None and st["reach"] >= 50), default=None)
    out = {"sample": n, "steps": steps, "realistic": realistic, "median": sorted(reach)[n // 2] if n else None}
    if setup:
        buy, risk = setup["direction"] == "BUY", abs(setup["entry"] - setup["sl"])
        for st in out["steps"]:  # on the tick, toward the entry (never further than the R it stands for)
            px = setup["entry"] + st["r"] * risk if buy else setup["entry"] - st["r"] * risk
            st["price"] = round((math.floor(px * 10 ** decimals + 1e-6) if buy else math.ceil(px * 10 ** decimals - 1e-6)) / 10 ** decimals, decimals)
    return out


BE_BAND = 0.05  # |R| at or below this = breakeven (costs only)


def trade_class(r: Optional[float]) -> str:
    """TP (closed in profit), SL (closed at a loss) or BE (out at the entry, costs only)."""
    if r is None or abs(r) <= BE_BAND:
        return "BE"
    return "TP" if r > 0 else "SL"


def history_stats(past: list[dict]) -> dict:
    """Performance of the pair's strategy over every closed trade: TP / SL / BE counts, win rate (BE excluded),
    total and average R, profit factor, max drawdown and the longest losing run."""
    rs = [p["r"] or 0.0 for p in past]
    cls = [trade_class(p["r"]) for p in past]
    tp, sl, be = cls.count("TP"), cls.count("SL"), cls.count("BE")
    gains, losses = sum(r for r in rs if r > BE_BAND), -sum(r for r in rs if r < -BE_BAND)
    eq = peak = dd = 0.0
    run = worst_run = 0
    for r, c in zip(rs, cls):
        eq += r
        peak, dd = max(peak, eq), max(dd, peak - eq)
        run = run + 1 if c == "SL" else 0 if c == "TP" else run
        worst_run = max(worst_run, run)
    return {"trades": len(past), "tp": tp, "sl": sl, "be": be, "winRate": round(100 * tp / (tp + sl)) if tp + sl else None,
            "totalR": round(sum(rs), 2), "avgR": round(sum(rs) / len(rs), 2) if rs else None,
            "profitFactor": round(gains / losses, 2) if losses else None, "maxDrawdownR": round(dd, 2),
            "avgWinR": round(gains / tp, 2) if tp else None, "avgLossR": round(-losses / sl, 2) if sl else None,
            "bestR": round(max(rs), 2) if rs else None, "worstR": round(min(rs), 2) if rs else None, "maxLosingRun": worst_run,
            "since": past[0]["signalTime"] if past else None}


def trade_record(s: dict, entry_tf_sec: int, c: Optional[list] = None, i: Optional[int] = None) -> dict:
    """A finished trade of the strategy, compact, for the history list: where it started, its levels, how it ended,
    and how far the market went for it before the stop (used to rate the reachable targets)."""
    lc = s["lifecycle"]
    single = s["params"].get("breakeven", True) is False
    ev = lc.get("events") or []
    last = ev[-1] if ev else None
    return {"id": s["id"], "setup": s["setup"], "direction": s["direction"], "time": s["signalTime"] - entry_tf_sec, "signalTime": s["signalTime"],
            "entry": s["entry"], "sl": s["sl"], "target": s["tp3"] if single else s["tp2"],
            "exitTime": lc.get("exitTime"), "exitPrice": round(last["price"], 5) if last and last["type"] != "FILL" else None,
            "exitType": last["type"] if last else None, "outcome": lc.get("outcome"), "r": lc.get("rMultiple"), "result": trade_class(lc.get("rMultiple")),
            "reachR": max_reach_r(c, i, s["direction"] == "BUY", s["entry"], s["sl"], entry_tf_sec) if c is not None and i is not None else None}


def active_window(ts_sec: int, windows: list[dict]) -> Optional[dict]:
    return next((w for w in windows if in_local_window(ts_sec, w["tz"], w["start"], w["end"])), None)


def volatility_ratio(atr: list[float], lookback: int) -> dict:
    """ATR now vs its average over `lookback` bars."""
    vals = [v for v in atr if math.isfinite(v)]
    now = vals[-1] if vals else math.nan
    window = vals[-lookback:] if lookback > 0 else vals
    s = 0.0
    for v in window:
        s += v
    avg = s / (len(window) or 1)
    return {"now": now, "avg": avg, "ratio": now / avg if avg > 0 else math.nan}


def item(key: str, rule: str, rule_ar: str, passed: bool, detail: str, weight: float, required: bool, quality: Optional[float] = None) -> dict:
    out = {"key": key, "rule": rule, "ruleAr": rule_ar, "passed": bool(passed), "detail": detail, "weight": weight, "required": required}
    if quality is not None:
        out["quality"] = clamp01(quality)
    return out


def to_signal_json(spec: dict, strategy: str, setup: dict, score: float, timeframes: dict, checklist: list[dict]) -> dict:
    expires = setup["expiresAt"] if setup["expiresAt"] is not None else setup["signalTime"] + 4 * 3600
    return {
        "symbol": spec["symbol"],
        "strategy": strategy,
        "setup": setup["setup"],
        "direction": setup["direction"],
        "entry_type": setup["entryType"],
        "entry": setup["entry"],
        "sl": setup["sl"],
        "tp1": setup["tp1"],
        "tp2": setup["tp2"],
        "tp3": setup["tp3"],
        "rr_tp2": round_to(setup["rrTp2"], 2),
        "score": score,
        "timeframes": timeframes,
        "checklist": [{"rule": c["rule"], "passed": c["passed"], "detail": c["detail"]} for c in checklist],
        "invalidation": setup["invalidation"],
        "expires_at": iso(expires),
        "explanation": "",
    }


def new_result(spec: dict, cfg: dict, inp: dict, price: float) -> dict:
    return {
        "symbol": spec["symbol"], "displaySymbol": spec["displaySymbol"], "strategy": cfg["strategy"], "strategyName": cfg["name"],
        "timeframes": cfg["timeframes"], "nowSec": inp["nowSec"], "price": price, "spec": spec,
        "dataQuality": {"ok": True, "reason": "Live data OK", "source": inp["dataSource"]},
        "market": {"isOpen": inp["isMarketOpen"], "window": None},
        "bias": {"direction": "NEUTRAL", "detail": ""},
        "status": "NO_TRADE", "score": 0, "checklist": [], "rejection": None, "headline": "", "headlineAr": "",
        "setup": None, "signal": None, "canNotify": False,
        "news": {"blocked": False, "detail": "", "next": None, "source": inp["news"]["source"]},
        "day": inp["day"], "drawings": [], "facts": {}, "history": [], "historyStats": None, "tpReach": None,
    }
