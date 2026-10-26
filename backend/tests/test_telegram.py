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
    assert "(24 pips)" in msg and "Lot" not in msg and "risk" not in msg


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
