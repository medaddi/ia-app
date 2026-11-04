"""
Candle-close scheduler: each pair's setup agent decides the moment its candle closes (M5; AUD/CHF H1) and its
trade-management agent runs the trades already sent. On Vercel the cron calls /api/cron/tick every minute.
At close + GRACE it re-downloads the entry timeframe (no cache), and retries every RETRY
until the provider has published the closed bar, then dispatches a fresh SIGNAL and updates
the outcome of the signals already sent.
"""

import asyncio
import time

from ..db import SessionLocal
from ..market.data import market_session_status
from ..strategies.replay import decision_tf
from ..strategies.service import STRATEGY_DEFS, get_strategy_result
from ..strategies.shared.jsnum import iso
from ..strategies.shared.types import TF_SEC
from ..push import push_setup
from ..store import get_setting, set_setting
from .bot import dispatch_setup, sync_profile
from ..agents.trade_manager import managers

TRADE_MANAGERS = managers(STRATEGY_DEFS)  # one trade-management agent per pair, next to its setup agent

GRACE = 1.2
RETRY = 2.0
PUBLISH_WAIT = 30  # seconds after a close to wait for the provider's closed bar within one tick
MAX_RETRIES = 10
TICK_TIMEOUT = 40.0  # seconds per pair in a serverless tick (the 4 pairs run in parallel; Vercel Pro allows 60 s+)


def next_close_sec(now: float, tf_sec: int) -> int:
    """Next candle close (unix seconds) strictly after `now`."""
    return (int(now // tf_sec) + 1) * tf_sec


async def _on_close(sym: str, close: int) -> None:
    d = STRATEGY_DEFS[sym]
    tf = decision_tf(d)  # gold decides at every M15 close (confirmation on the forming H1)
    tf_sec = TF_SEC[tf]
    bundle = None
    for _ in range(MAX_RETRIES + 1):
        bundle = await get_strategy_result(sym, fresh=True)
        entry = bundle["candles"].get(tf) or []
        if any(c.time == close - tf_sec for c in entry):
            break
        await asyncio.sleep(RETRY)
    out = await process_bundle(sym, bundle)
    record_tick({sym: out}, time.time())
    print(f"[candle-close] {sym} at {iso(close)[11:19]}: {out}")


async def process_bundle(sym: str, bundle: dict) -> str:
    """One pass for a pair: its trade-management agent runs the trades already sent, then a fresh setup of its setup
    agent goes out, to Telegram and to the app (Web Push) independently: one channel failing never stops the other."""
    r = bundle["result"]
    head = None
    if r["setup"] and r["status"] == "SIGNAL" and r["setup"]["lifecycle"]["state"] in ("PENDING", "OPEN"):
        # A new order first, before any other work, so it reaches the traders right at the candle close:
        # Telegram and the app (Web Push) at the same time, each on its own (one failing never stops the other)
        async def telegram() -> str:
            try:
                out = await dispatch_setup(sym, manual=False)
                return f"sent to {out.get('recipients')} chat(s)" if out["success"] else f"telegram: {out['error']}"
            except Exception as err:
                return f"telegram error: {err!r}"

        async def app_push() -> str:
            try:
                return await push_setup(sym)
            except Exception as err:
                return f"push error: {err!r}"

        tg, pushed = await asyncio.gather(telegram(), app_push())
        if "sent to" in tg or "pushed to" in pushed:
            head = f"{r['setup']['id']}: {tg} · {pushed}"
    # Then the trade-management agent runs the trades already sent
    manager = await TRADE_MANAGERS[sym].run(bundle, STRATEGY_DEFS[sym].entryTf)
    if manager["errors"]:
        print(f"[trade-manager] {sym}: {'; '.join(manager['errors'])}")
    managed = f"managed: {manager['closed']} closed, {manager['notices']} notice(s)" if (manager["closed"] or manager["notices"]) else ""
    return " · ".join(x for x in (head or f"{r['status']} · {r['headline']}", managed) if x)


_decided: dict[str, int] = {}  # last entry-candle close already decided per pair (kept while the instance is warm)


async def _decide(sym: str) -> dict:
    """The analysis for the candle that just closed: re-downloaded (no cache) until the provider has published that bar,
    a few seconds at most; between closes the cached analysis is enough (nothing can change before the next close)."""
    d = STRATEGY_DEFS[sym]
    tf = decision_tf(d)
    tf_sec = TF_SEC[tf]
    close = int(time.time() // tf_sec) * tf_sec
    if _decided.get(sym) == close:
        return await get_strategy_result(sym)
    bundle = None
    # The cron fires right at the close: keep re-reading for up to PUBLISH_WAIT seconds until the provider has the closed
    # bar, so the order goes out the moment it exists (not a minute later at the next tick)
    while True:
        bundle = await get_strategy_result(sym, fresh=True)
        if any(c.time == close - tf_sec for c in bundle["candles"].get(tf) or []):
            _decided[sym] = close
            break
        if time.time() - close > PUBLISH_WAIT:
            break  # still not published: the next tick tries again
        await asyncio.sleep(RETRY)
    return bundle


async def tick() -> dict:
    """One pass for serverless hosting (called every minute by an external pinger): same work as a candle close."""
    async def one(sym: str) -> str:
        if not market_session_status(sym)["isOpen"]:
            return "market closed"
        try:
            # Each pair has its own time budget, so one slow feed never makes the whole tick time out
            async def run() -> str:
                return await process_bundle(sym, await _decide(sym))
            return await asyncio.wait_for(run(), timeout=TICK_TIMEOUT)
        except asyncio.TimeoutError:
            return f"timeout after {TICK_TIMEOUT}s (next tick retries)"
        except Exception as err:  # one symbol failing must not stop the others
            return f"error: {err!r}"

    try:  # the bot's menu and description follow the code (once per instance)
        with SessionLocal() as db:
            token = get_setting(db, "telegram")["botToken"]
        if token:
            await asyncio.wait_for(sync_profile(token), timeout=5)
    except Exception:
        pass
    syms = list(STRATEGY_DEFS)
    started = time.time()
    results = dict(zip(syms, await asyncio.gather(*(one(s) for s in syms))))
    record_tick(results, started)
    return results


def record_tick(results: dict, started: float) -> None:
    """The engine's heartbeat in the database: when it last ran, how long it took, and each pair's outcome (sent, why not).
    GET /api/cron/status reads it, so a stopped pinger or a failing send is visible."""
    try:
        with SessionLocal() as db:
            prev = get_setting(db, "engine")
            sent = {sym: {"at": int(started), "result": out} for sym, out in results.items() if "sent to" in out}
            # merged: the in-process scheduler reports one pair at a time
            set_setting(db, "engine", {"lastTickAt": int(started), "durationSec": round(time.time() - started, 1),
                                       "results": {**(prev.get("results") or {}), **results},
                                       "lastSent": {**(prev.get("lastSent") or {}), **sent}, "ticks": int(prev.get("ticks") or 0) + 1})
    except Exception as err:  # the heartbeat never breaks a tick
        print(f"[engine] {err!r}")


async def run_symbol(sym: str, stop: asyncio.Event) -> None:
    tf = decision_tf(STRATEGY_DEFS[sym])
    tf_sec = TF_SEC[tf]
    print(f"[candle-close] {sym} evaluated at every {tf} close (+{GRACE}s)")
    while not stop.is_set():
        close = next_close_sec(time.time(), tf_sec)
        try:
            await asyncio.wait_for(stop.wait(), timeout=close + GRACE - time.time())
            return
        except asyncio.TimeoutError:
            pass
        if not market_session_status(sym)["isOpen"]:
            continue
        try:
            await _on_close(sym, close)
        except Exception as err:  # keep scheduling whatever happens
            print(f"[candle-close] {sym} evaluation failed: {err!r}")


async def heartbeat(stop: asyncio.Event) -> None:
    """Always-on server: the pairs decide only at their candle closes (5 min to 1 h apart), so the engine says it is
    alive every minute (GET /api/cron/status, the dashboard's engine line)."""
    while not stop.is_set():
        record_tick({}, time.time())
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass


def start(stop: asyncio.Event) -> list[asyncio.Task]:
    return [asyncio.create_task(run_symbol(sym, stop)) for sym in STRATEGY_DEFS] + [asyncio.create_task(heartbeat(stop))]
