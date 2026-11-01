"""Birthdays with a yearly reminder the day before, removed by its own id."""

from datetime import date, datetime
from types import SimpleNamespace

from helpers import TZ, make_config

from claudebot.birthdays import Birthdays, next_birthday, parse_birthday


def test_parse_birthday_forms():
    assert parse_birthday("Mom Mar 14") == ("Mom", 3, 14)
    assert parse_birthday("Aunt Sue 14th March") == ("Aunt Sue", 3, 14)
    assert parse_birthday("Dad 1961-03-14") == ("Dad", 3, 14)
    assert parse_birthday("Leap Feb 29") == ("Leap", 2, 29)
    assert parse_birthday("Bob Feb 30") is None
    assert parse_birthday("Mar 14") is None
    assert parse_birthday("<b>Eve</b> Sept 3") == ("b Eve /b", 9, 3)


def test_next_birthday_wraps_and_handles_leap_day():
    assert next_birthday(3, 14, date(2026, 3, 14)) == date(2026, 3, 14)
    assert next_birthday(3, 14, date(2026, 3, 15)) == date(2027, 3, 14)
    assert next_birthday(2, 29, date(2026, 11, 1)) == date(2027, 2, 28)
    assert next_birthday(2, 29, date(2027, 3, 1)) == date(2028, 2, 29)


async def test_birthday_command_reminder_replace_and_remove(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    unscheduled = []
    bot.schedule_reminder = lambda rid: None
    bot.unschedule_reminder = unscheduled.append
    replies, edits = [], []

    async def reply_text(text, *, reply_markup=None):
        replies.append((text, reply_markup))

    async def answer(text=None):
        pass

    async def edit(text, *, reply_markup=None):
        edits.append(text)

    def cmd(*args):
        return (SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text)),
                SimpleNamespace(args=list(args)))

    other = bot.db.add_reminder("Mom's flight", datetime(2030, 1, 1, tzinfo=TZ), "none", False)
    await bot.on_birthdays(*cmd("Mom", "Mar", "14"))
    assert "Saved Mom" in replies[-1][0]
    first = [r for r in bot.db.active_reminders() if r["repeat"] == "yearly"]
    assert len(first) == 1 and first[0]["text"] == "🎂 Mom's birthday is on Mar 14"
    remind = datetime.fromisoformat(first[0]["due_at"]).astimezone(TZ)
    assert (remind.month, remind.day, remind.hour) == (3, 13, 9)

    await bot.on_birthdays(*cmd("mom", "Mar", "15"))  # same person, fixed date: the old reminder goes
    yearly = [r for r in bot.db.active_reminders() if r["repeat"] == "yearly"]
    assert len(yearly) == 1 and "Mar 15" in yearly[0]["text"] and first[0]["id"] in unscheduled
    assert [b["name"] for b in Birthdays(bot.db).all()] == ["mom"]

    await bot.on_birthdays(*cmd("whenever"))
    assert "didn't get that date" in replies[-1][0]
    await bot.on_birthdays(*cmd())
    assert "mom: Mar 15" in replies[-1][0]

    def tap(data, user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id), data=data,
                                                              answer=answer, edit_message_text=edit))

    item = Birthdays(bot.db).all()[0]
    await bot.on_birthday_button(tap(f"bday:del:{item['id']}", user_id=999), None)
    assert Birthdays(bot.db).all()
    await bot.on_birthday_button(tap(f"bday:del:{item['id']}"), None)
    assert Birthdays(bot.db).all() == [] and "No birthdays yet" in edits[-1]
    assert [r["id"] for r in bot.db.active_reminders()] == [other]  # only its own reminder was removed
