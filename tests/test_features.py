import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from helpers import (
    TZ,
    FakeClient,
    FakeGoogle,
    make_agent,
    make_config,
    make_context,
    message,
)

from claudebot.agent import Agent
from claudebot.db import Database
from claudebot.files import MAX_FILE_BYTES, UnsupportedFile, to_content_block
from claudebot.inbox_watch import InboxWatcher, in_quiet_hours
from claudebot.outbox import Outbox
from claudebot.tools import run_tool
from claudebot.usage import BudgetExceeded, UsageTracker, estimate_cost


def at(hour, minute=0, day=20):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


# --- usage & budget ---


def test_estimate_cost_uses_model_prices_and_cache_rates():
    usage = message("end_turn", [], usage={
        "input_tokens": 1_000_000, "output_tokens": 100_000,
        "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0,
        "server_tool_use": {"web_search_requests": 2, "web_fetch_requests": 0},
    }).usage
    # Opus 5.5: $4 in + $2 out + $0.20 cache read + 2 searches at $0.01
    assert estimate_cost("claude-opus-5-5", usage) == pytest.approx(6.22)
    assert estimate_cost("claude-haiku-5-5", usage) < 0.5


def test_unknown_model_is_priced_conservatively_not_free():
    usage = message("end_turn", [], usage={"input_tokens": 1_000_000, "output_tokens": 0}).usage
    assert estimate_cost("claude-something-new", usage) == pytest.approx(4.0)


def test_usage_tracker_totals_and_budget(tmp_path):
    db = Database(tmp_path / "t.db")
    tracker = UsageTracker(db, TZ, monthly_budget=1.0)
    big = message("end_turn", [], usage={"input_tokens": 200_000, "output_tokens": 10_000})
    tracker.record(big, "chat")  # $0.80 + $0.20 = $1.00
    assert tracker.month_cost() == pytest.approx(1.0)
    with pytest.raises(BudgetExceeded):
        tracker.check_budget()
    assert "$1.00" in tracker.summary()
    UsageTracker(db, TZ, monthly_budget=None).check_budget()  # no cap, no error


async def test_agent_refuses_when_over_budget_without_calling_claude(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([])
    agent = make_agent(tmp_path, db, client, budget=0.0)
    with pytest.raises(BudgetExceeded):
        await agent.run([{"type": "text", "text": "hi"}])
    assert client.requests == []


async def test_agent_records_usage_per_call(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([message("end_turn", [{"type": "text", "text": "Hi."}])])
    agent = make_agent(tmp_path, db, client)
    await agent.run([{"type": "text", "text": "hi"}])
    requests, cost = db.usage_totals(datetime.now(timezone.utc) - timedelta(minutes=1))
    assert requests == 1 and cost > 0


# --- notices & thread versioning ---


async def test_notices_reach_the_agent_once(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_notice("📬 New email from Sam (id m1): wants lunch Friday")
    client = FakeClient([message("end_turn", [{"type": "text", "text": "ok"}])] * 2)
    agent = make_agent(tmp_path, db, client)
    await agent.run([{"type": "text", "text": "reply yes to Sam"}])
    await agent.run([{"type": "text", "text": "thanks"}])
    first = client.requests[0]["messages"][-1]["content"][0]["text"]
    second = client.requests[1]["messages"][-1]["content"][0]["text"]
    assert "wants lunch Friday" in first and "wants lunch Friday" not in second


def test_changed_prompt_or_tools_starts_a_new_thread(tmp_path):
    db = Database(tmp_path / "t.db")
    first, _ = db.current_thread(idle_hours=8, config_hash="v1")
    assert db.current_thread(idle_hours=8, config_hash="v1") == (first, False)
    second, is_new = db.current_thread(idle_hours=8, config_hash="v2")
    assert is_new and second != first


def test_agent_config_hash_depends_on_prompt_tools_and_model(tmp_path):
    db = Database(tmp_path / "t.db")
    a = Agent(make_config(tmp_path), db, FakeClient([]), UsageTracker(db, TZ, None))
    b = Agent(make_config(tmp_path, model="claude-sonnet-5-5"), db, FakeClient([]), UsageTracker(db, TZ, None))
    c = Agent(make_config(tmp_path, owner_name="boss"), db, FakeClient([]), UsageTracker(db, TZ, None))
    assert len({a.config_hash, b.config_hash, c.config_hash}) == 3


# --- outbox / undo send ---


class FakeUI:
    def __init__(self):
        self.announced, self.edits, self.notes = [], [], []

    async def announce(self, outbox_id, text):
        self.announced.append((outbox_id, text))
        return 100 + outbox_id

    async def edit(self, message_id, text):
        self.edits.append((message_id, text))

    async def notify(self, text):
        self.notes.append(text)


EMAIL = {"to": "sam@example.com", "subject": "Hi", "body": "Thursday works",
         "cc": "", "bcc": "", "reply_to_message_id": ""}


def make_outbox(tmp_path, google=None, undo_seconds=20):
    db = Database(tmp_path / "t.db")
    scheduled, ui = [], FakeUI()
    google = google or FakeGoogle()
    outbox = Outbox(db, google, undo_seconds, lambda i, when: scheduled.append((i, when)), ui)
    return outbox, db, google, ui, scheduled


async def test_outbox_queues_then_sends_after_delay(tmp_path):
    outbox, db, google, ui, scheduled = make_outbox(tmp_path)
    result = await outbox.submit(dict(EMAIL))
    assert result["status"] == "queued" and google.sent == []
    outbox_id, when = scheduled[0]
    assert 15 <= (when - datetime.now(timezone.utc)).total_seconds() <= 21
    assert "Undo" in ui.announced[0][1] or "sam@example.com" in ui.announced[0][1]
    await outbox.deliver(outbox_id)
    assert google.sent[0]["to"] == "sam@example.com"
    assert "Sent" in ui.edits[-1][1]
    await outbox.deliver(outbox_id)  # a second delivery attempt is a no-op
    assert len(google.sent) == 1


async def test_undo_cancels_and_tells_the_agent(tmp_path):
    outbox, db, google, ui, scheduled = make_outbox(tmp_path)
    await outbox.submit(dict(EMAIL))
    outbox_id = scheduled[0][0]
    assert "Cancelled" in await outbox.undo(outbox_id)
    await outbox.deliver(outbox_id)
    assert google.sent == []
    assert any("cancelled" in n.lower() for n in db.take_notices())


async def test_undo_after_send_is_too_late(tmp_path):
    outbox, db, google, ui, scheduled = make_outbox(tmp_path)
    await outbox.submit(dict(EMAIL))
    outbox_id = scheduled[0][0]
    await outbox.deliver(outbox_id)
    assert "already" in (await outbox.undo(outbox_id)).lower()
    assert len(google.sent) == 1


async def test_send_failure_is_reported_not_swallowed(tmp_path):
    outbox, db, google, ui, scheduled = make_outbox(tmp_path, google=FakeGoogle(fail_send=True))
    await outbox.submit(dict(EMAIL))
    await outbox.deliver(scheduled[0][0])
    assert ui.notes and "couldn't send" in ui.notes[0].lower()
    assert any("failed" in n.lower() for n in db.take_notices())


async def test_zero_delay_sends_immediately(tmp_path):
    outbox, db, google, ui, scheduled = make_outbox(tmp_path, undo_seconds=0)
    result = await outbox.submit(dict(EMAIL))
    assert result["status"] == "sent" and len(google.sent) == 1 and scheduled == []


async def test_pending_emails_are_rescheduled_after_restart(tmp_path):
    outbox, db, google, ui, scheduled = make_outbox(tmp_path)
    await outbox.submit(dict(EMAIL))
    restarted = Outbox(db, google, 20, lambda i, when: scheduled.append((i, when)), ui)
    await restarted.resume()
    assert [i for i, _ in scheduled] == [1, 1]


async def test_send_interrupted_by_a_crash_is_flagged_not_resent(tmp_path):
    outbox, db, google, ui, scheduled = make_outbox(tmp_path)
    await outbox.submit(dict(EMAIL))
    db.transition_outbox(1, "pending", "sending")  # crashed mid-send
    await Outbox(db, google, 20, lambda i, when: scheduled.append((i, when)), ui).resume()
    assert google.sent == [] and len(scheduled) == 1  # only the original schedule
    assert "may not have" in ui.notes[0].lower()
    assert db.get_outbox(1)["status"] == "unknown"


# --- inbox alerts ---


def test_quiet_hours_wrap_past_midnight():
    assert in_quiet_hours(at(23, 30), "23:00-07:00")
    assert in_quiet_hours(at(3), "23:00-07:00")
    assert not in_quiet_hours(at(7), "23:00-07:00")
    assert not in_quiet_hours(at(12), "23:00-07:00")
    assert in_quiet_hours(at(13), "12:00-14:00")
    assert not in_quiet_hours(at(3), None)


def classifier_reply(items):
    return message("end_turn", [{"type": "text", "text": json.dumps({"emails": items})}],
                   model="claude-haiku-5-5")


def make_watcher(tmp_path, google, responses, notes, quiet=None):
    db = Database(tmp_path / "t.db")
    client = FakeClient(responses)

    async def notify(text):
        notes.append(text)

    config = make_config(tmp_path, quiet_hours=quiet)
    return InboxWatcher(db, google, client, UsageTracker(db, TZ, None), config, notify), db, client


async def test_first_check_only_takes_a_baseline(tmp_path):
    notes = []
    watcher, db, client = make_watcher(tmp_path, FakeGoogle(), [], notes)
    assert await watcher.check(at(12)) == []
    assert notes == [] and client.requests == []


async def test_alerts_only_for_new_important_email_and_records_notice(tmp_path):
    google, notes = FakeGoogle(), []
    watcher, db, client = make_watcher(tmp_path, google, [classifier_reply([
        {"id": "m2", "notify": True, "summary": "Prof Lee moved the exam to Friday"},
        {"id": "m3", "notify": False, "summary": "Receipt"},
    ])], notes)
    await watcher.check(at(12))  # baseline: m1 is old news
    google.inbox = google.inbox + [
        {"id": "m2", "from": "Prof Lee <lee@utexas.edu>", "subject": "Exam", "snippet": "moved", "unread": True},
        {"id": "m3", "from": "store@shop.com", "subject": "Receipt", "snippet": "thanks", "unread": True},
    ]
    alerts = await watcher.check(at(12, 10))
    assert [a["id"] for a in alerts] == ["m2"]
    assert len(notes) == 1 and "exam to Friday" in notes[0]
    sent_ids = json.loads(client.requests[0]["messages"][0]["content"].split("<emails>")[1].split("</emails>")[0])
    assert {e["id"] for e in sent_ids} == {"m2", "m3"}  # m1 was not re-classified
    assert "m2" in " ".join(db.take_notices())
    assert await watcher.check(at(12, 20)) == []  # nothing new, no repeat alert


async def test_classifier_cannot_invent_ids_or_flood(tmp_path):
    google, notes = FakeGoogle(inbox=[]), []
    watcher, db, client = make_watcher(tmp_path, google, [classifier_reply([
        {"id": "evil", "notify": True, "summary": "x"},
        {"id": "m2", "notify": True, "summary": "y" * 1000},
    ])], notes)
    await watcher.check(at(12))
    google.inbox = [{"id": "m2", "from": "a@b.c", "subject": "s", "snippet": "", "unread": True}]
    alerts = await watcher.check(at(12, 10))
    assert [a["id"] for a in alerts] == ["m2"] and len(alerts[0]["summary"]) <= 200


async def test_classifier_failure_falls_back_to_plain_list(tmp_path):
    google, notes = FakeGoogle(inbox=[]), []
    watcher, db, client = make_watcher(
        tmp_path, google, [message("end_turn", [{"type": "text", "text": "not json"}])], notes
    )
    await watcher.check(at(12))
    google.inbox = [{"id": "m2", "from": "Sam", "subject": "Lunch?", "snippet": "", "unread": True}]
    alerts = await watcher.check(at(12, 10))
    assert [a["id"] for a in alerts] == ["m2"] and "Lunch?" in notes[0]


async def test_quiet_hours_skip_checks(tmp_path):
    notes = []
    watcher, db, client = make_watcher(tmp_path, FakeGoogle(), [], notes, quiet="23:00-07:00")
    assert await watcher.check(at(2)) == []
    assert db.get_setting("inbox_baseline") is None  # didn't even look


# --- files & attachments ---


def test_pdf_and_text_and_image_become_content_blocks():
    pdf = to_content_block(b"%PDF-1.4 x", "application/pdf", "syllabus.pdf")
    assert pdf["type"] == "document" and pdf["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(pdf["source"]["data"]) == b"%PDF-1.4 x"
    txt = to_content_block("héllo".encode(), "text/plain", "notes.txt")
    assert txt["source"] == {"type": "text", "media_type": "text/plain", "data": "héllo"}
    img = to_content_block(b"\x89PNG", "image/png", "a.png")
    assert img["type"] == "image"


def test_unsupported_or_huge_files_are_rejected():
    with pytest.raises(UnsupportedFile):
        to_content_block(b"x", "application/zip", "a.zip")
    with pytest.raises(UnsupportedFile):
        to_content_block(b"x" * (MAX_FILE_BYTES + 1), "application/pdf", "big.pdf")


async def test_attachment_tool_returns_document_blocks(tmp_path):
    google = FakeGoogle()
    google.attachments[("m1", "syllabus.pdf")] = (b"%PDF-1.4", "application/pdf")
    ctx = make_context(Database(tmp_path / "t.db"), google=google)
    content, err = await run_tool("read_email_attachment", {"message_id": "m1", "filename": "syllabus.pdf"}, ctx)
    assert not err and isinstance(content, list)
    assert content[-1]["type"] == "document"


async def test_attachment_tool_reports_unsupported_types(tmp_path):
    google = FakeGoogle()
    google.attachments[("m1", "a.zip")] = (b"PK", "application/zip")
    ctx = make_context(Database(tmp_path / "t.db"), google=google)
    content, err = await run_tool("read_email_attachment", {"message_id": "m1", "filename": "a.zip"}, ctx)
    assert err and "zip" in content
