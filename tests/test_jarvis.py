import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from anthropic.types.beta import BetaMessage

from jarvis.agent import BETAS, Agent
from jarvis.bot import split_message
from jarvis.config import Config
from jarvis.db import Database
from jarvis.reminders import next_occurrence
from jarvis.tools import TOOLS, ToolContext, run_tool

TZ = ZoneInfo("America/Chicago")


def make_config(tmp_path: Path) -> Config:
    return Config(
        telegram_token="x",
        owner_id=1,
        model="claude-opus-5-5",
        effort="medium",
        timezone=TZ,
        data_dir=tmp_path,
        google_credentials_file=tmp_path / "credentials.json",
        google_token_file=tmp_path / "token.json",
        google_token_json=None,
        daily_brief_time=None,
        new_thread_after_hours=8,
        owner_name="Ayan",
    )


class FakeGoogle:
    def __init__(self):
        self.sent = []

    def search_emails(self, query, max_results=10):
        return [{"id": "m1", "from": "sam@example.com", "subject": "Lunch?", "unread": True}]

    def send_email(self, **kwargs):
        self.sent.append(kwargs)
        return {"status": "sent", "id": "s1", "thread_id": "t1"}


def make_context(db: Database, google=None, notices=None, scheduled=None) -> ToolContext:
    notices = notices if notices is not None else []
    scheduled = scheduled if scheduled is not None else []

    async def notify(text):
        notices.append(text)

    return ToolContext(
        google=google or FakeGoogle(),
        db=db,
        tz=TZ,
        schedule_reminder=scheduled.append,
        unschedule_reminder=lambda _id: None,
        notify=notify,
    )


def message(stop_reason: str, content: list[dict]) -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
    )


class FakeClient:
    """Stands in for AsyncAnthropic, replaying canned responses and recording requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = self
        self.messages = self

    async def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)


# --- reminders ---


def test_next_occurrence_daily_and_none():
    due = datetime(2026, 10, 17, 9, 0, tzinfo=TZ)
    now = datetime(2026, 10, 17, 9, 0, 30, tzinfo=TZ)
    assert next_occurrence(due, "none", now, TZ) is None
    assert next_occurrence(due, "daily", now, TZ) == datetime(2026, 10, 18, 9, 0, tzinfo=TZ)


def test_next_occurrence_weekdays_skips_weekend():
    friday = datetime(2026, 10, 16, 8, 0, tzinfo=TZ)
    nxt = next_occurrence(friday, "weekdays", friday, TZ)
    assert nxt.weekday() == 0 and nxt.hour == 8


def test_next_occurrence_keeps_wall_time_across_dst():
    # US DST ends 2026-11-01; a 9am daily reminder must stay at 9am local.
    due = datetime(2026, 10, 31, 9, 0, tzinfo=TZ).astimezone(timezone.utc)
    nxt = next_occurrence(due, "daily", due, TZ)
    assert (nxt.hour, nxt.day) == (9, 1)


def test_next_occurrence_catches_up_after_downtime():
    due = datetime(2026, 10, 1, 7, 0, tzinfo=TZ)
    now = datetime(2026, 10, 17, 12, 0, tzinfo=TZ)
    assert next_occurrence(due, "weekly", now, TZ) == datetime(2026, 10, 22, 7, 0, tzinfo=TZ)


def test_split_message():
    text = "a" * 3000 + "\n\n" + "b" * 3000
    assert split_message(text) == ["a" * 3000, "b" * 3000]
    assert split_message("hi") == ["hi"]
    assert all(len(c) <= 4000 for c in split_message("x" * 9000))


# --- database ---


def test_threads_roll_over_after_idle(tmp_path):
    db = Database(tmp_path / "t.db")
    first, is_new = db.current_thread(idle_hours=8)
    assert is_new
    assert db.current_thread(idle_hours=8) == (first, False)
    stale = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
    db.conn.execute("UPDATE threads SET last_active_at = ?", (stale,))
    second, is_new = db.current_thread(idle_hours=8)
    assert is_new and second != first


# --- tools ---


async def test_memory_tools(tmp_path):
    db = Database(tmp_path / "t.db")
    ctx = make_context(db)
    out, err = await run_tool("remember", {"fact": "Mom's email is mom@example.com"}, ctx)
    assert not err and json.loads(out)["saved"]
    out, _ = await run_tool("list_memories", {}, ctx)
    assert json.loads(out)[0]["fact"].startswith("Mom")
    out, _ = await run_tool("forget", {"memory_id": 1}, ctx)
    assert json.loads(out)["deleted"] and db.list_memories() == []


async def test_set_reminder_schedules_and_rejects_past(tmp_path):
    db = Database(tmp_path / "t.db")
    scheduled = []
    ctx = make_context(db, scheduled=scheduled)
    when = (datetime.now(TZ) + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    out, err = await run_tool("set_reminder", {"text": "call mom", "when": when}, ctx)
    assert not err and scheduled == [json.loads(out)["reminder_id"]]
    _, err = await run_tool("set_reminder", {"text": "x", "when": "2020-01-01T09:00"}, ctx)
    assert err


async def test_send_email_notifies_owner(tmp_path):
    google, notices = FakeGoogle(), []
    ctx = make_context(Database(tmp_path / "t.db"), google=google, notices=notices)
    _, err = await run_tool(
        "send_email", {"to": "sam@example.com", "subject": "Hi", "body": "Thursday works"}, ctx
    )
    assert not err and google.sent[0]["to"] == "sam@example.com"
    assert notices == ["📤 Sent email to sam@example.com: Hi"]


async def test_bad_input_is_reported_not_raised(tmp_path):
    ctx = make_context(Database(tmp_path / "t.db"))
    out, err = await run_tool("search_emails", {}, ctx)
    assert err and "Invalid input" in out
    _, err = await run_tool("no_such_tool", {}, ctx)
    assert err


def test_tool_names_unique():
    names = [t["name"] for t in TOOLS]
    assert len(names) == len(set(names))


# --- agent loop ---


async def test_agent_tool_loop_and_append_only_history(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_memory("Prefers short replies")
    client = FakeClient(
        [
            message(
                "tool_use",
                [
                    {"type": "thinking", "thinking": "", "signature": "sig-1"},
                    {"type": "tool_use", "id": "tu_1", "name": "search_emails",
                     "input": {"query": "is:unread"}},
                ],
            ),
            message("end_turn", [{"type": "text", "text": "One unread: Sam asks about lunch."}]),
            message("end_turn", [{"type": "text", "text": "Sure."}]),
        ]
    )
    agent = Agent(make_config(tmp_path), db, client)
    agent.tool_context = make_context(db)

    reply = await agent.run([{"type": "text", "text": "anything in my inbox?"}])
    assert reply == "One unread: Sam asks about lunch."

    first, second = client.requests[0], client.requests[1]
    assert first["model"] == "claude-opus-5-5"
    assert first["betas"] == BETAS and first["fallbacks"] == "default"
    assert "thinking" not in first  # Opus 5.5 always thinks; effort is the control
    preamble = first["messages"][0]["content"][0]["text"]
    assert preamble.startswith("[Now: ") and "Prefers short replies" in preamble

    # The tool result goes back with the matching id, and the thinking block is replayed untouched.
    tool_result = second["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "tu_1" and not tool_result["is_error"]
    assert second["messages"][1]["content"][0] == {
        "type": "thinking", "thinking": "", "signature": "sig-1"
    }

    # Next turn: system, tools and every earlier message are byte-identical (preserved thinking).
    await agent.run([{"type": "text", "text": "thanks"}])
    third = client.requests[2]
    assert third["system"] == first["system"] and third["tools"] == first["tools"]
    assert third["messages"][: len(second["messages"]) + 1] == second["messages"] + [
        third["messages"][len(second["messages"])]
    ]
    assert "Prefers short replies" not in third["messages"][-1]["content"][0]["text"]


async def test_agent_resumes_pause_turn_and_reports_refusal(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient(
        [
            message("pause_turn", [{"type": "server_tool_use", "id": "srv_1", "name": "web_search",
                                    "input": {"query": "weather austin"}}]),
            message("end_turn", [{"type": "text", "text": "Sunny, 80F."}]),
            message("refusal", []),
        ]
    )
    agent = Agent(make_config(tmp_path), db, client)
    agent.tool_context = make_context(db)
    assert await agent.run([{"type": "text", "text": "weather?"}]) == "Sunny, 80F."
    assert client.requests[1]["messages"][-1]["role"] == "assistant"
    assert await agent.run([{"type": "text", "text": "something bad"}]) == "I can't help with that one."


@pytest.fixture(autouse=True)
def _no_env_leak(monkeypatch):
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)
