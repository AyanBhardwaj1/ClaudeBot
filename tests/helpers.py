"""Shared fakes and builders for the test suite."""

import copy
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from anthropic.types.beta import BetaMessage

from claudebot.agent import Agent
from claudebot.config import Config
from claudebot.db import Database
from claudebot.tools import ToolContext
from claudebot.usage import UsageTracker

TZ = ZoneInfo("America/Chicago")


def make_config(tmp_path: Path, **overrides) -> Config:
    values = dict(
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
    values.update(overrides)
    return Config(**values)


class FakeGoogle:
    def __init__(self, inbox=None, fail_send=False):
        self.sent = []
        self.inbox = inbox if inbox is not None else [
            {"id": "m1", "from": "sam@example.com", "subject": "Lunch?", "snippet": "Friday?", "unread": True}
        ]
        self.fail_send = fail_send
        self.attachments = {}

    def search_emails(self, query, max_results=10):
        return list(self.inbox)

    def send_email(self, **kwargs):
        if self.fail_send:
            raise RuntimeError("smtp down")
        self.sent.append(kwargs)
        return {"status": "sent", "id": "s1", "thread_id": "t1"}

    def get_attachment(self, message_id, filename):
        return self.attachments[(message_id, filename)]


def make_context(db: Database, google=None, scheduled=None, submitted=None) -> ToolContext:
    scheduled = scheduled if scheduled is not None else []
    submitted = submitted if submitted is not None else []

    async def send_email(email, needs_approval=False):
        submitted.append(email)
        return {"status": "queued", "outbox_id": len(submitted), "sends_in_seconds": 20}

    return ToolContext(
        google=google or FakeGoogle(),
        db=db,
        tz=TZ,
        schedule_reminder=scheduled.append,
        unschedule_reminder=lambda _id: None,
        send_email=send_email,
    )


def make_agent(tmp_path: Path, db: Database, client, budget=None, google=None) -> Agent:
    tracker = UsageTracker(db, TZ, budget)
    agent = Agent(make_config(tmp_path), db, client, tracker)
    agent.tool_context = make_context(db, google=google)
    return agent


def message(stop_reason: str, content: list[dict], model="claude-opus-5-5", usage=None) -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": usage or {"input_tokens": 10, "output_tokens": 10},
        }
    )


class FakeFiles:
    """Stands in for client.files: uploads get ids, deletes are recorded."""

    def __init__(self):
        self.uploaded, self.deleted = [], []
        self.fail_upload = None
        self.fail_delete = {}

    async def upload(self, *, file):
        if self.fail_upload:
            raise self.fail_upload
        self.uploaded.append(file)
        return SimpleNamespace(id=f"file_{len(self.uploaded)}")

    async def delete(self, file_id):
        if file_id in self.fail_delete:
            raise self.fail_delete[file_id]
        self.deleted.append(file_id)


class FakeClient:
    """Stands in for AsyncAnthropic, replaying canned responses and recording requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = self
        self.messages = self
        self.files = FakeFiles()

    async def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
