"""
Strategy service: the app's strategies, one per instrument.
  XAUUSD → H1 Trend Breakout (trend, breakout and entry on H1)
  Forex (EUR/USD, GBP/USD and the FXAlexG pairs) → FXAlexG Set & Forget Break & Retest (bias W1/D1, setup and entry H4), same rules
Fetches real candles, computes today's trade/loss count by replaying the strategy itself on
today's closed candles (deterministic, survives restarts), runs the strategy now and caches it.
"""

import asyncio
import time
from typing import Optional

from functools import partial

from ..agent.explain import build_explanation
from ..market.data import canonical, fetch_live_price, fetch_many, market_session_status
from .alexg.config import ALEXG_CONFIGS
from .alexg.strategy import evaluate_alexg
from .replay import ReplayState, StrategyDef, replay, stats_at
from .shared.jsnum import fmt_utc_minute
from .shared.news import load_news_calendar
from .shared.sessions import trading_day_key
from .shared.types import TF_SEC, Candle, closed_only
from .xauusd.config import XAU_CONFIG
from .xauusd.strategy import evaluate_xauusd

PROVIDER_TF = {"M5": "5M", "M15": "15M", "H1": "1H", "H4": "4H", "D1": "1D"}


def _fx_def(cfg: dict) -> StrategyDef:
    # Evaluated at every H4 close; D1 / W1 are built from H1 inside the strategy (same Yahoo request)
    return StrategyDef(entryTf="H4", run=partial(evaluate_alexg, cfg=cfg), tfs=["H4", "H1"],
                       limits={"H4": 3200, "H1": 12500}, canSignalAt=lambda close: True)


STRATEGY_DEFS: dict[str, StrategyDef] = {
    "XAU/USD": StrategyDef(
        entryTf="H1", run=evaluate_xauusd, tfs=["H1"],
        limits={"H1": 5000},
        canSignalAt=lambda close: True,  # every H1 close while the market is open
    ),
    **{pair: _fx_def(cfg) for pair, cfg in ALEXG_CONFIGS.items()},
}
CONFIGS = {"XAU/USD": XAU_CONFIG, **ALEXG_CONFIGS}


def normalize_symbol(s: str) -> str:
    return canonical(s)


async def load_strategy_candles(sym: str, live_price: Optional[float] = None, fresh: bool = False) -> dict:
    d = STRATEGY_DEFS[sym]
    # `fresh` re-downloads the entry timeframe (candle-close dispatch); higher timeframes use the cache
    limits = {PROVIDER_TF[tf]: n for tf, n in d.limits.items()}
    series = await fetch_many(sym, [PROVIDER_TF[tf] for tf in d.tfs], limits, live_price, PROVIDER_TF[d.entryTf] if fresh else None)
    return {"candles": {tf: s["candles"] for tf, s in zip(d.tfs, series)}, "isReal": all(not s["isSynthetic"] for s in series), "source": series[0]["source"]}


# Today's replay state per symbol, continued incrementally as new candles close
_day_replay: dict[str, ReplayState] = {}


def _today_stats(sym: str, base: dict, now_sec: int) -> dict:
    d = STRATEGY_DEFS[sym]
    tf_sec = TF_SEC[d.entryTf]
    entry = base["candles"].get(d.entryTf) or []
    day_key = trading_day_key(now_sec)
    key = f"{sym}|{day_key}"
    state = _day_replay.get(key)
    if state is None:
        for k in [k for k in _day_replay if k.startswith(sym)]:
            del _day_replay[k]
        day_start = next((c.time for c in entry if trading_day_key(c.time) == day_key), now_sec)
        state = ReplayState(day_start)
        _day_replay[key] = state
    # Up to the previous close: the current bar is evaluated live
    last_closed = closed_only(entry, tf_sec, now_sec)
    prev_close = last_closed[-2].time + tf_sec if len(last_closed) > 1 else now_sec
    replay(d, base, state.lastClose, prev_close, state)
    return stats_at(d, entry, {c.time: i for i, c in enumerate(entry)}, state.emitted, now_sec)


_cache: dict[str, tuple[dict, float]] = {}
_locks: dict[str, asyncio.Lock] = {}


async def get_strategy_result(raw_symbol: str, force: bool = False, fresh: bool = False, live_price: Optional[float] = None) -> dict:
    """Returns {"result": StrategyResult, "candles": {tf: [Candle]}}. Cached 4 s; concurrent callers share one run."""
    sym = normalize_symbol(raw_symbol)
    hit = _cache.get(sym)
    if not force and not fresh and hit and hit[1] > time.time():
        return hit[0]
    lock = _locks.setdefault(sym, asyncio.Lock())
    async with lock:
        hit = _cache.get(sym)
        if not force and not fresh and hit and hit[1] > time.time():
            return hit[0]
        price = live_price if live_price and live_price > 0 else (await fetch_live_price(sym, fresh))["price"]
        loaded, news = await asyncio.gather(load_strategy_candles(sym, price, fresh), load_news_calendar())
        now_sec = int(time.time())
        base = {"candles": loaded["candles"], "livePrice": price, "spread": None, "isRealData": loaded["isReal"], "dataSource": loaded["source"], "news": news}
        d = STRATEGY_DEFS[sym]
        # Replaying today's bars is CPU work: keep it off the event loop
        day = await asyncio.to_thread(_today_stats, sym, base, now_sec) if loaded["isReal"] else {"trades": 0, "losses": 0}
        result = await asyncio.to_thread(d.run, {**base, "nowSec": now_sec, "isMarketOpen": market_session_status(sym)["isOpen"], "day": day})
        if result["signal"]:
            result["signal"]["explanation"] = build_explanation(result)
        bundle = {"result": result, "candles": loaded["candles"]}
        _cache[sym] = (bundle, time.time() + 4)
        return bundle


async def get_strategy_result_as_of(raw_symbol: str, as_of: int) -> dict:
    """Review mode: the strategy exactly as it was at `as_of` (read-only, never notifies)."""
    sym = normalize_symbol(raw_symbol)
    loaded, news = await asyncio.gather(load_strategy_candles(sym), load_news_calendar())
    cut = {tf: closed_only(c, TF_SEC[tf], as_of) for tf, c in loaded["candles"].items()}
    d = STRATEGY_DEFS[sym]
    entry = cut.get(d.entryTf) or []
    base = {"candles": cut, "livePrice": entry[-1].close if entry else 0, "spread": None, "isRealData": loaded["isReal"], "news": news,
            "dataSource": f"{loaded['source']} · review as of {fmt_utc_minute(as_of)} UTC"}

    def run():
        day_start = next((c.time for c in entry if trading_day_key(c.time) == trading_day_key(as_of)), as_of)
        state = replay(d, base, day_start, as_of - TF_SEC[d.entryTf])
        day = stats_at(d, entry, {c.time: i for i, c in enumerate(entry)}, state.emitted, as_of)
        return d.run({**base, "nowSec": as_of, "isMarketOpen": False, "day": day})

    result = await asyncio.to_thread(run)
    if result["signal"]:
        result["signal"]["explanation"] = build_explanation(result)
    return {"result": result, "candles": cut}


async def all_results() -> list[dict]:
    """Current result of every instrument, in STRATEGY_DEFS order."""
    return [b["result"] for b in await asyncio.gather(*(get_strategy_result(sym) for sym in STRATEGY_DEFS))]


both_results = all_results  # older name
