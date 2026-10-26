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
    assert "1.13530" in msg and "1.13772" in msg and "1.13046" in msg
    assert "24 pips" in msg and "Lot" not in msg and "risk" not in msg  # no lot line for a group chat


def test_lot_from_the_risk_in_dollars():
    from app.trading import lot_for_risk

    # EURUSD SL 24.2 pips: $80 / (24.2 pips × $10) = 0.33 lot (rounded down), real risk $79.86
    lot = lot_for_risk("EUR/USD", 1.1353, 1.13772, 80)
    assert (lot["lots"], lot["actualRisk"], lot["tooSmall"]) == (0.33, 79.86, False)
    # Gold SL $4.30: $80 / ($4.30 × 100 oz) = 0.18 lot
    assert lot_for_risk("XAU/USD", 4000.25, 3995.95, 80)["lots"] == 0.18
    # Below the minimum lot: 0.01 and flagged
    small = lot_for_risk("EUR/USD", 1.1353, 1.13772, 1)
    assert small["lots"] == 0.01 and small["tooSmall"]

    msg = bot.format_signal_message(EURO, lot, "ABC123")
    assert "Lot <code>0.33</code> · risk $79.86" in msg and "Ref ABC123" in msg
    assert "/risk 80" in bot.format_signal_message(EURO, {})  # subscriber without a risk
    kb = bot.copy_keyboard(EURO, lot)["inline_keyboard"]
    copied = [b["copy_text"]["text"] for row in kb for b in row]
    assert copied == ["1.13530", "1.13772", "1.13288", "1.13046", "1.12804", "0.33"]


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
        db.merge(Subscriber(chat_id="9001", first_name="Ali", expires_at=datetime.now(timezone.utc) + timedelta(days=5)))
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
    assert "All time" in say("/stats") and "win rate" in sent[-1]
    assert "H1 Trend Breakout" in say("/rules")
    assert "/gold" in say("/help") and "/news" in sent[-1]
    assert "No signal running" in say("/open")
