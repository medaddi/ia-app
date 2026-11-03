"""
Candle-close scheduler: evaluates each strategy the moment its entry candle closes
(gold H1, forex H4) instead of waiting for a polling loop.
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
from ..trading import update_signal_outcomes
from ..followup import follow_up
from ..push import push_closed, push_setup
from ..store import get_setting, set_setting
from .bot import dispatch_setup, notify_closed, sync_profile

GRACE = 1.2
RETRY = 2.0
MAX_RETRIES = 10
TICK_TIMEOUT = 8.0  # seconds per pair in a serverless tick (the 9 pairs run in parallel)


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
    print(f"[candle-close] {sym} at {iso(close)[11:19]}: {await process_bundle(sym, bundle)}")


async def process_bundle(sym: str, bundle: dict) -> str:
    """Updates the outcome of the signals already sent and dispatches a fresh SIGNAL. Returns what happened."""
    r = bundle["result"]
    ended: list[dict] = []
    with SessionLocal() as db:
        update_signal_outcomes(db, sym, bundle["candles"].get(STRATEGY_DEFS[sym].entryTf) or [], ended)
    if ended:  # how each trade ended: Telegram and the phones
        try:
            await notify_closed(ended)
            await push_closed(ended)
        except Exception as err:  # never blocks the new signal below
            print(f"[result] {sym}: {err!r}")
    try:  # running trades: filled, +1R, near SL, news ahead, and the trade manager's exit / cancel calls
        await follow_up(sym, r.get("price"), None, (r.get("setup") or {}).get("id"))
    except Exception as err:
        print(f"[follow-up] {sym}: {err!r}")
    if r["canNotify"] and r["setup"]:
        out = await dispatch_setup(sym, manual=False)
        try:  # app notifications (Web Push), independent of Telegram
            pushed = await push_setup(sym)
        except Exception as err:  # a push failure never blocks the Telegram send
            pushed = f"push error: {err!r}"
        return f"{r['setup']['id']}: {'sent to ' + str(out.get('recipients')) + ' chat(s)' if out['success'] else out['error']} · {pushed}"
    return f"{r['status']} · {r['headline']}"


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
    for attempt in range(3):
        bundle = await get_strategy_result(sym, fresh=True)
        if any(c.time == close - tf_sec for c in bundle["candles"].get(tf) or []):
            _decided[sym] = close
            break
        await asyncio.sleep(RETRY)  # bar not published yet: the next tick tries again if this one runs out
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
            set_setting(db, "engine", {"lastTickAt": int(started), "durationSec": round(time.time() - started, 1), "results": results,
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


def start(stop: asyncio.Event) -> list[asyncio.Task]:
    return [asyncio.create_task(run_symbol(sym, stop)) for sym in STRATEGY_DEFS]
