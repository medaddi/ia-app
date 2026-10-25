"""Accounts, trades with the lot taken, history, win rate, daily loss limit and settings through the HTTP API (no network)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Trade
from app.trading import today_status


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "accessCode": "admin-test-code"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def login(client, name, code):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': name, 'accessCode': code}).json()['token']}"}


def test_login_rejects_wrong_code(client):
    assert client.post("/api/auth/login", json={"username": "admin", "accessCode": "nope-nope"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_admin_creates_accounts_only(client, admin):
    r = client.post("/api/users", headers=admin, json={"username": "Trader1", "accessCode": "secret-123"})
    assert r.status_code == 200, r.text
    assert set(r.json()["user"]) >= {"id", "username", "role", "dailyLossLimit"} and "capital" not in r.json()["user"]
    assert client.post("/api/users", headers=admin, json={"username": "trader1", "accessCode": "secret-123"}).status_code == 409
    me = login(client, "trader1", "secret-123")
    assert client.get("/api/users", headers=me).status_code == 403  # not admin


def test_trades_use_the_lot_taken(client, admin):
    client.post("/api/users", headers=admin, json={"username": "lots", "accessCode": "secret-456"})
    me = login(client, "lots", "secret-456")
    base = {"symbol": "XAUUSD", "direction": "BUY", "entry": 4000, "sl": 3995, "tp2": 4010}
    assert client.post("/api/trades", headers=me, json=base).status_code == 422  # the lot is required

    t1 = client.post("/api/trades", headers=me, json={**base, "lots": 0.1}).json()["trade"]
    assert t1["lots"] == 0.1 and t1["riskAmount"] == 50
    assert client.post("/api/trades", headers=me, json={**base, "sl": 4005, "lots": 0.1}).status_code == 400

    # Gold: $10 move × 0.10 lot × 100 oz = $100
    win = client.post(f"/api/trades/{t1['id']}/close", headers=me, json={"exitPrice": 4010}).json()["trade"]
    assert win["result"] == "WIN" and win["pnl"] == 100 and win["rMultiple"] == 2
    # EURUSD: 10 pips × 0.5 lot × 100 000 = $50
    t2 = client.post("/api/trades", headers=me, json={"symbol": "EUR/USD", "direction": "SELL", "entry": 1.1, "sl": 1.101, "lots": 0.5}).json()["trade"]
    loss = client.post(f"/api/trades/{t2['id']}/close", headers=me, json={"exitPrice": 1.101}).json()["trade"]
    assert loss["result"] == "LOSS" and loss["pnl"] == -50
    client.post("/api/trades", headers=me, json={"symbol": "XAUUSD", "direction": "SELL", "entry": 4000, "sl": 4004, "lots": 0.2})

    s = client.get("/api/stats", headers=me).json()
    assert (s["total"], s["open"], s["closed"], s["wins"], s["losses"]) == (3, 1, 2, 1, 1)
    assert s["winRate"] == 50 and s["totalPnl"] == 50 and s["totalLots"] == 0.8 and s["profitFactor"] == 2
    assert [p["pnl"] for p in s["pnlCurve"]] == [100, 50] and s["maxDrawdown"] == 50
    assert "currentCapital" not in s and s["today"]["pnl"] == 50

    assert client.get("/api/trades?status=closed", headers=me).json()["count"] == 2
    listed = {u["username"]: u for u in client.get("/api/users", headers=admin).json()["users"]}
    assert listed["lots"]["stats"]["winRate"] == 50
    detail = client.get(f"/api/users/{listed['lots']['id']}", headers=admin).json()
    assert len(detail["trades"]) == 3 and detail["stats"]["totalPnl"] == 50
    assert client.get("/api/users/stats").json()["stats"]["total"] >= 3  # route not shadowed by /users/{id}


def test_daily_loss_limit_blocks_new_trades(client, admin):
    client.post("/api/users", headers=admin, json={"username": "dl", "accessCode": "secret-789"})
    me = login(client, "dl", "secret-789")
    assert client.put("/api/me", headers=me, json={"dailyLossLimit": 60}).json()["user"]["dailyLossLimit"] == 60
    trade = {"symbol": "XAUUSD", "direction": "BUY", "entry": 4000, "sl": 3995, "lots": 0.1}
    for _ in range(2):  # two $50 losses = -$100 ≤ -$60
        t = client.post("/api/trades", headers=me, json=trade).json()["trade"]
        client.post(f"/api/trades/{t['id']}/close", headers=me, json={"exitPrice": 3995})
    today = client.get("/api/stats", headers=me).json()["today"]
    assert today["pnl"] == -100 and today["reached"] and today["remaining"] == -40
    r = client.post("/api/trades", headers=me, json=trade)
    assert r.status_code == 403 and "Daily loss limit" in r.json()["error"]
    # 0 removes the limit
    client.put("/api/me", headers=me, json={"dailyLossLimit": 0})
    assert client.post("/api/trades", headers=me, json=trade).status_code == 200


def test_daily_loss_resets_on_the_next_trading_day():
    closed = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
    t = Trade(symbol="XAU/USD", direction="BUY", entry=4000, sl=3995, lots=0.1, status="CLOSED", pnl=-100, closed_at=closed)
    assert today_status([t], 50, now=closed + timedelta(hours=1))["reached"]
    # 17:00 New York (21:00 UTC on this date) starts a new trading day
    assert not today_status([t], 50, now=closed + timedelta(hours=8))["reached"]


def test_settings_and_telegram_config(client, admin):
    r = client.put("/api/settings", headers=admin, json={"app": {"appName": "EXUNU", "bogus": 1}})
    assert r.json()["app"]["appName"] == "EXUNU" and "bogus" not in r.json()["app"] and "risk" not in r.json()
    cfg = client.post("/api/telegram/config", headers=admin, json={"botToken": "123456:ABCDEFGHIJKLMNOP", "chatId": "42"}).json()["config"]
    assert cfg["hasBotToken"] and cfg["botToken"] == "" and cfg["chatId"] == "42"  # token is never sent back
    codes = client.post("/api/telegram/activation/generate", headers=admin, json={"durationHours": 24, "count": 2}).json()["codes"]
    assert client.post("/api/telegram/activation/apply", headers=admin, json={"chatId": "777", "code": codes[0]}).json()["success"]
    assert not client.post("/api/telegram/activation/apply", headers=admin, json={"chatId": "888", "code": codes[0]}).json()["success"]
    assert client.get("/api/telegram/subscribers", headers=admin).json()["subscribers"][0]["active"]
    assert client.post("/api/risk/calculate", json={}).status_code == 404  # removed
