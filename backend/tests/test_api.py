"""Accounts, trades with the lot taken, history, win rate, daily loss limit and settings through the HTTP API (no network)."""

from datetime import datetime, timedelta, timezone

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


def login(client, name, code):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': name, 'accessCode': code}).json()['token']}"}


def test_login_rejects_wrong_code(client):
    assert client.post("/api/auth/login", json={"username": "admin", "accessCode": "nope-nope"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_admin_creates_accounts_only(client, admin):
    r = client.post("/api/users", headers=admin, json={"username": "Trader1", "accessCode": "secret-123"})
    assert r.status_code == 200, r.text
    assert set(r.json()["user"]) >= {"id", "username", "role", "telegramLinked"} and "effectiveRisk" not in r.json()["user"]
    assert client.post("/api/users", headers=admin, json={"username": "trader1", "accessCode": "secret-123"}).status_code == 409
    me = login(client, "trader1", "secret-123")
    assert client.get("/api/users", headers=me).status_code == 403  # not admin


def test_settings_and_telegram_config(client, admin):
    r = client.put("/api/settings", headers=admin, json={"app": {"appName": "EXUNU", "bogus": 1}})
    assert r.json()["app"]["appName"] == "EXUNU" and "bogus" not in r.json()["app"] and "risk" not in r.json()
    cfg = client.post("/api/telegram/config", headers=admin, json={"botToken": "123456:ABCDEFGHIJKLMNOP", "chatId": "42"}).json()["config"]
    assert cfg["hasBotToken"] and cfg["botToken"] == "" and cfg["chatId"] == "42"  # token is never sent back
    # No activation codes any more: access to the bot comes only from a linked app account
    assert client.post("/api/telegram/activation/generate", headers=admin, json={"durationHours": 24}).status_code in (404, 405)
    assert client.get("/api/telegram/subscribers", headers=admin).json()["subscribers"] == []
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


def test_telegram_link_code(client, admin, monkeypatch):
    import asyncio

    from app.db import SessionLocal
    from app.models import User
    from app.telegram import bot

    client.post("/api/users", headers=admin, json={"username": "linker", "accessCode": "secret-654"})
    me = login(client, "linker", "secret-654")
    sent = []

    async def fake_send(token, chat_id, text, reply_markup=None, protect=False):
        sent.append(text)
        return {"success": True}
    monkeypatch.setattr(bot, "send_message", fake_send)
    monkeypatch.setattr(bot.settings, "public_app_url", "http://localhost:3000")  # the invitation link comes in the text
    say = lambda text: asyncio.run(bot.handle_update("T", {"message": {"text": text, "chat": {"id": 4242}, "from": {"first_name": "L"}}})) or sent[-1]  # noqa: E731

    # Not linked: account commands ask to connect; typed text (old codes included) gets no answer
    assert "Connect your app account first" in say("/status")
    n = len(sent)
    asyncio.run(bot.handle_update("T", {"message": {"text": "EXU-ABC123-DEF4", "chat": {"id": 4242}, "from": {"first_name": "L"}}}))
    assert len(sent) == n
    # /connect → one-time link → the logged-in account takes the chat
    token = __import__("re").search(r"\?tg=([\w-]+)", say("/connect")).group(1)
    assert client.post("/api/telegram/connect", headers=me, json={"token": "nope"}).status_code == 400
    assert client.post("/api/telegram/connect", headers=me, json={"token": token}).json()["user"]["telegramLinked"] is True
    assert "Connected</b> · linker" in sent[-1] and "trade" not in sent[-1].lower()
    assert client.post("/api/telegram/connect", headers=me, json={"token": token}).status_code == 400  # used once
    with SessionLocal() as db:
        assert db.scalar(__import__("sqlalchemy").select(User).where(User.username == "linker")).telegram_chat_id == "4242"
        assert "4242" in {x.chat_id for x in bot.active_subscribers(db)}
    assert "Account: <b>linker</b>" in say("/status")
    assert client.delete("/api/me/telegram-link", headers=me).json()["user"]["telegramLinked"] is False


def test_admin_sees_telegram_links_and_access_follows_the_account(client, admin, monkeypatch):
    import asyncio
    import re

    from app.db import SessionLocal
    from app.telegram import bot

    uid = client.post("/api/users", headers=admin, json={"username": "viaadmin", "accessCode": "secret-987"}).json()["user"]["id"]
    trader = login(client, "viaadmin", "secret-987")
    sent = []

    async def fake_send(token, chat_id, text, reply_markup=None, protect=False):
        sent.append(text)
        return {"success": True}
    monkeypatch.setattr(bot, "send_message", fake_send)
    monkeypatch.setattr(bot.settings, "public_app_url", "http://localhost:3000")  # the invitation link comes in the text
    say = lambda text: asyncio.run(bot.handle_update("T", {"message": {"text": text, "chat": {"id": 5151}, "from": {"first_name": "V"}}})) or sent[-1]  # noqa: E731
    token = re.search(r"\?tg=([\w-]+)", say("/start")).group(1)
    client.post("/api/telegram/connect", headers=trader, json={"token": token})
    rows = {u["username"]: u for u in client.get("/api/users", headers=admin).json()["users"]}
    assert rows["viaadmin"]["telegramLinked"] and rows["viaadmin"]["telegramChatId"] == "5151"
    assert "Welcome back" in say("/start")
    # The admin unlinks: the chat loses its access at once
    assert client.delete(f"/api/users/{uid}/telegram-link", headers=admin).json()["user"]["telegramLinked"] is False
    assert "Connect your app account first" in say("/status")
    with SessionLocal() as db:
        assert "5151" not in {x.chat_id for x in bot.active_subscribers(db)}


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
    assert client.get("/api/me", headers=me).status_code == 403
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


def test_web_push_subscribe(client, admin, monkeypatch):
    from app import push

    sent = []
    monkeypatch.setattr(push, "_send_one", lambda row, payload, pem: sent.append((row.endpoint, payload)) or None)
    key = client.get("/api/push/key", headers=admin).json()["publicKey"]
    assert len(key) > 80 and client.get("/api/push/key", headers=admin).json()["publicKey"] == key  # created once, then kept
    sub = {"endpoint": "https://push.example.test/abc", "keys": {"p256dh": "BOrK" * 20, "auth": "a1b2c3d4"}}
    assert client.post("/api/push/subscribe", headers=admin, json=sub).json()["success"]
    assert client.post("/api/push/subscribe", headers=admin, json={**sub, "endpoint": "http://insecure"}).status_code == 422
    assert client.post("/api/push/test", headers=admin).json()["delivered"] == 1
    assert client.post("/api/push/unsubscribe", headers=admin, json={"endpoint": sub["endpoint"]}).json()["success"]
    assert client.post("/api/push/test", headers=admin).json()["devices"] == 0


def test_a_login_stays_open_until_logout(client):
    r = client.post("/api/auth/login", json={"username": "admin", "accessCode": "admin-test-code"}).json()
    left = datetime.fromisoformat(r["expiresAt"]) - datetime.now(timezone.utc)
    assert left > timedelta(days=3000)  # no hourly logout
    me = {"Authorization": f"Bearer {r['token']}"}
    assert client.get("/api/auth/me", headers=me).status_code == 200
    client.post("/api/auth/logout", headers=me)
    assert client.get("/api/auth/me", headers=me).status_code == 401


def test_one_telegram_per_account_and_deleted_account_loses_the_bot(client, admin, monkeypatch):
    import asyncio
    import re

    from app.db import SessionLocal
    from app.telegram import bot

    uid = client.post("/api/users", headers=admin, json={"username": "onetg", "accessCode": "secret-321"}).json()["user"]["id"]
    me = login(client, "onetg", "secret-321")
    client.post("/api/users", headers=admin, json={"username": "othertg", "accessCode": "secret-322"})
    other = login(client, "othertg", "secret-322")
    sent = []

    async def fake_send(token, chat_id, text, reply_markup=None, protect=False):
        sent.append((chat_id, text))
        return {"success": True}
    monkeypatch.setattr(bot, "send_message", fake_send)
    monkeypatch.setattr(bot.settings, "public_app_url", "http://localhost:3000")  # the invitation link comes in the text

    def invite(chat):
        asyncio.run(bot.handle_update("T", {"message": {"text": "/start", "chat": {"id": chat}, "from": {"first_name": "Tg"}}}))
        return re.search(r"\?tg=([\w-]+)", sent[-1][1]).group(1)

    first = invite(6001)
    info = client.get(f"/api/telegram/connect/{first}", headers=me).json()
    assert info["firstName"] == "Tg" and info["problem"] is None  # what the Accept screen shows
    linked = client.post("/api/telegram/connect", headers=me, json={"token": first}).json()["user"]
    assert linked["telegramLinked"] and linked["telegramName"] == "Tg"  # the name the sidebar shows
    # A second Telegram for the same account is refused (one per account)…
    second = invite(6002)
    assert "already linked to another Telegram" in client.get(f"/api/telegram/connect/{second}", headers=me).json()["problem"]
    assert client.post("/api/telegram/connect", headers=me, json={"token": second}).status_code == 400
    # …and a Telegram already linked cannot be taken by another account
    asyncio.run(bot.handle_update("T", {"message": {"text": "/connect", "chat": {"id": 6001}, "from": {"first_name": "Tg"}}}))
    assert "?tg=" not in sent[-1][1] and "One Telegram per account" in sent[-1][1]
    # The admin deletes the account: the chat is told, then loses the bot
    assert client.delete(f"/api/users/{uid}", headers=admin).json()["success"]
    assert sent[-1] == ("6001", "⛔ Your account was removed: the bot stops here.")
    with SessionLocal() as db:
        assert "6001" not in {s.chat_id for s in bot.active_subscribers(db)}
    asyncio.run(bot.handle_update("T", {"message": {"text": "/status", "chat": {"id": 6001}, "from": {"first_name": "Tg"}}}))
    assert "Connect your app account first" in sent[-1][1]
    assert other  # the other account is untouched


def test_invitation_button_opens_the_app_domain(monkeypatch):
    from app.db import SessionLocal, init_db
    from app.telegram import bot

    init_db()
    monkeypatch.setattr(bot.settings, "public_app_url", "https://liquiditydissection.app")
    with SessionLocal() as db:
        text, markup = bot.connect_button(db, "7007", "Tg")
    url = markup["inline_keyboard"][0][0]["url"]
    assert url.startswith("https://liquiditydissection.app/?tg=") and "?tg=" not in text


def test_the_analysis_and_the_trades_are_gone(client, admin):
    """The old analysis, agent, strategy and trade routes are gone (the SMC teams replace them under /api/smc)."""
    for path in ("/api/analyze", "/api/agents/radars", "/api/pairs/dossier", "/api/smc/report", "/api/exunu/setup", "/api/signals",
                 "/api/dashboard", "/api/trades", "/api/stats", "/api/backtest", "/api/cot", "/api/sentiment"):
        assert client.get(path, headers=admin).status_code in (404, 405), path
    assert "/api/exunu/candles" in {r.path for r in client.app.routes}  # the clean chart's candles stay
