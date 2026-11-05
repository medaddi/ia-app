"""
One pair's dossier: its team's decision, its SMC report and drawing, its trades (the orders its agent runs now, and the
signals it sent), all of THIS pair only and stamped with its symbol, so a screen can check it never shows another pair's.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Signal
from .team import pair_team


def trades_of(sym: str, live: Optional[dict], db: Optional[Session]) -> dict:
    running = [{**x, "symbol": sym} for x in ((live or {}).get("running") or [])]
    history = []
    if db is not None:
        rows = db.scalars(select(Signal).where(Signal.symbol == sym).order_by(Signal.signal_time.desc()).limit(10)).all()
        history = [{"id": r.id, "symbol": r.symbol, "setup": r.setup, "direction": r.direction, "entry": r.entry, "sl": r.sl, "tp": r.tp2,
                    "time": r.signal_time, "state": r.state, "outcome": r.outcome, "r": r.r_multiple} for r in rows]
    return {"running": running, "history": history}


async def pair_dossier(sym: str, db: Optional[Session] = None) -> dict:
    from ..analysis.engine import cached_analysis
    from ..strategies.service import cached_result, get_strategy_result

    a = await cached_analysis(sym)
    if not a.get("success"):
        return {"success": False, "symbol": sym, "error": a.get("error") or "No analysis right now"}
    live = cached_result(sym)
    if live is None:
        try:
            live = (await get_strategy_result(sym))["result"]
        except Exception:
            live = None
    smc = a.get("smc") or {}
    return {"success": True, "symbol": sym, "price": a.get("price"), "at": a.get("at"), "team": pair_team(a, live),
            "report": smc.get("report"), "draw": smc.get("reportDraw"), "trades": trades_of(sym, live, db)}
