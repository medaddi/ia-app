"""
EXUNU agent bridge.
Presents the strategy result of the app's two strategies as the 4-agent EXUNU view
(Structure, Liquidity, Risk, CTO). The agents run no logic of their own: each one reports its
part of the same deterministic result the chart and Telegram use.
"""

import re
import time
from typing import Optional

from ..agent.explain import build_explanation
from .alexg.config import NAMES as ASSET_NAMES
from .service import get_strategy_result, get_strategy_result_as_of, normalize_symbol
from .shared.jsnum import iso, js_str, to_fixed


def _grade(score: float) -> str:
    return "A+" if score >= 90 else "A" if score >= 75 else "B" if score >= 60 else "C"


def _legacy_status(r: dict) -> str:
    """Only a SIGNAL is a confirmed entry."""
    return "CONFIRMED_ENTRY" if r["status"] == "SIGNAL" else "WAITING_CONFIRMATION" if r["status"] == "WATCH" else "NO_SETUP"


_LOT_LABEL = re.compile(r" · [0-9.]+ lot / \$1k$")


def _without_lot_labels(drawings: list[dict]) -> list[dict]:
    """The app has no capital setting: drop the strategy's "lot per $1k" note from the trade box labels."""
    return [{**d, "text": _LOT_LABEL.sub("", d["text"])} if d.get("layer") == "trade" and d.get("text") else d for d in drawings]


def build_exunu_result(r: dict) -> dict:
    d = r["spec"]["decimals"]
    f = lambda v: to_fixed(v, d)  # noqa: E731
    s = r["setup"]
    a = (s or {}).get("anchors") or {}
    facts = r["facts"] or {}
    status = _legacy_status(r)
    action = s["direction"] if s and r["status"] not in ("NO_TRADE", "IGNORE") else "WAIT"
    now_ms = int(time.time() * 1000)

    structure_summary = f"Bias {r['bias']['direction']}: {r['bias']['detail']}"
    if a.get("sweep"):
        sw = a["sweep"]
        poi = f" · POI {a['poi']['kind']} {f(a['poi']['bottom'])}–{f(a['poi']['top'])}" if a.get("poi") else ""
        liquidity_summary = f"{sw['level']['label']} {f(sw['level']['price'])} swept (wick {f(sw['extreme'])}){poi}"
    elif a.get("reversion"):
        rv = a["reversion"]
        liquidity_summary = (f"{rv['session']}: close {f(rv['excursion'])} beyond the Bollinger band {f(rv['band'])} against the trend, "
                             f"then back inside at {f(rv['close'])} (middle {f(rv['mid'])})")
    elif a.get("breakout"):
        bo = a["breakout"]
        liquidity_summary = (f"H1 close {f(bo['close'])} {'above' if bo['direction'] == 'BUY' else 'below'} the {bo['lookback']}h "
                             f"{'high' if bo['direction'] == 'BUY' else 'low'} {f(bo['level'])} (range {f(bo['rangeLow'])}–{f(bo['rangeHigh'])})")
    elif a.get("gpa"):
        g = a["gpa"]
        z = g["aoi"]
        liquidity_summary = (f"{z['tfs']} AOI {f(z['lo'])}–{f(z['hi'])} ({z['touches']} touches)"
                             + (f" · {g['pattern']['type']}" if g["pattern"] else "") + f" · {g['session']} engulfing · grade {g['grade']} {g['score']}%")
    elif facts.get("areasOfInterest") and facts["areasOfInterest"][0].get("lo") is not None:
        liquidity_summary = "AOI: " + " · ".join(f"{x['tfs']} {f(x['lo'])}–{f(x['hi'])} ({x['touches']})" for x in facts["areasOfInterest"][:3])
    elif a.get("breakRetest"):
        br = a["breakRetest"]
        liquidity_summary = (f"Area of interest {f(br['level'])} ({br['touches']} touches) broken, moved to {f(br['extreme'])}, "
                             f"retested with {'an' if br['pattern'] == 'engulfing' else 'a'} {br['pattern']}")
    elif a.get("leg"):
        leg, ob = a["leg"], a.get("ob")
        liquidity_summary = f"Pullback into Fib 50–61.8% {f(min(leg['fib50'], leg['fib618']))}–{f(max(leg['fib50'], leg['fib618']))}"
        if ob:
            liquidity_summary += f" + H1 OB {f(ob['bottom'])}–{f(ob['top'])}"
    elif facts.get("areasOfInterest"):
        liquidity_summary = "Areas of interest: " + " · ".join(f"{x['kind']} {f(x['price'])}" for x in facts["areasOfInterest"])
    elif facts.get("asianRange"):
        liquidity_summary = f"Asian range {f(facts['asianRange']['low'])}–{f(facts['asianRange']['high'])}"
    else:
        liquidity_summary = "No liquidity event in the setup window"
    if s and s["params"].get("breakeven", True) is False:  # set & forget: one target
        risk_summary = (f"{s['entryType']} {s['direction']} {f(s['entry'])} · SL {f(s['sl'])} ({js_str(s['slPips'])}p) · "
                        f"TP {f(s['tp3'])} 1:{to_fixed(abs(s['tp3'] - s['entry']) / abs(s['entry'] - s['sl']), 1)} · no partials, no breakeven")
    else:
        risk_summary = (f"{s['entryType']} {s['direction']} {f(s['entry'])} · SL {f(s['sl'])} ({js_str(s['slPips'])}p) · TP1 {f(s['tp1'])} · "
                        f"TP2 {f(s['tp2'])} 1:{to_fixed(s['rrTp2'], 1)}") if s else "No levels: no setup"
    cto_summary = f"{r['status']} · score {r['score']}/100 · {r['headline']}"

    return {
        "terminal": "LiquidityDissection Terminal",
        "symbol": r["displaySymbol"],
        "current_price": r["price"],
        "status": status,
        "action": action,
        "confidence": r["score"],
        "setup_json": {
            "status": status,
            "state": s["lifecycle"]["state"] if s else "NO_SETUP",
            "action": action,
            "symbol": r["displaySymbol"],
            "confidence": r["score"],
            "setup_grade": _grade(r["score"]) if s else "—",
            "strategy": r["strategyName"],
            "current_price": r["price"],
            "entry_price": s["entry"] if s else 0,
            "stop_loss": s["sl"] if s else 0,
            "target1": s["tp1"] if s else 0,
            "target2": s["tp2"] if s else 0,
            "target3": s["tp3"] if s else 0,
            "risk_reward": f"1:{to_fixed(s['rrTp2'], 1)}" if s else "—",
            "sl_pips": s["slPips"] if s else 0,
            "risk_management": {"lot_sizing": {**(s["lots"] if s else {}), "standard_risk_pct": "1.0%"}, "is_rr_valid": bool(s) and s["rrTp2"] >= 2},
            "timestamp": now_ms,
        },
        "agents": {
            "structure_agent": {"agent": "Structure Agent", "summary": structure_summary, "bias": r["bias"]},
            "liquidity_agent": {"agent": "Liquidity Agent", "summary": liquidity_summary},
            "risk_agent": {"agent": "Risk Agent", "summary": risk_summary, "lots": s["lots"] if s else {}},
            "cto_agent": {"agent": "Chief Trading Officer (CTO)", "summary": cto_summary, "status": r["status"], "score": r["score"],
                          "checklist": r["checklist"], "rejection": r["rejection"], "can_notify": r["canNotify"]},
        },
        "inter_agent_dialogue": [
            {"sender": "Structure Agent", "recipient": "Liquidity Agent", "topic": "BIAS", "summary": structure_summary},
            {"sender": "Liquidity Agent", "recipient": "Risk Agent", "topic": "LIQUIDITY", "summary": liquidity_summary},
            {"sender": "Risk Agent", "recipient": "CTO Agent", "topic": "RISK", "summary": risk_summary},
            {"sender": "CTO Agent", "recipient": "Terminal", "topic": "DECISION", "summary": cto_summary},
        ],
        "summary_ar": r["headlineAr"],
        "explanation": build_explanation(r),
        "timestamp": now_ms,
        "strategy": {**r, "drawings": _without_lot_labels(r["drawings"])},
    }


async def run_exunu(symbol: str = "XAU/USD", price: Optional[float] = None, as_of: int = 0) -> dict:
    bundle = await (get_strategy_result_as_of(symbol, as_of) if as_of > 0 else get_strategy_result(symbol, live_price=price))
    return build_exunu_result(bundle["result"])


def to_ai_signal(res: dict, live_price: Optional[float] = None) -> dict:
    """The legacy AISignal shape the UI and Telegram formatter use."""
    r = res["strategy"]
    s = r["setup"]
    d = r["spec"]["decimals"]
    confirmed = r["status"] == "SIGNAL"
    sym = normalize_symbol(r["displaySymbol"])
    ck = {c["key"]: c["passed"] for c in r["checklist"]}
    trend = "Bullish" if r["bias"]["direction"] == "BULLISH" else "Bearish" if r["bias"]["direction"] == "BEARISH" else "Sideways"
    score = r["score"]
    return {
        "id": f"sig-{s['id']}" if s else f"sig-{r['symbol'].lower()}",
        "symbol": sym,
        "assetName": ASSET_NAMES.get(sym, "Spot Gold (XAU/USD)"),
        "signalType": res["action"],
        "signalLabel": f"{s['direction']} SIGNAL" if confirmed else f"{s['direction'] if s else 'undefined'} WATCH" if r["status"] == "WATCH" else "NO TRADE",
        "entryZone": to_fixed(s["entry"], d) if s else "",
        "entryPrice": s["entry"] if s else 0,
        "stopLoss": s["sl"] if s else 0,
        "target1": s["tp1"] if s else 0,
        "target2": s["tp2"] if s else 0,
        "target3": s["tp3"] if s else 0,
        "confidence": score,
        "grade": r.get("grade") if s and s.get("setup") == "GPA" else None,  # forex GPA grade (A+ / B / C+)
        "reasons": [f"{'✓' if c['passed'] else '✕'} {c['rule']}: {c['detail']}" for c in r["checklist"]],
        "riskReward": f"1:{to_fixed(s['rrTp2'], 1)}" if s else "—",
        "timeframe": r["timeframes"]["entry"],
        "createdAt": iso(s["signalTime"]) if s else "—",
        "status": "ACTIVE",
        "overallVerdict": ("STRONG_BUY_SETUP" if s["direction"] == "BUY" else "STRONG_SELL_SETUP") if confirmed else "WAIT",
        "currentLivePrice": live_price or r["price"],
        "isActionableNow": confirmed,
        "decisionStatus": "ALLOWED" if confirmed else "NO_TRADE",
        "confirmationCheckPassed": confirmed,
        "confirmationCloseTime": s["signalTime"] if s else None,
        "isMarketOpen": r["market"]["isOpen"],
        "tradeScore": score,
        "tradeScoreGrade": "EXCELLENT" if score >= 90 else "VERY_STRONG" if score >= 75 else "GOOD" if score >= 60 else "WEAK",
        "strategyUsed": r["strategyName"],
        "strategyType": "ICT_SMC",
        "setupGrade": _grade(score) if s else "B",
        "pipSize": r["spec"]["pipSize"],
        "pipsRisk": s["slPips"] if s else None,
        "slPointsOrPips": s["slPips"] if s else None,
        "dataSourceName": r["dataQuality"]["source"],
        "distanceToEntryText": r["headlineAr"],
        "invalidationCondition": s["invalidation"] if s else None,
        "invalidationConditionAr": f"الإلغاء: {s['invalidation']}" if s else None,
        "entryType": s["entryType"] if s else None,
        "expiresAt": r["signal"]["expires_at"] if r["signal"] else None,
        "signalJson": r["signal"],
        "explanation": res["explanation"],
        "marketSuitability": {"isSuitable": confirmed, "trend": trend, "reasonAr": r["headlineAr"], "reasonEn": r["headline"],
                              "emaAlignment": r["bias"]["detail"], "structureVerdict": r["bias"]["detail"]},
        "validationChecklist": {
            "dataValid": r["dataQuality"]["ok"],
            "structureValid": ck.get("mss", ck.get("trigger", False)),
            "htfAligned": ck.get("bias", False),
            "entryConfirmed": confirmed,
            "slLogical": ck.get("sl", False),
            "tpLogical": ck.get("rr", False),
            "acceptableRR": ck.get("rr", False),
            "spreadAcceptable": ck.get("spread", False),
            "volatilityAcceptable": ck.get("volatility", True),
            "noAbnormalConditions": not r["news"]["blocked"],
            "riskWithinLimits": ck.get("daily", ck.get("dailyLimit", True)),
            "allChecksPassed": confirmed,
        },
    }
