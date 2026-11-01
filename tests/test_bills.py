"""Bills with monthly reminders and a Paid button."""

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from helpers import TZ, make_config

from claudebot.bills import Bills, next_due
from claudebot.db import Database
from claudebot.expenses import Expenses
from claudebot.tools import run_tool


def test_next_due_handles_short_months():
    assert next_due(1, date(2026, 11, 10)) == date(2026, 12, 1)
    assert next_due(31, date(2026, 11, 10)) == date(2026, 11, 30)
    assert next_due(10, date(2026, 11, 10)) == date(2026, 11, 10)
    assert next_due(31, date(2027, 2, 1)) == date(2027, 2, 28)


async def test_bill_tool_reminder_and_paid_button(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    bot.schedule_reminder = lambda rid: None
    bot.unschedule_reminder = lambda rid: None
    ctx = bot.agent.tool_context
    result, is_error = await run_tool("add_bill", {"name": "Rent", "amount": 1200, "day": 1}, ctx)
    assert not is_error and json.loads(result)["bill"]["name"] == "Rent"
    reminders = bot.db.active_reminders()
    assert len(reminders) == 1 and reminders[0]["repeat"] == "monthly"
    remind = datetime.fromisoformat(reminders[0]["due_at"]).astimezone(TZ)
    assert remind.hour == 9 and (next_due(1, remind.date()) - remind.date()).days == 2

    replies, edits = [], []

    async def reply_text(text, *, reply_markup=None):
        replies.append((text, reply_markup))

    async def answer(text=None):
        pass

    async def edit(text, *, reply_markup=None):
        edits.append(text)

    await bot.on_bills(SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text)), None)
    assert "Rent: 1,200.00 USD" in replies[-1][0] and "Each month: 1,200.00 USD" in replies[-1][0]

    def tap(data, user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id), data=data,
                                                              answer=answer, edit_message_text=edit))

    await bot.on_bill_button(tap("bill:paid:1", user_id=999), None)
    await bot.on_bill_button(tap("bill:paid:1"), None)
    spent = Expenses(bot.db).summary(datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc) + timedelta(days=1))
    assert spent["total"] == {"USD": 1200.0}
    await bot.on_bill_button(tap("bill:del:1"), None)
    assert Bills(bot.db).all() == [] and bot.db.active_reminders() == []
    ctx.owner_present = False
    assert (await run_tool("add_bill", {"name": "x", "amount": 1, "day": 1}, ctx))[1]  # needs the owner


def test_bill_validation(tmp_path):
    import pytest

    bills = Bills(Database(tmp_path / "t.db"))
    with pytest.raises(ValueError):
        bills.add("Rent", 1200, 32)
    bills.add("Rent", 1200, 1)
    bills.add("rent", 1300, 1)  # same bill, updated
    assert [(b["name"], b["amount"]) for b in bills.all()] == [("rent", 1300.0)]



async def test_bills_can_be_listed_for_the_brief(tmp_path):
    from helpers import make_context

    from claudebot.bot import brief_prompt

    db = Database(tmp_path / "t.db")
    Bills(db).add("Rent", 1200, 1)
    listed = json.loads((await run_tool("list_bills", {}, make_context(db)))[0])["bills"]
    assert listed[0]["name"] == "Rent" and listed[0]["next_due"].endswith("-01")
    assert "list_bills" in brief_prompt(make_config(tmp_path), None)
