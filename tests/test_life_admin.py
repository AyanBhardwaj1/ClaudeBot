"""Life-admin radar: an important email with a date (a bill, a deadline, a delivery, a trip) gets a
one-tap reminder for the morning before."""

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from helpers import TZ, FakeClient, FakeGoogle, make_config, message

from claudebot.db import Database
from claudebot.inbox_watch import InboxWatcher, parse_due
from claudebot.usage import UsageTracker


def test_due_dates_must_be_real_and_soon():
    today = date(2026, 11, 10)
    assert parse_due("2026-11-20", today) == date(2026, 11, 20)
    assert parse_due("2026-11-09", today) is None  # past
    assert parse_due("2027-06-01", today) is None  # too far to be a nudge
    assert parse_due("next Friday", today) is None and parse_due("", today) is None


async def test_dated_alerts_get_a_reminder_button_instead_of_later(tmp_path):
    db = Database(tmp_path / "t.db")
    google = FakeGoogle(inbox=[])
    notes = []

    async def notify(text, actions=None):
        notes.append((text, actions))

    due = (datetime.now(TZ) + timedelta(days=5)).date().isoformat()
    verdicts = {"emails": [
        {"id": "abc111", "notify": True, "summary": "Austin Energy bill $84 due", "due": due, "kind": "bill"},
        {"id": "abc222", "notify": True, "summary": "Sam asked about lunch", "due": "", "kind": "other"},
    ]}
    client = FakeClient([message("end_turn", [{"type": "text", "text": json.dumps(verdicts)}], model="claude-haiku-5-5")])
    watcher = InboxWatcher(db, google, client, UsageTracker(db, TZ, None), make_config(tmp_path, quiet_hours=None), notify)
    await watcher.check()  # baseline
    google.inbox = [{"id": i, "from": "Billing <bill@energy.com>", "subject": "Your bill", "snippet": "", "unread": True}
                    for i in ("abc111", "abc222")]
    await watcher.check()
    actions = dict((data, label) for label, data in notes[-1][1])
    assert "mail:due:abc111" in actions and "mail:later:abc111" not in actions
    assert "mail:later:abc222" in actions
    assert json.loads(db.get_setting("alert:abc111"))["due"] == due
    assert "due" in client.requests[0]["system"].lower()


async def test_tapping_due_reminds_the_morning_before(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    bot.schedule_reminder = lambda rid: None
    due = (datetime.now(TZ) + timedelta(days=5)).date()
    bot.db.set_setting("alert:abc111", json.dumps({"from": "Austin Energy <bill@energy.com>", "subject": "Your bill",
                                                    "due": due.isoformat()}))
    answers = []

    async def answer(text=None):
        answers.append(text)

    tap = SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=1), data="mail:due:abc111",
                                                         answer=answer))
    await bot.on_mail_action(tap, None)
    await bot.on_mail_action(tap, None)
    reminders = bot.db.active_reminders()
    assert len(reminders) == 1 and answers[-1] == "Already on your reminders."
    when = datetime.fromisoformat(reminders[0]["due_at"]).astimezone(TZ)
    assert when.date() == due - timedelta(days=1) and when.hour == 9
    assert "Your bill" in reminders[0]["text"] and due.strftime("%b") in reminders[0]["text"]
