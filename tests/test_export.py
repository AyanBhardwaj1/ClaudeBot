"""/export gives the owner their data, without secrets."""

import json
from types import SimpleNamespace

from helpers import TZ, make_config

from claudebot.actions import ActionLog
from claudebot.alert_rules import AlertRules
from claudebot.db import Database
from claudebot.export import export_data
from claudebot.lists import Lists


def test_export_has_the_owners_data_and_no_secrets(tmp_path):
    from datetime import datetime

    db = Database(tmp_path / "t.db")
    db.add_memory("Mom's birthday is May 3")
    db.add_reminder("call mom", datetime(2026, 11, 12, 18, tzinfo=TZ), "weekly", False)
    Lists(db).add("Shopping", ["milk"])
    AlertRules(db).add("never alert me about LinkedIn")
    ActionLog(db).record("email", "Sent email to sam@example.com")
    db.set_setting("style_guide", "short and warm")
    db.set_setting("cfg:owner_name", "Ayan")
    db.set_setting("google_oauth", '{"state": "s", "verifier": "SECRET"}')
    db.set_setting("business_connection", '{"id": "bc1"}')
    data = export_data(db)
    blob = json.dumps(data)
    assert data["memories"][0]["text"] == "Mom's birthday is May 3" and data["reminders"][0]["repeat"] == "weekly"
    assert data["lists"][0]["items"][0]["text"] == "milk" and data["alert_rules"] == ["never alert me about LinkedIn"]
    assert data["writing_style"] == "short and warm" and data["settings"]["cfg:owner_name"] == "Ayan"
    assert data["action_log_60_days"][0]["summary"] == "Sent email to sam@example.com"
    assert "SECRET" not in blob and "bc1" not in blob


async def test_export_command_sends_a_file_to_the_owner(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    sent = []

    async def send_document(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(type(bot.app.bot), "send_document", lambda self, **kw: send_document(**kw))
    await bot.on_export(SimpleNamespace(effective_message=None), None)
    assert sent[0]["chat_id"] == 1 and sent[0]["filename"].startswith("claudebot-export-")
    assert json.loads(sent[0]["document"].getvalue())["claudebot_version"]
