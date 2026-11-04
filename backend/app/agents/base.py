"""
The base of the pair agents and the drawing contract each one emits for ITS OWN chart
(AgentChartOverlayState, frontend/src/agentOverlay.ts).

An agent is a deterministic state machine on closed candles. `scan()` returns:
  {"setups": [raw setup, ...],           every order the agent placed over the history (no look-ahead)
   "context": {state, banner, session, tag, zones, priceLines, markers}}   what it sees on the latest candle
A raw setup carries its order (side, entry type, entry, SL, TP1, TP2, partials, break-even, expiry, cancel level), its
reasons, and the zones / lines / markers that explain it on the chart.

FSM states: IDLE · ARMED · LIQUIDITY_SWEPT · MSS_CONFIRMED · PENDING_ORDER · IN_TRADE · COOLDOWN.
"""

from typing import Optional

from ..core.instrument_specs import INSTRUMENT_CONFIG, pips_to_price, price_to_pips

FSM = ("IDLE", "ARMED", "LIQUIDITY_SWEPT", "MSS_CONFIRMED", "PENDING_ORDER", "IN_TRADE", "COOLDOWN")

# The palette of each drawing category: fill (RGBA) and border
ZONE_STYLE = {
    "ASIAN_BOX": ("rgba(212, 175, 55, 0.10)", "rgba(212, 175, 55, 0.65)"),
    "LONDON_BOX": ("rgba(56, 189, 248, 0.08)", "rgba(56, 189, 248, 0.60)"),
    "FVG_BULL": ("rgba(22, 199, 132, 0.16)", "#16C784"),
    "FVG_BEAR": ("rgba(234, 57, 67, 0.16)", "#EA3943"),
    "OB_BULL": ("rgba(16, 185, 129, 0.20)", "#10B981"),
    "OB_BEAR": ("rgba(244, 63, 94, 0.20)", "#F43F5E"),
    "OTE_GOLD_ZONE": ("rgba(212, 175, 55, 0.22)", "#D4AF37"),
    "SUPPLY_BAND": ("rgba(234, 57, 67, 0.12)", "rgba(234, 57, 67, 0.70)"),
    "DEMAND_BAND": ("rgba(16, 185, 129, 0.12)", "rgba(16, 185, 129, 0.70)"),
}
LINE_STYLE = {
    "PDH": ("SOLID", "#94A3B8"), "PDL": ("SOLID", "#94A3B8"),
    "SESSION_HIGH": ("DASHED", "#D4AF37"), "SESSION_LOW": ("DASHED", "#D4AF37"),
    "MSS_BREAK": ("DOTTED", "#E2E8F0"), "EQUILIBRIUM": ("DASHED", "#C9A04A"), "DIVERGENCE_LINE": ("SOLID", "#A78BFA"),
    # the SMC view (agents/smc.py): context, never a signal
    "BSL": ("DOTTED", "#38BDF8"), "SSL": ("DOTTED", "#F472B6"), "BOS": ("SOLID", "#94A3B8"), "CHOCH": ("DASHED", "#FBBF24"),
}
BULL, BEAR, GOLD = "#16C784", "#EA3943", "#D4AF37"


def zone(id_: str, cat: str, t0: int, t1: int, top: float, bottom: float, label: str, mid: Optional[float] = None,
         mitigated: bool = False, fill: Optional[str] = None, border: Optional[str] = None) -> dict:
    f, b = ZONE_STYLE[cat]
    z = {"id": id_, "category": cat, "startTime": int(t0), "endTime": int(t1), "topPrice": max(top, bottom), "bottomPrice": min(top, bottom),
         "fillColor": fill or f, "borderColor": border or b, "label": label, "isMitigated": bool(mitigated)}
    if mid is not None:
        z["midPrice"] = mid
    return z


def line(id_: str, cat: str, t0: int, t1: int, p0: float, p1: Optional[float], label: str, style: Optional[str] = None,
         color: Optional[str] = None) -> dict:
    s, col = LINE_STYLE[cat]
    return {"id": id_, "category": cat, "startTime": int(t0), "endTime": int(t1), "startPrice": p0, "endPrice": p0 if p1 is None else p1,
            "lineStyle": style or s, "color": color or col, "label": label}


def marker(id_: str, t: int, price: float, above: bool, text: str, color: Optional[str] = None, shape: Optional[str] = None) -> dict:
    return {"id": id_, "time": int(t), "price": price, "position": "aboveBar" if above else "belowBar",
            "shape": shape or ("arrowDown" if above else "arrowUp"), "color": color or (BEAR if above else BULL), "text": text}


def context(state: str, banner: str, session: str = "", tag: str = "", zones=None, lines=None, markers=None) -> dict:
    assert state in FSM, state
    return {"state": state, "banner": banner, "session": session, "tag": tag, "zones": zones or [], "priceLines": lines or [],
            "markers": markers or []}


class PairAgent:
    """One pair, one agent, one chart. Subclasses set the class attributes and implement scan()."""

    symbol = ""          # "EURUSD"
    agent_id = ""        # "EURUSD_AsianSweep_FVG_Agent"
    name = ""            # short engine name
    tf = "M5"            # the timeframe the agent decides on
    peer: Optional[str] = None   # a second pair read at the same time ("EUR/USD" for the GBP/USD agent)
    history = 12000
    min_bars = 300
    windows: Optional[list[tuple[int, int]]] = None  # UTC+1 minutes where a signal may fire (None = any close)
    target_range = (2.0, 20.0)
    entry_types = ("LIMIT",)
    params: dict = {}
    steps: list[str] = []
    why = ""
    timeframes = {"bias": "M15", "setup": "M5", "entry": "M5"}

    def __init__(self):
        self.memo: dict = {}  # day cache: a finished day is scanned once

    @property
    def display(self) -> str:
        return INSTRUMENT_CONFIG[self.symbol]["display"]

    @property
    def pip(self) -> float:
        return INSTRUMENT_CONFIG[self.symbol]["pip_size"]

    def p2p(self, pips: float) -> float:
        return pips_to_price(self.symbol, pips)

    def pips(self, diff: float) -> float:
        return price_to_pips(self.symbol, diff)

    def scan(self, c, peer, memo_key: str = "") -> dict:  # pragma: no cover - abstract
        raise NotImplementedError

    def session_name(self, minute: int) -> str:
        return "Off-session"

    def cached_day(self, key: str, day: str, sig: tuple, compute):
        """The day cache: `compute()` only when that day's candles changed (today at each new candle)."""
        store = self.memo.setdefault(key, {})
        hit = store.get(day)
        if hit is not None and hit[0] == sig:
            return hit[1]
        res = compute()
        store[day] = (sig, res)
        if len(store) > 400:
            for k in sorted(store)[:-300]:
                del store[k]
        return res


def clamp_stop(agent: PairAgent, entry: float, sl: float, buy: bool, lo_pips: float, hi_pips: float) -> tuple[Optional[float], str]:
    """A stop below the minimum is widened to it (never tighter than the structure allows); above the maximum: no trade."""
    risk = agent.pips(entry - sl)
    if risk > hi_pips + 1e-9:
        return None, f"stop {risk:.1f} pips > {hi_pips:g}: skipped"
    if risk < lo_pips:
        d = agent.p2p(lo_pips)
        return (entry - d if buy else entry + d), f"stop widened to the {lo_pips:g}-pip minimum"
    return sl, f"stop {risk:.1f} pips"
