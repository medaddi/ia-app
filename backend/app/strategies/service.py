"""
Strategy service: the app's strategies, one per instrument.
  XAUUSD → H1 Trend Breakout (trend, breakout and entry on H1)
  GBP/USD → London breakout H1 (from the strategy report; +28.6R on 274 trades over 2 years vs +3.0R for RSI(2))
  EUR/USD → liquidity sweep + break of structure H4, USD/CAD → EMA pullback H4 (2nd report: +14.4R / +18.8R over 2 years)
  AUD/CAD → mean reversion Bollinger + Stochastic H4 (1st report)
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
from .london.config import LONDON_CONFIGS
from .report.config import REPORT_CONFIGS
from .report.engine import evaluate_report, observation_block
from .london.strategy import evaluate_london
from .rsi2.config import RSI2_CONFIGS
from .rsi2.strategy import evaluate_rsi2, exit_rule as rsi2_exit
from .replay import ReplayState, StrategyDef, decision_tf, replay, stats_at
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


def _london_def(cfg: dict) -> StrategyDef:
    # Evaluated at every H1 close; a signal is only possible on a candle that opened in the breakout window (07–10 GMT)
    S = cfg["session"]
    return StrategyDef(entryTf="H1", run=partial(evaluate_london, cfg=cfg), tfs=["H1"], limits={"H1": 12500},
                       canSignalAt=lambda close: S["asiaEndHour"] <= ((close - 3600) // 3600) % 24 < S["breakoutEndHour"])


def _report_def(cfg: dict) -> StrategyDef:
    # A report strategy that won its 2-year test (EUR/USD, USD/CAD, AUD/CAD): evaluated at every close of its timeframe
    tf = cfg["timeframes"]["entry"]
    return StrategyDef(entryTf=tf, run=partial(evaluate_report, cfg=cfg), tfs=[tf], limits={tf: cfg["history"]}, canSignalAt=lambda close: True)


LIVE_REPORT = {p: c for p, c in REPORT_CONFIGS.items() if c["live"]}


def _rsi2_def(cfg: dict) -> StrategyDef:
    # Evaluated at every H4 close; the exit (close back over EMA5) is part of the lifecycle, live and in backtests
    return StrategyDef(entryTf="H4", run=partial(evaluate_rsi2, cfg=cfg), tfs=["H4"], limits={"H4": 3200},
                       canSignalAt=lambda close: True, exit_rule=(lambda c, side: rsi2_exit(c, side, cfg["exitEma"])) if cfg.get("exitAtEma", True) else None)


STRATEGY_DEFS: dict[str, StrategyDef] = {
    "XAU/USD": StrategyDef(
        entryTf="H1", run=evaluate_xauusd, tfs=["H1", "M15"],
        limits={"H1": 5000, "M15": 200},
        canSignalAt=lambda close: True,  # every H1 close while the market is open
        # M15 confirmation: the H1 rules run at every 15-minute close on the H1 candle still forming, so a breakout or a
        # reversion is taken up to 45 min before the H1 close (60 days: +9.1R on 28 trades vs +7.6R on 18 at the close)
        confirmTf="M15",
    ),
    # Each pair runs the strategy that held up on it: London breakout H1 on GBP/USD, the live report plans, FXAlexG GPA on the others
    **{pair: (_london_def(LONDON_CONFIGS[pair]) if pair in LONDON_CONFIGS else _report_def(LIVE_REPORT[pair]) if pair in LIVE_REPORT
              else _rsi2_def(RSI2_CONFIGS[pair]) if pair in RSI2_CONFIGS else _fx_def(cfg)) for pair, cfg in ALEXG_CONFIGS.items()},
}
CONFIGS = {"XAU/USD": XAU_CONFIG, **ALEXG_CONFIGS, **RSI2_CONFIGS, **LONDON_CONFIGS, **LIVE_REPORT}


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
    tf_sec = TF_SEC[decision_tf(STRATEGY_DEFS[sym])]
    return bool(hit) and hit[1] > time.time() and _slot.get(sym) == int(time.time()) // tf_sec


_early: dict[str, tuple[int, dict]] = {}  # symbol → (entry candle start, the first signal its confirmation gave)


def _early_signal(sym: str, base: dict, now_sec: int, day: dict) -> Optional[dict]:
    """M15 confirmation: the strategy's rules on the entry candle still forming, rebuilt from the confirmation candles
    closed so far. The first signal of an entry candle is kept (its levels never change while that candle forms)."""
    d = STRATEGY_DEFS[sym]
    tf, ctf = TF_SEC[d.entryTf], TF_SEC[d.confirmTf]
    start = now_sec - now_sec % tf
    held = _early.get(sym)
    if held and held[0] == start:
        return held[1]
    parts = [c for c in base["candles"].get(d.confirmTf) or [] if start <= c.time and c.time + ctf <= now_sec]
    if not parts or len(parts) * ctf >= tf:  # nothing closed yet in this candle, or the candle is complete (normal close decision)
        return None
    forming = Candle(start, parts[0].open, max(c.high for c in parts), min(c.low for c in parts), parts[-1].close, 0)
    closed = [c for c in base["candles"][d.entryTf] if c.time < start]
    r = d.run({**base, "candles": {**base["candles"], d.entryTf: closed + [forming]}, "nowSec": start + tf,
               "isMarketOpen": market_session_status(sym)["isOpen"], "day": day})
    s = r["setup"]
    if not (s and s["isFresh"] and r["status"] == "SIGNAL" and r["canNotify"]):
        return None
    at = parts[-1].time + ctf
    r["facts"]["confirmation"] = {"tf": d.confirmTf, "at": at, "candle": d.entryTf}
    r["headline"] = f"{d.confirmTf} confirmation · {r['headline']}"
    r["dataQuality"] = {**r["dataQuality"], "source": f"{r['dataQuality'].get('source', '')} · {d.confirmTf} confirmation on the forming {d.entryTf}"}
    _early[sym] = (start, r)
    return r


async def _with_live_price(sym: str, bundle: dict) -> dict:
    """The cached analysis with the latest price (the rules only read closed candles, so nothing else changes)."""
    price = (await fetch_live_price(sym))["price"]
    if price > 0 and price != bundle["result"]["price"]:
        return {**bundle, "result": {**bundle["result"], "price": price}}
    return bundle
LONDON_REPORT = {"live": True, "recommendation": "London breakout of the Asian range (M5 / M15) + post-news exhaustion",
                 "test": {"trades": 257, "winRate": 48.4, "totalR": 25.2, "verdict": "Live: +25.2R (RSI(2) H4 it replaced: +3.0R)"},
                 "note": "Buys carried the result (+29.3R) while the sells were flat"}


async def _report_strategy(sym: str, base: dict, now_sec: int, real: bool) -> Optional[dict]:
    """The pair's strategy from the report: the live one's summary, or the observation plan computed next to it (no signal)."""
    if sym in LONDON_CONFIGS:
        return {"name": LONDON_CONFIGS[sym]["name"], "timeframe": "H1", **LONDON_REPORT}
    cfg = REPORT_CONFIGS.get(sym)
    if not cfg:
        return None
    if cfg["live"]:
        return {"name": cfg["name"], "timeframe": cfg["timeframes"]["entry"], "live": True, "recommendation": cfg["report"], "test": cfg["test"], "note": cfg.get("note")}
    if not real:
        return None
    try:
        r = await _cpu_run(evaluate_report, {**base, "nowSec": now_sec, "isMarketOpen": False, "day": {"trades": 0, "losses": 0}}, cfg)
        return observation_block(r)
    except Exception as err:  # the observation never breaks the pair's live analysis
        print(f"[report] {sym}: {err!r}")
        return None


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
        base = {"candles": loaded["candles"], "livePrice": price, "spread": None, "isRealData": loaded["isReal"], "dataSource": loaded["source"], "news": news}
        d = STRATEGY_DEFS[sym]
        # Replaying today's bars is CPU work: keep it off the event loop
        day = await _cpu_run(_today_stats, sym, base, now_sec) if loaded["isReal"] else {"trades": 0, "losses": 0}
        result = await _cpu_run(d.run, {**base, "nowSec": now_sec, "isMarketOpen": market_session_status(sym)["isOpen"], "day": day})
        if d.confirmTf and loaded["isReal"] and result["dataQuality"]["ok"] and not (result["setup"] and result["setup"]["isFresh"]):
            early = await _cpu_run(_early_signal, sym, base, now_sec, day)
            if early:
                result = {**early, "price": result["price"]}
        if result["signal"]:
            result["signal"]["explanation"] = build_explanation(result)
        result = {**result, "reportStrategy": await _report_strategy(sym, base, now_sec, loaded["isReal"])}
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


def cached_result(sym: str) -> Optional[dict]:
    """The latest analysis already in memory (None before the first run): never waits on the feed."""
    hit = _cache.get(sym) or _last_good.get(sym)
    return hit[0]["result"] if hit else None


async def all_results() -> list[dict]:
    """Current result of every instrument, in STRATEGY_DEFS order."""
    return [b["result"] for b in await asyncio.gather(*(get_strategy_result(sym) for sym in STRATEGY_DEFS))]


both_results = all_results  # older name
