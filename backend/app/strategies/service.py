"""
Strategy service: the app's strategies, one per instrument.
  XAUUSD → H1 Trend Breakout (trend, breakout and entry on H1)
  EUR/USD, GBP/USD → RSI(2) Connors pullback H4 (the strategy that held up on them over 2 years)
  The other forex pairs → FXAlexG Set & Forget GPA (trend W1/D1/H4, AOI W1/D1, entry 30m), same rules
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
from .rsi2.config import RSI2_CONFIGS
from .rsi2.strategy import evaluate_rsi2, exit_rule as rsi2_exit
from .replay import ReplayState, StrategyDef, replay, stats_at
from .shared.jsnum import fmt_utc_minute
from .shared.news import load_news_calendar
from .shared.common import active_window
from .shared.sessions import trading_day_key
from .shared.types import TF_SEC, Candle, closed_only
from .xauusd.config import XAU_CONFIG
from .xauusd.strategy import evaluate_xauusd

PROVIDER_TF = {"M5": "5M", "M15": "15M", "M30": "30M", "H1": "1H", "H4": "4H", "D1": "1D"}


def _fx_def(cfg: dict) -> StrategyDef:
    # Evaluated at every 30m close; a signal is only possible on a candle that opened at the London / New York open.
    # D1 / W1 are built from H1 inside the strategy (same Yahoo request as H4)
    tf = cfg["entryTf"]
    windows = cfg["sessions"]["windows"]
    return StrategyDef(entryTf=tf, run=partial(evaluate_alexg, cfg=cfg), tfs=[tf, "H1", "H4"],
                       limits={tf: 3000, "H1": 12500, "H4": 3200}, canSignalAt=lambda close: active_window(close - TF_SEC[tf], windows) is not None)


def _rsi2_def(cfg: dict) -> StrategyDef:
    # Evaluated at every H4 close; the exit (close back over EMA5) is part of the lifecycle, live and in backtests
    return StrategyDef(entryTf="H4", run=partial(evaluate_rsi2, cfg=cfg), tfs=["H4"], limits={"H4": 3200},
                       canSignalAt=lambda close: True, exit_rule=lambda c, side: rsi2_exit(c, side, cfg["exitEma"]))


STRATEGY_DEFS: dict[str, StrategyDef] = {
    "XAU/USD": StrategyDef(
        entryTf="H1", run=evaluate_xauusd, tfs=["H1"],
        limits={"H1": 5000},
        canSignalAt=lambda close: True,  # every H1 close while the market is open
    ),
    # Each pair runs the strategy that held up on it: RSI(2) H4 on EUR/USD and GBP/USD, FXAlexG GPA on the others
    **{pair: (_rsi2_def(RSI2_CONFIGS[pair]) if pair in RSI2_CONFIGS else _fx_def(cfg)) for pair, cfg in ALEXG_CONFIGS.items()},
}
CONFIGS = {"XAU/USD": XAU_CONFIG, **ALEXG_CONFIGS, **RSI2_CONFIGS}


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
_slot: dict[str, int] = {}  # entry-timeframe candle the cached analysis was computed in
REUSE_SEC = 30  # the analysis is recomputed at every new entry candle, and at least every 30 s
STALE_MAX_SEC = 20 * 60  # how long the last good analysis may stand in for a failing feed
_last_good: dict[str, tuple[dict, float]] = {}


def _reusable(sym: str) -> bool:
    hit = _cache.get(sym)
    tf_sec = TF_SEC[STRATEGY_DEFS[sym].entryTf]
    return bool(hit) and hit[1] > time.time() and _slot.get(sym) == int(time.time()) // tf_sec


async def _with_live_price(sym: str, bundle: dict) -> dict:
    """The cached analysis with the latest price (the rules only read closed candles, so nothing else changes)."""
    price = (await fetch_live_price(sym))["price"]
    if price > 0 and price != bundle["result"]["price"]:
        return {**bundle, "result": {**bundle["result"], "price": price}}
    return bundle
_locks: dict[str, asyncio.Lock] = {}


async def get_strategy_result(raw_symbol: str, force: bool = False, fresh: bool = False, live_price: Optional[float] = None) -> dict:
    """Returns {"result": StrategyResult, "candles": {tf: [Candle]}}. Recomputed at each new entry candle (and every 30 s),
    otherwise the cached analysis comes back with the live price; concurrent callers share one run."""
    sym = normalize_symbol(raw_symbol)
    if not force and not fresh and _reusable(sym):
        return await _with_live_price(sym, _cache[sym][0])
    lock = _locks.setdefault(sym, asyncio.Lock())
    async with lock:
        if not force and not fresh and _reusable(sym):
            return await _with_live_price(sym, _cache[sym][0])
        price = live_price if live_price and live_price > 0 else (await fetch_live_price(sym, fresh))["price"]
        # A new entry candle has closed since the last run: download it now (the raw candle cache is up to 60 s old)
        new_candle = _slot.get(sym) != int(time.time()) // TF_SEC[STRATEGY_DEFS[sym].entryTf]
        loaded, news = await asyncio.gather(load_strategy_candles(sym, price, fresh or new_candle), load_news_calendar())
        now_sec = int(time.time())
        base = {"candles": loaded["candles"], "livePrice": price, "spread": None, "isRealData": loaded["isReal"], "dataSource": loaded["source"], "news": news}
        d = STRATEGY_DEFS[sym]
        # Replaying today's bars is CPU work: keep it off the event loop
        day = await asyncio.to_thread(_today_stats, sym, base, now_sec) if loaded["isReal"] else {"trades": 0, "losses": 0}
        result = await asyncio.to_thread(d.run, {**base, "nowSec": now_sec, "isMarketOpen": market_session_status(sym)["isOpen"], "day": day})
        if result["signal"]:
            result["signal"]["explanation"] = build_explanation(result)
        bundle = {"result": result, "candles": loaded["candles"]}
        if result["dataQuality"]["ok"]:
            _last_good[sym] = (bundle, time.time())
        else:
            # Feed down for a moment: keep showing the last good analysis (never notifies) rather than a blank page
            prev = _last_good.get(sym)
            if prev and time.time() - prev[1] < STALE_MAX_SEC:
                age = int((time.time() - prev[1]) // 60)
                old = prev[0]["result"]
                stale = {**old, "canNotify": False,
                         "dataQuality": {**old["dataQuality"], "stale": True, "reason": f"Feed retrying · last good analysis {age} min ago",
                                         "source": f"{old['dataQuality'].get('source', '')} · last good, {age} min ago"}}
                bundle = {"result": stale, "candles": prev[0]["candles"]}
                _cache[sym] = (bundle, time.time() + 5)  # retry the feed soon
                return bundle
        _cache[sym] = (bundle, time.time() + REUSE_SEC)
        _slot[sym] = now_sec // TF_SEC[d.entryTf]
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
