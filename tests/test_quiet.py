"""/quiet pauses alerts, check-ins and meeting prep for a while."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from helpers import TZ, FakeClient, make_config

from claudebot.db import Database
from claudebot.heartbeat import run_heartbeat
from claudebot.quiet import DND_KEY, dnd_active, parse_pause
from claudebot.usage import UsageTracker

NOW = datetime(2026, 11, 10, 14, 0, tzinfo=TZ)


def test_parse_pause():
    assert parse_pause("2h", NOW) == NOW + timedelta(hours=2)
    assert parse_pause("30 min", NOW) == NOW + timedelta(minutes=30)
    assert parse_pause("morning", NOW) == datetime(2026, 11, 11, 8, 0, tzinfo=TZ)
    after_midnight = datetime(2026, 11, 11, 1, 15, tzinfo=TZ)
    assert parse_pause("morning", after_midnight) == datetime(2026, 11, 11, 8, 0, tzinfo=TZ)  # this morning
    assert parse_pause("99 days", NOW) == NOW + timedelta(days=2)  # alerts only catch up 2 days
    assert parse_pause("forever", NOW) is None and parse_pause("0h", NOW) is None


def test_pause_expires_on_its_own(tmp_path):
    db = Database(tmp_path / "t.db")
    db.set_setting(DND_KEY, (NOW + timedelta(hours=1)).isoformat())
    assert dnd_active(db, NOW) and not dnd_active(db, NOW + timedelta(hours=2))


async def test_paused_bot_stays_quiet(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc", quiet_hours=None))
    replies, checked = [], []

    async def reply_text(text, *, reply_markup=None):
        replies.append(text)

    async def check(now=None, urgent_only=False):
        checked.append(now)
        return []

    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_quiet(update, SimpleNamespace(args=["2h"]))
    assert "Quiet until" in replies[-1]
    bot.google.is_connected = lambda: True
    bot.watcher.check = check
    await bot._inbox_job(None)
    assert checked == []  # alerts wait (emails stay unseen and arrive after the pause)
    asked = []

    async def ask_agent(*a, **k):
        asked.append(a)
        return "brief"

    bot._ask_agent = ask_agent
    bot.google.list_events = lambda *a, **k: []
    await bot._meeting_prep_job(None)
    assert asked == []
    assert await run_heartbeat(None, FakeClient([]), UsageTracker(bot.db, TZ, None), bot.config, bot.db) is None
    await bot.on_quiet(update, SimpleNamespace(args=["off"]))
    await bot._inbox_job(None)
    assert len(checked) == 1


async def test_focus_session_and_note(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot
    from claudebot.lists import Lists

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    replies, sent, jobs = [], [], []

    async def reply_text(text, *, reply_markup=None):
        replies.append(text)

    async def send_to_owner(text, reply_markup=None):
        sent.append(text)

    bot.send_to_owner = send_to_owner
    monkeypatch.setattr(type(bot.app.job_queue), "run_once", lambda self, cb, when, name=None: jobs.append(when))
    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_focus(update, SimpleNamespace(args=["25"]))
    assert "Focus for 25 minutes" in replies[-1] and dnd_active(bot.db, datetime.now(TZ)) and len(jobs) == 1
    await bot._focus_done(None)
    assert sent == []  # still inside the session
    bot.db.delete_setting(DND_KEY)
    await bot._focus_done(None)
    assert "Focus session done" in sent[-1]
    await bot.on_focus(update, SimpleNamespace(args=["600"]))
    assert "5 to 180" in replies[-1]
    await bot.on_note(update, SimpleNamespace(args="call the landlord".split()))
    assert Lists(bot.db).items("Notes")[0]["text"] == "call the landlord" and replies[-1] == "🗒 Noted."


async def test_resume_button_cancels_the_focus_done_ping(tmp_path, monkeypatch):
    """Batch 5 L-5: Resume on the card ends a focus session like /quiet off does."""
    from types import SimpleNamespace

    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    sent = []

    async def send(text, **k):
        sent.append(text)

    async def noop(*a, **k):
        pass

    bot.send_to_owner = send
    bot.db.set_setting("focus_until", "2099-01-01T00:00:00+00:00")
    tap = SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=1), data="dnd:off", answer=noop))
    await bot.on_quiet_button(tap, None)
    await bot._focus_done(None)
    assert bot.db.get_setting("focus_until") is None and not any("Focus session done" in t for t in sent)
