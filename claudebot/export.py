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
from .expenses import Expenses
from .habits import Habits
from .ious import Ious
from .journal import Journal
from .lists import Lists
from .style import current_style

# Only the owner's own preferences are exported (an allow-list: new internal keys stay out).
EXPORTED_PREFIXES = ("cfg:", "role", "mode", "followups", "checkins", "drafts_only", "meeting_prep", "weekly_review",
                     "newsletter_digest", "journal", "onboarded")


def export_data(db: Database, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    lists = Lists(db)
    settings = {r["key"]: r["value"] for r in db.conn.execute("SELECT key, value FROM settings ORDER BY key")
                if r["key"].startswith(EXPORTED_PREFIXES) and not r["key"].startswith("followups:")}
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
        "expenses_1_year": Expenses(db).summary(now - timedelta(days=365), now + timedelta(days=1))["by_category"],
        "habits": Habits(db).export(),
        "ious": Ious(db).balances(),
        "journal": [dict(r) for r in Journal(db).db.conn.execute("SELECT day, text FROM journal ORDER BY day")],
    }


class ExportHandlers:
    """Mixed into TelegramBot."""

    async def on_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        data = json.dumps(export_data(self.db), ensure_ascii=False, indent=2).encode()
        stamp = datetime.now(self.config.timezone).strftime("%Y-%m-%d")
        await self.app.bot.send_document(
            chat_id=self.config.owner_id, document=io.BytesIO(data), filename=f"claudebot-export-{stamp}.json",
            caption="Your memories, reminders, lists, alert rules, writing style, expenses, IOUs, habits, journal, settings "
                    "and what I did in the last 60 days. Not included: chat history, Telegram DMs and sign-in details.")
