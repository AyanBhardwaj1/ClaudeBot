"""Charts drawn from a chart spec, and recurring web-only briefings."""

import io
import json
from datetime import datetime, timedelta

import pytest
from helpers import TZ, FakeClient, make_context, message

from claudebot.charts import ChartError, render_chart, validate_spec
from claudebot.db import Database
from claudebot.reminders import previous_window
from claudebot.tools import run_tool
from claudebot.usage import UsageTracker
from claudebot.web_agent import run_briefing

LINE = {
    "type": "line",
    "title": "Weekly spending",
    "categories": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    "series": [{"name": "Food", "values": [12, 30, 8, 22, 41]},
               {"name": "Transport", "values": [5, 5, 12, 5, 0]}],
    "y_label": "USD",
}


def png_size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return image.size


# --- charts ---


@pytest.mark.parametrize("spec", [
    LINE,
    {"type": "bar", "title": "Grades", "categories": ["CS 312", "M 408D", "BA 324H"],
     "series": [{"name": "Score", "values": [94, 88, 91]}]},
    {"type": "horizontal_bar", "title": "Top languages", "categories": ["Python", "TypeScript", "Go"],
     "series": [{"name": "2025", "values": [51, 38, 14]}, {"name": "2026", "values": [55, 41, 17]}]},
    {"type": "scatter", "title": "Sleep vs focus", "x_values": [5, 6, 7, 8, 9],
     "series": [{"name": "Focus", "values": [3, 5, 6, 8, 7]}], "x_label": "Hours slept"},
])
def test_each_chart_type_renders_a_png(spec):
    data = render_chart(validate_spec(spec))
    assert data.startswith(b"\x89PNG")
    width, height = png_size(data)
    assert 1000 <= width <= 2000 and height < width


@pytest.mark.parametrize("bad, why", [
    ({**LINE, "type": "pie"}, "type"),
    ({**LINE, "series": [{"name": f"s{i}", "values": [1] * 5} for i in range(9)]}, "other"),
    ({"type": "scatter", "title": "t", "x_values": [1, 2],
      "series": [{"name": f"s{i}", "values": [1, 2]} for i in range(4)]}, "3"),
    ({**LINE, "series": [{"name": "Food", "values": [1, 2]}]}, "categories"),
    ({**LINE, "series": [{"name": "Food", "values": [1, float("nan"), 3, 4, 5]}]}, "number"),
    ({**LINE, "series": []}, "series"),
    ({**LINE, "categories": [str(i) for i in range(600)],
      "series": [{"name": "x", "values": [1] * 600}]}, "points"),
    ({**LINE, "series": [{"name": "Food", "values": ["12", 1, 2, 3, 4]}]}, "number"),
])
def test_bad_specs_explain_what_to_fix(bad, why):
    with pytest.raises(ChartError) as error:
        validate_spec(bad)
    assert why in str(error.value).lower()


def test_long_text_is_clipped():
    spec = validate_spec({**LINE, "title": "x" * 500})
    assert len(spec["title"]) <= 120


async def test_make_chart_tool_sends_the_image_to_the_owner(tmp_path):
    sent = []

    async def send_photo(data, caption):
        sent.append((data, caption))

    ctx = make_context(Database(tmp_path / "t.db"))
    ctx.send_photo = send_photo
    out, err = await run_tool("make_chart", {**LINE, "caption": "Food spiked Friday"}, ctx)
    assert not err and json.loads(out)["sent"] is True
    assert sent[0][0].startswith(b"\x89PNG") and sent[0][1] == "Food spiked Friday"


async def test_make_chart_tool_reports_spec_problems(tmp_path):
    ctx = make_context(Database(tmp_path / "t.db"))

    async def send_photo(data, caption):
        raise AssertionError("should not send")

    ctx.send_photo = send_photo
    out, err = await run_tool("make_chart", {**LINE, "type": "pie"}, ctx)
    assert err and "type" in out.lower()


# --- briefings ---


def test_previous_window_matches_the_repeat():
    monday = datetime(2026, 10, 26, 8, 0, tzinfo=TZ)
    tuesday = monday + timedelta(days=1)
    assert previous_window(tuesday, "daily") == timedelta(days=1)
    assert previous_window(monday, "weekdays") == timedelta(days=3)  # covers the weekend
    assert previous_window(tuesday, "weekdays") == timedelta(days=1)
    assert previous_window(monday, "weekly") == timedelta(days=7)
    assert previous_window(monday, "none") == timedelta(days=7)


async def test_create_briefing_schedules_a_recurring_web_briefing(tmp_path):
    db = Database(tmp_path / "t.db")
    scheduled = []
    ctx = make_context(db, scheduled=scheduled)
    when = (datetime.now(TZ) + timedelta(days=1)).replace(hour=17, minute=0, tzinfo=None).isoformat()
    out, err = await run_tool("create_briefing", {"topic": "AI news", "when": when, "repeat": "weekly"}, ctx)
    assert not err
    row = db.get_reminder(json.loads(out)["briefing_id"])
    assert row["briefing"] == 1 and row["repeat"] == "weekly" and row["text"] == "AI news"
    assert scheduled == [row["id"]]
    listed = json.loads((await run_tool("list_reminders", {}, ctx))[0])
    assert listed[0]["is_briefing"] is True


async def test_briefings_need_the_owner_and_are_capped(tmp_path):
    db = Database(tmp_path / "t.db")
    ctx = make_context(db)
    when = (datetime.now(TZ) + timedelta(hours=2)).replace(tzinfo=None).isoformat()
    ctx.owner_present = False
    _, err = await run_tool("create_briefing", {"topic": "x", "when": when, "repeat": "daily"}, ctx)
    assert err
    ctx.owner_present = True
    for i in range(10):
        ctx.briefings_left = 1  # each in its own turn
        _, err = await run_tool("create_briefing", {"topic": f"t{i}", "when": when, "repeat": "daily"}, ctx)
        assert not err
    ctx.briefings_left = 1
    out, err = await run_tool("create_briefing", {"topic": "one too many", "when": when, "repeat": "daily"}, ctx)
    assert err and "10" in out


async def test_briefing_request_is_web_only_and_covers_only_whats_new(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_memory("private fact")
    client = FakeClient([message("end_turn", [{"type": "text", "text": "1. Big launch [link]"}])])
    since = datetime(2026, 10, 21, 17, 0, tzinfo=TZ)
    out = await run_briefing(client, UsageTracker(db, TZ, None), "claude-opus-5-5", "AI news", since)
    assert out == "1. Big launch [link]"
    request = client.requests[0]
    assert {t["name"] for t in request["tools"]} == {"web_search", "web_fetch"}
    fetch = next(t for t in request["tools"] if t["name"] == "web_fetch")
    assert fetch["url_sources"] == {"user_input": {"type": "none"}}
    prompt = request["messages"][0]["content"]
    assert "AI news" in prompt and "2026-10-21" in prompt
    assert "private fact" not in json.dumps(request)
    assert db.usage_totals(datetime(2020, 1, 1, tzinfo=TZ), source="briefing")[0] == 1


# --- review regressions ---


def test_dollar_signs_are_plain_text_not_math():
    from claudebot.charts import render_chart

    spec = validate_spec({"type": "bar", "title": "Spending ($) vs budget ($)", "categories": ["$0-$50", "cost $x^$"],
                          "series": [{"name": "Count", "values": [3, 5]}]})
    assert render_chart(spec).startswith(b"\x89PNG")  # used to raise on the unbalanced math markup
    import matplotlib

    assert matplotlib.rcParams["text.parse_math"] is False


def test_bar_charts_cap_the_number_of_bars():
    with pytest.raises(ChartError) as error:
        validate_spec({"type": "bar", "title": "t", "categories": [str(i) for i in range(100)],
                       "series": [{"name": f"s{i}", "values": [1] * 100} for i in range(3)]})
    assert "bars" in str(error.value).lower()


async def test_charts_and_briefings_are_limited_per_turn(tmp_path):
    db = Database(tmp_path / "t.db")
    told, photos = [], []

    async def send_photo(data, caption):
        photos.append(caption)

    async def notify_owner(text):
        told.append(text)

    ctx = make_context(db)
    ctx.send_photo, ctx.notify_owner = send_photo, notify_owner
    for _ in range(2):
        _, err = await run_tool("make_chart", LINE, ctx)
        assert not err
    _, err = await run_tool("make_chart", LINE, ctx)
    assert err and len(photos) == 2

    when = (datetime.now(TZ) + timedelta(hours=2)).replace(tzinfo=None).isoformat()
    _, err = await run_tool("create_briefing", {"topic": "AI news", "when": when, "repeat": "weekly"}, ctx)
    assert not err
    _, err = await run_tool("create_briefing", {"topic": "more", "when": when, "repeat": "daily"}, ctx)
    assert err and db.active_briefing_count() == 1
    assert len(told) == 1 and "AI news" in told[0] and "/briefings" in told[0]  # owner always sees it
