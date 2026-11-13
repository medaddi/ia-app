"""The owner's prompt of 2026-11-11 "risk USD par utilisateur, calcul du lot, copie Telegram": a private USD risk per user,
the lot from the pair's contract data and the signal's stop, per-user per-signal saved sizes, the private Telegram line,
/risk, and the isolation between users. No network: conversion prices are injected."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.smc import desk, notify, sizing

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


def test_each_user_gets_their_own_saved_size_from_the_signals_stop(client, users):
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
    for fn in (account.my_sizing, account.my_sizings, account.my_risk, account.my_risk_set):
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
    assert "Your lot <code>0.24</code> · risk $250" in sent["1001"][0] and "$40" not in sent["1001"][0]  # alice: hers only
    assert "Your lot <code>0.03</code> · risk $40" in sent["1002"][0] and "$250" not in sent["1002"][0]  # bob: his only
    assert sent["1001"][0].splitlines()[-1] == "<i>Signal only · no order placed</i>" and len(sent["1001"][0].splitlines()) == 4
    with SessionLocal() as db:
        set_setting(db, "telegram", {})
        for u in db.query(User).filter(User.username.in_(["alice", "bob"])):
            u.telegram_chat_id = None
        db.commit()


def test_telegram_risk_command_sets_only_the_linked_users_own_risk(client, users, monkeypatch):
    from app.db import SessionLocal
    from app.models import Subscriber, User
    from app.telegram import bot
    with SessionLocal() as db:
        db.query(User).filter(User.username == "bob").one().telegram_chat_id = "2002"
        if not db.get(Subscriber, "2002"):
            db.add(Subscriber(chat_id="2002", first_name="bob"))
        db.commit()
    replies = []

    async def fake_send(token, chat, text, markup=None, protect=False):
        replies.append((chat, text))
        return {"success": True}
    monkeypatch.setattr(bot, "send_message", fake_send)
    upd = lambda txt: {"message": {"text": txt, "chat": {"id": 2002}, "from": {"first_name": "Bob"}}}  # noqa: E731
    asyncio.run(bot.handle_update("123:TEST", upd("/risk 75")))
    assert "$75" in replies[-1][1]
    assert client.get("/api/me/risk", headers=users["bob"]).json()["riskUsd"] == 75
    assert client.get("/api/me/risk", headers=users["alice"]).json()["riskUsd"] == 250  # alice untouched
    asyncio.run(bot.handle_update("123:TEST", upd("/risk -4")))
    assert "positive amount" in replies[-1][1] and client.get("/api/me/risk", headers=users["bob"]).json()["riskUsd"] == 75
    asyncio.run(bot.handle_update("123:TEST", upd("/risk")))
    assert "$75" in replies[-1][1]
    stranger = {"message": {"text": "/risk 10", "chat": {"id": 3003}, "from": {"first_name": "X"}}}
    asyncio.run(bot.handle_update("123:TEST", stranger))  # a chat no account owns: nothing is set
    assert "Connect your app account first" in replies[-1][1]
    client.put("/api/me/risk", headers=users["bob"], json={"riskUsd": 40})
    with SessionLocal() as db:
        db.query(User).filter(User.username == "bob").one().telegram_chat_id = None
        db.commit()


def test_a_slow_price_provider_never_holds_a_screen(monkeypatch):
    monkeypatch.undo()  # the real fetch_live_price (the module's fixture swaps in a fake one)
    from app.market import data
    calls = []

    async def slow_now(sym):
        calls.append(sym)
        await asyncio.sleep(0.3)
        return {"price": 2.0, "source": "x", "quoteTime": int(time.time())}

    async def run():
        data._price_cache["EUR/USD"] = ({"price": 1.0, "source": "x", "quoteTime": int(time.time())}, time.time() - 5)  # 5 s past its refresh
        monkeypatch.setattr(data, "_fetch_live_price_now", slow_now)
        t0 = time.time()
        p = await data.fetch_live_price("EUR/USD")
        fast = time.time() - t0
        await asyncio.sleep(0.4)  # the background refresh lands
        return p, fast
    p, fast = asyncio.run(run())
    assert p["price"] == 1.0 and fast < 0.05 and calls == ["EUR/USD"]  # served at once, refreshed behind
    data._price_cache["EUR/USD"] = ({"price": 1.0}, time.time() - 120)  # too old: fetched now
    assert asyncio.run(data.fetch_live_price("EUR/USD"))["price"] == 2.0
    data._price_cache.pop("EUR/USD", None)


def test_only_the_signal_is_announced_the_trade_follower_is_silent():
    assert notify.TRADE_UPDATES is False
    assert asyncio.run(notify._quiet("XAU/USD", "text", "t", "b", "tag")) == {"telegram": 0, "push": 0}
    import inspect
    src = inspect.getsource(notify.tick)
    assert "manage_all(broadcast if TRADE_UPDATES else _quiet)" in src and "radar_message" not in src and not hasattr(notify, "radar_message")


def test_three_pairs_find_a_trade_in_the_same_minute_and_all_three_arrive_with_exact_numbers(monkeypatch):
    """Gold, a USD pair and a JPY cross find a trade at the same tick: all three are sent (no cross-pair limit), each once,
    and the Telegram text, the push and the app's feed carry exactly the setup's own numbers at the pair's decimals."""
    from app.db import SessionLocal
    from app.models import Signal
    with SessionLocal() as db:
        db.query(Signal).filter(Signal.id.like("SMC-%")).delete(synchronize_session=False)
        db.commit()
    T = int(time.time()) - 120
    T -= T % 300

    def sig(pair, side, e, sl, tp, etf):
        key = pair.replace("/", "")
        return {"id": f"SMC-{key}-SF_BR-{T}-{'B' if side == 'BUY' else 'S'}", "strategy": "SF_BR", "setupType": "SF_BR", "name": "x", "direction": side,
                "time": T, "entry": e, "sl": sl, "tp": tp, "tp1": None, "part": 0.0, "market": True, "zone": [e, e], "rr": round(abs(tp - e) / abs(e - sl), 2),
                "validUntil": T, "expiry": 0, "holdUntil": T + 86400, "liveUntil": T + 86400, "state": "ACTIVE", "pass": True, "checklist": [], "steps": [],
                "lots": {"1000": 0.0, "10000": 0.0}, "grade": "A", "gpa": 85, "etf": etf, "draw": {}}
    found = {"XAU/USD": sig("XAU/USD", "SELL", 2350.4, 2357.1, 2330.3, "M15"), "EUR/USD": sig("EUR/USD", "BUY", 1.10123, 1.09923, 1.10623, "H1"),
             "GBP/JPY": sig("GBP/JPY", "BUY", 190.123, 189.623, 191.623, "M30")}

    async def fake_team(pair, fresh=False):
        return {"success": True, "signals": [found[pair]] if pair in found else [], "decision": "EXECUTE" if pair in found else "WATCH_ONLY"}
    sent = []

    async def fake_broadcast(pair, text, title, body, tag, signal=None):
        sent.append((pair, text, title, body))
        return {"telegram": 1, "push": 1}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "broadcast", fake_broadcast)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    res = asyncio.run(notify.tick())
    asyncio.run(notify.tick())  # the next minute: nothing again
    assert sorted(p for p, *_ in sent) == ["EUR/USD", "GBP/JPY", "XAU/USD"] and len(sent) == 3
    assert all("→ telegram 1 · push 1" in res[p] for p in found)
    want = {"XAU/USD": ("2350.40", "2357.10", "2330.30"), "EUR/USD": ("1.10123", "1.09923", "1.10623"), "GBP/JPY": ("190.123", "189.623", "191.623")}
    for pair, text, title, body in sent:
        e, sl, tp = want[pair]
        assert f"Entry <code>{e}</code> · SL <code>{sl}</code> · TP <code>{tp}</code>" in text  # Telegram
        assert f"Entry {e} · SL {sl} · TP {tp}" in body and title.startswith(f"🎯 {pair} {found[pair]['direction']} · {found[pair]['etf']}")  # push
    feed = {x["symbol"]: x for x in notify.recent()}  # what the app's toast and bell read
    for pair, s in found.items():
        assert (feed[pair]["entry"], feed[pair]["sl"], feed[pair]["tp"], feed[pair]["etf"], feed[pair]["time"]) == (s["entry"], s["sl"], s["tp"], s["etf"], T)
    with SessionLocal() as db:
        for s in found.values():
            row = db.get(Signal, s["id"])
            assert (row.entry, row.sl, row.tp2, row.signal_time) == (s["entry"], s["sl"], s["tp"], T)  # the saved trade = the sent one
