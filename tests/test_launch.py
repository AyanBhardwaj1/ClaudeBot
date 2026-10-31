"""Launch polish: settings in chat, pairing, onboarding, Google from the chat, the setup wizard."""

import json
import os
import stat
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from helpers import TZ, FakeClient, make_config, message

from claudebot import google_connect, setup_wizard
from claudebot.db import Database
from claudebot.google_connect import ConnectError
from claudebot.roles import current_profile
from claudebot.settings import (
    InvalidSetting,
    apply_saved,
    resolve_place,
    save,
    save_owner_id,
)
from claudebot.usage import UsageTracker

CLIENT = {"installed": {"client_id": "id.apps.googleusercontent.com", "client_secret": "s3cret",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost"]}}


def place_reply(**fields):
    body = {"found": True, "city": "Austin", "region": "Texas", "country": "us", "timezone": "America/Chicago"}
    body.update(fields)
    return message("end_turn", [{"type": "text", "text": json.dumps(body)}], model="claude-haiku-5-5")


# --- saved settings ---


@pytest.mark.parametrize("text, stored", [
    ("8", "08:00"), ("7:30am", "07:30"), ("12am", "00:00"), ("7pm", "19:00"), ("19:05", "19:05"), ("off", ""),
])
def test_brief_times_are_forgiving(tmp_path, text, stored):
    assert save(Database(tmp_path / "t.db"), "daily_brief_time", text) == stored


@pytest.mark.parametrize("field, text", [
    ("daily_brief_time", "25:00"), ("daily_brief_time", "13pm"), ("quiet_hours", "late"),
    ("timezone", "Mars/Olympus"), ("undo_send_seconds", "9999"), ("monthly_budget_usd", "lots"),
    ("owner_name", "<>"), ("inbox_alerts", "maybe"),
])
def test_bad_settings_are_refused(tmp_path, field, text):
    with pytest.raises(InvalidSetting):
        save(Database(tmp_path / "t.db"), field, text)


def test_saved_settings_override_env_but_not_an_env_owner(tmp_path):
    db = Database(tmp_path / "t.db")
    save(db, "owner_name", "Ayan")
    save(db, "timezone", "Europe/London")
    save(db, "quiet_hours", "22:00 to 6am")
    save(db, "inbox_alerts", "off")
    save(db, "monthly_budget_usd", "$20")
    save_owner_id(db, 99)
    db.set_setting("cfg:undo_send_seconds", "garbage")  # skipped, not fatal
    config = apply_saved(make_config(tmp_path, owner_name="sir"), db)
    assert config.owner_name == "Ayan" and config.timezone.key == "Europe/London"
    assert config.quiet_hours == "22:00-06:00" and config.inbox_alerts is False
    assert config.monthly_budget_usd == 20 and config.undo_send_seconds == 20
    assert config.owner_id == 1  # TELEGRAM_OWNER_ID in .env wins over a paired ID
    assert apply_saved(make_config(tmp_path, owner_id=None), db).owner_id == 99


async def test_place_lookup_validates_what_the_model_returns(tmp_path):
    db = Database(tmp_path / "t.db")
    tracker = UsageTracker(db, TZ, None)
    client = FakeClient([place_reply(), place_reply(timezone="Nowhere/Land"), place_reply(found=False)])
    config = make_config(tmp_path)
    assert await resolve_place(client, tracker, config, "austin") == {
        "city": "Austin", "region": "Texas", "country": "US", "timezone": "America/Chicago"}
    assert await resolve_place(client, tracker, config, "x") is None
    assert await resolve_place(client, tracker, config, "asdf") is None


# --- the bot ---


def make_bot(tmp_path, monkeypatch, **config):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc", **config))
    sent, restarts = [], []

    async def send_to_owner(text, reply_markup=None):
        sent.append((text, reply_markup))

    bot.send_to_owner = send_to_owner
    bot.request_restart = lambda: restarts.append(True)
    return bot, sent, restarts


def text_message(text, user_id=1):
    replies = []

    async def reply_text(body, reply_markup=None):
        replies.append(body)

    async def delete():
        replies.append("<deleted>")

    return SimpleNamespace(text=text, reply_text=reply_text, delete=delete, forward_origin=None), replies


def tap(data, user_id=1, first_name="Ayan"):
    async def noop(*args, **kwargs):
        pass

    return SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, first_name=first_name), data=data, answer=noop,
        edit_message_reply_markup=noop, edit_message_text=noop))


def callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


async def test_pairing_needs_the_code_from_the_log(tmp_path, monkeypatch):
    bot, _, restarts = make_bot(tmp_path, monkeypatch, owner_id=None)
    code = bot.pairing_code
    assert len(code) == 6

    def update(text, user_id):
        msg, replies = text_message(text)
        return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), effective_message=msg), replies

    wrong = "000000" if code != "000000" else "111111"
    u, replies = update(f"/start {wrong}", 7)
    await bot.on_unconfigured(u, None)
    assert restarts == [] and "code" in replies[0]
    for _ in range(10):  # five wrong tries and that account is ignored, even with the right code
        await bot.on_unconfigured(update(f"/start {wrong}", 7)[0], None)
    await bot.on_unconfigured(update(f"/start {code}", 7)[0], None)
    assert restarts == []

    u, replies = update(f"/start {code}", 42)
    await bot.on_unconfigured(u, None)
    assert restarts == [True] and "Paired" in replies[0]
    assert apply_saved(make_config(tmp_path, owner_id=None), bot.db).owner_id == 42


async def test_onboarding_walks_through_four_questions(tmp_path, monkeypatch):
    bot, sent, restarts = make_bot(tmp_path, monkeypatch)
    bot.client = FakeClient([place_reply()])
    assert not bot.onboarded()
    await bot.begin_onboarding()
    assert "1/4" in sent[-1][0]

    for text in ("Ayan", "Austin TX", "nurse in the ER", "7:30am"):
        msg, _ = text_message(text)
        assert await bot.handle_answer(msg)
    assert "Connect now" in str(sent[-1][1].inline_keyboard)
    await bot.on_onboard_button(tap("ob:google:later"), None)

    assert bot.onboarded() and restarts == [True] and "All set, Ayan" in sent[-1][0]
    config = apply_saved(bot.config, bot.db)
    assert (config.owner_name, config.city, config.timezone.key, config.daily_brief_time) == (
        "Ayan", "Austin", "America/Chicago", "07:30")
    assert current_profile(bot.db).describe() == "Healthcare (in the ER)"
    msg, _ = text_message("what's on today?")
    assert not await bot.handle_answer(msg)  # done: normal messages go to Claude again


async def test_onboarding_buttons_and_skips(tmp_path, monkeypatch):
    bot, sent, restarts = make_bot(tmp_path, monkeypatch)
    await bot.begin_onboarding()
    await bot.on_onboard_button(tap("ob:tgname", first_name="Ayan<b>"), None)
    await bot.on_onboard_button(tap("ob:skip"), None)  # place
    assert "ob:role:student" in callbacks(sent[-1][1])
    await bot.on_onboard_button(tap("ob:role:student", user_id=999), None)  # a stranger: ignored
    assert current_profile(bot.db) is None
    await bot.on_onboard_button(tap("ob:role:student"), None)
    await bot.on_onboard_button(tap("ob:brief:off"), None)
    await bot.on_onboard_button(tap("ob:brief:0800"), None)  # an old question's button: ignored
    await bot.on_onboard_button(tap("ob:google:later"), None)
    config = apply_saved(bot.config, bot.db)
    assert config.owner_name == "Ayan b" and config.daily_brief_time is None and config.city is None
    assert current_profile(bot.db).role.key == "student" and restarts == [True]


async def test_bad_answers_ask_again(tmp_path, monkeypatch):
    bot, sent, _ = make_bot(tmp_path, monkeypatch)
    bot.client = FakeClient([place_reply(found=False)])
    bot._expect("ob:place")
    msg, _ = text_message("the moon")
    assert await bot.handle_answer(msg)
    assert "couldn't place" in sent[-1][0] and bot._awaiting() == "ob:place"
    bot._expect("set:daily_brief_time")
    msg, _ = text_message("whenever")
    assert await bot.handle_answer(msg)
    assert "8:00" in sent[-1][0] and bot._awaiting() == "set:daily_brief_time"


async def test_questions_expire(tmp_path, monkeypatch):
    bot, _, _ = make_bot(tmp_path, monkeypatch)
    bot.db.set_setting("await", json.dumps({"what": "ob:name", "at": time.time() - 3600}))
    msg, _ = text_message("hello there")
    assert not await bot.handle_answer(msg)


async def test_settings_buttons_save_and_restart(tmp_path, monkeypatch):
    bot, sent, restarts = make_bot(tmp_path, monkeypatch)
    msg, replies = text_message("/settings")
    await bot.on_settings(SimpleNamespace(effective_message=msg), None)
    assert "Daily brief: off" in replies[0]

    await bot.on_settings_button(tap("set:brief"), None)
    assert "setv:brief:0800" in callbacks(sent[-1][1])
    await bot.on_settings_button(tap("setv:brief:0800"), None)
    await bot.on_settings_button(tap("setv:quiet:2200-0800"), None)
    await bot.on_settings_button(tap("set:alerts"), None)
    await bot.on_settings_button(tap("setv:budget:9999999"), None)  # not a real choice: ignored
    await bot.on_settings_button(tap("setv:undo:20", user_id=999), None)
    config = apply_saved(bot.config, bot.db)
    assert config.daily_brief_time == "08:00" and config.quiet_hours == "22:00-08:00"
    assert config.inbox_alerts is False and config.monthly_budget_usd is None
    assert len(restarts) == 3 and sent[-1][0] == "✅ Inbox alerts: off"

    await bot.on_settings_button(tap("set:name"), None)
    msg, _ = text_message("Captain")
    assert await bot.handle_answer(msg)
    assert apply_saved(bot.config, bot.db).owner_name == "Captain" and len(restarts) == 4


# --- Google from the chat ---


def test_client_file_must_be_a_desktop_client(tmp_path):
    config = make_config(tmp_path)
    for bad in (b"not json", b"[]", json.dumps({"web": CLIENT["installed"]}).encode(), b'{"installed": {}}'):
        with pytest.raises(ConnectError):
            google_connect.save_client(config, bad)
    google_connect.save_client(config, json.dumps(CLIENT).encode())
    path = google_connect.client_file(config)
    assert path == tmp_path / "google_client.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


class FakeFlow:
    def __init__(self, scopes):
        self.code = None
        self.credentials = SimpleNamespace(granted_scopes=scopes, to_json=lambda: '{"token": "t"}')

    def fetch_token(self, code):
        self.code = code


def test_sign_in_checks_state_expiry_and_scopes(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    db = Database(tmp_path / "t.db")
    google_connect.save_client(config, json.dumps(CLIENT).encode())
    url = google_connect.start(config, db)
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"] and query["redirect_uri"] == ["http://localhost:1/"]
    state = query["state"][0]

    with pytest.raises(ConnectError, match="isn't the address"):
        google_connect.finish(config, db, "http://localhost:1/?state=forged&code=abc")
    with pytest.raises(ConnectError, match="allowed"):
        google_connect.finish(config, db, f"http://localhost:1/?state={state}&error=access_denied")

    url = google_connect.start(config, db)
    state = parse_qs(urlsplit(url).query)["state"][0]
    flow = FakeFlow(["https://www.googleapis.com/auth/gmail.modify"])
    monkeypatch.setattr(google_connect, "_flow", lambda path, **kw: flow)
    with pytest.raises(ConnectError, match="unticked"):
        google_connect.finish(config, db, f"http://localhost:1/?state={state}&code=c1&scope=x")
    assert not config.google_token_file.exists()

    flow.credentials.granted_scopes = list(google_connect.SCOPES)
    google_connect.finish(config, db, f"http://localhost:1/?state={state}&code=c2&scope=x")
    assert flow.code == "c2" and config.google_token_file.read_text() == '{"token": "t"}'
    assert stat.S_IMODE(os.stat(config.google_token_file).st_mode) == 0o600
    with pytest.raises(ConnectError, match="expired"):  # one sign-in, one use
        google_connect.finish(config, db, f"http://localhost:1/?state={state}&code=c2")


async def test_pasted_sign_in_codes_never_reach_claude(tmp_path, monkeypatch):
    bot, sent, _ = make_bot(tmp_path, monkeypatch)
    msg, replies = text_message("http://localhost:1/?state=abc&code=4/0secret&scope=x")
    assert await bot.handle_answer(msg)  # handled here, not sent to the agent
    assert replies == ["<deleted>"] and "expired" in sent[-1][0]


async def test_connect_asks_for_the_client_file_first(tmp_path, monkeypatch):
    bot, sent, _ = make_bot(tmp_path, monkeypatch)
    await bot.on_connect(None, None)
    assert "Desktop app" in sent[-1][0] and bot._awaiting() == "google:client"
    google_connect.save_client(bot.config, json.dumps(CLIENT).encode())
    await bot.on_connect(None, None)
    button = sent[-1][1].inline_keyboard[0][0]
    assert button.url.startswith("https://accounts.google.com/") and bot._awaiting() == "google:code"


# --- setup wizard ---


def test_update_env_keeps_comments_and_other_settings(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# Claude\nANTHROPIC_API_KEY=\n# keep me\nQUIET_HOURS=22:00-06:00\n")
    setup_wizard.update_env(env, {"ANTHROPIC_API_KEY": "sk-1", "TELEGRAM_OWNER_ID": "42"})
    assert env.read_text() == (
        "# Claude\nANTHROPIC_API_KEY=sk-1\n# keep me\nQUIET_HOURS=22:00-06:00\nTELEGRAM_OWNER_ID=42\n")
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600


def test_wizard_finds_the_owner_from_their_first_message(monkeypatch):
    calls = []
    updates = [[{"update_id": 5, "message": {"chat": {"type": "group"}, "from": {"id": 9}}},
                {"update_id": 6, "message": {"chat": {"type": "private"}, "from": {"id": 42, "first_name": "Ayan"}}}]]

    def fake(token, method, **params):
        calls.append((method, params.get("offset")))
        return updates.pop(0) if method == "getUpdates" and updates else []

    monkeypatch.setattr(setup_wizard, "telegram", fake)
    assert setup_wizard.wait_for_owner("t", timeout=5)["id"] == 42
    assert ("getUpdates", 7) in calls  # acknowledged, so the bot doesn't answer "hi" later


def test_wizard_rejects_tokens_that_cant_be_right():
    with pytest.raises(setup_wizard.SetupError):
        setup_wizard.check_telegram("my-password")
