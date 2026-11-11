"""The trader-skill in the teams: the portfolio risk check across all teams, and a blocked setup is never sent."""

import asyncio

from app.smc.skill import portfolio

NOW = 1_790_000_000


def setup(symbol, direction, t=NOW - 600):
    return {"symbol": symbol, "direction": direction, "time": t, "validUntil": t + 3600}


def test_one_trade_per_pair_at_a_time():
    chk = portfolio.check("EUR/USD", {"direction": "BUY"}, [setup("EUR/USD", "SELL")], NOW)
    assert chk["verdict"] == "BLOCK" and any(r.startswith("duplicate") for r in chk["reasons"])


def test_at_most_two_bets_the_same_way_on_the_dollar():
    sent = [setup("EUR/USD", "BUY"), setup("GBP/USD", "BUY")]  # two short-dollar bets live
    gold = portfolio.check("XAU/USD", {"direction": "BUY"}, sent, NOW)
    assert gold["verdict"] == "BLOCK" and any(r.startswith("USD:") for r in gold["reasons"])  # the cap now covers all 8 currencies
    assert portfolio.check("XAU/USD", {"direction": "SELL"}, sent, NOW)["verdict"] == "PASS"  # the other way is fine
    assert portfolio.check("AUD/CAD", {"direction": "BUY"}, sent, NOW)["verdict"] == "PASS"  # no dollar leg


def test_the_guide_correlation_cap():
    sent = [setup("AUD/CAD", "BUY")]
    chk = portfolio.check("AUD/CHF", {"direction": "BUY"}, sent, NOW)
    assert chk["verdict"] == "BLOCK" and chk["reasons"][0].startswith("correlation: AUD/CAD BUY (+0.66)")
    assert portfolio.check("AUD/CHF", {"direction": "SELL"}, sent, NOW)["verdict"] == "PASS"  # the other way is a hedge, not a double
    assert portfolio.check("EUR/CHF", {"direction": "BUY"}, sent, NOW)["verdict"] == "PASS"  # not in the guide's pairs
    eu = portfolio.check("GBP/USD", {"direction": "SELL"}, [setup("EUR/USD", "SELL")], NOW)
    assert eu["verdict"] == "PASS" and eu["riskPct"] == 0.5 and eu["notes"][0].startswith("correlation: EUR/USD SELL")  # split, not blocked
    assert portfolio.check("GBP/USD", {"direction": "BUY"}, [setup("EUR/USD", "SELL")], NOW)["riskPct"] == 1.0


def test_a_trade_stays_live_until_its_live_until():
    long_ = {**setup("EUR/CHF", "BUY", NOW - 10 * 3600), "liveUntil": NOW + 3600}
    assert portfolio.live([long_], NOW) == [long_] and portfolio.live([setup("EUR/CHF", "BUY", NOW - 10 * 3600)], NOW) == []


def test_total_risk_and_the_daily_limit():
    three = [setup("EUR/CHF", "BUY"), setup("AUD/CAD", "SELL"), setup("XAU/USD", "SELL")]
    assert any(r.startswith("total risk") for r in portfolio.check("AUD/CHF", {"direction": "BUY"}, three, NOW)["reasons"])
    old = [setup(p, "BUY", NOW - 6 * 3600) for p in ("EUR/CHF", "AUD/CAD", "AUD/CHF", "XAU/USD", "GBP/USD")]  # today, expired
    chk = portfolio.check("EUR/USD", {"direction": "BUY"}, old, NOW)
    assert [r.split(":")[0] for r in chk["reasons"]] == ["daily"] and chk["live"] == 0


def test_a_blocked_setup_is_saved_and_never_sent(monkeypatch):
    from app.db import init_db
    from app.smc import notify

    init_db()
    from app.db import SessionLocal
    from app.models import Signal
    with SessionLocal() as db:  # only this test's setups count as live (other tests saved theirs in the same test database)
        db.query(Signal).filter(Signal.id.like("SMC-%")).delete(synchronize_session=False)
        db.commit()
    first = {"id": "SMC-EURUSD-S1-1790001000-B", "strategy": "S1", "name": "x", "direction": "BUY", "time": 1790001000,
             "entry": 1.1, "sl": 1.098, "tp": 1.108, "rr": 4.0, "validUntil": 1790004600, "state": "PENDING", "pass": True,
             "checklist": [], "steps": [], "lots": {"1000": 0.05, "10000": 0.5}, "draw": {}}
    again = {**first, "id": "SMC-EURUSD-S3-1790001300-B", "strategy": "S3", "time": 1790001300}  # same pair, still live

    async def fake_team(pair, fresh=False):
        return {"success": True, "signals": [first, again] if pair == "EUR/USD" else []}
    sent = []

    async def fake_send(pair, s):
        sent.append(s["id"])
        return {"telegram": 1, "push": 0}
    monkeypatch.setattr(notify, "team", fake_team)
    monkeypatch.setattr(notify, "_send", fake_send)
    monkeypatch.setattr(notify, "market_session_status", lambda p: {"isOpen": True})
    monkeypatch.setattr(notify.time, "time", lambda: 1790001400)
    res = asyncio.run(notify.tick())
    assert sent == [first["id"]] and "BLOCKED by the portfolio check: duplicate" in res["EUR/USD"]
    assert all(x["id"] != again["id"] for x in notify.recent())  # a blocked setup is not listed as sent
    asyncio.run(notify.tick())
    assert sent == [first["id"]]  # and it is never checked or sent again


def test_the_news_calendar_keeps_its_last_good_week_when_the_source_refuses(monkeypatch):
    import time as _t

    import httpx

    from app.db import init_db
    from app.market import news

    init_db()
    week = [{"time": int(_t.time()) + 3600, "currency": "USD", "title": "CPI m/m", "impact": "High"}]
    news._save_week(week)

    class Refused:
        status_code = 429

        def json(self):
            raise ValueError("rate limited")

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return Refused()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    news._cache.update(events=[], expires=0.0, source="none")
    cal = asyncio.run(news.load_news_calendar())
    assert cal["events"] == week and "kept copy" in cal["source"]
    assert news._cache["expires"] > _t.time() + 50 * 60  # not asked again for an hour
