"""Expenses: logged by asking, summed exactly."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from helpers import TZ, make_config, make_context

from claudebot.db import Database
from claudebot.expenses import Expenses
from claudebot.tools import run_tool


def test_ledger_sums_exactly_by_category_and_currency(tmp_path):
    ledger = Expenses(Database(tmp_path / "t.db"))
    now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    for amount in (0.1, 0.2, 12.35):
        ledger.log(amount, "Food", "lunch", at=now)
    ledger.log(40, "transport", at=now)
    ledger.log(10, "food", currency="eur", at=now)
    ledger.log(99, "food", at=now - timedelta(days=40))  # last month
    data = ledger.summary(now - timedelta(days=10), now + timedelta(days=1))
    food_usd = next(c for c in data["by_category"] if c["category"] == "food" and c["currency"] == "USD")
    assert food_usd["amount"] == 12.65 and food_usd["count"] == 3  # no 12.649999
    assert data["total"] == {"USD": 52.65, "EUR": 10.0}
    with pytest.raises(ValueError):
        ledger.log(-5, "food")


async def test_expense_tools(tmp_path):
    db = Database(tmp_path / "t.db")
    ctx = make_context(db)
    result, is_error = await run_tool("log_expense", {"amount": 12.5, "category": "food", "note": "tacos"}, ctx)
    assert not is_error and json.loads(result)["logged"]["amount"] == 12.5
    now = datetime.now(TZ)
    summary = json.loads((await run_tool("spending_summary", {
        "start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(days=1)).isoformat()}, ctx))[0])
    assert summary["total"] == {"USD": 12.5}
    ctx.owner_present = False  # an email can't add to your spending
    result, is_error = await run_tool("log_expense", {"amount": 999, "category": "x"}, ctx)
    assert is_error


async def test_spent_command(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    replies = []

    async def reply_text(text, *, reply_markup=None):
        replies.append(text)

    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_spent(update, None)
    assert "No expenses" in replies[-1]
    Expenses(bot.db).log(12.5, "food")
    await bot.on_spent(update, None)
    assert "food: 12.50 USD" in replies[-1] and "Total: 12.50 USD" in replies[-1]


def test_end_dates_are_inclusive_and_currencies_validated(tmp_path):
    from claudebot.expenses import currency_code, expense_tool

    db = Database(tmp_path / "t.db")
    ledger = Expenses(db)
    ledger.log(40, "food", at=datetime(2026, 10, 31, 18, tzinfo=TZ))
    ledger.log(12.1, "food", at=datetime(2026, 10, 5, 12, tzinfo=TZ))
    total = expense_tool("spending_summary", {"start": "2026-10-01", "end": "2026-10-31"}, db, TZ)["total"]
    assert total == {"USD": 52.1}  # Oct 31 counts
    assert currency_code("$") == "USD" and currency_code("eur") == "EUR" and currency_code("US dollars") == "USD"
    with pytest.raises(ValueError):
        currency_code("monopoly money")
    assert ledger.log(1_500_000, "rent", currency="VND")["amount"] == 1_500_000
