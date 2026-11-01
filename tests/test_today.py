"""/today: an instant, free dashboard."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from helpers import TZ, make_config

from claudebot.lists import Lists


async def test_today_shows_calendar_reminders_and_lists_without_a_model_call(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    bot.client = None  # any model call would fail
    now = datetime.now(TZ)
    bot.google.is_connected = lambda: True
    bot.google.list_events = lambda start, end, max_results=50: [
        {"id": "e1", "summary": "Standup http://evil.example", "start": now.replace(hour=9, minute=0).isoformat(),
         "end": now.replace(hour=9, minute=15).isoformat()},
        {"id": "e2", "summary": "Mom visiting", "start": now.date().isoformat(),
         "end": (now.date() + timedelta(days=1)).isoformat()}]
    bot.db.add_reminder("call the dentist", now.replace(hour=23, minute=0), "none", False)
    bot.db.add_reminder("next week thing", now + timedelta(days=7), "none", False)
    Lists(bot.db).add("Shopping", ["milk", "eggs"])
    from claudebot.birthdays import Birthdays
    soon = now.date() + timedelta(days=2)
    Birthdays(bot.db).add("Mom", soon.month, min(soon.day, 28) if soon.month == 2 else soon.day)
    later = now.date() + timedelta(days=30)
    Birthdays(bot.db).add("Far", later.month, min(later.day, 28))
    from claudebot.bills import Bills
    tomorrow = now.date() + timedelta(days=1)
    Bills(bot.db).add("Phone", 45, tomorrow.day if tomorrow.day <= 28 else 28)
    paid, _ = Bills(bot.db).add("Rent", 1200, now.date().day if now.date().day <= 28 else 28)
    Bills(bot.db).mark_paid(paid["id"], now.date())
    replies = []

    async def reply_text(text, *, reply_markup=None):
        replies.append(text)

    await bot.on_today(SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text)), None)
    text = replies[-1]
    assert "09:00–09:15  Standup" in text and "http://evil" not in text and "all day  Mom visiting" in text
    assert "call the dentist" in text and "next week thing" not in text
    assert "Shopping: 2" in text
    assert "🎂 Mom" in text and "Far" not in text
    if tomorrow.day <= 28:  # month-end days clamp; the line itself is still covered most days
        assert "🧾 Phone 45.00 USD tomorrow" in text
    assert "Rent" not in text  # already paid



def test_usage_breaks_spend_down_by_feature(tmp_path):
    from helpers import message

    from claudebot.db import Database
    from claudebot.usage import UsageTracker

    db = Database(tmp_path / "t.db")
    tracker = UsageTracker(db, TZ, None)
    tracker.record(message("end_turn", [], usage={"input_tokens": 100000, "output_tokens": 1000}), "chat")
    tracker.record(message("end_turn", [], model="claude-haiku-5-5", usage={"input_tokens": 1000, "output_tokens": 100}),
                   "heartbeat")
    summary = tracker.summary()
    assert "This month by feature:" in summary
    assert summary.index("Conversations") < summary.index("Check-ins")  # most expensive first


async def test_menu_buttons_run_their_command_and_forwards_dont(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    called, replies = [], []

    async def fake_today(update, context):
        called.append(("today", context.args))

    async def fake_quiet(update, context):
        called.append(("quiet", context.args))

    async def reply_text(text, *, reply_markup=None):
        replies.append((text, reply_markup))

    bot.on_today = fake_today
    bot.on_quiet = fake_quiet

    def update(text, forwarded=False):
        return SimpleNamespace(effective_message=SimpleNamespace(text=text, forward_origin=object() if forwarded else None,
                                                                 reply_text=reply_text))

    assert await bot.handle_menu_button(update("📆 Today"))
    assert await bot.handle_menu_button(update("🔕 Quiet 1h"))
    assert not await bot.handle_menu_button(update("📆 Today", forwarded=True))
    assert not await bot.handle_menu_button(update("what's on today?"))
    assert called == [("today", []), ("quiet", ["1h"])]
    await bot.on_menu(update("/menu"), SimpleNamespace(args=[]))
    assert replies[-1][1].keyboard[0][0].text == "📆 Today"
