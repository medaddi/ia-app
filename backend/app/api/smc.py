"""The pair teams in the app: each team's read now, and the setups already sent (research, not advice)."""

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..market.data import canonical
from ..smc.desk import BY_SYMBOL, team
from ..smc.notify import recent

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


@router.get("/smc/signals")
def smc_signals(_=Depends(current_user)):
    return {"success": True, "signals": recent()}
