"""/log: what ClaudeBot actually did, recorded from results (a delivered email, a created event),
never from what the model said it did."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from helpers import TZ, FakeGoogle, make_config, make_context

from claudebot.actions import ActionLog
from claudebot.db import Database
from claudebot.outbox import Outbox
from claudebot.tools import run_tool


def test_log_keeps_what_happened_in_order_and_prunes(tmp_path):
    log = ActionLog(Database(tmp_path / "t.db"))
    now = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    log.record("email", "Sent email to sam@example.com: Lunch", now=now - timedelta(days=90))
    log.record("calendar", "Added \"Dentist\"", now=now - timedelta(hours=2))
    log.record("email", "Sent email to sam@example.com: Lunch", now=now - timedelta(hours=1))
    rows = log.since(now - timedelta(days=1))
    assert [r["kind"] for r in rows] == ["calendar", "email"]
    log.prune(now=now)
    assert len(log.since(now - timedelta(days=365))) == 2


async def test_tool_results_are_logged_only_when_they_happened(tmp_path):
    db = Database(tmp_path / "t.db")
    google = FakeGoogle()
    google.create_event = lambda *a, **k: {"status": "created", "id": "e1", "link": ""}
    google.create_draft = lambda **k: {"status": "draft saved", "draft_id": "d1"}
    ctx = make_context(db, google=google)
    await run_tool("create_calendar_event", {"summary": "Dentist", "start": "2026-11-12T15:00:00",
                                             "end": "2026-11-12T16:00:00"}, ctx)
    await run_tool("create_draft", {"to": "sam@example.com", "subject": "Lunch", "body": "Friday?"}, ctx)
    await run_tool("set_reminder", {"text": "call mom", "when": "2099-01-01T18:00:00"}, ctx)
    await run_tool("forget", {"memory_id": 12345}, ctx)  # nothing to forget: not an action
    await run_tool("send_email", {"to": "sam@example.com", "subject": "Hi", "body": "x"}, ctx)  # only queued
    await run_tool("list_calendar_events", {"start": "2026-11-12T00:00:00", "end": "2026-11-13T00:00:00"}, ctx)
    summaries = [r["summary"] for r in ActionLog(db).since(datetime.now(timezone.utc) - timedelta(minutes=1))]
    assert summaries == ['Added "Dentist" (2026-11-12T15:00:00)', "Saved a draft to sam@example.com: Lunch",
                         "Set a reminder: call mom (2099-01-01T18:00:00)"]


async def test_delivered_emails_are_logged_failed_ones_are_not(tmp_path):
    db = Database(tmp_path / "t.db")
    ui = SimpleNamespace(announce=None, edit=None, notify=None)

    async def noop(*a, **k):
        return 1

    ui.announce = ui.edit = ui.notify = noop
    outbox = Outbox(db, FakeGoogle(), 0, lambda *a: None, ui)
    await outbox.submit({"to": "sam@example.com", "subject": "Lunch", "body": "Friday?"})
    failing = Outbox(db, FakeGoogle(fail_send=True), 0, lambda *a: None, ui)
    try:
        await failing.submit({"to": "ana@example.com", "subject": "Report", "body": "x"})
    except RuntimeError:
        pass  # the tool reports the failure to Claude
    rows = ActionLog(db).since(datetime.now(timezone.utc) - timedelta(minutes=1))
    assert [r["summary"] for r in rows] == ["Sent email to sam@example.com: Lunch"]


async def test_log_command_and_tool(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    replies = []

    async def reply_text(text, reply_markup=None):
        replies.append(text)

    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_log(update, SimpleNamespace(args=[]))
    assert "Nothing yet today" in replies[-1]
    ActionLog(bot.db).record("email", "Sent email to sam@example.com: see https://evil.example/x")
    await bot.on_log(update, SimpleNamespace(args=["week"]))
    assert "Sent email to sam@example.com" in replies[-1] and "https://evil.example" not in replies[-1]

    result, is_error = await run_tool("action_log", {"days": 1}, make_context(bot.db))
    assert not is_error and json.loads(result)["actions"][0]["kind"] == "email"
    assert datetime.fromisoformat(json.loads(result)["actions"][0]["at"]).tzinfo is not None
    assert TZ  # times come back in the owner's time zone
