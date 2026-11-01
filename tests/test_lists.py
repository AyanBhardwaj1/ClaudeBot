"""Lists: shopping, packing, to-dos. Ask ClaudeBot to add things; tap to check them off."""

import json
from types import SimpleNamespace

from helpers import make_config, make_context

from claudebot.db import Database
from claudebot.lists import Lists
from claudebot.tools import run_tool


def test_lists_add_check_and_clear(tmp_path):
    lists = Lists(Database(tmp_path / "t.db"))
    added = lists.add("Shopping", ["milk", "eggs", "  milk  ", ""])
    assert [i["text"] for i in added] == ["milk", "eggs"]  # no blanks, no duplicates
    assert lists.add("shopping", ["bread"])[0]["text"] == "bread"  # names are case-insensitive
    milk = lists.items("shopping")[0]
    assert lists.toggle(milk["id"])["done"] is True
    assert lists.clear_done("Shopping") == 1
    assert [i["text"] for i in lists.items("Shopping")] == ["eggs", "bread"]
    assert lists.names() == ["Shopping"]
    lists.delete_list("shopping")
    assert lists.names() == []


def test_list_limits(tmp_path):
    lists = Lists(Database(tmp_path / "t.db"))
    lists.add("x" * 200, ["<b>" + "y" * 500])
    name = lists.names()[0]
    item = lists.items(name)[0]["text"]
    assert len(name) <= 40 and len(item) <= 200 and "<" not in item
    import pytest

    from claudebot.lists import ListFull

    with pytest.raises(ListFull) as full:
        lists.add("big", [f"item {i}" for i in range(150)])
    assert len(full.value.added) == 100 and len(lists.items("big")) == 100


async def test_list_tools(tmp_path):
    db = Database(tmp_path / "t.db")
    ctx = make_context(db)
    result, is_error = await run_tool("add_to_list", {"list": "Packing", "items": ["charger", "passport"]}, ctx)
    assert not is_error and json.loads(result)["added"] == ["charger", "passport"]
    shown = json.loads((await run_tool("show_lists", {}, ctx))[0])
    assert shown["lists"][0]["name"] == "Packing" and len(shown["lists"][0]["items"]) == 2
    item_id = shown["lists"][0]["items"][1]["id"]
    await run_tool("check_off", {"item_ids": [item_id]}, ctx)
    shown = json.loads((await run_tool("show_lists", {"list": "packing"}, ctx))[0])
    assert shown["lists"][0]["items"][1]["done"] is True

    ctx.owner_present = False  # an email read during the brief can't stuff your lists
    result, is_error = await run_tool("add_to_list", {"list": "Packing", "items": ["gift card codes"]}, ctx)
    assert is_error


async def test_lists_command_and_buttons(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    replies, edits = [], []

    async def reply_text(text, *, reply_markup=None):
        replies.append((text, reply_markup))

    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_lists(update, SimpleNamespace(args=[]))
    assert "No lists yet" in replies[-1][0]
    Lists(bot.db).add("Shopping", ["milk", "eggs"])
    await bot.on_lists(update, SimpleNamespace(args=[]))
    text, markup = replies[-1]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "milk" in text and any(d.startswith("li:") for d in datas)

    async def answer(text=None):
        pass

    async def edit(text, *, reply_markup=None):
        edits.append(text)

    milk_id = Lists(bot.db).items("Shopping")[0]["id"]
    list_id = Lists(bot.db).id_of("Shopping")
    assert f"li:{list_id}:{milk_id}" in datas and f"ld:{list_id}" in datas
    tap = SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=1), data=f"li:{list_id}:{milk_id}",
                                                         answer=answer, edit_message_text=edit))
    await bot.on_list_button(tap, None)
    assert Lists(bot.db).items("Shopping")[0]["done"] and "✅ milk" in edits[-1]
    stranger = SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=9), data=f"li:{list_id}:{milk_id}",
                                                              answer=answer, edit_message_text=edit))
    await bot.on_list_button(stranger, None)
    assert Lists(bot.db).items("Shopping")[0]["done"]  # unchanged



def test_old_buttons_cant_touch_another_lists_items(tmp_path):
    lists = Lists(Database(tmp_path / "t.db"))
    lists.add("Shopping", ["milk", "eggs"])
    eggs = lists.items("Shopping")[1]
    shopping_id = lists.id_of("Shopping")
    lists.delete_list("Shopping")
    lists.add("Packing", ["passport", "charger"])  # SQLite may hand out the freed ids again
    assert lists.toggle(eggs["id"], list_id=shopping_id) is None
    assert not any(i["done"] for i in lists.items("Packing"))


def test_list_count_is_capped(tmp_path):
    import pytest

    from claudebot.lists import MAX_LISTS

    lists = Lists(Database(tmp_path / "t.db"))
    for i in range(MAX_LISTS):
        lists.add(f"list {i}", ["x"])
    with pytest.raises(ValueError):
        lists.add("one more", ["x"])
