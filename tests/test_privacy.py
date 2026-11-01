"""/privacy shows what's kept and clears it after a confirmation."""

from types import SimpleNamespace

from helpers import make_config

from claudebot.actions import ActionLog
from claudebot.journal import Journal
from claudebot.privacy import counts


async def test_privacy_clears_only_after_confirming(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    thread = bot.db.new_thread("x")
    bot.db.append_message(thread, {"role": "user", "content": "secret plans"})
    Journal(bot.db).write("2026-11-10", "dear diary")
    ActionLog(bot.db).record("email", "Sent email to x")
    bot.db.add_memory("keep me")
    replies, edits = [], []

    async def reply_text(text, *, reply_markup=None):
        replies.append((text, reply_markup))

    async def answer(text=None):
        pass

    async def edit(text, *, reply_markup=None):
        edits.append(text)

    def tap(data, user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id), data=data,
                                                              answer=answer, edit_message_text=edit))

    await bot.on_privacy(SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text)), None)
    assert "1 conversation messages" in replies[-1][0] and "1 journal entries" in replies[-1][0]
    await bot.on_privacy_button(tap("priv:ask:chat"), None)
    assert counts(bot.db)["chat"] == 1 and "can't be undone" in edits[-1]
    await bot.on_privacy_button(tap("priv:do:chat", user_id=999), None)
    assert counts(bot.db)["chat"] == 1
    await bot.on_privacy_button(tap("priv:do:chat"), None)
    await bot.on_privacy_button(tap("priv:do:journal"), None)
    c = counts(bot.db)
    assert c["chat"] == 0 and c["journal"] == 0 and c["log"] == 1 and c["memories"] == 1
