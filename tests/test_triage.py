"""/triage walks through unread email one card at a time."""

from types import SimpleNamespace

from helpers import make_config


async def test_triage_cards_and_actions(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    emails = [{"id": f"abc00{i}", "from": f"Person {i} <p{i}@x.com>", "subject": f"Subject {i} http://evil.example",
               "snippet": "hi"} for i in range(3)]
    bot.google.search_emails = lambda q, n: emails
    archived, conversed, replies, edits, scheduled = [], [], [], [], []
    bot.google.modify_email = lambda mid, action: archived.append((mid, action))
    bot.schedule_reminder = scheduled.append

    async def converse(content, question, effort=None, owner_present=True):
        conversed.append((content[0]["text"], owner_present))

    async def reply_text(text, *, reply_markup=None):
        replies.append((text, reply_markup))

    async def answer(text=None):
        pass

    async def edit(text, *, reply_markup=None):
        edits.append((text, reply_markup))

    bot._converse = converse

    def tap(data, user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id), data=data,
                                                              answer=answer, edit_message_text=edit))

    await bot.on_triage(SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text)), None)
    text, markup = replies[-1]
    assert "3 to go" in text and "http://evil" not in text
    assert [b.callback_data for b in markup.inline_keyboard[0]] == [
        "tri:arch:abc000", "tri:draft:abc000", "tri:later:abc000", "tri:snooze:abc000", "tri:next:abc000"]
    await bot.on_triage_button(tap("tri:arch:abc000", user_id=999), None)
    assert archived == []
    await bot.on_triage_button(tap("tri:arch:abc000"), None)
    await bot.on_triage_button(tap("tri:arch:abc000"), None)  # an old card does nothing
    assert archived == [("abc000", "archive")] and "2 to go" in edits[-1][0]
    await bot.on_triage_button(tap("tri:later:abc001"), None)
    assert len(scheduled) == 1
    await bot.on_triage_button(tap("tri:draft:abc002"), None)
    assert "That's all" in edits[-1][0] and conversed[0][1] is False and "abc002" in conversed[0][0]



async def test_snoozed_email_comes_back(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from helpers import TZ

    from claudebot.bot import TelegramBot
    from claudebot.snooze import due

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    bot.google.search_emails = lambda q, n: [{"id": "abc000", "from": "Sam <s@x.com>", "subject": "Lunch", "snippet": ""}]
    moves, sent = [], []
    bot.google.modify_email = lambda mid, action: moves.append((mid, action))

    async def send_to_owner(text, reply_markup=None):
        sent.append(text)

    async def noop(*a, **k):
        pass

    bot.send_to_owner = send_to_owner
    await bot.on_triage(SimpleNamespace(effective_message=SimpleNamespace(reply_text=noop)), None)
    await bot.on_triage_button(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=1), data="tri:snooze:abc000", answer=noop, edit_message_text=noop)), None)
    assert moves == [("abc000", "archive")] and due(bot.db, datetime.now(TZ)) == []
    later = datetime.now(TZ) + timedelta(days=2)
    assert len(due(bot.db, later)) == 1
    monkeypatch.setattr("claudebot.snooze.datetime", SimpleNamespace(now=lambda tz=None: later,
                                                                     fromisoformat=datetime.fromisoformat))
    await bot._snooze_job(None)
    assert moves[-1] == ("abc000", "inbox") and "Back in your inbox: Sam: Lunch" in sent[-1]
    await bot._snooze_job(None)
    assert len(sent) == 1


async def test_a_double_tap_acts_once(tmp_path, monkeypatch):
    import asyncio

    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    bot.google.search_emails = lambda q, n: [{"id": f"abc00{i}", "from": "a@b.c", "subject": "s", "snippet": ""}
                                             for i in range(3)]
    scheduled = []
    bot.schedule_reminder = scheduled.append

    async def noop(*a, **k):
        pass

    await bot.on_triage(SimpleNamespace(effective_message=SimpleNamespace(reply_text=noop)), None)
    tap = SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=1), data="tri:later:abc000",
                                                         answer=noop, edit_message_text=noop))
    await asyncio.gather(bot.on_triage_button(tap, None), bot.on_triage_button(tap, None))
    assert len(scheduled) == 1
