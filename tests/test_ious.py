"""IOUs: who owes whom, summed by code."""

import json
from types import SimpleNamespace

from helpers import make_config, make_context

from claudebot.db import Database
from claudebot.ious import Ious
from claudebot.tools import run_tool


def test_balances_net_out_and_settle(tmp_path):
    ious = Ious(Database(tmp_path / "t.db"))
    ious.add("Alex", 20, True, "dinner")
    ious.add("alex", 5.5, False, "coffee")
    ious.add("Sam", 15, False)
    balances = {b["person"].lower(): b["balance"] for b in ious.balances()}
    assert balances == {"alex": 14.5, "sam": -15.0}
    ious.settle("Alex")
    assert [b["person"] for b in ious.balances()] == ["Sam"]


async def test_iou_tools_and_command(tmp_path, monkeypatch):
    db = Database(tmp_path / "t.db")
    ctx = make_context(db)
    await run_tool("record_iou", {"person": "Alex", "amount": 20, "they_owe_me": True, "note": "dinner"}, ctx)
    result = json.loads((await run_tool("list_ious", {}, ctx))[0])
    assert result["balances"][0]["balance"] == 20.0
    ctx.owner_present = False
    _, is_error = await run_tool("record_iou", {"person": "x", "amount": 999, "they_owe_me": False}, ctx)
    assert is_error

    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    Ious(bot.db).add("Alex", 20, True)
    replies, edits = [], []

    async def reply_text(text, *, reply_markup=None):
        replies.append((text, reply_markup))

    async def answer(text=None):
        pass

    async def edit(text, *, reply_markup=None):
        edits.append(text)

    await bot.on_owed(SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text)), None)
    assert "Alex owes you 20.00 USD" in replies[-1][0]
    data = replies[-1][1].inline_keyboard[0][0].callback_data
    await bot.on_iou_button(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=1), data=data, answer=answer, edit_message_text=edit)), None)
    assert "All square" in edits[-1]
