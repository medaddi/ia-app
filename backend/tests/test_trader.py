"""The trader chain for gold and forex (the trader-skill method): COT positioning → budget → risk check → tickets."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.trader import budget as B, cot as C, risk as R, tickets as T


def raw_week(code, day, long, short):
    return {"report_date_as_yyyy_mm_dd": f"{day}T00:00:00.000", "cftc_contract_market_code": code, "noncomm_positions_long_all": str(long),
            "noncomm_positions_short_all": str(short), "comm_positions_long_all": "100", "comm_positions_short_all": "200", "open_interest_all": "1000"}


def fake_rows():
    """12 weeks per market: gold heavily net long, euro net short at its 3-year low, franc flat, others mildly short."""
    raw = []
    for w in range(12):
        day = f"2026-{8 + w // 4:02d}-{1 + (w % 4) * 7:02d}"
        raw += [raw_week("088691", day, 200000 + w * 1000, 40000), raw_week("099741", day, 200000, 250000 + w * 10000),
                raw_week("096742", day, 50000, 60000), raw_week("092741", day, 30000, 30000), raw_week("232741", day, 90000, 120000),
                raw_week("090741", day, 80000, 90000)]
    views = {k: C.market_view(v) for k, v in C._series(raw).items()}
    return [r for r in (C.pair_view(s, views) for s in C.LEGS) if r]


def test_cot_copies_the_speculators_side():
    rows = {r["symbol"]: r for r in fake_rows()}
    g, e = rows["XAU/USD"], rows["EUR/USD"]
    assert g["bias"] == "BUY" and g["netPct"] > 60 and g["score"] == 100 and g["crowded"]  # most long of the period
    assert e["bias"] == "SELL" and e["score"] == 0 and e["crowded"]
    assert rows["EUR/CHF"]["legs"][1]["market"].startswith("Swiss") and rows["EUR/CHF"]["bias"] == "SELL"  # euro short − franc flat
    w, skipped = C.targets(list(rows.values()), top=2)
    assert [x["symbol"] for x in w] == ["XAU/USD", "EUR/CHF"] or w[0]["symbol"] == "XAU/USD"
    assert abs(sum(x["weight"] for x in w) - 100) < 0.05 and any("top 2" in s["why"] for s in skipped)


def test_budget_sizes_the_risk_not_the_money():
    fx = {"USD/CAD": 1.40, "USD/CHF": 0.80, "AUD/USD": 0.65, "EUR/USD": 1.12, "GBP/USD": 1.34}
    t = [{"symbol": "EUR/USD", "side": "SELL", "weight": 50.0}, {"symbol": "XAU/USD", "side": "BUY", "weight": 50.0}]
    out = B.size(t, {"balance": 10000, "risk_pct": 1, "max_total_risk_pct": 3, "stop_atr": 1, "rr": 2},
                 {"EUR/USD": 1.12, "XAU/USD": 4000}, {"EUR/USD": 0.0080, "XAU/USD": 50.0}, fx)
    eu, xau = out["orders"]
    # $100 cap per trade (1 %), EUR/USD stop 80 pips × $10 a pip → 0.12 lot (rounded down), stop above for a SELL
    assert eu["lots"] == 0.12 and eu["sl"] > eu["entry"] > eu["tp"] and eu["riskUsd"] == 96.0
    # gold: stop $50 = 500 pips × $10 a pip per lot → $100 → 0.02 lot
    assert xau["lots"] == 0.02 and xau["sl"] < xau["entry"] < xau["tp"]
    assert out["summary"]["riskUsed"] <= 300 and out["summary"]["riskIdle"] >= 0
    assert abs(B.pip_value_usd("AUD/CAD", fx) - 10 / 1.40) < 1e-9
    tiny = B.size([{"symbol": "XAU/USD", "side": "BUY", "weight": 100.0}], {"balance": 200, "risk_pct": 1}, {"XAU/USD": 4000}, {"XAU/USD": 50.0}, fx)
    assert not tiny["orders"] and "less than 0.01 lot" in tiny["skipped"][0]["why"]


def test_risk_check_blocks_what_breaks_a_limit_together():
    o1 = {"symbol": "EUR/USD", "side": "sell", "type": "market", "lots": 0.1, "entry": 1.12, "sl": 1.128, "tp": 1.104, "riskUsd": 80, "marginUsd": 370}
    o2 = {**o1, "symbol": "GBP/USD", "entry": 1.34, "sl": 1.35, "tp": 1.32}
    o3 = {**o1, "symbol": "XAU/USD", "side": "buy", "entry": 4000, "sl": 3950, "tp": 4100, "riskUsd": 150}
    cfg = {"balance": 10000, "max_risk_pct": 2, "max_total_risk_pct": 2.5, "max_usd_same_side": 2}
    res = R.check([o1, o2, o3], cfg, [], 1_790_000_000, True, [])
    v = [r["verdict"] for r in res["results"]]
    assert v[:2] == ["PASS", "PASS"] and v[2] == "BLOCK"  # $80 + $80 + $150 is over 2.5 % of $10,000
    assert any(x.startswith("risk:") for x in res["results"][2]["reasons"])
    news = [{"time": 1_790_000_600, "currency": "USD", "title": "CPI m/m", "impact": "High"}]
    r2 = R.check([o1], cfg, news, 1_790_000_000, False, [{"symbol": "EUR/USD"}])["results"][0]
    assert r2["verdict"] == "BLOCK" and {x.split(":")[0] for x in r2["reasons"]} >= {"news", "market", "duplicate"}
    bad = R.check([{**o1, "sl": 1.10}], cfg, [], 1_790_000_000, True, [])["results"][0]
    assert "format: the stop is on the wrong side of the entry" in bad["reasons"]


def test_a_yes_is_for_one_exact_order():
    o = {"symbol": "EUR/USD", "side": "sell", "lots": 0.12, "sl": 1.128, "tp": 1.104, "riskUsd": 96}
    assert T.parse_yes("yes", o)[0] and T.parse_yes("yes 0.12", o)[0] and T.parse_yes("oui", o)[0]
    for reply in ("ok", "sure", "yes to all", "yes but later", "yes?", "yes 0.5", ""):
        assert not T.parse_yes(reply, o)[0], reply
    assert not T.parse_yes("yes gbp/usd", o, ["EUR/USD", "GBP/USD"])[0]


def test_one_setup_is_sized_from_its_own_stop():
    fx = {"USD/CAD": 1.40, "USD/CHF": 0.80, "AUD/USD": 0.65, "EUR/USD": 1.12, "GBP/USD": 1.34}
    o = B.size_setup("EUR/USD", "SELL", 1.1200, 1.1240, 1.1120, {"balance": 10000, "risk_pct": 1}, fx)  # 40-pip stop
    assert o["lots"] == 0.25 and o["riskUsd"] == 100.0 and o["rr"] == 2.0 and o["side"] == "sell"
    g = B.size_setup("XAU/USD", "BUY", 4000.0, 3990.0, 4020.0, {"balance": 5000, "risk_pct": 1}, fx)  # $10 = 100 pips × $10
    assert g["lots"] == 0.05 and g["riskUsd"] == 50.0
    small = B.size_setup("XAU/USD", "BUY", 4000.0, 3900.0, 4200.0, {"balance": 500, "risk_pct": 1}, fx)
    assert small["lots"] == 0 and "less than 0.01 lot" in small["why"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_each_pair_gets_a_ticket_from_its_setup(client, monkeypatch):
    import app.analysis.engine as E
    import app.api.trader as A

    analysis = {"success": True, "price": 1.12, "pick": {"family": "plan", "id": "EUR-X"},
                "strategies": [{"id": "EUR-X", "name": "Test plan", "setup": {"direction": "SELL", "entry": 1.12, "sl": 1.124, "tp": 1.112}}],
                "scenarios": {"buy": {"main": {"dir": "BUY", "entry": 1.11, "sl": 1.106, "tp": 1.118, "name": "Fade", "trigger": "H1 close below 1.11", "family": "plan"}},
                              "sell": {"main": None}},
                "skill": {"cot": {"bias": "SELL", "crowded": False}}}

    async def cached(pair):
        return analysis

    async def calendar():
        return {"events": [], "source": "test"}

    async def fx():
        return {"USD/CAD": 1.4, "USD/CHF": 0.8, "AUD/USD": 0.65, "EUR/USD": 1.12, "GBP/USD": 1.34}

    monkeypatch.setattr(E, "cached_analysis", cached)
    monkeypatch.setattr(A, "load_news_calendar", calendar)
    monkeypatch.setattr(A, "_fx", fx)
    monkeypatch.setattr(A, "market_session_status", lambda s: {"isOpen": True})
    h = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': 'admin', 'accessCode': 'admin-test-code'}).json()['token']}"}

    assert client.put("/api/trader/config", headers=h, json={"balance": 10000, "risk_pct": 1}).json()["config"]["balance"] == 10000
    assert client.put("/api/trader/config", headers=h, json={"risk_pct": 50}).status_code == 422
    t = client.post("/api/trader/ticket?symbol=EUR/USD", headers=h, json={"source": "pick"}).json()["ticket"]
    assert t["ready"] and t["order"]["lots"] == 0.25 and t["plain"].startswith("SELL 0.25 lots of EUR/USD")
    assert client.post("/api/trader/ticket/approve?symbol=EUR/USD", headers=h, json={"reply": "ok"}).status_code == 422
    done = client.post("/api/trader/ticket/approve?symbol=EUR/USD", headers=h, json={"reply": "yes"}).json()["ticket"]
    assert done["status"].startswith("DONE: approved") and not done["ready"]
    assert client.post("/api/trader/ticket/approve?symbol=EUR/USD", headers=h, json={"reply": "yes"}).status_code == 409  # once
    # the BUY scenario goes against the big players (COT on the SELL side): it is said on the ticket
    b = client.post("/api/trader/ticket?symbol=EUR/USD", headers=h, json={"source": "buy"}).json()["ticket"]
    assert any("against them" in w for w in b["verdict"]["warnings"]) and b["setup"]["condition"] == "H1 close below 1.11"
    assert client.post("/api/trader/ticket?symbol=EUR/USD", headers=h, json={"source": "sell"}).status_code == 409
    assert client.get("/api/trader/log", headers=h).json()["log"][-1]["reply"] == "yes"
