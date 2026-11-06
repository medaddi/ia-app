"""The Telegram bot: it reads commands only, links an account and retries a rate-limited send (Telegram API mocked)."""

from app.telegram import bot


def test_bot_reads_only_commands_and_codes(monkeypatch):
    import asyncio

    sent = []

    async def fake_send(token, chat_id, text, *a, **k):
        sent.append(text)
        return {"success": True}

    monkeypatch.setattr(bot, "send_message", fake_send)
    msg = lambda text: {"message": {"text": text, "chat": {"id": 777001}, "from": {"first_name": "T"}}}  # noqa: E731
    asyncio.run(bot.handle_update("t", msg("/status")))
    assert "Connect your app account first" in sent[-1]  # account commands need a linked account
    asyncio.run(bot.handle_update("t", msg("/help")))
    assert "<b>📊 Market</b>" in sent[-1] and "/news" in sent[-1] and "/signal" not in sent[-1]  # no analysis command any more
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
