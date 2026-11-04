"""
The pair's one agent: its proven plan, the SMC strategies of the course and the trader skill (the big players' COT
positioning) read together, the way a trader weighs every view before acting.

  decision   the setup that applies now: the proven plan's first (2 years of proof), else an SMC setup confirmed by its
             rules and the 7 questions; with none, the side the scenarios lean to and the trigger closest to price
  votes      plan · SMC · big players (COT) · market (H1 trend, SMC structure, premium / discount): each says BUY,
             SELL or nothing, and whether it agrees with the decision
  grade      A = at least 3 views agree with the decision and none is against it; B = 2 agree; C = the decision stands
             alone or a view is against it. A grade is confluence, not a guarantee.
"""

from typing import Optional


def _side(x: Optional[str]) -> Optional[str]:
    x = (x or "").upper()
    return x if x in ("BUY", "SELL") else None


def brain(a: dict) -> dict:
    """The one-agent read of a pair, from its full analysis (analysis.engine.analyse_all)."""
    plans = a.get("strategies") or []
    smc = (a.get("smc") or {}).get("strategies") or []
    sc = a.get("scenarios") or {}
    skill = a.get("skill") or {}
    cot = skill.get("cot") or {}
    read = a.get("read") or {}
    smc_read = (a.get("smc") or {}).get("read") or {}

    # the decision
    pick = a.get("pick")
    decision: dict
    if pick:
        rows = plans if pick["family"] == "plan" else smc
        row = next((r for r in rows if r["id"] == pick["id"]), None) or {}
        st = row.get("setup") or {}
        decision = {"status": "SETUP", "family": pick["family"], "side": _side(st.get("direction")), "name": row.get("name"),
                    "entry": st.get("entry"), "entryZone": st.get("entryZone"), "sl": st.get("sl"), "tp": st.get("tp"), "rr": st.get("rr"),
                    "why": (row.get("reason") if pick["family"] == "plan" else "every SMC rule and the 7 questions met")}
    else:
        bias = sc.get("bias")
        main = (sc.get("buy" if bias == "BUY" else "sell") or {}).get("main") if bias in ("BUY", "SELL") else None
        decision = {"status": "WAITING", "family": (main or {}).get("family"), "side": _side(bias), "name": (main or {}).get("name"),
                    "trigger": (main or {}).get("trigger"), "entry": (main or {}).get("entry"), "sl": (main or {}).get("sl"),
                    "tp": (main or {}).get("tp"), "rr": (main or {}).get("rr"),
                    "why": (f"no setup yet: the scenarios lean {bias} ({sc.get('buyPct' if bias == 'BUY' else 'sellPct')}%)" if main
                            else "no setup and no side: every view is waiting")}
    d = decision["side"]

    # each view's vote
    def plan_vote():
        r = next((r for r in plans if r["status"] in ("SETUP", "LATE")), None)
        if r:
            return {"side": _side((r.get("setup") or {}).get("direction")), "state": r["status"], "line": f"{r['name']}: {r['reason']}"}
        w = next((r for r in plans if r["status"] == "WAITING"), None)
        return {"side": None, "state": "WAITING", "line": f"{w['name']}: {w['reason']}" if w else "no plan"}

    def smc_vote():
        order = {"CONFIRMED": 0, "RUNNING": 1, "FORMING": 2, "BLOCKED": 3, "WAITING": 4}
        r = min(smc, key=lambda r: order.get(r["status"], 9)) if smc else None
        if not r:
            return {"side": None, "state": "WAITING", "line": "no SMC read"}
        side = _side((r.get("setup") or {}).get("direction"))
        if side is None and r["status"] == "FORMING":
            side = None
        passed = sum(1 for c in r.get("checklist") or [] if c["ok"])
        extra = f" · checklist {passed}/7" if r.get("checklist") else ""
        return {"side": side if r["status"] in ("CONFIRMED", "RUNNING") else None, "state": r["status"],
                "line": f"SMC {r['id']} · {r['name']}: {r['reason']}{extra}", "lean": side}

    def cot_vote():
        if not cot:
            return {"side": None, "state": "UNAVAILABLE", "line": "the CFTC report is unavailable right now"}
        return {"side": _side(cot.get("bias")), "state": "CROWDED" if cot.get("crowded") else "POSITIONED" if _side(cot.get("bias")) else "NEUTRAL",
                "line": f"speculators {cot['netPct']:+.1f}% net{' · crowded (3-year extreme)' if cot.get('crowded') else ''} · report {cot.get('reportDate')}"}

    def market_vote():
        pts = []
        if read.get("trend") in ("bullish", "bearish"):
            pts.append("BUY" if read["trend"] == "bullish" else "SELL")
        if smc_read.get("trend") in ("bullish", "bearish"):
            pts.append("BUY" if smc_read["trend"] == "bullish" else "SELL")
        zone_txt = smc_read.get("zone") or ""
        if zone_txt:
            pts.append("SELL" if "premium" in zone_txt else "BUY")
        b, s = pts.count("BUY"), pts.count("SELL")
        side = "BUY" if b > s else "SELL" if s > b else None
        return {"side": side, "state": f"{b} buy · {s} sell", "line": f"H1 trend {read.get('trend', '?')} · SMC structure {smc_read.get('trend', '?')} · price {zone_txt or '?'}"}

    votes = [{"key": "plan", "name": "Proven plan", **plan_vote()}, {"key": "smc", "name": "SMC", **smc_vote()},
             {"key": "skill", "name": "Big players (COT)", **cot_vote()}, {"key": "market", "name": "Market", **market_vote()}]
    for v in votes:
        v["agrees"] = None if not d or not v["side"] else v["side"] == d
    agree = sum(1 for v in votes if v["agrees"] is True)
    against = sum(1 for v in votes if v["agrees"] is False)
    grade = None if not d else ("A" if agree >= 3 and not against else "B" if agree >= 2 else "C")
    return {"agent": a.get("agent"), "decision": decision, "votes": votes, "agree": agree, "against": against, "grade": grade,
            "buyPct": sc.get("buyPct"), "sellPct": sc.get("sellPct"), "at": a.get("at"),
            "smcSummary": (a.get("read") or {}).get("smc")}
