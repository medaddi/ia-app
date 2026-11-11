"""The owner's prompt of 2026-11-11 "risk USD par utilisateur, calcul du lot, copie Telegram": a private USD risk per user,
the lot from the pair's contract data, the fixed stop, per-user per-signal snapshots, the copy payload and its import,
and the isolation between users. No network: conversion prices are injected."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.smc import desk, notify, signal_copy, sizing

USD = {"rate": 1.0, "pair": None, "source": "USD-quoted"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def users(client):
    r = client.post("/api/auth/login", json={"username": "admin", "accessCode": "admin-test-code"})
    admin = {"Authorization": f"Bearer {r.json()['token']}"}
    out = {"admin": admin}
    for name in ("alice", "bob"):
        client.post("/api/users", headers=admin, json={"username": name, "accessCode": f"{name}-code-123"})
        tok = client.post("/api/auth/login", json={"username": name, "accessCode": f"{name}-code-123"}).json()["token"]
        out[name] = {"Authorization": f"Bearer {tok}"}
    return out


@pytest.fixture(autouse=True)
def _rates(monkeypatch):
    """Live conversion prices, fixed for the test (EUR/USD 1.10, GBP/USD 1.25, USD/JPY 150)."""
    rates = {"EUR/USD": 1.10, "GBP/USD": 1.25, "USD/JPY": 150.0, "USD/CHF": 0.90, "USD/CAD": 1.37, "AUD/USD": 0.66, "NZD/USD": 0.60}

    async def fake(sym, fresh=False):
        if sym not in rates:
            return {"price": 0, "source": "unavailable"}
        return {"price": rates[sym], "source": "test feed", "quoteTime": int(time.time()), "isMarketOpen": True}
    monkeypatch.setattr("app.market.data.fetch_live_price", fake)
    return rates


def _signal(sid: str, symbol: str, side: str, entry: float, sl: float, tp: float, t: int, etf: str = "M15", state: str = "OPEN"):
    from app.db import SessionLocal
    from app.models import Signal
    with SessionLocal() as db:
        if db.get(Signal, sid):
            db.delete(db.get(Signal, sid))
            db.commit()
        db.add(Signal(id=sid, symbol=symbol, setup="SF_BR", direction=side, entry_type="MARKET", entry=entry, sl=sl, tp1=tp, tp2=tp, tp3=tp,
                      rr_tp2=2.0, score=80, signal_time=t, state=state, params={}, payload={"etf": etf, "id": sid}))
        db.commit()


def _payload(sid, symbol, side, entry, sl, tp, t, etf="M15"):
    return signal_copy.payload({"id": sid, "direction": side, "entry": entry, "sl": sl, "tp": tp, "time": t, "etf": etf}, symbol)


# ---------------------------------------------------------------- the lot maths
def test_gold_usd_quoted_lot_with_costs_and_step_rounding():
    cfg = desk.BY_SYMBOL["XAU/USD"]
    # $10 stop (100 pips of $0.10) on 100 oz: $1,000 per lot + costs (2.5 + 0.5 pips) x $0.10 x 100 = $30 -> $1,030 per lot
    z = sizing.compute(cfg, 2350.40, 2340.40, 250.0, USD)
    assert z["status"] == "ok" and z["meta"]["riskPerLotUsd"] == 1030.0 and z["meta"]["costsPerLotUsd"] == 30.0
    assert z["lots"] == 0.24 and z["estLossUsd"] == round(0.24 * 1030, 2) <= 250  # 0.2427 -> rounded DOWN to 0.24
    assert sizing.compute(cfg, 2350.40, 2340.40, 5.0, USD)["status"] == "unavailable"  # 0.0049 lot: under 0.01, never rounded up
    assert "minimum lot" in sizing.compute(cfg, 2350.40, 2340.40, 5.0, USD)["reason"]


def test_usd_quoted_and_cross_pairs_convert_the_quote_currency():
    eu = sizing.compute(desk.BY_SYMBOL["EUR/USD"], 1.10000, 1.09800, 100.0, USD)  # 20 pips
    per = 0.002 * 100000 + (desk.BY_SYMBOL["EUR/USD"]["spread_pips"] + desk.BY_SYMBOL["EUR/USD"]["slippage_pips"]) * 0.0001 * 100000
    assert abs(eu["meta"]["riskPerLotUsd"] - per) < 1e-6 and eu["lots"] == int(100 / per * 100) / 100
    conv = asyncio.run(sizing.conversion("EUR/GBP"))
    assert conv["pair"] == "GBP/USD" and conv["rate"] == 1.25  # GBP-quoted: x GBP/USD
    eg = sizing.compute(desk.BY_SYMBOL["EUR/GBP"], 0.85000, 0.84800, 100.0, conv)
    cfg = desk.BY_SYMBOL["EUR/GBP"]
    per = 0.002 * 100000 * 1.25 + (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"] * 100000 * 1.25 + cfg["commission_usd_per_lot"]
    assert abs(eg["meta"]["riskPerLotUsd"] - round(per, 4)) < 1e-6 and eg["lots"] * per <= 100
    conv = asyncio.run(sizing.conversion("GBP/JPY"))
    assert conv["pair"] == "USD/JPY" and abs(conv["rate"] - 1 / 150) < 1e-12  # JPY-quoted: / USD/JPY
    gj = sizing.compute(desk.BY_SYMBOL["GBP/JPY"], 190.000, 189.500, 100.0, conv)  # 50 pips
    assert gj["status"] == "ok" and gj["estLossUsd"] <= 100 and abs(gj["meta"]["riskPerLotUsd"] - (0.5 * 100000 / 150 + gj["meta"]["costsPerLotUsd"])) < 1e-3
    for pair in desk.PAIRS:  # every pair of the app has the contract data and a conversion path
        assert all(desk.BY_SYMBOL[pair].get(k) is not None for k in sizing.NEEDED), pair
        assert "error" not in asyncio.run(sizing.conversion(pair)), pair


def test_missing_or_stale_data_means_size_unavailable(monkeypatch):
    cfg = {**desk.BY_SYMBOL["EUR/USD"]}
    cfg.pop("lot_step")
    assert "lot_step" in sizing.compute(cfg, 1.1, 1.098, 100.0, USD)["reason"]
    assert sizing.compute(desk.BY_SYMBOL["EUR/USD"], 1.1, 1.098, None, USD)["status"] == "unavailable"  # no risk set: no invented default

    async def old(sym, fresh=False):
        return {"price": 1.25, "source": "test feed", "quoteTime": int(time.time()) - 3600, "isMarketOpen": True}
    monkeypatch.setattr("app.market.data.fetch_live_price", old)
    c = asyncio.run(sizing.conversion("EUR/GBP"))
    assert "error" in c and "min old" in c["error"]
    assert sizing.compute(desk.BY_SYMBOL["EUR/GBP"], 0.85, 0.848, 100.0, c)["status"] == "unavailable"

    async def last_known(sym, fresh=False):
        return {"price": 1.25, "source": "Interbank Forex GBPUSD=X (last known)", "quoteTime": int(time.time()), "isMarketOpen": True}
    monkeypatch.setattr("app.market.data.fetch_live_price", last_known)
    assert "not live" in asyncio.run(sizing.conversion("EUR/GBP"))["error"]
    assert sizing.valid_risk("abc") is None and sizing.valid_risk(-5) is None and sizing.valid_risk(float("inf")) is None and sizing.valid_risk(0) is None


# ---------------------------------------------------------------- the private setting, the snapshots, the isolation
def test_the_risk_setting_is_private_and_per_user(client, users):
    assert client.get("/api/me/risk", headers=users["alice"]).json() == {"riskUsd": None}
    assert client.put("/api/me/risk", headers=users["alice"], json={"riskUsd": -3}).status_code == 422
    assert client.put("/api/me/risk", headers=users["alice"], json={"riskUsd": 250}).json()["riskUsd"] == 250
    assert client.put("/api/me/risk", headers=users["bob"], json={"riskUsd": 40}).json()["riskUsd"] == 40
    assert client.get("/api/me/risk", headers=users["alice"]).json()["riskUsd"] == 250 and client.get("/api/me/risk", headers=users["bob"]).json()["riskUsd"] == 40
    listing = client.get("/api/users", headers=users["admin"]).json()["users"]
    assert all("riskUsd" not in u and "risk_usd" not in u for u in listing)  # not even the admin list shows a user's risk
    assert client.get("/api/me/risk").status_code == 401


def test_each_user_gets_their_own_saved_size_and_the_stop_never_moves(client, users):
    t = int(time.time()) - 600
    sid = f"SMC-XAUUSD-SF_BR-{t}-S"
    _signal(sid, "XAU/USD", "SELL", 2350.40, 2360.40, 2330.30, t)
    a = client.get(f"/api/me/sizing/{sid}", headers=users["alice"]).json()
    b = client.get(f"/api/me/sizing/{sid}", headers=users["bob"]).json()
    assert a["status"] == b["status"] == "ok" and a["riskUsd"] == 250 and b["riskUsd"] == 40
    assert a["lots"] == 0.24 and b["lots"] == 0.03 and a["sl"] == b["sl"] == 2360.40  # same market levels, each user's own lot
    client.put("/api/me/risk", headers=users["alice"], json={"riskUsd": 1000})  # a later change: future signals only
    again = client.get(f"/api/me/sizing/{sid}", headers=users["alice"]).json()
    assert again["lots"] == 0.24 and again["riskUsd"] == 250 and again["createdAt"] == a["createdAt"]
    mine = client.get("/api/me/sizings", headers=users["bob"]).json()["items"]
    assert [x["signalId"] for x in mine] == [sid] and mine[0]["riskUsd"] == 40  # bob sees his row only
    from app.db import SessionLocal
    from app.models import Signal
    with SessionLocal() as db:
        assert db.get(Signal, sid).sl == 2360.40
    client.put("/api/me/risk", headers=users["alice"], json={"riskUsd": 250})


def test_a_setup_not_sent_has_no_size(client, users):
    z = client.get("/api/me/sizing/SMC-EURUSD-SF_BR-1-B", headers=users["alice"]).json()
    assert z["status"] == "unavailable" and "not been sent" in z["reason"]


# ---------------------------------------------------------------- the copy payload and the import
def test_payload_round_trip_and_strict_parsing():
    t = 1794400200
    sid = f"SMC-XAUUSD-SF_BR-{t}-S"
    p = _payload(sid, "XAU/USD", "SELL", 2350.4, 2357.1, 2330.3, t)
    assert p == f"LD|v=1|id={sid}|symbol=XAUUSD|side=SELL|entry=2350.40|sl=2357.10|tp=2330.30|tf=M15|time=" + signal_copy.iso_min(t)
    f, errs = signal_copy.parse("🎯 XAU/USD — SELL\n" + p + "\nResearch signal")  # a whole pasted message is fine
    assert not errs and f == {"id": sid, "symbol": "XAU/USD", "side": "SELL", "entry": 2350.4, "sl": 2357.1, "tp": 2330.3, "tf": "M15", "time": t}
    bad = {
        "": "nothing pasted", "hello": "no setup data", p + "\n" + p: "more than one",
        p.replace("|tf=M15", ""): "missing tf", p + "|lot=0.5": "unexpected lot", p.replace("side=SELL", "side=HOLD"): "unknown side",
        p.replace("symbol=XAUUSD", "symbol=XAGUSD"): "unknown symbol", p.replace("sl=2357.10", "sl=2340.10"): "a SELL needs",
        p.replace("entry=2350.40", "entry=abc"): "not a price", p.replace("time=" + signal_copy.iso_min(t), "time=11:30Z"): "not YYYY",
        p.replace("side=SELL", "side=BUY"): "does not match", p.replace("entry=2350.40", "entry=2350.4012"): "more decimals",
        p.replace("|v=1|", "|v=2|"): "unknown version",
    }
    for text, why in bad.items():
        f, errs = signal_copy.parse(text)
        assert f is None and any(why in e for e in errs), (text[:40], errs)


def test_import_checks_the_app_signal_and_sizes_for_the_signed_in_user(client, users):
    t = int(time.time()) - 900
    sid = f"SMC-EURGBP-SF_BR-{t}-B"
    _signal(sid, "EUR/GBP", "BUY", 0.85000, 0.84800, 0.85600, t, etf="H1")
    p = _payload(sid, "EUR/GBP", "BUY", 0.85000, 0.84800, 0.85600, t, etf="H1")
    pre = client.post("/api/me/import/preview", headers=users["bob"], json={"text": p}).json()
    assert pre["success"] and pre["sizing"]["riskUsd"] == 40 and not pre["sizing"]["saved"]
    assert client.get("/api/me/sizings", headers=users["bob"]).json()["items"][0]["signalId"] != sid  # a preview saves nothing
    pasted = p + "\n👤 Your size: 5.00 lot for your $9999 risk"  # someone else's lot in the paste is never read
    imp = client.post("/api/me/import", headers=users["bob"], json={"text": pasted}).json()
    cfg = desk.BY_SYMBOL["EUR/GBP"]
    per = 0.002 * 100000 * 1.25 + (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"] * 100000 * 1.25
    assert imp["success"] and imp["sizing"]["source"] == "import" and imp["sizing"]["riskUsd"] == 40 and imp["sizing"]["lots"] == int(40 / per * 100) / 100
    other = client.post("/api/me/import", headers=users["alice"], json={"text": p}).json()
    assert other["sizing"]["riskUsd"] == 250 and other["sizing"]["lots"] > imp["sizing"]["lots"]  # alice: her own risk
    # tampered, unknown, stale, ended
    forged = p.replace("sl=0.84800", "sl=0.84700")
    assert any("does not match" in e for e in client.post("/api/me/import", headers=users["bob"], json={"text": forged}).json()["errors"])
    unknown = _payload(f"SMC-EURGBP-SF_BR-{t + 60}-B", "EUR/GBP", "BUY", 0.85000, 0.84800, 0.85600, t + 60, etf="H1")
    assert any("never sent" in e for e in client.post("/api/me/import", headers=users["bob"], json={"text": unknown}).json()["errors"])
    old_t = int(time.time()) - 3 * 86400
    old = f"SMC-EURGBP-SF_BR-{old_t}-B"
    _signal(old, "EUR/GBP", "BUY", 0.85000, 0.84800, 0.85600, old_t, etf="H1")
    r = client.post("/api/me/import", headers=users["bob"], json={"text": _payload(old, "EUR/GBP", "BUY", 0.85, 0.848, 0.856, old_t, "H1")}).json()
    assert not r["success"] and any("stale" in e for e in r["errors"])
    done_t = int(time.time()) - 1200
    done = f"SMC-EURGBP-SF_BR-{done_t}-B"
    _signal(done, "EUR/GBP", "BUY", 0.85000, 0.84800, 0.85600, done_t, etf="H1", state="CLOSED")
    r = client.post("/api/me/import", headers=users["bob"], json={"text": _payload(done, "EUR/GBP", "BUY", 0.85, 0.848, 0.856, done_t, "H1")}).json()
    assert not r["success"] and any("no longer live" in e for e in r["errors"])
    assert client.post("/api/me/import", json={"text": p}).status_code == 401


def test_no_user_can_read_another_users_rows(client, users):
    from app.db import SessionLocal
    from app.models import User, UserSignalSize
    with SessionLocal() as db:
        bob = db.query(User).filter(User.username == "bob").one()
        alice_rows = db.query(UserSignalSize).join(User, User.id == UserSignalSize.user_id).filter(User.username == "alice").all()
        assert alice_rows and all(r.user_id != bob.id for r in alice_rows)
    seen = client.get("/api/me/sizings", headers=users["bob"]).json()["items"]
    assert all(x["riskUsd"] == 40 for x in seen)  # never alice's 250
    # the sizing route takes the user from the session: there is no parameter to ask for someone else's
    from app.api import account
    import inspect
    for fn in (account.my_sizing, account.my_sizings, account.my_risk, account.my_import, account.my_import_preview):
        assert "user_id" not in inspect.signature(fn).parameters


def test_the_shared_telegram_message_carries_no_risk_and_a_private_chat_gets_its_own(client, users, monkeypatch):
    t = int(time.time()) - 300
    sid = f"SMC-XAUUSD-SF_BR-{t}-B"
    _signal(sid, "XAU/USD", "BUY", 2350.40, 2340.40, 2380.40, t)
    from app.db import SessionLocal
    from app.models import Subscriber, User
    from app.store import set_setting
    with SessionLocal() as db:
        db.query(User).filter(User.username == "alice").one().telegram_chat_id = "1001"
        db.query(User).filter(User.username == "bob").one().telegram_chat_id = "1002"
        for chat in ("1001", "1002"):
            if not db.get(Subscriber, chat):
                db.add(Subscriber(chat_id=chat, first_name=chat))
        set_setting(db, "telegram", {"botToken": "123:TEST", "chatId": "-100777", "enabled": True})
        db.commit()
    sent = {}

    async def fake_send(token, chat, text, markup=None, protect=False):
        sent[chat] = (text, markup)
        return {"success": True}
    monkeypatch.setattr("app.telegram.bot.send_message", fake_send)
    s = {"id": sid, "strategy": "SF_BR", "setupType": "SF_BR", "direction": "BUY", "entry": 2350.40, "sl": 2340.40, "tp": 2380.40, "rr": 3.0,
         "time": t, "etf": "M15", "grade": "A"}
    asyncio.run(notify.broadcast("XAU/USD", notify.message(s, "XAU/USD", 2), "t", "b", "x", s))
    group_text = sent["-100777"][0]
    assert "Your size" not in group_text and "$" not in group_text  # the admin group: market data only
    assert "<code>0.24</code> lot for your $250 risk" in sent["1001"][0] and "$40" not in sent["1001"][0]  # alice: hers only
    assert "<code>0.03</code> lot for your $40 risk" in sent["1002"][0] and "$250" not in sent["1002"][0]  # bob: his only
    btn = sent["1001"][1]["inline_keyboard"][0][0]
    assert btn["copy_text"]["text"] == _payload(sid, "XAU/USD", "BUY", 2350.40, 2340.40, 2380.40, t) and "lot" not in btn["copy_text"]["text"]
    with SessionLocal() as db:
        set_setting(db, "telegram", {})
        for u in db.query(User).filter(User.username.in_(["alice", "bob"])):
            u.telegram_chat_id = None
        db.commit()


def test_importing_places_no_order():
    import app.api.account as acc
    src = open(acc.__file__, encoding="utf-8").read() + open(signal_copy.__file__, encoding="utf-8").read() + open(sizing.__file__, encoding="utf-8").read()
    assert not any(w in src for w in ("place_order", "create_order", "submit_order", "/orders", "oanda.order"))
