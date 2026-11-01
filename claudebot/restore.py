"""Restore from /export: send the claudebot-export-*.json file back (on a new server, say) and
confirm with one tap. Only the owner's own upload, never a forward. The card shows every memory,
rule, reminder and the writing style before anything is added, because those steer the assistant
and a file can come from anyone. What is added is capped and de-duplicated, and everything goes
through the same validation as normal use."""

import calendar
import io
import json
import logging
import secrets
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from .alert_rules import AlertRules
from .bills import MAX_BILLS, Bills
from .birthdays import MAX_BIRTHDAYS, Birthdays, parse_birthday
from .business import MAX_QUICK, MAX_QUICK_LEN, QUICK_KEY
from .expenses import currency_code
from .habits import Habits
from .journal import Journal
from .lists import Lists
from .modes import defang_urls
from .reminders import next_occurrence
from .style import STYLE_KEY, clean_style
from .ui import split_message

log = logging.getLogger(__name__)

PENDING_PREFIX = "restore_pending:"
MAX_FILE = 2_000_000
MAX_MEMORIES = 100
MAX_REMINDERS = 50
MAX_RULES = 20
MAX_LIST_ITEMS = 300
MAX_CARD_MESSAGES = 3
REPEATS = ("none", "daily", "weekdays", "weekly", "biweekly", "monthly", "yearly")


def looks_like_export(name: str, data: bytes) -> dict | None:
    if not name.lower().startswith("claudebot-export") or not name.lower().endswith(".json") or len(data) > MAX_FILE:
        return None
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return None
    return payload if isinstance(payload, dict) and "claudebot_version" in payload else None


def _clean(text, limit: int) -> str:
    return " ".join(str(text).replace("<", " ").replace(">", " ").split())[:limit]


def _due(value) -> datetime | None:
    try:
        due = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return due if due.tzinfo else due.replace(tzinfo=timezone.utc)


def plan(payload: dict, tz=timezone.utc) -> dict:
    """What a restore would add, capped and cleaned: the same thing the card shows and restore adds."""
    memories = [str(m.get("text", ""))[:500] for m in payload.get("memories", []) if isinstance(m, dict)]
    now = datetime.now(timezone.utc)
    reminders = []
    for r in payload.get("reminders", []):
        if not isinstance(r, dict) or r.get("task") or r.get("briefing") or r.get("repeat") not in REPEATS:
            continue
        due = _due(r.get("next_run"))
        if due and due <= now and r["repeat"] != "none":  # an older export: the next one, same wall time
            due = next_occurrence(due, r["repeat"], now, tz)
        if due and due > now:
            reminders.append({"text": str(r.get("text", ""))[:300], "due": due, "repeat": r["repeat"]})
    lists = []
    room = MAX_LIST_ITEMS
    for lst in payload.get("lists", [])[:20]:
        if not isinstance(lst, dict):
            continue
        items = [_clean(i.get("text", ""), 200) for i in lst.get("items", []) if isinstance(i, dict)]
        items = [i for i in items if i][:room]
        room -= len(items)
        lists.append({"name": _clean(lst.get("name", "List"), 40) or "List", "items": items})
    birthdays = []
    for b in payload.get("birthdays", []):
        if isinstance(b, dict):
            parsed = parse_birthday(f"{_clean(b.get('name', ''), 40)} {b.get('month')}-{b.get('day')}")
            if parsed:
                birthdays.append(parsed)
    bills = []
    for b in payload.get("bills", []):
        try:
            bill = {"name": _clean(b["name"], 40), "amount": round(float(b["amount"]), 2),
                    "currency": currency_code(str(b.get("currency", "USD"))), "day": int(b["day"])}
        except (KeyError, TypeError, ValueError):
            continue
        if bill["name"] and 0 < bill["amount"] <= 1_000_000_000 and 1 <= bill["day"] <= 31:
            bills.append(bill)
    raw_quick = payload.get("quick_replies")
    quick = [" ".join(str(t).split())[:MAX_QUICK_LEN] for t in raw_quick][:MAX_QUICK] if isinstance(raw_quick, list) else []
    quick = [t for t in quick if t]
    return {
        "memories": list(dict.fromkeys(m for m in memories if m))[:MAX_MEMORIES],
        "rules": list(dict.fromkeys(_clean(t, 150) for t in payload.get("alert_rules", []) if t))[:MAX_RULES],
        "reminders": reminders[:MAX_REMINDERS],
        "style": clean_style(str(payload["writing_style"])) if payload.get("writing_style") else "",
        "lists": lists,
        "birthdays": birthdays[:MAX_BIRTHDAYS],
        "bills": bills[:MAX_BILLS],
        "quick_replies": quick,
        "habits": [h for h in payload.get("habits", []) if isinstance(h, dict)][:10],
        "journal": [e for e in payload.get("journal", []) if isinstance(e, dict)][:3650],
    }


def preview(p: dict) -> str:
    """Everything that steers the assistant, spelled out in full (links defanged) before the owner taps:
    the card shows exactly the text that would be stored, so nothing can hide past a cut-off."""
    def show(text: str) -> str:
        return defang_urls(text)

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
    if p["quick_replies"]:  # these go out from your own Telegram account on a tap
        parts.append("⚡ Quick replies:\n" + "\n".join(f"- {show(t)}" for t in p["quick_replies"]))
    if p["bills"]:
        parts.append(f"🧾 {len(p['bills'])} bills:\n" + "\n".join(
            f"- {show(b['name'])}: {b['amount']:,.2f} {b['currency']} on day {b['day']}" for b in p["bills"]))
    if p["birthdays"]:
        parts.append(f"🎂 {len(p['birthdays'])} birthdays:\n" + "\n".join(
            f"- {show(name)}: {calendar.month_abbr[m]} {d}" for name, m, d in p["birthdays"]))
    for lst in p["lists"]:
        if lst["items"]:
            parts.append(f"📋 List {show(lst['name'])}:\n" + "\n".join(f"- {show(i)}" for i in lst["items"]))
    extra = [f"{len(p['lists'])} lists", f"{len(p['habits'])} habits", f"{len(p['journal'])} journal days"]
    parts.append("Also: " + ", ".join(extra) + ". Nothing you have now is deleted.")
    return "\n\n".join(parts)


def restore(db, payload: dict, tz=timezone.utc) -> dict:
    """Add what's in the export, skipping what's already here. Returns counts."""
    p = plan(payload, tz)
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
            counts["list items"] += len(lists.add(lst["name"], lst["items"]))
        except ValueError:
            continue
    def key(text, repeat, due: datetime):
        """Same reminder only if it fires at the same local time on the same pattern: "Take meds" at 8:00 and
        20:00, gym on Mondays and Thursdays, rent on the 1st and the 15th all stay separate (DST-proof)."""
        local = due.astimezone(tz)
        pattern = {"none": local.date().isoformat(), "weekly": local.weekday(),
                   "biweekly": (local.weekday(), local.date().toordinal() // 7 % 2), "monthly": local.day,
                   "yearly": (local.month, local.day)}.get(repeat, "")
        return text, repeat, local.strftime("%H:%M"), pattern

    existing = {key(r["text"], r["repeat"], datetime.fromisoformat(r["due_at"])) for r in db.active_reminders()}
    for r in p["reminders"]:
        k = key(r["text"], r["repeat"], r["due"])
        if k not in existing:  # restoring twice doesn't stack copies
            db.add_reminder(r["text"], r["due"], r["repeat"], False)
            existing.add(k)
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
    if p["quick_replies"]:
        db.set_setting(QUICK_KEY, json.dumps(p["quick_replies"]))
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
            text = preview(plan(payload, self.config.timezone))
        except Exception:
            log.exception("Couldn't read an export file")
            await message.reply_text("That export file is damaged; nothing was restored.")
            return True
        card = secrets.token_hex(4)  # each card restores its own file, not whatever was sent last
        self.db.set_setting(PENDING_PREFIX + card, json.dumps(payload))
        self.db.prune_settings(PENDING_PREFIX, 3)
        chunks = split_message(text)
        if len(chunks) > MAX_CARD_MESSAGES:  # a big export: the full list as a file, not dozens of messages
            p = plan(payload, self.config.timezone)
            await message.reply_document(document=io.BytesIO(text.encode()), filename="restore-preview.txt")
            chunks = [f"This export would add {len(p['memories'])} memories, {len(p['rules'])} alert rules, "
                      f"{len(p['reminders'])} reminders{', a writing style' if p['style'] else ''} and "
                      f"{sum(len(lst['items']) for lst in p['lists'])} list items. Every one is in "
                      "restore-preview.txt above, exactly as it would be stored: memories, rules and reminders "
                      "steer what I do, so read it before restoring, and only restore a file you made yourself."]
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
            counts = restore(self.db, json.loads(raw), self.config.timezone)
        except Exception:
            log.exception("Restore failed")
            await query.edit_message_text("That restore failed partway; check /memory and /reminders.")
            return
        p = plan(json.loads(raw), self.config.timezone)
        have = {b["name"].lower() for b in Birthdays(self.db).all()}
        for name, month, day in p["birthdays"]:  # through the normal path, so each gets its own reminder
            if name.lower() not in have:
                try:
                    self.add_birthday(name, month, day)
                except ValueError:
                    break
                have.add(name.lower())
                counts["birthdays"] = counts.get("birthdays", 0) + 1
        have = {b["name"].lower() for b in Bills(self.db).all()}
        for b in p["bills"]:
            if b["name"].lower() not in have:
                try:
                    self.add_bill(b["name"], b["amount"], b["day"], b["currency"])
                except ValueError:
                    break
                have.add(b["name"].lower())
                counts["bills"] = counts.get("bills", 0) + 1
        for row in self.db.active_reminders():
            self.schedule_reminder(row["id"])
        done = ", ".join(f"{n} {what}" for what, n in counts.items() if n) or "nothing new"
        await query.edit_message_text(f"✅ Restored: {done}.")
