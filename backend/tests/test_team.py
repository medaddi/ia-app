"""A pair's team: each member's role and view, the probabilities, and the decision they take together."""

from app.pairs.dossier import trades_of
from app.pairs.team import pair_team


def analysis(htf="BEARISH", itf="BEARISH", ltf="BEARISH", draw="SSL", idm="SWEPT", val="PREMIUM", pos=80.0, a5_status="WAITING",
             a5_dir=None, rr=3.5, chk="7/7", cot="SELL", guard=True):
    a5 = {"status": a5_status, "direction": a5_dir, "riskRewardRatio": rr, "checklistScore": chk if a5_dir else None,
          "entryPrice": 1.125, "entryZone": [1.1248, 1.1252], "stopLoss": 1.127, "tp2_finalRunner": 1.118}
    rep = {"meta": {"guard": {"ok": guard}}, "agent1_structure": {"htfBias": htf, "itfBias": itf, "ltfBias": ltf,
                                                                   "dealingRange": {"currentValuation": val, "positionPct": pos}},
           "agent2_liquidity": {"drawOnLiquidity": {"side": draw, "label": "PDL", "price": 1.12} if draw else None,
                                "idm": {"status": idm, "price": 1.124} if idm else None, "retailTrapWarning": None},
           "agent4_strategy": {"strategyName": "Session sweep"}, "agent5_riskAndTrade": a5}
    return {"symbol": "EUR/USD", "agent": {"id": "EURUSD_Test_Agent"}, "at": 8 * 3600, "smc": {"report": rep},  # 08:00 UTC: London
            "skill": {"cot": {"bias": cot, "netPct": -24.0, "crowded": False}},
            "scenarios": {"sell": {"main": {"trigger": "H1 close below 1.12", "entry": 1.12, "sl": 1.124, "tp": 1.112, "rr": 2}}, "buy": {"main": None}}}


def live_trade(direction="SHORT", state="IN_TRADE"):
    return {"overlay": {"agentId": "EURUSD_AsianFade_Agent", "fsmState": state,
                        "tradeExecutionBox": {"direction": direction, "entryPrice": 1.12598, "stopLoss": 1.12598, "tp1Price": 1.12458,
                                              "tp2Price": 1.12316, "rrRatio": 1.5, "floatingPips": 34.8, "status": "TP1_HIT_BE"}},
            "running": [{"id": "x1", "direction": "SELL", "entryType": "MARKET", "entry": 1.12598, "sl": 1.12598, "tp1": 1.12458, "tp2": 1.12316,
                         "state": "TP1_HIT", "signalTime": 1}]}


def test_every_member_has_its_role_and_the_probabilities_add_up():
    t = pair_team(analysis())
    keys = [m["key"] for m in t["members"]]
    assert keys == ["structure", "liquidity", "zones", "strategy", "cot"] and t["risk"]["key"] == "risk"
    p = t["probabilities"]
    assert p["buy"] + p["sell"] + p["wait"] == 100 and p["sell"] > 50 and p["buy"] == 0
    assert t["decision"]["status"] == "WAITING" and t["decision"]["side"] == "SELL" and t["decision"]["trigger"] == "H1 close below 1.12"


def test_the_trade_being_managed_leads_the_team():
    t = pair_team(analysis(htf="BULLISH", itf="BULLISH", ltf="BULLISH", draw="BSL", val="DISCOUNT", pos=20.0, cot="BUY"), live_trade())
    d = t["decision"]
    assert t["members"][0]["key"] == "trade" and d["status"] == "IN_TRADE" and d["side"] == "SELL"  # never a BUY while a SELL runs
    assert t["members"][0]["agrees"] is True and sum(m["agrees"] is False for m in t["members"]) >= 3


def test_a_ready_smc_setup_backed_by_the_team_and_risk_is_a_setup():
    t = pair_team(analysis(a5_status="READY_TO_EXECUTE", a5_dir="SELL"))
    assert t["risk"]["approves"] and t["decision"]["status"] == "SETUP" and t["decision"]["side"] == "SELL" and t["grade"] in ("A", "B")


def test_risk_refuses_a_setup_under_1_to_3():
    t = pair_team(analysis(a5_status="READY_TO_EXECUTE", a5_dir="SELL", rr=2.0))
    assert not t["risk"]["approves"] and t["decision"]["status"] == "CONFLICT" and t["decision"]["side"] is None


def test_split_members_give_no_side():
    t = pair_team(analysis(htf="BULLISH", itf="BEARISH", ltf="BEARISH", draw="SSL", idm=None, val="DISCOUNT", pos=40.0, cot="NEUTRAL"))
    assert t["decision"]["status"] == "WAITING" and t["decision"]["side"] is None


def test_the_dossier_keeps_only_its_own_pair():
    tr = trades_of("EUR/USD", live_trade(), None)
    assert tr["running"] and all(x["symbol"] == "EUR/USD" for x in tr["running"]) and tr["history"] == []


def test_each_pair_has_its_own_specialist_team():
    from app.agents.registry import AGENT_CONFIGS
    from app.pairs.desks import DESKS

    assert set(DESKS) == set(AGENT_CONFIGS)  # one team per pair, no pair without its team
    assert DESKS["XAU/USD"]["weights"]["cot"] > DESKS["EUR/CHF"]["weights"]["cot"]  # gold's COT is one contract; a cross is built from two
    a = analysis()
    gold = pair_team({**a, "symbol": "XAU/USD"})
    chf = pair_team({**a, "symbol": "EUR/CHF"})
    assert gold["desk"]["teamFr"] == "Équipe Or" and chf["desk"]["teamFr"] == "Équipe EUR/CHF"
    assert gold["probabilities"] != chf["probabilities"]  # the same market read, weighed by each pair's own team


def test_a_ready_setup_waits_for_the_pairs_own_hours():
    a = analysis(a5_status="READY_TO_EXECUTE", a5_dir="SELL")
    night = pair_team(a, now=20 * 3600)  # 20:00 UTC: EUR/USD's London and NY windows are shut
    assert not night["session"]["open"] and night["decision"]["status"] == "WAITING" and night["decision"]["side"] == "SELL"
    day = pair_team(a, now=8 * 3600)
    assert day["session"]["open"] and day["session"]["label"] == "London" and day["decision"]["status"] == "SETUP"
