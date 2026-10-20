"""Files go to the Files API once; conversations keep only their ids."""

from datetime import datetime, timedelta, timezone

import anthropic
import httpx2
from helpers import FakeClient, FakeGoogle, make_agent, make_context, message

from claudebot.db import Database
from claudebot.files import FileUploader, clean_up_uploads
from claudebot.tools import run_tool

PDF = b"%PDF-1.4 hello"


def api_error(status):
    request = httpx2.Request("DELETE", "https://api.anthropic.com/v1/files/x")
    cls = {404: anthropic.NotFoundError, 500: anthropic.InternalServerError}[status]
    return cls("err", response=httpx2.Response(status, request=request), body=None)


async def test_upload_returns_a_file_reference_block(tmp_path):
    db, client = Database(tmp_path / "t.db"), FakeClient([])
    block = await FileUploader(client, db).to_block(PDF, "application/pdf", "syllabus.pdf")
    assert block == {"type": "document", "source": {"type": "file", "file_id": "file_1"}, "title": "syllabus.pdf"}
    assert client.files.uploaded == [("syllabus.pdf", PDF, "application/pdf")]


async def test_text_is_uploaded_as_plain_text_and_images_as_images(tmp_path):
    db, client = Database(tmp_path / "t.db"), FakeClient([])
    uploader = FileUploader(client, db)
    text = await uploader.to_block("héllo".encode(), "text/csv", "grades.csv")
    assert text["source"]["type"] == "file" and client.files.uploaded[0] == ("grades.csv.txt", "héllo".encode(), "text/plain")
    assert text["title"] == "grades.csv"  # Claude still sees the real name
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 8
    image = await uploader.to_block(png, "image/png", "a.png")
    assert image == {"type": "image", "source": {"type": "file", "file_id": "file_2"}}


async def test_upload_failure_falls_back_to_sending_the_file_inline(tmp_path):
    db, client = Database(tmp_path / "t.db"), FakeClient([])
    client.files.fail_upload = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))
    block = await FileUploader(client, db).to_block(PDF, "application/pdf", "s.pdf")
    assert block["source"]["type"] == "base64"


async def test_invalid_files_are_rejected_before_uploading(tmp_path):
    import pytest

    from claudebot.files import UnsupportedFile

    db, client = Database(tmp_path / "t.db"), FakeClient([])
    with pytest.raises(UnsupportedFile):
        await FileUploader(client, db).to_block(b"<html>", "application/pdf", "fake.pdf")
    assert client.files.uploaded == []


async def test_history_stores_only_the_file_id(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([message("end_turn", [{"type": "text", "text": "A syllabus."}])])
    block = await FileUploader(client, db).to_block(PDF * 100_000, "application/pdf", "big.pdf")
    await make_agent(tmp_path, db, client).run([block, {"type": "text", "text": "what is this?"}])
    stored = db.conn.execute("SELECT SUM(LENGTH(content_json)) FROM messages").fetchone()[0]
    assert stored < 5_000  # the 1.4 MB PDF is not in the database


async def test_attachment_tool_uses_the_uploader(tmp_path):
    db, client = Database(tmp_path / "t.db"), FakeClient([])
    google = FakeGoogle()
    google.attachments[("m1", "s.pdf")] = (PDF, "application/pdf")
    ctx = make_context(db, google=google)
    ctx.prepare_file = FileUploader(client, db).to_block
    content, err = await run_tool("read_email_attachment", {"message_id": "m1", "filename": "s.pdf"}, ctx)
    assert not err and content[-1]["source"] == {"type": "file", "file_id": "file_1"}


async def test_cleanup_deletes_files_from_finished_conversations_only(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([message("end_turn", [{"type": "text", "text": "ok"}])] * 2)
    agent = make_agent(tmp_path, db, client)
    uploader = FileUploader(client, db)

    old = await uploader.to_block(PDF, "application/pdf", "old.pdf")
    await agent.run([old, {"type": "text", "text": "read"}])
    db.new_thread(agent.config_hash)  # that conversation is over
    current = await uploader.to_block(PDF, "application/pdf", "new.pdf")
    await agent.run([current, {"type": "text", "text": "read"}])
    orphan = await uploader.to_block(PDF, "application/pdf", "never-used.pdf")  # recent, unused

    await clean_up_uploads(client, db)
    assert client.files.deleted == ["file_1"]

    db.conn.execute("UPDATE uploaded_files SET created_at = ? WHERE file_id = ?",
                    ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), orphan["source"]["file_id"]))
    await clean_up_uploads(client, db)
    assert client.files.deleted == ["file_1", "file_3"]  # the current file_2 is never touched


async def test_cleanup_treats_missing_files_as_gone_and_retries_other_errors(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([])
    uploader = FileUploader(client, db)
    for name in ("a.pdf", "b.pdf"):
        await uploader.to_block(PDF, "application/pdf", name)
    db.conn.execute("UPDATE uploaded_files SET created_at = '2020-01-01T00:00:00+00:00'")
    client.files.fail_delete = {"file_1": api_error(404), "file_2": api_error(500)}
    await clean_up_uploads(client, db)
    remaining = [r["file_id"] for r in db.conn.execute("SELECT file_id FROM uploaded_files")]
    assert remaining == ["file_2"]  # 404 means already deleted; 500 is retried next time


async def test_agent_reports_busy_while_a_turn_runs(tmp_path):
    import asyncio

    db = Database(tmp_path / "t.db")
    gate = asyncio.Event()

    class SlowClient(FakeClient):
        async def create(self, **kwargs):
            await gate.wait()
            return await super().create(**kwargs)

    agent = make_agent(tmp_path, db, SlowClient([message("end_turn", [{"type": "text", "text": "ok"}])]))
    assert not agent.busy
    turn = asyncio.create_task(agent.run([{"type": "text", "text": "hi"}]))
    await asyncio.sleep(0)
    assert agent.busy  # the bot's cleanup job skips its run while this is true
    gate.set()
    await turn
    assert not agent.busy
