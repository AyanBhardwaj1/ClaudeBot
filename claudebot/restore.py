"""Restore from /export: send the claudebot-export-*.json file back (on a new server, say) and
confirm with one tap. Only the owner's own upload, never a forward. The card shows every memory,
rule, reminder and the writing style before anything is added, because those steer the assistant
and a file can come from anyone. What is added is capped and de-duplicated, and everything goes
through the same validation as normal use."""

import json
import logging
import secrets
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from .alert_rules import AlertRules
from .habits import Habits
from .inbox_watch import clip
from .journal import Journal
from .lists import Lists
from .modes import defang_urls
from .style import STYLE_KEY, clean_style
from .ui import split_message

log = logging.getLogger(__name__)

PENDING_PREFIX = "restore_pending:"
MAX_FILE = 2_000_000
MAX_MEMORIES = 100
MAX_REMINDERS = 50
MAX_RULES = 20
REPEATS = ("none", "daily", "weekdays", "weekly", "biweekly", "monthly", "yearly")


def looks_like_export(name: str, data: bytes) -> dict | None:
    if not name.lower().startswith("claudebot-export") or not name.lower().endswith(".json") or len(data) > MAX_FILE:
        return None
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return None
    return payload if isinstance(payload, dict) and "claudebot_version" in payload else None


def _due(value) -> datetime | None:
    try:
        due = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return due if due.tzinfo else due.replace(tzinfo=timezone.utc)


def plan(payload: dict) -> dict:
    """What a restore would add, capped and cleaned: the same thing the card shows and restore adds."""
    memories = [str(m.get("text", ""))[:500] for m in payload.get("memories", []) if isinstance(m, dict)]
    now = datetime.now(timezone.utc)
    reminders = []
    for r in payload.get("reminders", []):
        if not isinstance(r, dict) or r.get("task") or r.get("briefing") or r.get("repeat") not in REPEATS:
            continue
        due = _due(r.get("next_run"))
        if due and due > now:
            reminders.append({"text": str(r.get("text", ""))[:300], "due": due, "repeat": r["repeat"]})
    return {
        "memories": [m for m in memories if m][:MAX_MEMORIES],
        "rules": [str(t)[:150] for t in payload.get("alert_rules", []) if t][:MAX_RULES],
        "reminders": reminders[:MAX_REMINDERS],
        "style": clean_style(str(payload["writing_style"])) if payload.get("writing_style") else "",
        "lists": [lst for lst in payload.get("lists", []) if isinstance(lst, dict)][:20],
        "habits": [h for h in payload.get("habits", []) if isinstance(h, dict)][:10],
        "journal": [e for e in payload.get("journal", []) if isinstance(e, dict)][:3650],
    }


def preview(p: dict) -> str:
    """Everything that steers the assistant, spelled out (links defanged) before the owner taps."""
    def show(text: str) -> str:
        return defang_urls(clip(text, 160))

    parts = ["This looks like a ClaudeBot export. Check what it would add before restoring: memories, rules "
             "and reminders steer what I do, so only restore a file you made yourself."]
    if p["memories"]:
        parts.append(f"🧠 {len(p['memories'])} memories:\n" + "\n".join(f"- {show(m)}" for m in p["memories"]))
    if p["rules"]:
        parts.append(f"📏 {len(p['rules'])} alert rules:\n" + "\n".join(f"- {show(r)}" for r in p["rules"]))
    if p["reminders"]:
        parts.append(f"⏰ {len(p['reminders'])} reminders:\n" + "\n".join(
            f"- {show(r['text'])} ({r['repeat']}, next {r['due']:%b %-d})" for r in p["reminders"]))
    if p["style"]:
        parts.append(f"✍️ Writing style:\n{show(p['style'])}")
    extra = [f"{len(p['lists'])} lists", f"{len(p['habits'])} habits", f"{len(p['journal'])} journal days"]
    parts.append("Also: " + ", ".join(extra) + ". Nothing you have now is deleted.")
    return "\n\n".join(parts)


def restore(db, payload: dict) -> dict:
    """Add what's in the export, skipping what's already here. Returns counts."""
    p = plan(payload)
    counts = {"memories": 0, "list items": 0, "reminders": 0, "rules": 0, "habit days": 0, "journal days": 0}
    known = {m["text"] for m in db.list_memories()}
    for text in p["memories"]:
        if text not in known:
            db.add_memory(text)
            known.add(text)
            counts["memories"] += 1
    lists = Lists(db)
    for lst in p["lists"]:
        try:
            counts["list items"] += len(lists.add(str(lst.get("name", "List")),
                                                  [str(i.get("text", "")) for i in lst.get("items", []) if isinstance(i, dict)]))
        except ValueError:
            continue
    existing = {(r["text"], r["repeat"]) for r in db.active_reminders()}
    for r in p["reminders"]:
        if (r["text"], r["repeat"]) not in existing:  # restoring twice doesn't stack copies
            db.add_reminder(r["text"], r["due"], r["repeat"], False)
            existing.add((r["text"], r["repeat"]))
            counts["reminders"] += 1
    rules = AlertRules(db)
    have = {r["text"] for r in rules.all()}
    for text in p["rules"]:
        if text not in have:
            try:
                rules.add(text)
                counts["rules"] += 1
            except ValueError:
                break
    if p["style"]:
        db.set_setting(STYLE_KEY, p["style"])
    habits = Habits(db)
    for h in p["habits"]:
        try:
            habit = habits.add(str(h.get("name", "")))
        except ValueError:
            continue
        for day in h.get("days_done", [])[:3650]:
            try:
                counts["habit days"] += habits.mark(habit["id"], datetime.fromisoformat(str(day)).date())
            except ValueError:
                continue
    journal = Journal(db)
    for entry in p["journal"]:
        day, text = str(entry.get("day", ""))[:10], str(entry.get("text", ""))
        if not day or not text:
            continue
        current = journal.recent(1, day)
        if current and text in current[0]["text"]:
            continue  # already there
        journal.write(day, text)
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
        try:
            text = preview(plan(payload))
        except Exception:
            log.exception("Couldn't read an export file")
            await message.reply_text("That export file is damaged; nothing was restored.")
            return True
        card = secrets.token_hex(4)  # each card restores its own file, not whatever was sent last
        self.db.set_setting(PENDING_PREFIX + card, json.dumps(payload))
        self.db.prune_settings(PENDING_PREFIX, 3)
        chunks = split_message(text)
        for chunk in chunks[:-1]:
            await message.reply_text(chunk)
        await message.reply_text(chunks[-1], reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Restore", callback_data=f"restore:yes:{card}"),
            InlineKeyboardButton("✖️ No", callback_data=f"restore:no:{card}")]]))
        return True

    async def on_restore_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        _, answer, card = query.data.split(":")
        raw = self.db.get_setting(PENDING_PREFIX + card)
        self.db.delete_setting(PENDING_PREFIX + card)
        if answer == "no" or not raw:
            await query.edit_message_text("Not restored.")
            return
        try:
            counts = restore(self.db, json.loads(raw))
        except Exception:
            log.exception("Restore failed")
            await query.edit_message_text("That restore failed partway; check /memory and /reminders.")
            return
        for row in self.db.active_reminders():
            self.schedule_reminder(row["id"])
        done = ", ".join(f"{n} {what}" for what, n in counts.items() if n) or "nothing new"
        await query.edit_message_text(f"✅ Restored: {done}.")
