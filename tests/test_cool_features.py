"""Live streaming, follow-up buttons, actionable inbox alerts, memory manager, local search, reply context."""

import json

from helpers import TZ, FakeClient, FakeGoogle, make_agent, make_config, message

from claudebot.db import Database
from claudebot.followups import suggest_followups
from claudebot.inbox_watch import InboxWatcher
from claudebot.tools import TOOLS, build_tools
from claudebot.usage import UsageTracker


def reply(text, **kw):
    return message("end_turn", [{"type": "text", "text": text}], **kw)


# --- live streaming ---


async def test_replies_stream_live_while_written(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([reply("The final is on December 12 in GDC.")])
    seen = []

    async def on_text(snapshot):
        seen.append(snapshot)

    out = await make_agent(tmp_path, db, client).run([{"type": "text", "text": "when?"}], on_text=on_text)
    assert out == "The final is on December 12 in GDC."
    assert len(seen) >= 2 and seen[-1] == out and seen[0] != out  # grew piece by piece
    assert client.requests[0]["_streamed"] and client.requests[0]["max_tokens"] == 16000


async def test_streamed_text_accumulates_across_tool_steps(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([
        message("tool_use", [{"type": "text", "text": "Checking. "},
                             {"type": "tool_use", "id": "t", "name": "list_memories", "input": {}}]),
        reply("You have no memories yet."),
    ])
    seen = []

    async def on_text(snapshot):
        seen.append(snapshot)

    await make_agent(tmp_path, db, client).run([{"type": "text", "text": "what do you know?"}], on_text=on_text)
    assert seen[-1].startswith("Checking.") and seen[-1].endswith("You have no memories yet.")


# --- follow-up suggestions ---


def followup_reply(items, **kw):
    return message("end_turn", [{"type": "text", "text": json.dumps({"suggestions": items})}],
                   model="claude-haiku-5-5", **kw)


async def test_followups_are_short_distinct_and_capped(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([followup_reply(["Draft a reply to Sam", "Draft a reply to Sam", "x" * 200,
                                         "  ", "Add it to my calendar", "One more"])])
    out = await suggest_followups(client, UsageTracker(db, TZ, None), make_config(tmp_path),
                                  "anything from Sam?", "Sam asked to move lunch to Friday.")
    assert out[:2] == ["Draft a reply to Sam", "Add it to my calendar"] or len(out) <= 3
    assert len(out) <= 3 and len(set(out)) == len(out) and all(0 < len(s) <= 60 for s in out)
    request = client.requests[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["output_config"]["format"]["type"] == "json_schema"
    from datetime import datetime

    assert db.usage_totals(datetime(2020, 1, 1, tzinfo=TZ), source="followups")[0] == 1


async def test_followups_fail_quietly(tmp_path):
    db = Database(tmp_path / "t.db")
    bad = FakeClient([message("end_turn", [{"type": "text", "text": "not json"}], model="claude-haiku-5-5")])
    assert await suggest_followups(bad, UsageTracker(db, TZ, None), make_config(tmp_path), "q", "a") == []
    broke = FakeClient([])
    assert await suggest_followups(broke, UsageTracker(db, TZ, 0.0), make_config(tmp_path), "q", "a") == []
    assert broke.requests == []  # over budget: no call at all


# --- actionable inbox alerts ---


async def test_inbox_alerts_carry_action_buttons_and_remember_the_email(tmp_path):
    db = Database(tmp_path / "t.db")
    google = FakeGoogle(inbox=[])
    client = FakeClient([message("end_turn", [{"type": "text", "text": json.dumps({"emails": [
        {"id": "18c2f0a1b2c3d4e5", "notify": True, "summary": "Prof Lee moved the exam to Friday"}]})}],
        model="claude-haiku-5-5")])
    sent = []

    async def notify(text, actions=None):
        sent.append((text, actions))

    watcher = InboxWatcher(db, google, client, UsageTracker(db, TZ, None), make_config(tmp_path, quiet_hours=None), notify)
    await watcher.check()
    google.inbox = [{"id": "18c2f0a1b2c3d4e5", "from": "Prof Lee <lee@utexas.edu>", "subject": "Exam",
                     "snippet": "", "unread": True}]
    await watcher.check()
    text, actions = sent[0]
    datas = [data for _, data in actions]
    assert datas == ["mail:arch:18c2f0a1b2c3d4e5", "mail:draft:18c2f0a1b2c3d4e5", "mail:later:18c2f0a1b2c3d4e5"]
    assert all(len(d.encode()) <= 64 for d in datas)  # Telegram's callback_data limit
    stored = json.loads(db.get_setting("alert:18c2f0a1b2c3d4e5"))
    assert stored["subject"] == "Exam" and "lee@utexas.edu" in stored["from"]


# --- memory manager ---


def test_memory_view_lists_facts_with_delete_buttons(tmp_path):
    from claudebot.ui import memory_view

    db = Database(tmp_path / "t.db")
    assert "nothing" in memory_view(db.list_memories())[0].lower()
    for fact in ("Mom's email is mom@example.com", "Allergic to peanuts"):
        db.add_memory(fact)
    text, buttons = memory_view(db.list_memories())
    assert "Allergic to peanuts" in text
    assert [row[0].callback_data for row in buttons] == ["mem:del:1", "mem:del:2"]


# --- local awareness ---


def test_web_search_knows_where_the_owner_lives(tmp_path):
    from zoneinfo import ZoneInfo

    tools = build_tools({"city": "Austin", "region": "Texas", "country": "US"}, ZoneInfo("America/Chicago"))
    search = next(t for t in tools if t.get("name") == "web_search")
    assert search["user_location"] == {"type": "approximate", "city": "Austin", "region": "Texas",
                                       "country": "US", "timezone": "America/Chicago"}
    plain = next(t for t in TOOLS if t.get("name") == "web_search")
    assert "user_location" not in plain


async def test_agent_uses_the_configured_location(tmp_path):
    from claudebot.agent import Agent

    db = Database(tmp_path / "t.db")
    client = FakeClient([reply("Try Veracruz.")])
    agent = Agent(make_config(tmp_path, city="Austin", country="us"), db, client, UsageTracker(db, TZ, None))
    from helpers import make_context

    agent.tool_context = make_context(db)
    await agent.run([{"type": "text", "text": "best tacos near me?"}])
    search = next(t for t in client.requests[0]["tools"] if t.get("name") == "web_search")
    assert search["user_location"]["city"] == "Austin" and search["user_location"]["country"] == "US"


# --- reply context ---


def test_replying_to_the_bot_quotes_it_without_live_links():
    from claudebot.ui import reply_context

    text = reply_context("Dec 12, see https://registrar.utexas.edu/exams", from_bot=True)
    assert text.startswith("[Replying to your earlier message:") and "https://registrar" not in text
    mine = reply_context("buy milk https://store.example/milk", from_bot=False)
    assert mine.startswith("[Replying to my earlier message:") and "https://store.example/milk" in mine
    assert len(reply_context("x" * 5000, from_bot=True)) < 1700
