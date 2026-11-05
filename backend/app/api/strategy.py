"""The two strategies on the chart, the AI agent and the backtester."""

import time

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from ..agent.agent import ask_agent, build_agent_context, detect_lang, explain_overlay_item
from ..agent.system_prompt import build_system_prompt
from ..auth import admin_user, current_user
from ..backtest import run_backtest
from ..market.data import TIMEFRAME_SECONDS, fetch_candle_series, fetch_live_price
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
    live = await fetch_live_price(sym)
    return {"success": True, "symbol": sym, "timeframe": tf, "candles": [c.to_dict() for c in candles], "isSynthetic": series["isSynthetic"], "source": series["source"],
            "price": live.get("price"), "quoteTime": live.get("quoteTime"), "priceSource": live.get("source")}


@router.get("/analyze")
async def analyze_pair(symbol: str = "XAU/USD", _=Depends(current_user)):
    """The "Analyse" button: the proven plans and the SMC strategies checked now, the one that applies picked and drawn."""
    from ..agents.registry import AGENT_CONFIGS
    from ..analysis.engine import analyse_all

    sym = normalize_symbol(symbol)
    if sym not in AGENT_CONFIGS:
        raise HTTPException(404, f"{sym} is not traded by the app")
    return await analyse_all(sym)


@router.get("/analyze/smc")
async def analyze_pair_smc(symbol: str = "XAU/USD", _=Depends(current_user)):
    """The "SMC" button: the four mechanical SMC strategies checked now, a confirmed setup when every rule is met."""
    from ..agents.registry import AGENT_CONFIGS
    from ..analysis.engine import analyse_smc

    sym = normalize_symbol(symbol)
    if sym not in AGENT_CONFIGS:
        raise HTTPException(404, f"{sym} is not traded by the app")
    return await analyse_smc(sym)


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


@router.get("/agents/radar")
async def agents_radar(symbol: str = "XAU/USD", _=Depends(current_user)):
    """The pair agent's radar: what it confirms now, or what is closest (its analysis, at most a minute old)."""
    from ..agents.registry import AGENT_CONFIGS
    from ..analysis.engine import agent_radar

    sym = normalize_symbol(symbol)
    if sym not in AGENT_CONFIGS:
        raise HTTPException(404, f"{sym} is not traded by the app")
    return await agent_radar(sym)


@router.get("/agents/radars")
async def agents_radars(symbols: str = "", _=Depends(current_user)):
    """Several pairs' radars in one call (the dashboard shows every pair at once): one request instead of one per pair."""
    import asyncio

    from ..agents.registry import AGENT_CONFIGS
    from ..analysis.engine import agent_radar

    syms = list(dict.fromkeys(s for s in (normalize_symbol(x) for x in symbols.split(",") if x.strip()) if s in AGENT_CONFIGS))[:12]
    rows = await asyncio.gather(*(agent_radar(s) for s in syms), return_exceptions=True)
    return {"success": True, "radars": {s: r for s, r in zip(syms, rows) if isinstance(r, dict)}}


@router.get("/smc/report")
async def smc_report_get(symbol: str = "XAU/USD", _=Depends(current_user)):
    """The six SMC agents' report of the pair (SMCAnalysisReport) and its drawing for the chart."""
    from ..agents.registry import AGENT_CONFIGS
    from ..analysis.engine import cached_analysis

    sym = normalize_symbol(symbol)
    if sym not in AGENT_CONFIGS:
        raise HTTPException(404, f"{sym} is not traded by the app")
    a = await cached_analysis(sym)
    smc = a.get("smc") or {}
    if not smc.get("report"):
        raise HTTPException(502, "No SMC report right now")
    return {"success": True, "symbol": sym, "report": smc["report"], "draw": smc.get("reportDraw")}


@router.get("/agents/brain")
async def agents_brain(symbol: str = "XAU/USD", _=Depends(current_user)):
    """The pair's one agent: its proven plan, the SMC strategies and the big players' positioning read together."""
    from ..agents.registry import AGENT_CONFIGS
    from ..analysis.brain import brain
    from ..analysis.engine import cached_analysis

    sym = normalize_symbol(symbol)
    if sym not in AGENT_CONFIGS:
        raise HTTPException(404, f"{sym} is not traded by the app")
    a = await cached_analysis(sym)
    if not a.get("success"):
        raise HTTPException(502, a.get("error") or "No analysis right now")
    return {"success": True, "symbol": sym, **brain(a)}


@router.get("/agents/overlay")
async def agent_overlay(symbol: str = "XAU/USD", asOf: int = 0):
    """The AgentChartOverlayState the pair's own agent emits for its chart (zones, price lines, markers, trade box)."""
    sym = normalize_symbol(symbol)
    bundle = await (get_strategy_result_as_of(sym, asOf) if asOf > 0 else get_strategy_result(sym))
    r = bundle["result"]
    return {"success": True, "symbol": sym, "overlay": r.get("overlay"), "status": r["status"], "price": r["price"],
            "decimals": r["spec"]["decimals"], "entryTf": r["timeframes"]["entry"], "dataQuality": r["dataQuality"]}


@router.post("/agent/explain-drawing")
async def agent_explain_drawing(body: dict = Body(...)):
    """Explains one item of the agent's chart overlay (zone, line, marker or "trade")."""
    symbol = str(body.get("symbol") or "XAU/USD")
    as_of = int(body.get("asOf") or 0)
    bundle = await (get_strategy_result_as_of(symbol, as_of) if as_of > 0 else get_strategy_result(symbol))
    lang = body.get("lang") if body.get("lang") in ("ar", "fr", "en", "darija") else detect_lang(str(body.get("question") or ""))
    text = explain_overlay_item(bundle["result"], str(body.get("drawingId") or ""), lang)
    if text is None:
        raise HTTPException(404, "Drawing not found (the chart may have refreshed)")
    return {"success": True, "text": text}


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
