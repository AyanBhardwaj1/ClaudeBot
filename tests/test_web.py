"""The web app: only the owner gets in (one-time link from Telegram), changes need the CSRF token and
the app's own origin, and every action goes through the same code as the Telegram buttons."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from helpers import TZ, make_config

from claudebot.web import WebServer, auth, login_url
from claudebot.web.api import COOKIE, history_view


@pytest.fixture
async def setup(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc", web_port=8765))
    bot.schedule_reminder = lambda rid: None
    bot.unschedule_reminder = lambda rid: None
    server = WebServer(bot)
    client = TestClient(TestServer(server.app))
    await client.start_server()
    yield bot, client
    await client.close()


async def sign_in(bot, client) -> str:
    token = auth.new_login_token(bot.db)
    res = await client.post("/api/login", json={"token": token}, headers={"Origin": origin(client)})
    assert res.status == 200
    return (await res.json())["csrf"]


def origin(client) -> str:
    return f"http://{client.server.host}:{client.server.port}"


def write(client, csrf):
    return {"Origin": origin(client), "X-CSRF-Token": csrf}


async def test_nothing_without_signing_in(setup):
    bot, client = setup
    for path in ("/api/me", "/api/history", "/api/today", "/api/memories", "/api/log"):
        assert (await client.get(path)).status == 401
    res = await client.get("/")
    assert res.status == 200 and "ClaudeBot" in await res.text()
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]
    assert res.headers["X-Frame-Options"] == "DENY" and res.headers["Referrer-Policy"] == "no-referrer"
    assert (await client.get("/static/../web/auth.py")).status == 404


async def test_login_links_work_once_and_expire(setup):
    bot, client = setup
    token = auth.new_login_token(bot.db)
    ok = await client.post("/api/login", json={"token": token}, headers={"Origin": origin(client)})
    assert ok.status == 200
    cookie = ok.cookies[COOKIE]
    assert cookie["httponly"] and cookie["samesite"] == "Strict"
    again = await client.post("/api/login", json={"token": token}, headers={"Origin": origin(client)})
    assert again.status == 401  # used up
    old = auth.new_login_token(bot.db)
    key = auth.LOGIN_PREFIX + auth._hash(old)
    bot.db.set_setting(key, (datetime.now(TZ) - timedelta(seconds=1)).isoformat())
    assert (await client.post("/api/login", json={"token": old}, headers={"Origin": origin(client)})).status == 401
    assert not any(k.startswith(auth.SESSION_PREFIX) and token in k for (k,) in
                   bot.db.conn.execute("SELECT key FROM settings").fetchall())  # only hashes are stored


async def test_changes_need_csrf_and_same_origin(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    me = await (await client.get("/api/me")).json()
    assert me["csrf"] == csrf and me["name"] == "Ayan"
    body = {"name": "Mom", "month": 3, "day": 14}
    assert (await client.post("/api/birthdays", json=body, headers={"Origin": origin(client)})).status == 403
    assert (await client.post("/api/birthdays", json=body,
                              headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf})).status == 403
    assert (await client.post("/api/birthdays", json=body,
                              headers={"Origin": origin(client), "X-CSRF-Token": "nope"})).status == 403
    res = await client.post("/api/birthdays", json=body, headers=write(client, csrf))
    assert res.status == 200 and (await res.json())["birthday"]["name"] == "Mom"


async def test_sign_out_everywhere(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    assert (await client.post("/api/logout-all", headers=write(client, csrf))).status == 200
    assert (await client.get("/api/me")).status == 401


async def test_birthdays_bills_reminders_go_through_the_normal_paths(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    await client.post("/api/birthdays", json={"name": "Mom", "month": 3, "day": 14}, headers=write(client, csrf))
    bday = (await (await client.get("/api/birthdays")).json())["birthdays"][0]
    bot.add_bill("Rent", 1200, 1)
    bill = (await (await client.get("/api/bills")).json())["bills"][0]
    reminders = (await (await client.get("/api/reminders")).json())["reminders"]
    assert len(reminders) == 2
    owned = next(r for r in reminders if r["text"].startswith("🎂"))
    res = await client.post(f"/api/reminders/{owned['id']}/cancel", headers=write(client, csrf))
    assert res.status == 400  # a birthday's reminder goes with the birthday
    paid = await client.post(f"/api/bills/{bill['id']}/paid", headers=write(client, csrf))
    assert paid.status == 200
    assert (await client.post(f"/api/bills/{bill['id']}/paid", headers=write(client, csrf))).status == 409
    assert (await client.delete(f"/api/bills/{bill['id']}", headers=write(client, csrf))).status == 200
    assert (await client.delete(f"/api/birthdays/{bday['id']}", headers=write(client, csrf))).status == 200
    assert bot.db.active_reminders() == []
    actions = (await (await client.get("/api/log")).json())["actions"]
    assert any("(web)" in a["summary"] for a in actions)


async def test_lists_memory_settings(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    res = await client.post("/api/lists/items", json={"list": "Shopping", "items": ["milk"]}, headers=write(client, csrf))
    assert res.status == 200
    lst = (await (await client.get("/api/lists")).json())["lists"][0]
    item = lst["items"][0]
    await client.post(f"/api/lists/{lst['id']}/items/{item['id']}/toggle", headers=write(client, csrf))
    assert (await (await client.get("/api/lists")).json())["lists"][0]["items"][0]["done"]
    bot.db.add_memory("likes tea")
    mem = (await (await client.get("/api/memories")).json())["memories"][0]
    assert (await client.delete(f"/api/memories/{mem['id']}", headers=write(client, csrf))).status == 200
    assert bot.db.list_memories() == []
    s = await (await client.post("/api/settings", json={"quiet": "1h", "urgent_wakes": True, "alert_mode": "hourly"},
                                 headers=write(client, csrf))).json()
    assert s["quiet_until"] and s["urgent_wakes"] and s["alert_mode"] == "hourly"
    bad = await client.post("/api/settings", json={"quiet": "whenever"}, headers=write(client, csrf))
    assert bad.status == 400


async def test_chat_streams_and_uses_the_shared_conversation(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    seen = []

    async def run(content, owner_present=True, effort=None, on_text=None, source="chat"):
        seen.append((content, owner_present, source))
        await on_text("Hel")
        return "Hello!"

    bot.agent.run = run
    res = await client.post("/api/chat", json={"text": "hi"}, headers=write(client, csrf))
    body = await res.text()
    assert res.headers["Content-Type"].startswith("text/event-stream")
    assert 'event: done\ndata: {"text": "Hello!", "ok": true}' in body
    assert seen == [([{"type": "text", "text": "hi"}], True, "web")]
    assert (await client.post("/api/chat", json={"text": "  "}, headers=write(client, csrf))).status == 400


def test_history_shows_only_what_was_said():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "[Now: Monday]"},
                                     {"type": "text", "text": "<background_events>\nan email said hi"},
                                     {"type": "text", "text": "what's up?"}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "hmm"},
                                          {"type": "tool_use", "id": "t", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "secret tool output"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Not much."}]},
    ]
    assert history_view(messages) == [{"role": "you", "text": "what's up?"}, {"role": "claudebot", "text": "Not much."}]


async def test_web_command_sends_a_one_time_link(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc", web_port=8765))
    bot.web = object()
    replies = []

    async def reply_text(text, *, reply_markup=None):
        replies.append(text)

    update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=reply_text))
    await bot.on_web(update, SimpleNamespace(args=[]))
    assert "http://localhost:8765/login#t=" in replies[-1] and "once" in replies[-1]
    token = replies[-1].split("#t=")[1].split()[0]
    assert auth.redeem_login_token(bot.db, token)
    await bot.on_web(update, SimpleNamespace(args=["signout"]))
    assert "Signed out everywhere" in replies[-1]


def test_login_url_prefers_the_public_address(tmp_path):
    config = make_config(tmp_path, web_port=8765, web_public_url="https://bot.example.com")
    assert login_url(config, "abc") == "https://bot.example.com/login#t=abc"


def test_web_port_setting(monkeypatch):
    from claudebot.config import _web_port

    assert _web_port("8765") == 8765 and _web_port("off") is None and _web_port("") is None
    with pytest.raises(ValueError):
        _web_port("70000")


def test_static_files_ship_with_the_package():
    from claudebot.web import STATIC_FILES, _static

    for name, _ in STATIC_FILES.values():
        assert _static(name)
    js = _static("app.js").decode()
    assert "innerHTML" not in js and "style:" not in js.replace('{ style: "currency"', "")  # CSP: no inline styles
    json.loads(_static("manifest.webmanifest"))
