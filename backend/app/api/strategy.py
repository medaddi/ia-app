"""The two strategies on the chart, the AI agent and the backtester."""

import time

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from ..agent.agent import ask_agent, build_agent_context, detect_lang, explain_drawing
from ..agent.system_prompt import build_system_prompt
from ..auth import admin_user, current_user
from ..backtest import run_backtest
from ..market.data import TIMEFRAME_SECONDS, fetch_candle_series
from ..strategies.exunu import run_exunu, to_ai_signal
from ..strategies.service import both_results, get_strategy_result, get_strategy_result_as_of, normalize_symbol
from ..telegram.bot import dispatch_setup

router = APIRouter(prefix="/api")


@router.get("/exunu/setup")
async def exunu_setup(symbol: str = "XAU/USD", asOf: int = 0):
    sym = normalize_symbol(symbol)
    res = await run_exunu(sym, as_of=asOf)
    return {"success": True, "terminal": "LiquidityDissection Terminal", "symbol": sym, "currentPrice": res["current_price"], "result": res,
            "setup": res["setup_json"], "agents": res["agents"], "interAgentDialogue": res["inter_agent_dialogue"], "signal": to_ai_signal(res)}


@router.get("/exunu/candles")
async def exunu_candles(symbol: str = "XAU/USD", timeframe: str = "15M", count: int = 300, asOf: int = 0):
    sym = normalize_symbol(symbol)
    tf = timeframe if timeframe in TIMEFRAME_SECONDS else "15M"
    count = min(1000, max(count, 10))
    series = await fetch_candle_series(sym, tf, 2000 if asOf > 0 else count)
    candles = series["candles"]
    if asOf > 0:
        tf_sec = TIMEFRAME_SECONDS[tf]
        candles = [c for c in candles if c.time + tf_sec <= asOf + tf_sec * 12][-count:]
    return {"success": True, "symbol": sym, "timeframe": tf, "candles": [c.to_dict() for c in candles], "isSynthetic": series["isSynthetic"], "source": series["source"]}


@router.post("/exunu/dispatch-telegram")
async def exunu_dispatch(body: dict = Body(default={}), _=Depends(admin_user)):
    r = await dispatch_setup(body.get("symbol") or "XAU/USD", manual=True)
    return {"success": r["success"], "error": r.get("error"), "state": r.get("state"), "result": {"sent": r["success"], "error": r.get("error")}}


@router.post("/agent/ask")
async def agent_ask(body: dict = Body(...)):
    question = str(body.get("question") or "")[:2000]
    if not question.strip():
        raise HTTPException(400, "Empty question")
    return {"success": True, **(await ask_agent(question, await both_results()))}


@router.post("/agent/explain-drawing")
async def agent_explain_drawing(body: dict = Body(...)):
    symbol = str(body.get("symbol") or "XAU/USD")
    as_of = int(body.get("asOf") or 0)
    bundle = await (get_strategy_result_as_of(symbol, as_of) if as_of > 0 else get_strategy_result(symbol))
    r = bundle["result"]
    drawing = next((d for d in r["drawings"] if d["id"] == str(body.get("drawingId") or "")), None)
    if not drawing:
        raise HTTPException(404, "Drawing not found (the chart may have refreshed)")
    lang = body.get("lang") if body.get("lang") in ("ar", "fr", "en", "darija") else detect_lang(str(body.get("question") or ""))
    return {"success": True, "text": explain_drawing(r, drawing, lang), "drawing": drawing}


@router.get("/agent/context")
async def agent_context():
    return build_agent_context(await both_results())


@router.get("/agent/system-prompt", response_class=PlainTextResponse)
def agent_system_prompt():
    return build_system_prompt()


_bt_cache: dict[str, tuple[dict, float]] = {}


@router.get("/backtest")
async def backtest(symbol: str = "XAU/USD", _=Depends(current_user)):
    sym = normalize_symbol(symbol)
    hit = _bt_cache.get(sym)
    if hit and hit[1] > time.time():
        return hit[0]
    try:
        report = await run_backtest(sym)
    except RuntimeError as err:
        raise HTTPException(503, str(err))
    _bt_cache[sym] = (report, time.time() + 1800)
    return report
