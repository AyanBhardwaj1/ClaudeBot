"""Monthly and yearly repeats, and Done / Snooze buttons on fired reminders."""

from datetime import datetime
from types import SimpleNamespace

from helpers import TZ, make_config

from claudebot.reminders import next_occurrence, previous_window


def at(y, m, d, h=9):
    return datetime(y, m, d, h, tzinfo=TZ)


def test_monthly_and_yearly_repeats():
    assert next_occurrence(at(2026, 1, 15), "monthly", at(2026, 1, 20), TZ) == at(2026, 2, 15)
    assert next_occurrence(at(2026, 1, 31), "monthly", at(2026, 2, 1), TZ) == at(2026, 2, 28)  # short month
    assert next_occurrence(at(2026, 12, 1), "monthly", at(2026, 12, 2), TZ) == at(2027, 1, 1)
    assert next_occurrence(at(2026, 5, 3), "yearly", at(2026, 5, 4), TZ) == at(2027, 5, 3)
    assert next_occurrence(at(2028, 2, 29), "yearly", at(2028, 3, 1), TZ) == at(2029, 2, 28)
    assert next_occurrence(at(2026, 3, 1), "monthly", at(2026, 7, 10), TZ) == at(2026, 8, 1)  # catches up
    assert previous_window(at(2026, 3, 1), "monthly").days >= 28


async def test_fired_reminders_have_done_and_snooze(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    sent, edits, scheduled = [], [], []

    async def send_to_owner(text, reply_markup=None):
        sent.append((text, reply_markup))

    bot.send_to_owner = send_to_owner
    bot.schedule_reminder = scheduled.append
    rid = bot.db.add_reminder("call mom", at(2026, 11, 10), "none", False)
    await bot._reminder_job(SimpleNamespace(job=SimpleNamespace(data=rid)))
    text, markup = sent[-1]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert text == "⏰ call mom" and datas == [f"rem:done:{rid}", f"rem:1h:{rid}", f"rem:tmr:{rid}"]

    async def answer(text=None):
        pass

    async def edit(text, reply_markup=None):
        edits.append(text)

    def tap(data, user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id), data=data,
                                                              answer=answer, edit_message_text=edit))

    await bot.on_reminder_button(tap(f"rem:1h:{rid}", user_id=999), None)
    assert scheduled == []
    await bot.on_reminder_button(tap(f"rem:1h:{rid}"), None)
    snoozed = bot.db.active_reminders()
    assert len(snoozed) == 1 and snoozed[0]["text"] == "call mom" and "Snoozed" in edits[-1]
    await bot.on_reminder_button(tap(f"rem:tmr:{rid}"), None)
    later = bot.db.active_reminders()
    assert len(later) == 1  # snoozing again moves it, it doesn't pile up
    when = datetime.fromisoformat(later[0]["due_at"]).astimezone(TZ)
    assert when.hour == 9
    await bot.on_reminder_button(tap(f"rem:done:{rid}"), None)
    assert "✅" in edits[-1]


async def test_follow_up_if_no_reply(tmp_path, monkeypatch):
    import json as _json

    from claudebot.bot import TelegramBot
    from claudebot.outbox import Outbox

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    edits, scheduled, answers = [], [], []

    class UI:
        async def announce(self, outbox_id, text, needs_approval=False):
            return 77

        async def edit(self, message_id, text, followup_id=None):
            edits.append((text, followup_id))

        async def notify(self, text):
            pass

    from helpers import FakeGoogle

    outbox = Outbox(bot.db, FakeGoogle(), 20, lambda *a: None, UI())
    queued = await outbox.submit({"to": "lee@uni.edu", "subject": "Extension?", "body": "Could I have until Friday?"})
    await outbox.deliver(queued["outbox_id"])
    assert edits[-1] == ("📤 Sent to lee@uni.edu: Extension?", queued["outbox_id"])

    bot.schedule_reminder = scheduled.append

    async def answer(text=None):
        answers.append(text)

    def tap(user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(
            from_user=SimpleNamespace(id=user_id), data=f"nr:{queued['outbox_id']}", answer=answer))

    await bot.on_no_reply_button(tap(user_id=999), None)
    assert scheduled == []
    await bot.on_no_reply_button(tap(), None)
    await bot.on_no_reply_button(tap(), None)
    tasks = bot.db.active_reminders()
    assert len(tasks) == 1 and tasks[0]["run_as_task"] and "Extension?" in tasks[0]["text"]
    assert "don't send it" in tasks[0]["text"] and answers[-1] == "Already on it."
    assert _json  # the email itself stays in the outbox row



async def test_added_events_get_a_remove_card(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot
    from claudebot.tools import run_tool

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    sent, deleted, edits = [], [], []

    async def send_to_owner(text, reply_markup=None):
        sent.append((text, reply_markup))

    bot.send_to_owner = send_to_owner
    bot.google.create_event = lambda *a, **k: {"status": "created", "id": "evt_abc", "link": ""}
    bot.google.delete_event = lambda event_id: deleted.append(event_id) or {"status": "deleted"}
    ctx = bot.agent.tool_context
    ctx.owner_present = False  # even in an unattended turn, the owner sees it
    await run_tool("create_calendar_event", {"summary": "Dentist http://x.co", "start": "2026-11-12T15:00:00",
                                             "end": "2026-11-12T16:00:00"}, ctx)
    text, markup = sent[-1]
    assert text.startswith("📅 Added: Dentist") and "http://x.co" not in text and "Thu Nov 12 15:00" in text
    data = markup.inline_keyboard[0][0].callback_data

    async def answer(text=None):
        pass

    async def edit(text, reply_markup=None):
        edits.append(text)

    def tap(user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id), data=data,
                                                              answer=answer, edit_message_text=edit))

    await bot.on_event_undo(tap(user_id=999), None)
    assert deleted == []
    await bot.on_event_undo(tap(), None)
    await bot.on_event_undo(tap(), None)
    assert deleted == ["evt_abc"] and "Removed" in edits[-1]
