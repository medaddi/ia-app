"""
A pair's team. Every member has one role, reads the same market of THIS pair only, and gives its view: a side and how sure
it is (0 to 1). The team then weighs the views into probabilities (buy / sell / wait) and decides together.

  trade      the trade manager: the order the pair agent is running (it leads while a trade is open)
  structure  SMC agent 1: H1 bias, sure when M15 and M5 agree
  liquidity  SMC agent 2: the side of the liquidity price is drawn to, surer once the IDM is swept
  zones      SMC agent 3: premium sells, discount buys, surer far from the 50 %
  strategy   SMC agents 4 + 5: the course's strategy setup, as sure as its 7-question checklist
  cot        the big players (CFTC COT, trader skill): their net side, less sure when crowded
  risk       votes no side: approves a setup only with RR >= 1:3, the 7 questions met and clean data

  desk       each pair's own team (pairs/desks/<pair>.py): its hours, the weight of each member on THIS pair, the trust in
             its COT report. A setup is only taken inside the pair's hours.

  decision   1. a trade being managed: the team follows it, it never calls the other side meanwhile
             2. an SMC setup ready to execute, approved by risk, with its side more probable than the other: SETUP
             3. else wait, leaning only to a side at least 35 % probable and 15 points ahead of the other
  grade      A = the decided side is 60 %+ probable · B = 45 %+ · C = below: confluence, not a guarantee
"""

import time
from typing import Optional

from .desks import DESKS

WEIGHT = {"trade": 1.5, "structure": 1.0, "liquidity": 1.0, "zones": 0.8, "strategy": 1.5, "cot": 0.8}


def _m(key: str, side: Optional[str], conf: float, line: str) -> dict:
    return {"key": key, "side": side, "conf": round(max(0.0, min(1.0, conf)), 2) if side else 0.0, "line": line}


def _live_trade(live: Optional[dict]) -> Optional[dict]:
    ov = (live or {}).get("overlay") or {}
    box = ov.get("tradeExecutionBox")
    if ov.get("fsmState") not in ("IN_TRADE", "PENDING_ORDER") or not box:
        return None
    return {"side": "BUY" if box["direction"] == "LONG" else "SELL", "state": ov["fsmState"], "entry": box["entryPrice"], "sl": box["stopLoss"],
            "tp": box.get("tp2Price") or box.get("tp1Price"), "rr": box.get("rrRatio"), "pips": box.get("floatingPips"),
            "be": box.get("status") == "TP1_HIT_BE", "agent": ov.get("agentId")}


def members(a: dict, live: Optional[dict]) -> tuple[list[dict], dict, Optional[dict]]:
    rep = (a.get("smc") or {}).get("report") or {}
    a1, a2, a5 = rep.get("agent1_structure") or {}, rep.get("agent2_liquidity") or {}, rep.get("agent5_riskAndTrade") or {}
    cot = (a.get("skill") or {}).get("cot") or {}
    side_of = {"BULLISH": "BUY", "BEARISH": "SELL"}
    out = []
    trade = _live_trade(live)
    if trade:
        out.append(_m("trade", trade["side"], 0.9, f"{trade['side']} {'pending at' if trade['state'] == 'PENDING_ORDER' else 'in trade from'} {trade['entry']}"
                      + (f" · {trade['pips']:+.1f} pips" if trade["state"] == "IN_TRADE" and trade["pips"] is not None else "")
                      + (" · stop at break-even" if trade["be"] else "")))
    htf = a1.get("htfBias")
    s = side_of.get(htf)
    out.append(_m("structure", s, 0.5 + 0.25 * (a1.get("itfBias") == htf) + 0.25 * (a1.get("ltfBias") == htf),
                  f"H1 {str(htf).lower()} · M15 {str(a1.get('itfBias')).lower()} · M5 {str(a1.get('ltfBias')).lower()}"))
    draw, idm = a2.get("drawOnLiquidity"), a2.get("idm")
    s = {"BSL": "BUY", "SSL": "SELL"}.get((draw or {}).get("side"))
    out.append(_m("liquidity", s, 0.6 + (0.2 if (idm or {}).get("status") == "SWEPT" else 0) - (0.2 if a2.get("retailTrapWarning") else 0),
                  (f"drawn to {draw['label']} {draw['price']}" if draw else "no clear pool") + (f" · IDM {idm['status'].lower()}" if idm else "")))
    rng = a1.get("dealingRange") or {}
    val = rng.get("currentValuation")
    s = "BUY" if val in ("DISCOUNT", "BELOW_RANGE") else "SELL" if val in ("PREMIUM", "ABOVE_RANGE") else None
    pos = rng.get("positionPct")
    out.append(_m("zones", s, max(0.3, abs((pos if pos is not None else 50) - 50) / 50), f"price {str(val).lower().replace('_', ' ')}" + (f" ({pos:.0f} %)" if pos is not None else "")))
    st = a5.get("status")
    chk = a5.get("checklistScore") or "0/7"
    passed = int(chk.split("/")[0]) if "/" in chk else 0
    s = a5.get("direction") if st in ("READY_TO_EXECUTE", "RUNNING", "BLOCKED") else None
    out.append(_m("strategy", s, passed / 7 if st != "BLOCKED" else 0.3,
                  f"{(rep.get('agent4_strategy') or {}).get('strategyName') or 'SMC'}: {str(st).replace('_', ' ').lower()}" + (f" · {chk}" if a5.get("direction") else "")))
    s = cot.get("bias") if cot.get("bias") in ("BUY", "SELL") else None
    out.append(_m("cot", s, 0.4 if cot.get("crowded") else 0.6,
                  f"speculators {cot['netPct']:+.1f}% net" + (" · crowded" if cot.get("crowded") else "") if cot else "report unavailable"))
    guard = (rep.get("meta") or {}).get("guard") or {}
    ok = bool(a5.get("direction")) and (a5.get("riskRewardRatio") or 0) >= 3 and passed == 7 and guard.get("ok", False)
    risk = {"key": "risk", "approves": ok,
            "line": ("setup approved: 1:%s, 7/7, clean data" % a5.get("riskRewardRatio")) if ok else
                    ("no setup to approve" if not a5.get("direction") else f"setup refused: 1:{a5.get('riskRewardRatio')} · {chk}"
                     + ("" if guard.get("ok", True) else " · data not clean"))}
    return out, risk, trade


def probabilities(ms: list[dict], weights: Optional[dict] = None) -> dict:
    w = weights or WEIGHT
    buy = sum(w[m["key"]] * m["conf"] for m in ms if m["side"] == "BUY")
    sell = sum(w[m["key"]] * m["conf"] for m in ms if m["side"] == "SELL")
    # waiting: the doubt of the members who give a side, and half the weight of those with no view yet
    wait = sum(w[m["key"]] * ((1 - m["conf"]) if m["side"] else 0.5) for m in ms)
    tot = buy + sell + wait or 1
    b, s_ = round(100 * buy / tot), round(100 * sell / tot)
    return {"buy": b, "sell": s_, "wait": 100 - b - s_}


def session_now(desk: Optional[dict], now: int) -> dict:
    """Whether the pair's own hours are open now (UTC), and which window."""
    if not desk:
        return {"open": True, "label": None}
    h = (now // 3600) % 24
    win = next((w for w in desk["sessions"] if w[0] <= h < w[1]), None)
    return {"open": win is not None, "label": win[2] if win else None,
            "windows": [{"from": a, "to": b, "label": c} for a, b, c in desk["sessions"]]}


def pair_team(a: dict, live: Optional[dict] = None, now: Optional[int] = None) -> dict:
    """The team of one pair: its members' views, the probabilities and the decision they take together."""
    desk = DESKS.get(a.get("symbol") or "")
    ses = session_now(desk, int(now if now is not None else a.get("at") or time.time()))
    ms, risk, trade = members(a, live)
    p = probabilities(ms, (desk or {}).get("weights"))
    rep = (a.get("smc") or {}).get("report") or {}
    a5 = rep.get("agent5_riskAndTrade") or {}
    sc = a.get("scenarios") or {}
    if trade:
        decision = {"status": "IN_TRADE" if trade["state"] == "IN_TRADE" else "PENDING", "side": trade["side"], "entry": trade["entry"],
                    "sl": trade["sl"], "tp": trade["tp"], "rr": trade["rr"], "why": "the trade manager runs its trade: the team holds that side"}
    elif a5.get("status") == "READY_TO_EXECUTE" and a5.get("direction"):
        side = a5["direction"]
        mine, other = (p["buy"], p["sell"]) if side == "BUY" else (p["sell"], p["buy"])
        base = {"entry": a5.get("entryPrice"), "entryZone": a5.get("entryZone"), "sl": a5.get("stopLoss"), "tp": a5.get("tp2_finalRunner"),
                "rr": a5.get("riskRewardRatio"), "name": (rep.get("agent4_strategy") or {}).get("strategyName")}
        if risk["approves"] and mine > other and not ses["open"]:
            decision = {**base, "status": "WAITING", "side": side, "why": f"{side} setup ready, but outside the pair's hours: the team waits for its session"}
        elif risk["approves"] and mine > other:
            decision = {**base, "status": "SETUP", "side": side, "why": f"SMC setup approved by risk, {mine} % {side} against {other} %"}
        else:
            decision = {**base, "status": "CONFLICT", "side": None,
                        "why": risk["line"] if not risk["approves"] else f"the team does not back the {side} setup ({mine} % against {other} %)"}
    else:
        lean = "BUY" if p["buy"] >= 35 and p["buy"] - p["sell"] >= 15 else "SELL" if p["sell"] >= 35 and p["sell"] - p["buy"] >= 15 else None
        main = (sc.get("buy" if lean == "BUY" else "sell") or {}).get("main") if lean else None
        decision = {"status": "WAITING", "side": lean, "trigger": (main or {}).get("trigger"), "entry": (main or {}).get("entry"),
                    "sl": (main or {}).get("sl"), "tp": (main or {}).get("tp"), "rr": (main or {}).get("rr"),
                    "why": f"no setup: {p[lean.lower()]} % {lean}" if lean else "no setup and no clear side: wait"}
    d = decision["side"]
    for m in ms:
        m["agrees"] = None if not d or not m["side"] else m["side"] == d
    sure = p[d.lower()] if d else None
    grade = None if sure is None else "A" if sure >= 60 else "B" if sure >= 45 else "C"
    team = {k: desk[k] for k in ("team", "teamFr", "teamAr", "tags")} if desk else None
    return {"agent": a.get("agent"), "desk": team, "session": ses, "members": ms, "risk": risk, "probabilities": p, "decision": decision,
            "grade": grade, "at": a.get("at")}
