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


async def test_junk_logins_cant_lock_the_owner_out(setup, monkeypatch):
    """Web review M1: only failures are throttled, and a valid link always gets in."""
    import claudebot.web

    monkeypatch.setattr(claudebot.web, "FAILED_LOGIN_DELAY", 0)
    bot, client = setup
    for _ in range(30):
        await client.post("/api/login", json={"token": "x" * 40})
    assert (await client.post("/api/login", json={"token": "y" * 40})).status == 429
    good = await client.post("/api/login", json={"token": auth.new_login_token(bot.db)}, headers={"Origin": origin(client)})
    assert good.status == 200


async def test_other_host_names_are_turned_away(setup):
    """Web review M2: a DNS-rebinding page arrives as evil.example and gets 421, even for open paths."""
    bot, client = setup
    for path in ("/", "/api/health"):
        res = await client.get(path, headers={"Host": "evil.example:8765"})
        assert res.status == 421
    res = await client.post("/api/login", json={"token": auth.new_login_token(bot.db)},
                            headers={"Host": "evil.example:8765", "Origin": "http://evil.example:8765"})
    assert res.status == 421
    assert (await client.get("/", headers={"Host": "localhost:8765"})).status == 200


async def test_public_address_needs_its_https_origin(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc", web_port=8765,
                                  web_public_url="https://bot.example.com"))
    client = TestClient(TestServer(WebServer(bot).app))
    await client.start_server()
    try:
        host = {"Host": "bot.example.com"}
        ok = await client.post("/api/login", json={"token": auth.new_login_token(bot.db)},
                               headers={**host, "Origin": "https://bot.example.com"})
        assert ok.status == 200 and ok.cookies[COOKIE]["secure"]
        bad = await client.post("/api/login", json={"token": auth.new_login_token(bot.db)},
                                headers={**host, "Origin": "http://bot.example.com"})
        assert bad.status == 403
    finally:
        await client.close()


def test_plain_http_public_address_is_refused(tmp_path):
    from claudebot.web import check_public_url

    with pytest.raises(RuntimeError):
        check_public_url(make_config(tmp_path, web_port=8765, web_public_url="http://192.168.1.20:8765"))
    check_public_url(make_config(tmp_path, web_port=8765, web_public_url="http://localhost:8765"))
    check_public_url(make_config(tmp_path, web_port=8765, web_public_url="https://bot.example.com"))


async def test_security_headers_on_streams_and_errors(setup):
    """Web review L3."""
    bot, client = setup
    csrf = await sign_in(bot, client)

    async def run(content, owner_present=True, effort=None, on_text=None, source="chat"):
        return "ok"

    bot.agent.run = run
    res = await client.post("/api/chat", json={"text": "hi"}, headers=write(client, csrf))
    await res.text()
    assert "default-src 'self'" in res.headers["Content-Security-Policy"] and res.headers["X-Content-Type-Options"] == "nosniff"
    missing = await client.get("/nope")
    assert missing.status == 404 and missing.headers["X-Content-Type-Options"] == "nosniff"


async def test_one_chat_turn_at_a_time(setup):
    """Web review L4: a second message while one is being answered is refused, not queued."""
    import asyncio

    bot, client = setup
    csrf = await sign_in(bot, client)
    release = asyncio.Event()

    async def run(content, owner_present=True, effort=None, on_text=None, source="chat"):
        await release.wait()
        return "done"

    bot.agent.run = run
    first = asyncio.ensure_future(client.post("/api/chat", json={"text": "one"}, headers=write(client, csrf)))
    await asyncio.sleep(0.2)
    second = await client.post("/api/chat", json={"text": "two"}, headers=write(client, csrf))
    assert second.status == 409
    release.set()
    assert "done" in await (await first).text()


def test_ipv6_login_links_are_bracketed(tmp_path):
    config = make_config(tmp_path, web_port=8765, web_host="fd00::5")
    assert login_url(config, "abc") == "http://[fd00::5]:8765/login#t=abc"


def test_fly_gets_its_https_address(monkeypatch):
    from claudebot.config import _public_url

    monkeypatch.delenv("WEB_PUBLIC_URL", raising=False)
    monkeypatch.setenv("FLY_APP_NAME", "my-bot")
    assert _public_url() == "https://my-bot.fly.dev"
    monkeypatch.setenv("WEB_PUBLIC_URL", "https://bot.example.com/")
    assert _public_url() == "https://bot.example.com"


def test_plain_http_listen_address_is_refused(tmp_path):
    """Round 2 L2: WEB_HOST=192.168.1.5 without an https WEB_PUBLIC_URL would send links in the clear."""
    from claudebot.web import check_public_url

    with pytest.raises(RuntimeError):
        check_public_url(make_config(tmp_path, web_port=8765, web_host="192.168.1.5"))
    check_public_url(make_config(tmp_path, web_port=8765, web_host="0.0.0.0"))
    check_public_url(make_config(tmp_path, web_port=8765, web_host="192.168.1.5", web_public_url="https://bot.example.com"))


async def test_login_failures_stay_bounded(setup):
    """Round 2 L1."""
    bot, client = setup
    server = WebServer(bot)
    assert server._failures.maxlen == 21


async def test_local_public_address_keeps_direct_access_working(tmp_path, monkeypatch):
    """Round 2 L3: WEB_PUBLIC_URL=http://localhost:9000 doesn't lock out http://localhost:<port>."""
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc", web_port=8765, web_public_url="http://localhost:9000"))
    client = TestClient(TestServer(WebServer(bot).app))
    await client.start_server()
    try:
        res = await client.post("/api/login", json={"token": auth.new_login_token(bot.db)}, headers={"Origin": origin(client)})
        assert res.status == 200
    finally:
        await client.close()


async def test_unexpected_errors_still_end_the_chat_stream(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)

    async def boom(*a, **k):
        raise KeyError("x")

    bot._run_agent = boom
    body = await (await client.post("/api/chat", json={"text": "hi"}, headers=write(client, csrf))).text()
    assert "event: done" in body and '"ok": false' in body


async def test_emails_waiting_on_you_show_and_act_like_the_telegram_buttons(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    sent, edits = [], []
    bot.google.send_email = lambda **email: sent.append(email) or {"status": "sent"}

    async def announce(outbox_id, text, needs_approval=False):
        return 900 + outbox_id

    async def edit(message_id, text, followup_id=None):
        edits.append((message_id, text))

    async def notify(text):
        pass

    bot.outbox.ui = SimpleNamespace(announce=announce, edit=edit, notify=notify)
    bot.outbox.schedule = lambda outbox_id, when: None
    held = await bot.outbox.submit({"to": "sam@example.com", "bcc": "boss@example.com", "subject": "Hi", "body": "Friday works"},
                                   needs_approval=True)
    pending = await bot.outbox.submit({"to": "lee@example.com", "subject": "Quiz", "body": "Thanks!"})
    emails = (await (await client.get("/api/outbox")).json())["emails"]
    assert [(e["status"], e["to"]) for e in emails] == [("held", "sam@example.com"), ("pending", "lee@example.com")]
    assert emails[0]["bcc"] == "boss@example.com" and emails[0]["body"] == "Friday works"  # nothing hidden

    # Send only works on a held email: a pending one can't skip its Undo window this way
    assert (await client.post(f"/api/outbox/{pending['outbox_id']}/send", headers=write(client, csrf))).status == 409
    ok = await client.post(f"/api/outbox/{held['outbox_id']}/send", headers=write(client, csrf))
    assert ok.status == 200 and sent[0]["to"] == "sam@example.com"
    assert (await client.post(f"/api/outbox/{held['outbox_id']}/send", headers=write(client, csrf))).status == 409  # once
    undo = await client.post(f"/api/outbox/{pending['outbox_id']}/cancel", headers=write(client, csrf))
    assert undo.status == 200 and len(sent) == 1
    assert any("Cancelled" in t for _, t in edits)  # the Telegram card follows along
    assert (await (await client.get("/api/outbox")).json())["emails"] == []


async def test_chat_with_a_file_goes_in_like_a_telegram_file(setup):
    from aiohttp import FormData

    bot, client = setup
    csrf = await sign_in(bot, client)
    seen = []

    async def run(content, owner_present=True, effort=None, on_text=None, source="chat"):
        seen.append(content)
        return "It's a syllabus."

    async def to_block(data, mime, name, origin="owner"):
        return {"type": "document", "source": {"type": "file", "file_id": "f1"}, "title": name}

    bot.agent.run = run
    bot.uploader.to_block = to_block
    form = FormData()
    form.add_field("text", "what's due?")
    form.add_field("file", b"%PDF-1.4 hello", filename="syllabus.pdf", content_type="application/pdf")
    body = await (await client.post("/api/chat", data=form, headers=write(client, csrf))).text()
    assert "It's a syllabus." in body
    assert seen[0][0]["title"] == "syllabus.pdf" and seen[0][1] == {"type": "text", "text": "what's due?"}

    for name, data in (("claudebot-export-2026-11-01.json", b"{}"), ("credentials.json", b'{"installed": {"client_secret": "x"}}')):
        form = FormData()
        form.add_field("file", data, filename=name, content_type="application/json")
        res = await client.post("/api/chat", data=form, headers=write(client, csrf))
        assert res.status == 400 and "Telegram" in (await res.json())["error"]
    assert len(seen) == 1

    big = await client.post("/api/settings", data=b"x" * 100_000,
                            headers={**write(client, csrf), "Content-Type": "application/json"})
    assert big.status == 413  # only chat takes big bodies


def test_history_marks_messages_with_files():
    messages = [{"role": "user", "content": [{"type": "text", "text": "[Now]"},
                                             {"type": "document", "source": {"type": "file", "file_id": "f"}},
                                             {"type": "text", "text": "what's due?"}]}]
    assert history_view(messages) == [{"role": "you", "text": "📎 what's due?"}]


async def test_add_reminders_and_memories_and_search(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    scheduled = []
    bot.schedule_reminder = scheduled.append
    later = (datetime.now(TZ) + timedelta(days=1)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M")
    ok = await client.post("/api/reminders", json={"text": "renew passport", "when": later, "repeat": "none"},
                           headers=write(client, csrf))
    assert ok.status == 200 and scheduled == [(await ok.json())["id"]]
    past = (datetime.now(TZ) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    for body in ({"text": "x", "when": past}, {"text": "x", "when": later, "repeat": "hourly"},
                 {"text": "", "when": later}, {"text": "x", "when": "soon"}):
        assert (await client.post("/api/reminders", json=body, headers=write(client, csrf))).status == 400
    assert (await client.post("/api/reminders", json={"text": "standup", "when": past, "repeat": "weekdays"},
                              headers=write(client, csrf))).status == 200  # a repeat may start in the past

    assert (await client.post("/api/memories", json={"text": "Passport number ends in 42"}, headers=write(client, csrf))).status == 200
    assert (await client.post("/api/memories", json={"text": "Passport number ends in 42"}, headers=write(client, csrf))).status == 409
    hits = (await (await client.get("/api/search?q=PASSPORT")).json())["results"]
    assert {h["kind"] for h in hits} == {"memory", "reminder"}
    assert (await (await client.get("/api/search?q=p")).json())["results"] == []


async def test_chunked_bodies_are_capped_too(setup):
    """Web review round 3, H1: a body with no Content-Length can't get past the 64 KB cap, even before sign-in."""
    bot, client = setup

    async def chunks():
        for _ in range(40):
            yield b"x" * 4096  # 160 KB, no Content-Length

    res = await client.post("/api/login", data=chunks(), headers={"Content-Type": "application/json"})
    assert res.status in (400, 401, 413)  # refused either way; nothing over 64 KB was buffered
    csrf = await sign_in(bot, client)

    async def chunks2():
        yield b'{"text": "'
        for _ in range(40):
            yield b"y" * 4096
        yield b'"}'

    res = await client.post("/api/memories", data=chunks2(), headers={**write(client, csrf), "Content-Type": "application/json"})
    assert res.status == 413 and bot.db.list_memories() == []


async def test_multipart_parts_are_capped_while_reading(setup, monkeypatch):
    """Round 3, M1: a huge part is refused once it passes the cap, not after it's all in memory."""
    from aiohttp import FormData

    import claudebot.web.api as api_module

    bot, client = setup
    csrf = await sign_in(bot, client)
    monkeypatch.setattr(api_module, "MAX_FILE_BYTES", 100_000)
    form = FormData()
    form.add_field("file", b"z" * 300_000, filename="big.pdf", content_type="application/pdf")
    res = await client.post("/api/chat", data=form, headers=write(client, csrf))
    assert res.status == 400 and "too big" in (await res.json())["error"]
    form = FormData()
    form.add_field("text", "a" * 40_000, content_type="text/plain")  # a content type makes it multipart
    res = await client.post("/api/chat", data=form, headers=write(client, csrf))
    assert res.status == 400 and "too long" in (await res.json())["error"]
    form = FormData()
    for name in ("text", "file", "extra"):
        form.add_field(name, "x", filename="f.txt" if name != "text" else None)
    assert (await client.post("/api/chat", data=form, headers=write(client, csrf))).status == 400


async def test_reminder_dates_must_be_sensible(setup):
    """Round 3, L1."""
    bot, client = setup
    csrf = await sign_in(bot, client)
    for when, repeat in (("9999-12-31T23:59", "none"), ("0001-01-01T00:00", "daily")):
        res = await client.post("/api/reminders", json={"text": "x", "when": when, "repeat": repeat}, headers=write(client, csrf))
        assert res.status == 400
    assert bot.db.active_reminders() == []


async def test_answer_telegram_dms_from_the_web(setup):
    from datetime import timezone as tzu

    from claudebot.business import quick_tag

    bot, client = setup
    csrf = await sign_in(bot, client)
    delivered = []

    async def send_as_owner(chat_id, text, business_connection_id):
        delivered.append((chat_id, text))
        return SimpleNamespace(message_id=500 + len(delivered))

    bot._send_as_owner = send_as_owner
    bot.dms.save_connection(SimpleNamespace(id="bc1", user=SimpleNamespace(id=1), user_chat_id=1, is_enabled=True,
                                            rights=SimpleNamespace(can_reply=True)))

    def dm(text, message_id):
        return SimpleNamespace(business_connection_id="bc1", chat=SimpleNamespace(id=500, type="private", full_name="Alex"),
                               from_user=SimpleNamespace(id=500, full_name="Alex"), message_id=message_id,
                               date=datetime.now(tzu.utc), text=text, caption=None)

    bot.dms.record(dm("running late?", 1))
    d = await (await client.get("/api/dms")).json()
    chat = d["waiting"][0]
    assert chat["message_id"] == 1 and d["quick"][0]["text"] == "On it 👍"

    stale = await client.post("/api/dms/500/reply", json={"text": "ok", "message_id": 0}, headers=write(client, csrf))
    assert stale.status == 409 and delivered == []
    ok = await client.post("/api/dms/500/reply", json={"text": "No worries!", "message_id": 1}, headers=write(client, csrf))
    assert ok.status == 200 and delivered == [(500, "No worries!")]
    again = await client.post("/api/dms/500/reply", json={"text": "No worries!", "message_id": 1}, headers=write(client, csrf))
    assert again.status == 409 and len(delivered) == 1  # answered: nobody waiting, nothing sent twice

    bot.dms.record(dm("and tomorrow?", 2))
    quick = {"index": 0, "tag": quick_tag("On it 👍"), "message_id": 2}
    assert (await client.post("/api/dms/500/quick", json=quick, headers=write(client, csrf))).status == 200
    assert delivered[-1] == (500, "On it 👍")
    bot.dms.record(dm("one more", 3))
    bad_tag = {**quick, "tag": "deadbeef", "message_id": 3}
    assert (await client.post("/api/dms/500/quick", json=bad_tag, headers=write(client, csrf))).status == 409
    later = await (await client.post("/api/dms/500/later", headers=write(client, csrf))).json()
    assert "remind you" in later["message"] and len(delivered) == 2


async def test_one_reply_per_message_across_typed_and_quick_and_failures_are_explained(setup):
    """Round 4 M1/M2: a typed reply and a quick reply share one slot per message; an uncertain send keeps
    it (nothing goes out on top), and the reason reaches the page as an error."""
    from datetime import timezone as tzu

    from telegram.error import TimedOut

    from claudebot.business import quick_tag

    bot, client = setup
    csrf = await sign_in(bot, client)
    delivered, drop = [], {"on": True}

    async def send_as_owner(chat_id, text, business_connection_id):
        delivered.append(text)
        if drop["on"]:
            raise TimedOut("dropped")
        return SimpleNamespace(message_id=900)

    bot._send_as_owner = send_as_owner
    bot.dms.save_connection(SimpleNamespace(id="bc1", user=SimpleNamespace(id=1), user_chat_id=1, is_enabled=True,
                                            rights=SimpleNamespace(can_reply=True)))
    bot.dms.record(SimpleNamespace(business_connection_id="bc1", chat=SimpleNamespace(id=500, type="private", full_name="Alex"),
                                   from_user=SimpleNamespace(id=500, full_name="Alex"), message_id=7,
                                   date=datetime.now(tzu.utc), text="you there?", caption=None))
    res = await client.post("/api/dms/500/reply", json={"text": "Yes, 10 min", "message_id": 7}, headers=write(client, csrf))
    body = await res.json()
    assert res.status == 409 and "may have gone out" in body["error"]
    quick = {"index": 0, "tag": quick_tag("On it 👍"), "message_id": 7}
    again = await client.post("/api/dms/500/quick", json=quick, headers=write(client, csrf))
    assert again.status == 409 and delivered == ["Yes, 10 min"]  # nothing on top of a reply that may have landed
    assert (await client.post("/api/dms/500/reply", json={"text": "x", "message_id": True},
                              headers=write(client, csrf))).status == 400
    assert (await client.post("/api/dms/500/reply", json={"text": "x" * 4001, "message_id": 7},
                              headers=write(client, csrf))).status == 400


async def test_settings_switches_use_the_telegram_keys(setup):
    bot, client = setup
    csrf = await sign_in(bot, client)
    s = await (await client.get("/api/settings")).json()
    assert s["switches"]["checkins"] and not s["switches"]["drafts_only"]
    s = await (await client.post("/api/settings", json={"switch": "checkins", "on": False}, headers=write(client, csrf))).json()
    assert not s["switches"]["checkins"] and bot.db.get_setting("checkins") == "off"
    s = await (await client.post("/api/settings", json={"switch": "drafts_only", "on": True}, headers=write(client, csrf))).json()
    assert s["switches"]["drafts_only"] and bot.db.get_setting("drafts_only") == "on"
    for bad in ({"switch": "monthly_budget_usd", "on": True}, {"switch": "checkins", "on": "yes"}):
        assert (await client.post("/api/settings", json=bad, headers=write(client, csrf))).status == 400
