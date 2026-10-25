"""
Candle-close scheduler: evaluates each strategy the moment its entry candle closes
(gold M5, EURUSD M15) instead of waiting for a polling loop.
At close + GRACE it re-downloads the entry timeframe (no cache), and retries every RETRY
until the provider has published the closed bar, then dispatches a fresh SIGNAL and updates
the outcome of the signals already sent.
"""

import asyncio
import time

from ..db import SessionLocal
from ..market.data import market_session_status
from ..strategies.service import STRATEGY_DEFS, get_strategy_result
from ..strategies.shared.jsnum import iso
from ..strategies.shared.types import TF_SEC
from ..trading import update_signal_outcomes
from .bot import dispatch_setup

GRACE = 1.2
RETRY = 2.0
MAX_RETRIES = 10


def next_close_sec(now: float, tf_sec: int) -> int:
    """Next candle close (unix seconds) strictly after `now`."""
    return (int(now // tf_sec) + 1) * tf_sec


async def _on_close(sym: str, close: int) -> None:
    d = STRATEGY_DEFS[sym]
    tf_sec = TF_SEC[d.entryTf]
    bundle = None
    for _ in range(MAX_RETRIES + 1):
        bundle = await get_strategy_result(sym, fresh=True)
        entry = bundle["candles"].get(d.entryTf) or []
        if any(c.time == close - tf_sec for c in entry):
            break
        await asyncio.sleep(RETRY)
    r = bundle["result"]
    with SessionLocal() as db:
        update_signal_outcomes(db, sym, bundle["candles"].get(d.entryTf) or [])
    if r["canNotify"] and r["setup"]:
        out = await dispatch_setup(sym, manual=False)
        print(f"[candle-close] {sym} {r['setup']['id']} at {iso(close)[11:19]}: {'sent' if out['success'] else out['error']}")


async def run_symbol(sym: str, stop: asyncio.Event) -> None:
    tf_sec = TF_SEC[STRATEGY_DEFS[sym].entryTf]
    print(f"[candle-close] {sym} evaluated at every {STRATEGY_DEFS[sym].entryTf} close (+{GRACE}s)")
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
