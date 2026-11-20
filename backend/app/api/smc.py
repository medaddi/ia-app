"""The pair teams in the app: each team's read now, and the setups already sent (research, not advice)."""

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..market.data import canonical
from ..smc.desk import BY_SYMBOL, team
import asyncio

from ..smc.notify import overview, recent, recent_radar, refresh_overview

router = APIRouter(prefix="/api")


@router.get("/smc/team")
async def smc_team(symbol: str = "XAU/USD", _=Depends(current_user)):
    sym = canonical(symbol)
    if sym not in BY_SYMBOL:
        raise HTTPException(404, f"{sym} is not a pair of the app")
    return await team(sym)


@router.get("/smc/results")
def smc_results(_=Depends(current_user)):
    """The teams' real results: every setup sent, followed by the trade manager to its end (win rate, R, per pair)."""
    from ..smc.manager import results

    return {"success": True, **results()}


@router.get("/smc/history")
def smc_history(_=Depends(current_user)):
    """The app's history: every trade sent since the history began, its result, the win rate and the R total."""
    from ..smc.manager import history

    return {"success": True, **history()}


@router.get("/smc/overview")
async def smc_overview(_=Depends(current_user)):
    """Every pair's state at a glance (the dashboard): the summaries the notifier saves each minute. When none is fresh
    (no pass for 3 minutes), a read-only refresh starts in the background (it sends nothing) and the last ones are returned."""
    o = overview()
    if o["ageSec"] is None or o["ageSec"] > 180:
        asyncio.get_running_loop().create_task(refresh_overview())
        o["refreshing"] = True
    return {"success": True, **o}


@router.get("/smc/signals")
def smc_signals(_=Depends(current_user)):
    return {"success": True, "signals": recent(), "radar": recent_radar()}  # the live feed: the sent trades (no radar any more)
