"""Anti copy-trading protection, candle-close timing and the signal message (Telegram API mocked)."""

import asyncio
from datetime import datetime, timezone

from app.telegram import bot
from app.telegram.protection import hash32, personal_offset, personalize_signal, reference_code
from app.telegram.scheduler import next_close_sec

GOLD = {"id": "sig-XAUUSD-1-2", "symbol": "XAU/USD", "signalType": "BUY", "entryPrice": 4000.25, "stopLoss": 3995.95, "target1": 4004.55,
        "target2": 4012, "target3": 4016.3, "confidence": 94, "strategyUsed": "XAUUSD · H1 Trend Breakout"}
EURO = {"id": "sig-EURUSD-B-3", "symbol": "EUR/USD", "signalType": "SELL", "entryPrice": 1.1353, "stopLoss": 1.13772, "target1": 1.13288,
        "target2": 1.13046, "target3": 1.12804, "confidence": 86, "strategyUsed": "EURUSD · Trend Pullback + London Breakout Filter"}


def test_hashes_match_the_javascript_version():
    # Values computed with the original TypeScript functions (Node)
    assert hash32("abc") == 440920331
    assert hash32("عربي") == 838755277
    assert hash32("off|1001|sig-XAUUSD-1-2") == 2022985815
    assert reference_code("1001", "sig-XAUUSD-1-2") == "Y5S2RJ"
    assert reference_code("5000000123", "sig-EURUSD-B-3") == "XPBCKI"


def test_personal_offsets_keep_risk_and_differ_per_subscriber():
    a, off_a, ref_a = personalize_signal(GOLD, "1001")
    b, off_b, ref_b = personalize_signal(GOLD, "1002")
    assert 0 < abs(off_a) <= 0.09 + 1e-9
    assert abs(abs(a["entryPrice"] - a["stopLoss"]) - abs(GOLD["entryPrice"] - GOLD["stopLoss"])) < 1e-6
    assert abs(abs(a["target2"] - a["entryPrice"]) - abs(GOLD["target2"] - GOLD["entryPrice"])) < 1e-6
    assert personalize_signal(GOLD, "1001") == (a, off_a, ref_a)
    assert len({f"{personal_offset('XAU/USD', str(5000 + i), GOLD['id']):.2f}" for i in range(50)}) >= 10
    assert (a["entryPrice"], ref_a) != (b["entryPrice"], ref_b)
    e = personalize_signal(EURO, "1001")[1]
    assert 0 < abs(e) <= 0.00009 + 1e-12


def test_next_candle_close():
    t = datetime(2026, 10, 27, 8, 3, 20, tzinfo=timezone.utc).timestamp()
    assert next_close_sec(t, 300) == datetime(2026, 10, 27, 8, 5, tzinfo=timezone.utc).timestamp()
    assert next_close_sec(t, 900) == datetime(2026, 10, 27, 8, 15, tzinfo=timezone.utc).timestamp()
    on_close = datetime(2026, 10, 27, 8, 15, tzinfo=timezone.utc).timestamp()
    assert next_close_sec(on_close, 900) == datetime(2026, 10, 27, 8, 30, tzinfo=timezone.utc).timestamp()


def test_message_prints_exact_levels_only():
    msg = bot.format_signal_message({**EURO, "confirmationCheckPassed": True, "confirmationCloseTime": 1790668800})
    # one value per line, the single target (TP3) only
    assert msg.split("\n") == ["🔴 <b>SELL LIMIT | EUR/USD</b>", "📍 Entry: <code>1.13530</code>", "🎯 TP: <code>1.12804</code>",
                                "🛑 SL: <code>1.13772</code>"]  # no lot line for a group chat


def test_lot_from_the_risk_in_dollars():
    from app.trading import lot_for_risk

    # EURUSD SL 24.2 pips + 1.2 pips spread/slippage: $80 / (25.4 pips × $10) = 0.31 lot (rounded down), real risk $78.74
    lot = lot_for_risk("EUR/USD", 1.1353, 1.13772, 80)
    assert (lot["lots"], lot["actualRisk"], lot["tooSmall"]) == (0.31, 78.74, False)
    # Gold SL $4.30 + $0.30 costs: $80 / ($4.60 × 100 oz) = 0.17 lot
    assert lot_for_risk("XAU/USD", 4000.25, 3995.95, 80)["lots"] == 0.17
    # Below the minimum lot: 0.01 and flagged
    small = lot_for_risk("EUR/USD", 1.1353, 1.13772, 1)
    assert small["lots"] == 0.01 and small["tooSmall"]

    msg = bot.format_signal_message(EURO, lot, "ABC123")
    assert "📦 Lot: <code>0.31</code>" in msg and "Ref ABC123" in msg
    assert "Lot" not in bot.format_signal_message(EURO, {})  # subscriber without a risk
    kb = bot.copy_keyboard(EURO, lot)["inline_keyboard"]
    copied = [b["copy_text"]["text"] for row in kb for b in row]
    assert copied == ["1.13530", "1.13772", "1.13288", "1.13046", "1.12804", "0.31"]


def test_signal_messages_are_protected(monkeypatch):
    captured = {}

    async def fake_call(token, method, payload):
        captured.update(payload)
        return {"ok": True, "result": {"message_id": 7}}

    monkeypatch.setattr(bot, "call", fake_call)
    out = asyncio.run(bot.send_message("TEST", "42", "x", protect=True))
    assert out == {"success": True, "messageId": 7} and captured["protect_content"] is True and captured["chat_id"] == "42"
    captured.clear()
    asyncio.run(bot.send_message("TEST", "42", "y"))
    assert "protect_content" not in captured


def test_bot_commands(monkeypatch):
    from datetime import timedelta

    from app.db import SessionLocal, init_db
    from app.models import Signal, Subscriber

    init_db()
    sent = []

    async def fake_send(token, chat_id, text, reply_markup=None, protect=False):
        sent.append(text)
        return {"success": True}

    monkeypatch.setattr(bot, "send_message", fake_send)
    with SessionLocal() as db:
        from app.auth import hash_code
        from app.models import User
        from sqlalchemy import select
        u = db.scalar(select(User).where(User.username == "ali-tg")) or User(username="ali-tg", access_code_hash=hash_code("secret-111"))
        u.telegram_chat_id, u.active, u.status = "9001", True, "approved"  # access comes from the linked app account
        db.add(u)
        db.merge(Subscriber(chat_id="9001", first_name="Ali", code="ACCOUNT"))
        db.merge(Signal(id="XAUUSD-BO-1", symbol="XAU/USD", setup="BREAKOUT", direction="BUY", entry_type="MARKET", entry=4000, sl=3990,
                        tp1=4010, tp2=4020, tp3=4030, rr_tp2=2, score=90, signal_time=1, state="CLOSED", outcome="WIN", r_multiple=1.75,
                        params={}, payload={}))
        db.commit()

    def say(text):
        asyncio.run(bot.handle_update("T", {"message": {"text": text, "chat": {"id": 9001}, "from": {"first_name": "Ali"}}}))
        return sent[-1]

    assert "9001" in say("/myid")
    assert "No risk set" in say("/risk") and "$80" in say("/risk 80")
    with SessionLocal() as db:
        assert db.get(Subscriber, "9001").risk_usd == 80
        assert bot.chat_risks(db, ["9001", "group"]) == {"9001": 80}  # a non-subscriber chat gets no lot line
    assert "$80" in say("/risk")
    assert "paused" in say("/stop").lower()
    with SessionLocal() as db:
        assert db.get(Subscriber, "9001").muted
    assert "paused" in say("/status").lower()
    assert "resumed" in say("/resume").lower()
    assert "XAU/USD" in say("/history") and "+1.75R" in sent[-1]
    assert "All time" in say("/stats") and "Win rate" in sent[-1]
    assert "Bollinger reversion" in say("/rules") and "Breakout" in sent[-1]
    assert "/pairs" in say("/help") and "/news" in sent[-1]
    assert "/gold · XAU/USD" in say("/pairs") and "/eurusd · EUR/USD" in sent[-1]  # the pair commands, tappable
    assert "No trade running" in say("/open")


def test_close_messages():
    base = {"id": "x", "symbol": "XAU/USD", "direction": "BUY", "state": "CLOSED", "rrTarget": 2.0}
    assert bot.format_close_message({**base, "outcome": "WIN", "rMultiple": 2.0}) == \
        "<b>✅ TP HIT | XAU/USD (BUY)</b>\nResult: +2.00R\n👉 Profit taken. Nothing to do."
    assert bot.close_message({**base, "outcome": "WIN", "rMultiple": 0.8})[0] == "✅ CLOSED IN PROFIT"  # RSI(2) EMA5 exit
    assert bot.close_message({**base, "outcome": "LOSS", "rMultiple": -1.03})[0] == "❌ SL HIT"
    assert bot.close_message({**base, "outcome": "BREAKEVEN", "rMultiple": 0.0})[0] == "➖ BREAKEVEN"
    assert bot.close_message({**base, "state": "EXPIRED", "outcome": None, "rMultiple": None}) == \
        ("⚪ CANCELLED", "Order not filled.\n👉 Delete your pending order.")


def test_follow_up_notices():
    from types import SimpleNamespace as N

    from app.followup import events_for

    now = 1_800_000_000
    sig = N(symbol="EUR/USD", direction="SELL", entry=1.1000, sl=1.1020, entry_type="LIMIT", state="OPEN")
    keys = lambda price, news=(): [k for k, _, _ in events_for(sig, price, list(news), now)]  # noqa: E731
    assert keys(1.0990) == ["fill"]  # +0.5R: just filled
    assert keys(1.0978) == ["fill", "1r"]  # +1.1R
    assert keys(1.1015) == ["fill", "nearsl"]  # -0.75R
    news = [{"time": now + 900, "impact": "High", "currency": "USD", "title": "CPI"},
            {"time": now + 900, "impact": "High", "currency": "JPY", "title": "BoJ"},  # not one of the pair's currencies
            {"time": now + 7200, "impact": "High", "currency": "EUR", "title": "ECB"}]  # too far
    ev = events_for(sig, 1.0995, news, now)
    assert [k for k, _, _ in ev] == ["fill", f"news{now + 900}"] and ev[1][1] == "📰 NEWS IN 15 MIN" and "USD CPI" in ev[1][2]
    pending = N(**{**sig.__dict__, "state": "PENDING"})
    assert [k for k, _, _ in events_for(pending, 1.0978, [], now)] == []  # not filled: no price notice
    market = N(**{**sig.__dict__, "entry_type": "MARKET"})
    assert [k for k, _, _ in events_for(market, 1.0995, [], now)] == []  # a market order is live at once


def test_bot_reads_only_commands_and_codes(monkeypatch):
    import asyncio

    sent = []

    async def fake_send(token, chat_id, text, *a, **k):
        sent.append(text)
        return {"success": True}

    monkeypatch.setattr(bot, "send_message", fake_send)
    msg = lambda text: {"message": {"text": text, "chat": {"id": 777001}, "from": {"first_name": "T"}}}  # noqa: E731
    asyncio.run(bot.handle_update("t", msg("/signal")))
    assert "Connect your app account first" in sent[-1]  # commands need a linked account
    asyncio.run(bot.handle_update("t", msg("/help")))
    assert "<b>📊 Market</b>" in sent[-1] and "/signal\n<i>Every pair right now</i>" in sent[-1]
    n = len(sent)
    for typed in ("WRONGCODE", "EXU-ABC123-DEF4", "hello, how are you?"):
        asyncio.run(bot.handle_update("t", msg(typed)))
    assert len(sent) == n  # nothing typed gets an answer: no codes, no chat


def test_send_retries_on_rate_limit(monkeypatch):
    import asyncio

    answers = [{"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 0}},
               {"ok": True, "result": {"message_id": 7}}]
    monkeypatch.setattr(bot, "call", lambda *a, **k: asyncio.sleep(0, answers.pop(0)))
    assert asyncio.run(bot.send_message("t", "1", "hi")) == {"success": True, "messageId": 7}  # waited, then delivered
    monkeypatch.setattr(bot, "call", lambda *a, **k: asyncio.sleep(0, {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked"}))
    assert asyncio.run(bot.send_message("t", "1", "hi"))["success"] is False  # a blocked bot is not retried


def test_chart_picture_and_command(monkeypatch):
    import asyncio
    import math

    from sqlalchemy import select

    from app.auth import hash_code
    from app.db import SessionLocal, init_db
    from app.models import User
    from app.strategies.shared.types import Candle
    from app.telegram import chart_image

    init_db()

    # The picture: a PNG of the pair with its trade
    candles = [Candle(time=1_800_000_000 + i * 900, open=100 + math.sin(i / 5), high=101 + math.sin(i / 5), low=99 + math.sin(i / 5),
                      close=100.3 + math.sin(i / 5), volume=0) for i in range(300)]
    result = {"spec": {"decimals": 2}, "displaySymbol": "XAU/USD", "strategyName": "Gold · H1 Trend Breakout", "price": 100.2, "status": "SIGNAL",
              "setup": {"direction": "SELL", "entry": 100.5, "sl": 102.5, "tp3": 96.5, "signalTime": candles[-5].time, "lifecycle": {"state": "OPEN"}}}
    result.update(drawings=[{"kind": "hline", "layer": "structure", "t1": candles[-40].time, "t2": None, "p1": 100.4,
                             "text": "Breakout 20h low", "color": "bear", "style": "solid"}],
                  checklist=[{"rule": "H1 close beyond the 20-hour low", "passed": True}, {"rule": "Spread <= $0.5", "passed": True}],
                  timeframes={"entry": "H1"}, headline="SELL breakout")
    png = chart_image.render_chart(candles, result)
    card = chart_image.render_card(result, {"verdict": "HOLD", "action": {"en": "Hold: plan intact."}})
    assert card[:8] == b"\x89PNG\r\n\x1a\n" and len(card) > 5_000  # the follow-up card
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 10_000

    # The bot: /chart lists the pairs, /chart_gold sends the picture
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.username == "chart-tg")) or User(username="chart-tg", access_code_hash=hash_code("secret-222"))
        u.telegram_chat_id, u.active, u.status = "9333", True, "approved"
        db.add(u)
        db.commit()
    sent, photos = [], []

    async def fake_send(token, chat_id, text, reply_markup=None, protect=False):
        sent.append(text)
        return {"success": True}

    async def fake_photo(token, chat_id, data, caption=""):
        photos.append((chat_id, caption))
        return {"success": True}

    async def fake_chart(sym):
        return png, f"<b>{sym}</b>"
    monkeypatch.setattr(bot, "send_message", fake_send)
    monkeypatch.setattr(bot, "send_photo", fake_photo)
    monkeypatch.setattr(chart_image, "pair_chart", fake_chart)
    say = lambda text: asyncio.run(bot.handle_update("T", {"message": {"text": text, "chat": {"id": 9333}, "from": {"first_name": "C"}}}))  # noqa: E731
    say("/chart")
    assert "/chart_gold · XAU/USD" in sent[-1] and "/chart_audchf · AUD/CHF" in sent[-1]
    say("/chart_gold")
    assert photos[-1] == ("9333", "<b>XAU/USD</b>")
    say("/chart_eurusd")
    assert photos[-1][1] == "<b>EUR/USD</b>"
