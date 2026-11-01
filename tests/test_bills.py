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
    told = []

    async def notify(text):
        told.append(text)

    ctx.notify_owner = notify
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


async def test_bill_reminders_are_tied_to_their_bill(tmp_path, monkeypatch):
    """Batch 6 N-3/N-4/N-6/N-8: replace and delete touch only the bill's own reminder; Paid logs once."""
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    bot.schedule_reminder = lambda rid: None
    bot.unschedule_reminder = lambda rid: None
    mine = bot.db.add_reminder("Gas (check the meter reading)", datetime(2030, 1, 1, tzinfo=TZ), "monthly", False)
    bot.add_bill("Gas (garage)", 40, 3)
    bot.add_bill("Gas", 60, 10)
    bot.add_bill("gas", 65, 12)  # same bill, new amount and day: one reminder, the new one
    texts = sorted(r["text"] for r in bot.db.active_reminders())
    assert texts == ["Gas (check the meter reading)", "🧾 Gas (garage) (40.00 USD) is due on the 3rd",
                     "🧾 gas (65.00 USD) is due on the 12th"]

    async def answer(text=None):
        answers.append(text)

    async def edit(text, *, reply_markup=None):
        from telegram.error import BadRequest
        raise BadRequest("Message is not modified")

    def tap(data):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=1), data=data,
                                                              answer=answer, edit_message_text=edit))

    answers = []
    gas = next(b for b in Bills(bot.db).all() if b["name"] == "gas")
    await bot.on_bill_button(tap(f"bill:paid:{gas['id']}"), None)
    await bot.on_bill_button(tap(f"bill:paid:{gas['id']}"), None)  # double tap
    spent = Expenses(bot.db).summary(datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc) + timedelta(days=1))
    assert spent["total"] == {"USD": 65.0} and "already" in answers[-1]
    await bot.on_bill_button(tap(f"bill:del:{gas['id']}"), None)
    assert sorted(r["text"] for r in bot.db.active_reminders()) == texts[:2]
    assert mine in [r["id"] for r in bot.db.active_reminders()]
    new = bot.add_bill("Gym", 30, 5)
    assert new["id"] > gas["id"]  # ids aren't reused, so an old card's button can't hit a new bill


def test_bill_reminder_names_the_due_day():
    from claudebot.bills import reminder_text

    assert reminder_text({"name": "Rent", "amount": 1200, "currency": "USD", "day": 1}) == \
        "🧾 Rent (1,200.00 USD) is due on the 1st"
    assert "31st (or the month's last day)" in reminder_text({"name": "X", "amount": 1, "currency": "USD", "day": 31})


async def test_bill_tool_tells_the_owner(tmp_path):
    from helpers import make_context

    from claudebot.tools import run_tool

    db = Database(tmp_path / "t.db")
    told = []
    ctx = make_context(db)

    async def notify(text):
        told.append(text)

    ctx.notify_owner = notify
    ctx.add_bill = lambda name, amount, day, currency="USD": Bills(db).add(name, amount, day, currency)[0]
    result, is_error = await run_tool("add_bill", {"name": "Rent", "amount": 1200, "day": 1}, ctx)
    assert not is_error and told and told[0].startswith("🧾 New bill: Rent")


async def test_old_bills_without_a_reminder_id_still_clean_up(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    bot.unschedule_reminder = lambda rid: None
    when = datetime(2030, 1, 1, tzinfo=TZ)
    old = bot.db.add_reminder("Gas (60.00 USD) is due in 2 days", when, "monthly", False)
    other = bot.db.add_reminder("Gas (60.00 USD) is due in 2 days, check", when, "monthly", False)
    bot._cancel_bill_reminder({"id": 1, "name": "Gas", "amount": 60.0, "currency": "USD", "day": 3})
    assert [r["id"] for r in bot.db.active_reminders()] == [other] and old != other


def test_paid_settles_the_nearest_due_date(tmp_path):
    """Batch 7 N-11: paying early or late settles that bill's due date, not the month of the tap."""
    from claudebot.bills import paying_for

    assert paying_for(1, date(2026, 10, 30)) == date(2026, 11, 1)
    assert paying_for(1, date(2026, 11, 2)) == date(2026, 11, 1)
    assert paying_for(1, date(2026, 10, 3)) == date(2026, 10, 1)
    assert paying_for(15, date(2026, 10, 15)) == date(2026, 10, 15)
    assert paying_for(31, date(2026, 3, 2)) == date(2026, 2, 28)
    bills = Bills(Database(tmp_path / "t.db"))
    bill, _ = bills.add("Rent", 1200, 1)
    assert bills.mark_paid(bill["id"], date(2026, 10, 30))
    assert not bills.mark_paid(bill["id"], date(2026, 11, 2))  # same Nov 1 bill
    assert bills.mark_paid(bill["id"], date(2026, 11, 29))  # Dec 1 is next
