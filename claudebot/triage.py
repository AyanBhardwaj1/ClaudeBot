"""/triage: unread important email, one at a time, with Archive / Reply / Later / Next. Listing
and archiving are plain Gmail calls; Claude is only involved when you tap Reply."""

import asyncio
import json
import logging
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .actions import ActionLog
from .google_services import GoogleNotConnected
from .inbox_watch import GMAIL_ID, _sender, clip
from .modes import defang_urls
from .quiet import next_morning
from .snooze import done, snooze

log = logging.getLogger(__name__)

QUERY = "in:inbox is:unread category:primary newer_than:14d"
MAX_QUEUE = 20
QUEUE_KEY = "triage_queue"


def _card(email: dict, left: int) -> tuple[str, InlineKeyboardMarkup]:
    name, address = _sender(email["from"])
    who = f"{name} <{address}>" if name else address
    text = (f"📥 {left} to go\n\nFrom: {who}\nSubject: {defang_urls(clip(email['subject'] or '(no subject)', 120))}\n\n"
            f"{defang_urls(clip(email.get('snippet', ''), 300))}")
    i = email["id"]
    return text, InlineKeyboardMarkup([[
        InlineKeyboardButton("🗄 Archive", callback_data=f"tri:arch:{i}"),
        InlineKeyboardButton("✍️ Reply", callback_data=f"tri:draft:{i}"),
        InlineKeyboardButton("⏰ Later", callback_data=f"tri:later:{i}"),
        InlineKeyboardButton("💤 Tmrw", callback_data=f"tri:snooze:{i}"),
        InlineKeyboardButton("⏭ Next", callback_data=f"tri:next:{i}"),
    ]])


class TriageHandlers:
    """Mixed into TelegramBot."""

    async def on_triage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        try:
            emails = await asyncio.to_thread(self.google.search_emails, QUERY, MAX_QUEUE)
        except GoogleNotConnected:
            await message.reply_text("Connect Gmail first: /connect")
            return
        except Exception:
            log.exception("Listing unread email failed")
            await message.reply_text("I couldn't read your inbox just now. Try again in a minute.")
            return
        queue = [{k: e.get(k, "") for k in ("id", "from", "subject", "snippet")} for e in emails if GMAIL_ID.fullmatch(e["id"])]
        if not queue:
            await message.reply_text("✨ No unread important email from the last two weeks. Inbox zero.")
            return
        self.db.set_setting(QUEUE_KEY, json.dumps(queue))
        text, markup = _card(queue[0], len(queue))
        await message.reply_text(text, reply_markup=markup)

    def _requeue(self, item: dict) -> None:
        queue = json.loads(self.db.get_setting(QUEUE_KEY) or "[]")
        self.db.set_setting(QUEUE_KEY, json.dumps([item] + [q for q in queue if q["id"] != item["id"]]))

    async def on_triage_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        _, action, message_id = query.data.split(":")
        queue = json.loads(self.db.get_setting(QUEUE_KEY) or "[]")
        if not queue or queue[0]["id"] != message_id:
            await query.answer("That card is old; send /triage again.")
            return
        current = queue.pop(0)
        self.db.set_setting(QUEUE_KEY, json.dumps(queue))  # claimed now: a double tap finds an old card
        if action == "arch":
            try:
                await asyncio.to_thread(self.google.modify_email, message_id, "archive")
                ActionLog(self.db).record("email", "Archived an email (/triage)")
            except Exception:
                log.exception("Archiving %s failed", message_id)
                self._requeue(current)  # the card still works: try again or pick another button
                await query.answer("Couldn't archive that one.")
                return
        elif action == "snooze":
            name, address = _sender(current["from"])
            until = next_morning(datetime.now(self.config.timezone) + timedelta(hours=4), time(8))
            try:  # held first, so a full snooze list is refused before the email leaves the inbox
                snooze(self.db, message_id, f"{name or address}: {clip(current['subject'], 100)}", until)
            except ValueError as e:
                self._requeue(current)
                await query.answer(str(e))
                return
            try:
                await asyncio.to_thread(self.google.modify_email, message_id, "archive")
            except Exception:
                log.exception("Snoozing %s failed", message_id)
                done(self.db, message_id)
                self._requeue(current)  # the card still works: try again or pick another button
                await query.answer("Couldn't snooze that one.")
                return
            ActionLog(self.db).record("email", f"Snoozed an email until {until:%a %H:%M}")
        elif action == "later":
            when = datetime.now(self.config.timezone) + timedelta(hours=3)
            name, address = _sender(current["from"])
            text = f"Follow up on the email from {name or address}: {clip(current['subject'], 100)}"
            self.schedule_reminder(self.db.add_reminder(text, when, "none", False))
            ActionLog(self.db).record("reminder", f"Set a reminder: {text} ({when:%a %H:%M})")
        await query.answer({"arch": "🗄 Archived", "later": "⏰ Reminder in 3 hours", "next": "⏭",
                            "draft": "✍️ Drafting...", "snooze": "💤 Back at 8:00"}[action])
        self.db.set_setting(QUEUE_KEY, json.dumps(queue))
        if queue:
            text, markup = _card(queue[0], len(queue))
            await query.edit_message_text(text, reply_markup=markup)
        else:
            await query.edit_message_text("✨ That's all of them. Nice work.")
        if action == "draft":
            prompt = (f"Draft a reply to the email with message id {message_id}. Read it first. Show me the draft "
                      "here, and don't send or save it until I say so.")
            async with self._message_order:
                await self._converse([{"type": "text", "text": prompt}], "Draft a reply", owner_present=False)
