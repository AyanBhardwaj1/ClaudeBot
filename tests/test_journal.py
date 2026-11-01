"""The optional evening journal."""

from types import SimpleNamespace

from helpers import make_config

from claudebot.db import Database
from claudebot.journal import Journal


def test_one_entry_per_day_that_grows(tmp_path):
    journal = Journal(Database(tmp_path / "t.db"))
    journal.write("2026-11-09", "long day")
    journal.write("2026-11-10", "good run")
    journal.write("2026-11-10", "and a nice dinner")
    entries = journal.recent(7, "2026-11-10")
    assert [e["day"] for e in entries] == ["2026-11-09", "2026-11-10"]
    assert entries[1]["text"] == "good run\n\nand a nice dinner"


async def test_evening_prompt_and_answer(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    sent, replies = [], []

    async def send_to_owner(text, reply_markup=None):
        sent.append(text)
        return SimpleNamespace(message_id=500 + len(sent))

    async def reply_text(text, *, reply_markup=None):
        replies.append(text)

    bot.send_to_owner = send_to_owner
    await bot._journal_job(None)
    assert sent == []  # off by default
    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_journal(update, SimpleNamespace(args=["on"]))
    await bot._journal_job(None)
    assert "How was your day" in sent[-1]
    prompt_id = 500 + len(sent)
    # A normal message right after the prompt isn't an entry...
    assert not await bot.handle_answer(SimpleNamespace(text="remind me at 6pm", forward_origin=None,
                                                       reply_to_message=None))
    # ...a reply to the prompt is.
    assert await bot.handle_answer(SimpleNamespace(text="Shipped the release. Tired but happy.", forward_origin=None,
                                                   reply_to_message=SimpleNamespace(message_id=prompt_id)))
    await bot.on_journal(update, SimpleNamespace(args=[]))
    assert "Shipped the release" in replies[-1]
    assert not await bot.handle_answer(SimpleNamespace(text="what's on tomorrow?", forward_origin=None))
