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
    assert set(r.json()["user"]) >= {"id", "username", "role", "dailyLossLimit", "capital", "riskPct", "effectiveRisk", "telegramLinked"}
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


def test_admin_code_change_is_final(client, admin):
    """The starting admin code stops working once the admin sets a new one."""
    from app.config import settings

    client.post("/api/users", headers=admin, json={"username": "boss", "accessCode": "first-code-1", "role": "admin"})
    me = login(client, "boss", "first-code-1")
    assert client.put("/api/me", headers=me, json={"accessCode": "second-code-2"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "boss", "accessCode": "first-code-1"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "boss", "accessCode": "second-code-2"}).status_code == 200
    # The default bootstrap code is not a master key
    assert client.post("/api/auth/login", json={"username": settings.admin_username, "accessCode": "admin1234"}).status_code == 401


def test_risk_in_dollars_gives_the_lot(client, admin):
    client.post("/api/users", headers=admin, json={"username": "risky", "accessCode": "secret-321"})
    me = login(client, "risky", "secret-321")
    assert client.put("/api/me", headers=me, json={"riskUsd": 80}).json()["user"]["riskUsd"] == 80
    lot = client.get("/api/lot?symbol=XAU/USD&entry=4000&sl=3995", headers=me).json()
    assert lot["lots"] == 0.15 and lot["actualRisk"] == 79.5  # ($5 + $0.30 costs) × 100 oz = $530 per lot → 0.15
    assert client.put("/api/me", headers=me, json={"riskUsd": 0}).json()["user"]["riskUsd"] is None


def test_profit_and_loss_days():
    from app.trading import trade_days

    def t(pnl, day, hour=12):
        return Trade(symbol="EUR/USD", direction="BUY", entry=1, sl=0.99, lots=0.1, status="CLOSED", pnl=pnl,
                     closed_at=datetime(2026, 10, day, hour, 0, tzinfo=timezone.utc))
    # Mon +50 and -20 (= +30), Tue -40, Wed +10 and +15 (= +25): 2 profit days, 1 loss day, streak +1
    rows = [t(50, 19), t(-20, 19), t(-40, 20), t(10, 21), t(15, 21)]
    d = trade_days(rows, now=datetime(2026, 10, 21, 15, tzinfo=timezone.utc))
    assert [x["value"] for x in d["days"]] == [30, -40, 25] and (d["profitDays"], d["lossDays"], d["streak"]) == (2, 1, 1)
    assert d["bestDay"]["day"] == "2026-10-19" and d["worstDay"]["value"] == -40 and d["dayWinRate"] == 66.7
    assert (d["today"], d["week"], d["month"]) == (25, 15, 15) and d["avgProfitDay"] == 27.5
    # A close after 17:00 New York (21:00 UTC in October) belongs to the next trading day
    assert trade_days([t(5, 21, 22)], now=datetime(2026, 10, 21, 23, tzinfo=timezone.utc))["days"][0]["day"] == "2026-10-22"


def test_telegram_link_code_and_capital_risk(client, admin, monkeypatch):
    import asyncio

    from app.db import SessionLocal
    from app.models import Subscriber, User
    from app.telegram import bot
    from app.trading import effective_risk

    assert effective_risk(None, 5000, 1) == 50 and effective_risk(80, 5000, 1) == 80 and effective_risk(None, 0, 1) is None

    client.post("/api/users", headers=admin, json={"username": "linker", "accessCode": "secret-654"})
    me = login(client, "linker", "secret-654")
    # Capital + risk in % → effective risk $50 → lot from the signal's stop
    u = client.put("/api/me", headers=me, json={"capital": 5000, "riskPct": 1}).json()["user"]
    assert (u["capital"], u["riskPct"], u["effectiveRisk"], u["riskUsd"]) == (5000, 1, 50, None)
    assert client.get("/api/lot?symbol=XAU/USD&entry=4000&sl=3995", headers=me).json()["lots"] == 0.09  # $50 / ($5.30 × 100 oz)

    code = client.post("/api/me/telegram-link", headers=me).json()["code"]
    assert code.startswith("LD-") and len(code) == 9

    sent = []

    async def fake_send(token, chat_id, text, reply_markup=None, protect=False):
        sent.append(text)
        return {"success": True}
    monkeypatch.setattr(bot, "send_message", fake_send)
    say = lambda text: asyncio.run(bot.handle_update("T", {"message": {"text": text, "chat": {"id": 4242}, "from": {"first_name": "L"}}})) or sent[-1]  # noqa: E731

    assert "invalid or expired" in say("LD-ZZZZZZ")
    assert "Linked to <b>linker</b>" in say(f"/start {code.replace('-', '')}") and "$50 per trade (1% of $5000)" in sent[-1]
    assert "invalid or expired" in say(code)  # one-time code
    with SessionLocal() as db:
        assert db.scalar(__import__("sqlalchemy").select(User).where(User.username == "linker")).telegram_chat_id == "4242"
        assert bot.chat_risks(db, ["4242"]) == {"4242": 50} and db.get(Subscriber, "4242").expires_at is not None
    # The bot's /capital and /risk change the app account too
    assert "$6000" in say("/capital 6000") and "$60" in sent[-1]
    assert "$80" in say("/risk 80")
    assert client.get("/api/me", headers=me).json()["user"]["effectiveRisk"] == 80
    assert "$120" in say("/risk 2%")  # 2% of $6000
    assert client.get("/api/me", headers=me).json()["user"]["effectiveRisk"] == 120
    assert client.delete("/api/me/telegram-link", headers=me).json()["user"]["telegramLinked"] is False


def test_admin_makes_the_telegram_code_for_a_user(client, admin, monkeypatch):
    import asyncio

    from app.telegram import bot

    uid = client.post("/api/users", headers=admin, json={"username": "viaadmin", "accessCode": "secret-987"}).json()["user"]["id"]
    trader = login(client, "viaadmin", "secret-987")
    assert client.post(f"/api/users/{uid}/telegram-link", headers=trader).status_code == 403  # admin only
    out = client.post(f"/api/users/{uid}/telegram-link", headers=admin).json()
    assert out["code"].startswith("LD-") and out["expiresAt"] - __import__("time").time() > 23 * 3600  # valid 24 h

    async def fake_send(token, chat_id, text, reply_markup=None, protect=False):
        return {"success": True}
    monkeypatch.setattr(bot, "send_message", fake_send)
    asyncio.run(bot.handle_update("T", {"message": {"text": out["code"], "chat": {"id": 5151}, "from": {"first_name": "V"}}}))
    rows = {u["username"]: u for u in client.get("/api/users", headers=admin).json()["users"]}
    assert rows["viaadmin"]["telegramLinked"] and rows["viaadmin"]["telegramChatId"] == "5151"
    assert client.delete(f"/api/users/{uid}/telegram-link", headers=admin).json()["user"]["telegramLinked"] is False


def test_sign_up_waits_for_admin_approval(client, admin):
    good = {"firstName": "Salma", "lastName": "El Amrani", "username": "Salma.Trader", "password": "Gold!Rush2026x"}
    # Weak passwords are refused with what they miss
    weak = client.post("/api/auth/register", json={**good, "password": "short1"})
    assert weak.status_code == 400 and "10 characters" in weak.text and "uppercase" in weak.text and "symbol" in weak.text
    assert client.post("/api/auth/register", json={**good, "password": "Salma.trader!99X"}).status_code == 400  # contains the username
    assert client.get("/api/auth/password-check", params={"password": good["password"]}).json()["missing"] == []
    assert client.post("/api/auth/register", json={**good, "firstName": "S4lma"}).status_code == 400
    # A pending account logs in but only sees who it is, nothing else
    r = client.post("/api/auth/register", json=good)
    assert r.status_code == 200, r.text
    me = {"Authorization": f"Bearer {r.json()['token']}"}
    u = client.get("/api/auth/me", headers=me).json()["user"]
    assert (u["status"], u["username"], u["firstName"], u["lastName"]) == ("pending", "salma.trader", "Salma", "El Amrani")
    assert client.get("/api/me", headers=me).status_code == 403 and client.get("/api/dashboard", headers=me).status_code == 403
    assert client.post("/api/auth/register", json=good).status_code == 409
    # The admin sees it waiting, approves it: the whole app opens
    listed = next(x for x in client.get("/api/users", headers=admin).json()["users"] if x["username"] == "salma.trader")
    assert listed["status"] == "pending"
    assert client.post(f"/api/users/{listed['id']}/approve", headers=me).status_code == 403
    assert client.post(f"/api/users/{listed['id']}/approve", headers=admin).json()["user"]["status"] == "approved"
    assert client.get("/api/me", headers=me).status_code == 200
    # A refused sign-up is deleted: that login no longer works
    r2 = client.post("/api/auth/register", json={**good, "username": "spam.bot", "firstName": "Spam"})
    sid = r2.json()["user"]["id"]
    assert client.delete(f"/api/users/{sid}", headers=admin).json()["success"]
    assert client.post("/api/auth/login", json={"username": "spam.bot", "accessCode": good["password"]}).status_code == 401


def test_web_push_subscribe_and_one_push_per_trade(client, admin, monkeypatch):
    import asyncio

    from app import push

    sent = []
    monkeypatch.setattr(push, "_send_one", lambda row, payload, pem: sent.append((row.endpoint, payload)) or None)
    key = client.get("/api/push/key", headers=admin).json()["publicKey"]
    assert len(key) > 80 and client.get("/api/push/key", headers=admin).json()["publicKey"] == key  # created once, then kept
    sub = {"endpoint": "https://push.example.test/abc", "keys": {"p256dh": "BOrK" * 20, "auth": "a1b2c3d4"}}
    assert client.post("/api/push/subscribe", headers=admin, json=sub).json()["success"]
    assert client.post("/api/push/subscribe", headers=admin, json={**sub, "endpoint": "http://insecure"}).status_code == 422
    assert client.post("/api/push/test", headers=admin).json()["delivered"] == 1
    signal = {"id": "XAUUSD-BO-1", "symbol": "XAU/USD", "signalType": "BUY", "entryPrice": 4000, "stopLoss": 3990, "target3": 4020, "confidence": 80}
    assert asyncio.run(push.notify_trade(signal)) == 1 and asyncio.run(push.notify_trade(signal)) == 0  # pushed once only
    assert "BUY XAU/USD" in sent[-1][1] and "TP 4020" in sent[-1][1]
    assert client.post("/api/push/unsubscribe", headers=admin, json={"endpoint": sub["endpoint"]}).json()["success"]
    assert client.post("/api/push/test", headers=admin).json()["devices"] == 0
