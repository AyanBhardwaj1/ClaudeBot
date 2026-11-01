"""Habits with an evening check-in and streaks."""

from datetime import date, datetime
from types import SimpleNamespace

from helpers import TZ, make_config

from claudebot.db import Database
from claudebot.habits import Habits


def test_streaks(tmp_path):
    habits = Habits(Database(tmp_path / "t.db"))
    h = habits.add("Workout")
    assert habits.add("workout")["id"] == h["id"]  # same habit, any case
    for d in (7, 8, 9):
        habits.mark(h["id"], date(2026, 11, d))
    assert habits.streak(h["id"], date(2026, 11, 10)) == 3  # today not marked yet: still counts
    habits.mark(h["id"], date(2026, 11, 10))
    assert habits.streak(h["id"], date(2026, 11, 10)) == 4
    assert habits.streak(h["id"], date(2026, 11, 12)) == 0


async def test_habit_command_buttons_and_evening_job(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    replies, sent, edits = [], [], []

    async def reply_text(text, reply_markup=None):
        replies.append((text, reply_markup))

    async def send_to_owner(text, reply_markup=None):
        sent.append((text, reply_markup))

    bot.send_to_owner = send_to_owner
    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_habit(update, SimpleNamespace(args=["read", "20", "pages"]))
    assert "Tracking read 20 pages" in replies[-1][0]
    await bot._habit_job(None)
    text, markup = sent[-1]
    data = markup.inline_keyboard[0][0].callback_data
    today = datetime.now(TZ).date()
    assert data == f"hab:1:{today:%Y%m%d}"

    async def answer(text=None):
        pass

    async def edit(text, reply_markup=None):
        edits.append((text, reply_markup))

    await bot.on_habit_button(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=1), data=data, answer=answer, edit_message_text=edit)), None)
    assert "✅ read 20 pages · 1 day streak" in edits[-1][0] and edits[-1][1] is None
    count = len(sent)
    await bot._habit_job(None)  # all done today: no nagging
    assert len(sent) == count
    await bot.on_habit(update, SimpleNamespace(args=["stop", "read", "20", "pages"]))
    assert Habits(bot.db).active() == []
