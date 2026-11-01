"""/export: everything ClaudeBot keeps about the owner, as one JSON file they own. Sign-in state
and other secrets are left out."""

import io
import json
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from . import __version__
from .actions import ActionLog
from .alert_rules import AlertRules
from .db import Database
from .lists import Lists
from .style import current_style

# Settings that are secrets, one-time sign-in state, or button bookkeeping: never exported.
PRIVATE_PREFIXES = ("google_oauth", "await", "followups:", "alert:", "hb_", "prep", "thread_", "expects_reply:",
                    "snoozed:", "business_connection", "style_pending", "inbox_failures", "onboarding")


def export_data(db: Database, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    lists = Lists(db)
    settings = {r["key"]: r["value"] for r in db.conn.execute("SELECT key, value FROM settings ORDER BY key")
                if not r["key"].startswith(PRIVATE_PREFIXES)}
    return {
        "exported_at": now.isoformat(),
        "claudebot_version": __version__,
        "memories": [dict(m) for m in db.conn.execute("SELECT id, text, created_at FROM memories ORDER BY id")],
        "reminders": [{"id": r["id"], "text": r["text"], "next_run": r["due_at"], "repeat": r["repeat"],
                       "task": bool(r["run_as_task"]), "briefing": bool(r["briefing"])} for r in db.active_reminders()],
        "lists": [{"name": n, "items": lists.items(n)} for n in lists.names()],
        "alert_rules": [r["text"] for r in AlertRules(db).all()],
        "writing_style": current_style(db),
        "settings": settings,
        "action_log_60_days": ActionLog(db).since(now - timedelta(days=60)),
    }


class ExportHandlers:
    """Mixed into TelegramBot."""

    async def on_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        data = json.dumps(export_data(self.db), ensure_ascii=False, indent=2).encode()
        stamp = datetime.now(self.config.timezone).strftime("%Y-%m-%d")
        await self.app.bot.send_document(
            chat_id=self.config.owner_id, document=io.BytesIO(data), filename=f"claudebot-export-{stamp}.json",
            caption="Everything I keep about you: memories, reminders, lists, rules, style, settings and what I did "
                    "in the last 60 days. Sign-in details aren't included.")
