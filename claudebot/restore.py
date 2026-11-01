"""Restore from /export: send the claudebot-export-*.json file back (on a new server, say) and
confirm with one tap. Only the owner's own file, never a forward; everything is re-validated by
the same code that stores it normally."""

import json
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from .alert_rules import AlertRules
from .habits import Habits
from .journal import Journal
from .lists import Lists
from .style import STYLE_KEY, clean_style

log = logging.getLogger(__name__)

PENDING_KEY = "restore_pending"
MAX_FILE = 5_000_000


def looks_like_export(name: str, data: bytes) -> dict | None:
    if not name.lower().startswith("claudebot-export") or not name.lower().endswith(".json") or len(data) > MAX_FILE:
        return None
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) and "claudebot_version" in payload else None


def restore(db, payload: dict) -> dict:
    """Add what's in the export (nothing existing is deleted). Returns counts."""
    counts = {"memories": 0, "list items": 0, "reminders": 0, "rules": 0, "habit days": 0, "journal days": 0}
    known = {m["text"] for m in db.list_memories()}
    for m in payload.get("memories", [])[:1000]:
        text = str(m.get("text", ""))[:500]
        if text and text not in known:
            db.add_memory(text)
            counts["memories"] += 1
    lists = Lists(db)
    for lst in payload.get("lists", [])[:20]:
        try:
            counts["list items"] += len(lists.add(str(lst.get("name", "List")), [str(i.get("text", "")) for i in lst.get("items", [])]))
        except ValueError:
            continue
    now = datetime.now(timezone.utc)
    for r in payload.get("reminders", [])[:200]:
        try:
            due = datetime.fromisoformat(r["next_run"])
        except (KeyError, TypeError, ValueError):
            continue
        if due > now and not r.get("task") and not r.get("briefing") and r.get("repeat") in (
                "none", "daily", "weekdays", "weekly", "biweekly", "monthly", "yearly"):
            db.add_reminder(str(r.get("text", ""))[:500], due, r["repeat"], False)
            counts["reminders"] += 1
    rules = AlertRules(db)
    existing = {r["text"] for r in rules.all()}
    for text in payload.get("alert_rules", [])[:20]:
        if text not in existing:
            try:
                rules.add(str(text))
                counts["rules"] += 1
            except ValueError:
                break
    if payload.get("writing_style"):
        db.set_setting(STYLE_KEY, clean_style(str(payload["writing_style"])))
    habits = Habits(db)
    for h in payload.get("habits", [])[:10]:
        try:
            habit = habits.add(str(h.get("name", "")))
        except ValueError:
            continue
        for day in h.get("days_done", [])[:3650]:
            try:
                counts["habit days"] += habits.mark(habit["id"], datetime.fromisoformat(day).date())
            except (TypeError, ValueError):
                continue
    journal = Journal(db)
    for entry in payload.get("journal", [])[:3650]:
        if entry.get("day") and entry.get("text"):
            journal.write(str(entry["day"])[:10], str(entry["text"]))
            counts["journal days"] += 1
    return counts


class RestoreHandlers:
    """Mixed into TelegramBot."""

    async def handle_export_file(self, message: Message, data: bytes) -> bool:
        if message.forward_origin:
            return False  # someone else's file can't load memories or rules into your assistant
        payload = looks_like_export(message.document.file_name or "", data)
        if payload is None:
            return False
        self.db.set_setting(PENDING_KEY, json.dumps(payload))
        summary = (f"{len(payload.get('memories', []))} memories, {len(payload.get('lists', []))} lists, "
                   f"{len(payload.get('reminders', []))} reminders, {len(payload.get('alert_rules', []))} rules")
        await message.reply_text(
            f"This looks like a ClaudeBot export ({summary}). Restore it? Nothing you have now is deleted.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Restore", callback_data="restore:yes"),
                                                InlineKeyboardButton("✖️ No", callback_data="restore:no")]]))
        return True

    async def on_restore_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        raw = self.db.get_setting(PENDING_KEY)
        self.db.delete_setting(PENDING_KEY)
        if query.data == "restore:no" or not raw:
            await query.edit_message_text("Not restored.")
            return
        counts = restore(self.db, json.loads(raw))
        for row in self.db.active_reminders():
            self.schedule_reminder(row["id"])
        done = ", ".join(f"{n} {what}" for what, n in counts.items() if n) or "nothing new"
        await query.edit_message_text(f"✅ Restored: {done}.")
