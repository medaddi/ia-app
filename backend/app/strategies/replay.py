"""
Bar-by-bar replay of a strategy. Used by the live service (today's trade / loss count) and by
the backtester, so both run the exact same strategy code and order lifecycle.
At each closed entry-timeframe bar the strategy only sees candles closed at that moment.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from .shared.lifecycle import simulate_lifecycle
from .shared.sessions import trading_day_key
from .shared.types import TF_SEC, Candle


@dataclass
class StrategyDef:
    entryTf: str
    run: Callable[[dict], dict]
    canSignalAt: Callable[[int], bool]  # cheap pre-filter: windows where a signal is possible
    tfs: list[str]
    limits: dict
    trail: Optional[Callable[[list[Candle], str], Optional[Callable[[int], Optional[float]]]]] = None
    exit_rule: Optional[Callable[[list[Candle], str], Callable[[int], bool]]] = None  # strategy exit at a close
    # Decide earlier: at every close of this smaller timeframe, run the rules on the entry candle still forming
    confirmTf: Optional[str] = None


def decision_tf(d: StrategyDef) -> str:
    """The timeframe whose closes trigger a decision (the confirmation timeframe when the strategy has one)."""
    return d.confirmTf or d.entryTf


@dataclass
class ReplayState:
    lastClose: int
    emitted: list[dict] = field(default_factory=list)


def replay(d: StrategyDef, base: dict, from_sec: int, to_sec: int, state: Optional[ReplayState] = None) -> ReplayState:
    if state is None:
        state = ReplayState(from_sec)
    tf_sec = TF_SEC[d.entryTf]
    entry = base["candles"].get(d.entryTf) or []
    index_of = {c.time: i for i, c in enumerate(entry)}
    for c in entry:
        close = c.time + tf_sec
        if close <= state.lastClose or close > to_sec:
            continue
        state.lastClose = close
        if not d.canSignalAt(close):
            continue
        day = stats_at(d, entry, index_of, state.emitted, close)
        r = d.run({**base, "nowSec": close, "isMarketOpen": True, "day": day})
        s = r["setup"]
        if r["canNotify"] and s and not any(e["id"] == s["id"] for e in state.emitted):
            state.emitted.append({"id": s["id"], "dayKey": trading_day_key(close - 1), "signalTime": s["signalTime"], "setup": s,
                                  "score": r["score"], "status": r["status"], "headline": r["headline"], "checklist": r["checklist"]})
    return state


def stats_at(d: StrategyDef, entry: list[Candle], index_of: dict, emitted: list[dict], at_sec: int) -> dict:
    """Trades placed and losses closed so far on the trading day of `at_sec`."""
    tf_sec = TF_SEC[d.entryTf]
    day_key = trading_day_key(at_sec - 1)
    trades = losses = 0
    upto = -1
    for i in range(len(entry) - 1, -1, -1):
        if entry[i].time + tf_sec <= at_sec:
            upto = i
            break
    for e in emitted:
        if e["dayKey"] != day_key:
            continue
        lc = outcome(d, entry, index_of, e["setup"], upto)
        if lc["state"] not in ("CANCELLED", "EXPIRED"):
            trades += 1
        if lc["outcome"] == "LOSS":
            losses += 1
    return {"trades": trades, "losses": losses}


def outcome(d: StrategyDef, entry: list[Candle], index_of: dict, setup: dict, upto_index: Optional[int] = None) -> dict:
    """Lifecycle of an emitted setup using candles up to `upto_index` (the whole series by default)."""
    tf_sec = TF_SEC[d.entryTf]
    sig_idx = index_of.get(setup["signalTime"] - tf_sec)
    if sig_idx is None:
        return setup["lifecycle"]
    trail = d.trail(entry, setup["params"]["side"]) if d.trail else None
    rule = d.exit_rule(entry, setup["params"]["side"]) if d.exit_rule else None
    return simulate_lifecycle(entry, setup["params"], sig_idx + 1, trail, upto_index, rule)
