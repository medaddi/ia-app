"""
Strategy service: the 6 pair agents (app/agents/registry.py), one per chart, each on its high-win-rate plan proven on
2 years of H1 / H4 (gold H4 breakout; EUR/USD, GBP/USD, EUR/CHF, AUD/CAD, AUD/CHF H1 fades).
Fetches real candles, computes today's trade/loss count by replaying the agent itself on today's closed candles
(deterministic, survives restarts), runs the agent now and caches its result and its chart overlay.
"""

import asyncio
import time
from typing import Optional

from functools import partial

from ..agent.explain import build_explanation
from ..agents.engine import can_signal_at, evaluate_agent, make_trigger
from ..agents.registry import AGENT_CONFIGS, AGENTS
from ..market.data import canonical, fetch_live_price, fetch_many, market_session_status
from .replay import ReplayState, StrategyDef, decision_tf, replay, stats_at
from .shared.jsnum import fmt_utc_minute
from .shared.news import load_news_calendar
from .shared.sessions import trading_day_key
from .shared.types import TF_SEC, closed_only

PROVIDER_TF = {"M5": "5M", "M15": "15M", "M30": "30M", "H1": "1H", "H4": "4H", "D1": "1D"}


def _agent_def(pair: str) -> StrategyDef:
    # The pair's own agent, decided at every close of its timeframe (H4 for gold, H1 for the forex pairs)
    ag, cfg = AGENTS[pair], AGENT_CONFIGS[pair]
    tf = ag.tf
    return StrategyDef(entryTf=tf, run=partial(evaluate_agent, agent=ag, cfg=cfg), tfs=[tf], limits={tf: ag.history},
                       canSignalAt=can_signal_at(ag, TF_SEC[tf]), trigger=make_trigger(ag), peer=ag.peer)


STRATEGY_DEFS: dict[str, StrategyDef] = {pair: _agent_def(pair) for pair in AGENTS}
CONFIGS = AGENT_CONFIGS


def normalize_symbol(s: str) -> str:
    return canonical(s)


async def load_strategy_candles(sym: str, live_price: Optional[float] = None, fresh: bool = False) -> dict:
    d = STRATEGY_DEFS[sym]
    # `fresh` re-downloads the entry timeframe (candle-close dispatch); higher timeframes use the cache
    limits = {PROVIDER_TF[tf]: n for tf, n in d.limits.items()}
    fresh_tf = PROVIDER_TF[d.entryTf] if fresh else None
    jobs = [fetch_many(sym, [PROVIDER_TF[tf] for tf in d.tfs], limits, live_price, fresh_tf)]
    if d.peer:  # GBP/USD's agent reads EUR/USD at the same moment (SMT): both feeds in parallel
        jobs.append(fetch_many(d.peer, [PROVIDER_TF[tf] for tf in d.tfs], limits, None, fresh_tf))
    got = await asyncio.gather(*jobs)
    series = got[0]
    out = {"candles": {tf: s["candles"] for tf, s in zip(d.tfs, series)}, "isReal": all(not s["isSynthetic"] for s in series), "source": series[0]["source"]}
    if d.peer:
        out["peer"] = {tf: s["candles"] for tf, s in zip(d.tfs, got[1])}
        out["isReal"] = out["isReal"] and all(not s["isSynthetic"] for s in got[1])
    return out


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
    tf_sec = TF_SEC[decision_tf(STRATEGY_DEFS[sym])]
    return bool(hit) and hit[1] > time.time() and _slot.get(sym) == int(time.time()) // tf_sec


async def _with_live_price(sym: str, bundle: dict) -> dict:
    """The cached analysis with the latest price (the rules only read closed candles, so nothing else changes)."""
    price = (await fetch_live_price(sym))["price"]
    if price > 0 and price != bundle["result"]["price"]:
        return {**bundle, "result": {**bundle["result"], "price": price}}
    return bundle


_locks: dict[str, asyncio.Lock] = {}
# One strategy computation at a time in the worker threads: with all 9 at once (cold start) the threads fight over
# the GIL and starve the event loop for seconds; one at a time keeps every other request answering in milliseconds
_cpu = asyncio.Semaphore(1)


async def _cpu_run(fn, *args):
    async with _cpu:
        return await asyncio.to_thread(fn, *args)


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
        new_candle = _slot.get(sym) != int(time.time()) // TF_SEC[decision_tf(STRATEGY_DEFS[sym])]
        loaded, news = await asyncio.gather(load_strategy_candles(sym, price, fresh or new_candle), load_news_calendar())
        now_sec = int(time.time())
        base = {"candles": loaded["candles"], "livePrice": price, "spread": None, "isRealData": loaded["isReal"], "dataSource": loaded["source"], "news": news,
                "peer": loaded.get("peer")}
        d = STRATEGY_DEFS[sym]
        # Replaying today's bars is CPU work: keep it off the event loop
        day = await _cpu_run(_today_stats, sym, base, now_sec) if loaded["isReal"] else {"trades": 0, "losses": 0}
        result = await _cpu_run(d.run, {**base, "nowSec": now_sec, "isMarketOpen": market_session_status(sym)["isOpen"], "day": day})
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
        _slot[sym] = now_sec // TF_SEC[decision_tf(d)]
        return bundle


async def get_strategy_result_as_of(raw_symbol: str, as_of: int) -> dict:
    """Review mode: the strategy exactly as it was at `as_of` (read-only, never notifies)."""
    sym = normalize_symbol(raw_symbol)
    loaded, news = await asyncio.gather(load_strategy_candles(sym), load_news_calendar())
    cut = {tf: closed_only(c, TF_SEC[tf], as_of) for tf, c in loaded["candles"].items()}
    d = STRATEGY_DEFS[sym]
    entry = cut.get(d.entryTf) or []
    peer = {tf: closed_only(c, TF_SEC[tf], as_of) for tf, c in (loaded.get("peer") or {}).items()} or None
    base = {"candles": cut, "livePrice": entry[-1].close if entry else 0, "spread": None, "isRealData": loaded["isReal"], "news": news, "peer": peer,
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


def cached_result(sym: str) -> Optional[dict]:
    """The latest analysis already in memory (None before the first run): never waits on the feed."""
    hit = _cache.get(sym) or _last_good.get(sym)
    return hit[0]["result"] if hit else None


async def all_results() -> list[dict]:
    """Current result of every instrument, in STRATEGY_DEFS order."""
    return [b["result"] for b in await asyncio.gather(*(get_strategy_result(sym) for sym in STRATEGY_DEFS))]


both_results = all_results  # older name
