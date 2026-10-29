"""Claude-specific features: answers with receipts, the code workbench, and /think."""

import json
from datetime import datetime

from helpers import TZ, FakeClient, make_agent, make_context, message

from claudebot.citations import SourceList
from claudebot.db import Database
from claudebot.files import FileUploader, to_content_block
from claudebot.tools import run_tool
from claudebot.usage import UsageTracker
from claudebot.workbench import SKILLS, run_workbench

PDF = b"%PDF-1.4 hello"


def cited_text(text, citations):
    return message("end_turn", [{"type": "text", "text": text, "citations": citations}])


PAGE = {"type": "page_location", "cited_text": "The final exam is on December 12 in GDC 2.216.",
        "document_index": 0, "document_title": "syllabus.pdf", "start_page_number": 3, "end_page_number": 4}
WEB = {"type": "web_search_result_location", "cited_text": "Austin will see highs near 85F.",
       "url": "https://weather.example/austin", "title": "Austin forecast", "encrypted_index": "x"}


# --- answers with receipts ---


def test_sources_are_numbered_deduplicated_and_quoted():
    sources = SourceList()
    reply = message("end_turn", [
        {"type": "text", "text": "Your final is Dec 12", "citations": [PAGE]},
        {"type": "text", "text": " in GDC.", "citations": [PAGE]},
        {"type": "text", "text": " It'll be warm", "citations": [WEB]},
        {"type": "text", "text": " so dress light."},
    ])
    text = "".join(sources.mark(b) for b in reply.content if b.type == "text")
    assert text == "Your final is Dec 12 [1] in GDC. [1] It'll be warm [2] so dress light."
    footer = sources.footer()
    assert footer.startswith("Sources:")
    assert '[1] syllabus.pdf, p. 3: "The final exam is on December 12 in GDC 2.216."' in footer
    assert "[2] Austin forecast - https://weather.example/austin" in footer


def test_long_quotes_are_clipped_and_sources_capped():
    sources = SourceList()
    for i in range(12):
        sources.mark(message("end_turn", [{"type": "text", "text": "x", "citations": [
            {**WEB, "url": f"https://site{i}.example", "title": f"Site {i}", "cited_text": "y" * 500}]}]).content[0])
    footer = sources.footer()
    assert footer.count("\n[") <= 8 and "more source" in footer
    assert SourceList().footer() == ""


def test_documents_ask_for_citations():
    assert to_content_block(PDF, "application/pdf", "s.pdf")["citations"] == {"enabled": True}
    assert to_content_block(b"notes", "text/plain", "n.txt")["citations"] == {"enabled": True}


async def test_agent_replies_end_with_sources(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([cited_text("Your final is Dec 12.", [PAGE])])
    reply = await make_agent(tmp_path, db, client).run([{"type": "text", "text": "when's my final?"}])
    assert reply.startswith("Your final is Dec 12. [1]")
    assert "syllabus.pdf, p. 3" in reply


async def test_web_only_answers_get_sources_too(tmp_path):
    from claudebot.web_agent import ask_with_web

    db = Database(tmp_path / "t.db")
    client = FakeClient([cited_text("Warm today.", [WEB])])
    out = await ask_with_web(client, UsageTracker(db, TZ, None), model="m", system="s", prompt="p", effort="low",
                             max_searches=1, max_fetches=1, max_page_tokens=100, fetch_from_prompt=True, source="group")
    assert "Austin forecast - https://weather.example/austin" in out


# --- code workbench (Agent Skills + code execution) ---

CONTAINER = {"id": "container_1", "expires_at": "2026-11-28T00:00:00Z"}


def ran_code(file_ids):
    return {"type": "bash_code_execution_tool_result", "tool_use_id": "srv_1", "content": {
        "type": "bash_code_execution_result", "stdout": "", "stderr": "", "return_code": 0,
        "content": [{"type": "bash_code_execution_output", "file_id": f} for f in file_ids]}}


async def test_workbench_request_uses_skills_and_attaches_files(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([message("end_turn", [{"type": "text", "text": "Done."}], container=CONTAINER)])
    result = await run_workbench(client, UsageTracker(db, TZ, None), "claude-opus-5-5",
                                 "Total my food spending", ["file_a", "file_b"])
    request = client.requests[0]
    assert request["tools"] == [{"type": "code_execution_20260521", "name": "code_execution"}]
    assert [s["skill_id"] for s in request["container"]["skills"]] == list(SKILLS)
    assert "code-execution-2025-08-25" in request["betas"]
    content = request["messages"][0]["content"]
    assert content[:2] == [{"type": "container_upload", "file_id": "file_a"},
                           {"type": "container_upload", "file_id": "file_b"}]
    assert "Total my food spending" in content[-1]["text"]
    assert result.text == "Done." and result.files == []
    assert db.usage_totals(datetime(2020, 1, 1, tzinfo=TZ), source="workbench")[0] == 1


async def test_workbench_resumes_in_the_same_container_and_returns_files(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([
        message("pause_turn", [ran_code(["gen_1"])], container=CONTAINER),
        message("end_turn", [ran_code(["gen_2"]), {"type": "text", "text": "Made your deck."}], container=CONTAINER),
    ])
    client.files.generated = {"gen_1": ("chart.png", b"\x89PNG..."), "gen_2": ("../../deck.pptx", b"PK...")}
    result = await run_workbench(client, UsageTracker(db, TZ, None), "claude-opus-5-5", "make a deck", [])
    assert client.requests[1]["container"]["id"] == "container_1"
    assert client.requests[1]["messages"][-1]["role"] == "assistant"
    assert [name for name, _ in result.files] == ["chart.png", "deck.pptx"]  # no path tricks
    assert client.files.deleted == ["gen_1", "gen_2"]  # nothing left in storage


async def test_workbench_tool_is_owner_only_and_once_per_turn(tmp_path):
    db = Database(tmp_path / "t.db")
    asked = []

    async def workbench(task, attach):
        asked.append((task, attach))
        return {"summary": "Food: $412.18 across 37 purchases.", "files": ["food.xlsx"]}

    ctx = make_context(db)
    ctx.workbench = workbench
    ctx.owner_present = False
    _, err = await run_tool("code_workbench", {"task": "x", "attach_recent_files": True}, ctx)
    assert err and asked == []
    ctx.owner_present = True
    out, err = await run_tool("code_workbench", {"task": "total food", "attach_recent_files": True}, ctx)
    assert not err and json.loads(out)["summary"].startswith("Food: $412.18")
    _, err = await run_tool("code_workbench", {"task": "again", "attach_recent_files": False}, ctx)
    assert err and asked == [("total food", True)]


async def test_office_files_are_stored_for_the_workbench(tmp_path):
    db, client = Database(tmp_path / "t.db"), FakeClient([])
    xlsx = b"PK\x03\x04 fake spreadsheet"
    file_id = await FileUploader(client, db).store_raw(
        xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "budget.xlsx")
    assert file_id == "file_1" and client.files.uploaded[0][0] == "budget.xlsx"
    assert db.recent_upload_ids(limit=5) == ["file_1"]


# --- /think ---


async def test_think_streams_at_max_effort(tmp_path):
    db = Database(tmp_path / "t.db")
    client = FakeClient([message("end_turn", [{"type": "text", "text": "Take the offer."}])] * 2)
    agent = make_agent(tmp_path, db, client)
    assert await agent.run([{"type": "text", "text": "Google or Meta?"}], effort="max") == "Take the offer."
    think = client.requests[0]
    assert think["_streamed"] and think["output_config"]["effort"] == "max" and think["max_tokens"] >= 64000
    await agent.run([{"type": "text", "text": "thanks"}])
    normal = client.requests[1]
    assert "_streamed" not in normal and normal["output_config"]["effort"] == "medium"
    assert normal["messages"][:2] == think["messages"][:1] + [normal["messages"][1]]  # same conversation
