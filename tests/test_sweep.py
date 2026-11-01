"""/sweep archives old promotions, social and update emails in one tap."""

from types import SimpleNamespace

from helpers import make_config

from claudebot.actions import ActionLog
from claudebot.google_services import Google


def test_message_ids_and_archive_many(tmp_path, monkeypatch):
    google = Google(make_config(tmp_path))
    modified, listed = [], []

    class Messages:
        def list(self, **kw):
            listed.append(kw)
            page = int(kw.get("pageToken") or 0)
            ids = [{"id": f"m{page + i}"} for i in range(3)]
            nxt = {"nextPageToken": str(page + 3)} if page < 3 else {}
            return SimpleNamespace(execute=lambda: {"messages": ids, **nxt})

        def batchModify(self, **kw):
            modified.append(kw)
            return SimpleNamespace(execute=lambda: None)

    monkeypatch.setattr(google, "_gmail", lambda: SimpleNamespace(users=lambda: SimpleNamespace(messages=Messages)))
    ids = google.message_ids("category:promotions", 5)
    assert ids == ["m0", "m1", "m2", "m3", "m4"]
    google.archive_many(ids)
    assert modified[0]["body"] == {"ids": ids, "removeLabelIds": ["INBOX"]}
    google.archive_many([])
    assert len(modified) == 1


async def test_sweep_counts_then_archives_on_tap(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    archived, replies, sent = [], [], []
    bot.google.message_ids = lambda query, limit: ["a", "b"] if "promotions" in query else []
    bot.google.archive_many = archived.extend

    async def reply_text(text, reply_markup=None):
        replies.append((text, reply_markup))

    async def send_to_owner(text, reply_markup=None):
        sent.append(text)

    bot.send_to_owner = send_to_owner
    await bot.on_sweep(SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text)), None)
    text, markup = replies[-1]
    assert [b.callback_data for row in markup.inline_keyboard for b in row] == ["sweep:promo"]
    assert "Archive 2 promotions" in markup.inline_keyboard[0][0].text and archived == []

    async def answer(text=None):
        pass

    await bot.on_sweep_button(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=999), data="sweep:promo", answer=answer)), None)
    assert archived == []
    await bot.on_sweep_button(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=1), data="sweep:promo", answer=answer)), None)
    assert archived == ["a", "b"] and "Archived 2 promotions" in sent[-1]
    from datetime import datetime, timedelta, timezone

    assert "Archived 2 promotions" in ActionLog(bot.db).since(datetime.now(timezone.utc) - timedelta(minutes=1))[0]["summary"]
