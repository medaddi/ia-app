"""Users, capital, trades, history, win rate and settings through the HTTP API (no network)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "accessCode": "admin-test-code"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_login_rejects_wrong_code(client):
    assert client.post("/api/auth/login", json={"username": "admin", "accessCode": "nope-nope"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_user_lifecycle_and_trade_stats(client, admin):
    r = client.post("/api/users", headers=admin, json={"username": "Trader1", "accessCode": "secret-123", "capital": 5000, "riskPct": 1})
    assert r.status_code == 200, r.text
    assert client.post("/api/users", headers=admin, json={"username": "trader1", "accessCode": "secret-123"}).status_code == 409

    tok = client.post("/api/auth/login", json={"username": "trader1", "accessCode": "secret-123"}).json()["token"]
    me = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/auth/me", headers=me).json()["user"]["capital"] == 5000
    assert client.get("/api/users", headers=me).status_code == 403  # not admin

    # Lot from capital and risk: $5000 × 1% = $50 over a $5 gold stop × 100 oz → 0.10 lot
    t1 = client.post("/api/trades", headers=me, json={"symbol": "XAUUSD", "direction": "BUY", "entry": 4000, "sl": 3995, "tp2": 4010}).json()["trade"]
    assert t1["lots"] == 0.1 and t1["riskAmount"] == 50
    assert client.post("/api/trades", headers=me, json={"symbol": "XAUUSD", "direction": "BUY", "entry": 4000, "sl": 4005}).status_code == 400

    win = client.post(f"/api/trades/{t1['id']}/close", headers=me, json={"exitPrice": 4010}).json()["trade"]
    assert win["result"] == "WIN" and win["pnl"] == 100 and win["rMultiple"] == 2

    t2 = client.post("/api/trades", headers=me, json={"symbol": "EUR/USD", "direction": "SELL", "entry": 1.1, "sl": 1.101, "lots": 0.5}).json()["trade"]
    loss = client.post(f"/api/trades/{t2['id']}/close", headers=me, json={"exitPrice": 1.101}).json()["trade"]
    assert loss["result"] == "LOSS" and loss["pnl"] == -50

    client.post("/api/trades", headers=me, json={"symbol": "XAUUSD", "direction": "SELL", "entry": 4000, "sl": 4004})

    s = client.get("/api/stats", headers=me).json()
    assert (s["total"], s["open"], s["closed"], s["wins"], s["losses"]) == (3, 1, 2, 1, 1)
    assert s["winRate"] == 50 and s["totalPnl"] == 50 and s["currentCapital"] == 5050 and s["profitFactor"] == 2
    assert [p["equity"] for p in s["equityCurve"]] == [5100, 5050] and s["maxDrawdown"] == 50

    hist = client.get("/api/trades?status=closed", headers=me).json()
    assert hist["count"] == 2
    assert client.put("/api/me", headers=me, json={"capital": 8000, "riskPct": 0.5}).json()["user"]["riskPct"] == 0.5

    listed = {u["username"]: u for u in client.get("/api/users", headers=admin).json()["users"]}
    assert listed["trader1"]["stats"]["winRate"] == 50


def test_settings_and_telegram_config(client, admin):
    r = client.put("/api/settings", headers=admin, json={"app": {"appName": "EXUNU", "bogus": 1}, "risk": {"defaultCapital": 2500}})
    assert r.json()["app"]["appName"] == "EXUNU" and "bogus" not in r.json()["app"] and r.json()["risk"]["defaultCapital"] == 2500
    cfg = client.post("/api/telegram/config", headers=admin, json={"botToken": "123456:ABCDEFGHIJKLMNOP", "chatId": "42"}).json()["config"]
    assert cfg["hasBotToken"] and cfg["botToken"] == "" and cfg["chatId"] == "42"  # token is never sent back
    codes = client.post("/api/telegram/activation/generate", headers=admin, json={"durationHours": 24, "count": 2}).json()["codes"]
    ok = client.post("/api/telegram/activation/apply", headers=admin, json={"chatId": "777", "code": codes[0]}).json()
    assert ok["success"]
    assert not client.post("/api/telegram/activation/apply", headers=admin, json={"chatId": "888", "code": codes[0]}).json()["success"]
    assert client.get("/api/telegram/subscribers", headers=admin).json()["subscribers"][0]["active"]


def test_risk_calculator(client):
    r = client.post("/api/risk/calculate", json={"accountBalance": 1000, "riskPercent": 1, "entryPrice": 1.1, "stopLoss": 1.098, "target1": 1.104, "symbol": "EUR/USD"}).json()
    assert r["pipsRisked"] == 20 and r["recommendedLotSize"] == 0.05 and r["riskRewardRatio"] == 2 and r["status"] == "SAFE"
