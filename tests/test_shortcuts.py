"""/catchup, /trips and check-in counters."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from helpers import make_config

from claudebot.db import Database
from claudebot.shortcuts import CATCHUP_KEY, bump, last_days


def test_counters_sum_the_last_days(tmp_path):
    db = Database(tmp_path / "t.db")
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    bump(db, "checkins_sent", now)
    bump(db, "checkins_sent", now - timedelta(days=3))
    bump(db, "checkins_sent", now - timedelta(days=9))
    assert last_days(db, "checkins_sent", 7, now) == 2


async def test_catchup_covers_the_time_since_last_time(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    asked = []

    async def converse(content, question, effort=None, owner_present=True):
        asked.append(content[0]["text"])

    bot._converse = converse
    await bot.on_catchup(SimpleNamespace(), None)
    assert "last 12 hours" in asked[-1]
    bot.db.set_setting(CATCHUP_KEY, (datetime.now(timezone.utc) - timedelta(hours=5, minutes=10)).isoformat())
    await bot.on_catchup(SimpleNamespace(), None)
    assert "last 5 hours" in asked[-1] and "newer_than:5h" in asked[-1]
    await bot.on_trips(SimpleNamespace(), None)
    assert "trips" in asked[-1]



async def test_health_check_follows_the_alive_file(tmp_path, monkeypatch):
    import os
    import time

    from claudebot.__main__ import healthy
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    assert not healthy(tmp_path)
    await bot._alive_job(None)
    assert healthy(tmp_path)
    old = time.time() - 600
    os.utime(tmp_path / "alive", (old, old))
    assert not healthy(tmp_path)


def test_whats_new_once_per_version_and_not_on_fresh_installs(tmp_path):
    from claudebot.whatsnew import SEEN_KEY, notes_to_show

    db = Database(tmp_path / "t.db")
    assert notes_to_show(db, onboarded=False) is None  # fresh install: they just saw /start
    db.set_setting(SEEN_KEY, "1.1.0")
    assert "What's new" in notes_to_show(db, onboarded=True)
    assert notes_to_show(db, onboarded=True) is None
