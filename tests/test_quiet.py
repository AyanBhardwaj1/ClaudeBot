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

    async def check(now=None):
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
