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



async def test_trips_and_deadlines_get_an_add_to_calendar_button(tmp_path, monkeypatch):
    db = Database(tmp_path / "t.db")
    google = FakeGoogle(inbox=[])
    notes = []

    async def notify(text, actions=None):
        notes.append(actions)

    due = (datetime.now(TZ) + timedelta(days=9)).date().isoformat()
    verdicts = {"emails": [{"id": "abc333", "notify": True, "summary": "Flight AA123 to NYC", "due": due,
                            "kind": "travel"}]}
    client = FakeClient([message("end_turn", [{"type": "text", "text": json.dumps(verdicts)}], model="claude-haiku-5-5")])
    watcher = InboxWatcher(db, google, client, UsageTracker(db, TZ, None), make_config(tmp_path, quiet_hours=None), notify)
    await watcher.check()
    google.inbox = [{"id": "abc333", "from": "American <no-reply@aa.com>", "subject": "Your trip", "snippet": "",
                     "unread": True}]
    await watcher.check()
    datas = [data for _, data in notes[-1]]
    assert datas == ["mail:arch:abc333", "mail:cal:abc333", "mail:due:abc333"]

    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    conversed = []

    async def converse(content, question, effort=None, owner_present=True):
        conversed.append((content[0]["text"], owner_present))

    async def answer(text=None):
        pass

    bot._converse = converse
    await bot.on_mail_action(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=1), data="mail:cal:abc333", answer=answer)), None)
    prompt, owner_present = conversed[0]
    assert "abc333" in prompt and "without attendees" in prompt and owner_present is False


async def test_hourly_digest_holds_alerts_and_sends_them_together(tmp_path):
    db = Database(tmp_path / "t.db")
    db.set_setting("alert_mode", "hourly")
    google = FakeGoogle(inbox=[])
    notes = []

    async def notify(text, actions=None):
        notes.append((text, actions))

    def verdict(*ids):
        body = {"emails": [{"id": i, "notify": True, "summary": f"about {i}", "due": "", "kind": "other"} for i in ids]}
        return message("end_turn", [{"type": "text", "text": json.dumps(body)}], model="claude-haiku-5-5")

    client = FakeClient([verdict("abc111"), verdict("abc222")])
    watcher = InboxWatcher(db, google, client, UsageTracker(db, TZ, None), make_config(tmp_path, quiet_hours=None), notify)
    await watcher.check()
    google.inbox = [{"id": "abc111", "from": "a@b.c", "subject": "one", "snippet": "", "unread": True}]
    await watcher.check()
    google.inbox.append({"id": "abc222", "from": "d@e.f", "subject": "two", "snippet": "", "unread": True})
    await watcher.check()
    assert notes == []  # held for the digest
    assert await watcher.flush_digest() == 2
    text, actions = notes[-1]
    assert text.startswith("📬 2 important emails this hour") and "about abc111" in text and "about abc222" in text
    assert any(data == "mail:arch:abc111" for _, data in actions)
    assert await watcher.flush_digest() == 0



async def test_meeting_requests_get_a_propose_times_button(tmp_path, monkeypatch):
    db = Database(tmp_path / "t.db")
    google = FakeGoogle(inbox=[])
    notes = []

    async def notify(text, actions=None):
        notes.append(actions)

    verdicts = {"emails": [{"id": "abc444", "notify": True, "summary": "Dana wants to meet next week", "due": "",
                            "kind": "meeting"}]}
    client = FakeClient([message("end_turn", [{"type": "text", "text": json.dumps(verdicts)}], model="claude-haiku-5-5")])
    watcher = InboxWatcher(db, google, client, UsageTracker(db, TZ, None), make_config(tmp_path, quiet_hours=None), notify)
    await watcher.check()
    google.inbox = [{"id": "abc444", "from": "Dana <dana@acme.com>", "subject": "Coffee?", "snippet": "", "unread": True}]
    await watcher.check()
    assert "mail:times:abc444" in [data for _, data in notes[-1]]

    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    conversed = []

    async def converse(content, question, effort=None, owner_present=True):
        conversed.append((content[0]["text"], owner_present))

    async def answer(text=None):
        pass

    bot._converse = converse
    await bot.on_mail_action(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=1), data="mail:times:abc444", answer=answer)), None)
    prompt, owner_present = conversed[0]
    assert "find_free_time" in prompt and "abc444" in prompt and owner_present is False


async def test_big_digests_go_out_in_pages_and_nothing_is_dropped(tmp_path):
    db = Database(tmp_path / "t.db")
    db.set_setting("alert_digest", json.dumps([{"id": f"abc{i:03d}", "from": "a@b.c", "subject": f"s{i}",
                                                 "summary": f"email {i}", "due": "", "kind": "other"} for i in range(23)]))
    notes = []

    async def notify(text, actions=None):
        notes.append(text)

    watcher = InboxWatcher(db, FakeGoogle(inbox=[]), FakeClient([]), UsageTracker(db, TZ, None),
                           make_config(tmp_path, quiet_hours=None), notify)
    assert await watcher.flush_digest() == 23
    assert len(notes) == 3 and all(f"email {i}" in "".join(notes) for i in range(23))
    assert "more" not in "".join(notes) and json.loads(db.get_setting("alert_digest")) == []



async def test_urgent_email_skips_the_hourly_digest(tmp_path):
    db = Database(tmp_path / "t.db")
    db.set_setting("alert_mode", "hourly")
    google = FakeGoogle(inbox=[])
    notes = []

    async def notify(text, actions=None):
        notes.append(text)

    body = {"emails": [
        {"id": "abc111", "notify": True, "summary": "Flight AA12 cancelled today", "due": "", "kind": "travel", "urgent": True},
        {"id": "abc222", "notify": True, "summary": "Sam about lunch", "due": "", "kind": "other", "urgent": False}]}
    client = FakeClient([message("end_turn", [{"type": "text", "text": json.dumps(body)}], model="claude-haiku-5-5")])
    watcher = InboxWatcher(db, google, client, UsageTracker(db, TZ, None), make_config(tmp_path, quiet_hours=None), notify)
    await watcher.check()
    google.inbox = [{"id": i, "from": "a@b.c", "subject": "s", "snippet": "", "unread": True} for i in ("abc111", "abc222")]
    await watcher.check()
    assert len(notes) == 1 and notes[0].startswith("🚨 Urgent email") and "cancelled" in notes[0]
    assert [a["id"] for a in json.loads(db.get_setting("alert_digest"))] == ["abc222"]
