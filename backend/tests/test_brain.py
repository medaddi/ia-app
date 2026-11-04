"""The pair's one agent: its proven plan, the SMC strategies, the big players (COT) and the market, read together."""

from app.analysis.brain import brain


def analysis(pick=True, cot="SELL", trend="bearish", structure="bearish", zone="premium (70 % of the H1 range)"):
    return {
        "agent": {"id": "EURUSD_Test_Agent", "name": "Test", "read": ""}, "at": 0,
        "pick": {"family": "plan", "id": "P1"} if pick else None,
        "strategies": [{"id": "P1", "name": "Plan one", "status": "SETUP" if pick else "WAITING", "reason": "fired",
                        "setup": {"direction": "SELL", "entry": 1.12, "sl": 1.124, "tp": 1.112, "rr": 2} if pick else None}],
        "smc": {"strategies": [{"id": "D", "name": "Session sweep", "status": "WAITING", "reason": "waiting", "steps": [], "checklist": []}],
                "read": {"trend": structure, "zone": zone}},
        "scenarios": {"bias": "BUY", "buyPct": 64, "sellPct": 36,
                      "buy": {"main": {"family": "plan", "name": "Fade", "trigger": "H1 close below 1.11", "entry": 1.11, "sl": 1.106, "tp": 1.118, "rr": 2}},
                      "sell": {"main": None}},
        "skill": {"cot": {"bias": cot, "netPct": -24.0, "crowded": False, "reportDate": "2026-10-27"}},
        "read": {"trend": trend, "smc": ""},
    }


def test_a_setup_backed_by_every_view_is_grade_a():
    b = brain(analysis())
    assert b["decision"]["status"] == "SETUP" and b["decision"]["side"] == "SELL" and b["decision"]["name"] == "Plan one"
    v = {x["key"]: x for x in b["votes"]}
    assert v["plan"]["agrees"] and v["skill"]["agrees"] and v["market"]["agrees"] and v["smc"]["agrees"] is None
    assert b["grade"] == "A" and b["agree"] == 3 and b["against"] == 0


def test_a_contradicted_decision_is_grade_c():
    b = brain(analysis(cot="BUY"))
    assert b["grade"] == "B" or b["grade"] == "C"
    assert next(x for x in b["votes"] if x["key"] == "skill")["agrees"] is False and b["against"] == 1


def test_no_setup_the_agent_leans_with_the_scenarios():
    b = brain(analysis(pick=False, cot="BUY", trend="bullish", structure="bullish", zone="discount (20 % of the H1 range)"))
    d = b["decision"]
    assert d["status"] == "WAITING" and d["side"] == "BUY" and d["trigger"] == "H1 close below 1.11"
    assert b["grade"] == "B" and next(x for x in b["votes"] if x["key"] == "plan")["side"] is None
