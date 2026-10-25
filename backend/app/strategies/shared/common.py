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
        "day": inp["day"], "drawings": [], "facts": {},
    }
