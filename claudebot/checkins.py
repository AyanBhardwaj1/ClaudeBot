"""Telegram side of ClaudeBot 1.1: /reminders, /waiting (reply tracking with Nudge and Reply
buttons), check-ins, and telling the owner when inbox alerts stop working. Mixed into TelegramBot.
"""

import logging
from datetime import datetime

from google.auth.exceptions import RefreshError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .google_services import GoogleNotConnected
from .heartbeat import run_heartbeat
from .inbox_watch import GMAIL_ID, in_quiet_hours
from .replies import find_reply_gaps

log = logging.getLogger(__name__)

INBOX_FAILURE_NOTICE = 3  # consecutive failed checks before telling the owner
INBOX_FAILURES_KEY = "inbox_failures"
MAX_LISTED = 5
NUDGE_PROMPT = (
    "Draft a short, polite follow-up to the email with message id {id}: I wrote last and haven't "
    "heard back. Read the thread first. Show me the draft here, and don't send or save it until I say so."
)
REPLY_PROMPT = (
    "Draft a reply to the email with message id {id}. Read it first. Show me the draft here, and "
    "don't send or save it until I say so."
)


def _reason(error: Exception) -> str:
    if isinstance(error, GoogleNotConnected):
        return "Google isn't connected. Send /connect to fix it."
    if isinstance(error, RefreshError):
        return "Google sign-in expired or was revoked. Send /connect to sign in again."
    return f"Checking Gmail keeps failing ({type(error).__name__}). I'll keep trying."


class CheckinHandlers:
    # --- /reminders ---

    async def on_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        rows = self.db.active_reminders()
        if not rows:
            await update.effective_message.reply_text(
                "No reminders. Just ask, e.g. \"remind me at 6pm to call mom\" or \"every Monday at 9, "
                "plan my week\"."
            )
            return
        lines, rows_of_buttons = [], []
        for r in rows:
            when = datetime.fromisoformat(r["due_at"]).astimezone(self.config.timezone)
            icon = "🗞" if r["briefing"] else ("⚙️" if r["run_as_task"] else "⏰")
            repeat = "" if r["repeat"] == "none" else f", {r['repeat']}"
            lines.append(f"{icon} {r['text'][:80]} ({when:%a %b %d %H:%M}{repeat})")
            rows_of_buttons.append([InlineKeyboardButton(f"✖️ {r['text'][:40]}", callback_data=f"unrem:{r['id']}")])
        await update.effective_message.reply_text(
            "Your reminders and scheduled tasks:\n" + "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(rows_of_buttons),
        )

    async def on_reminder_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        reminder_id = int(query.data.split(":")[1])
        row = self.db.get_reminder(reminder_id)
        if row is None or not row["active"]:
            await query.answer("Already cancelled.")
            return
        self.db.deactivate_reminder(reminder_id)
        self.unschedule_reminder(reminder_id)
        await query.answer(f"Cancelled: {row['text'][:150]}")

    # --- /waiting ---

    async def on_waiting(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        try:
            gaps = await find_reply_gaps(self.google, self.client, self.tracker, self.config, self.db)
        except GoogleNotConnected:
            await message.reply_text("Connect Gmail first: /connect")
            return
        except Exception:
            log.exception("Reply tracking failed")
            await message.reply_text("I couldn't check your email just now. Try again in a minute.")
            return
        await message.reply_text(*self._waiting_view(gaps))

    def _waiting_view(self, gaps) -> tuple[str, InlineKeyboardMarkup | None]:
        owed, waiting = gaps["owed"][:MAX_LISTED], gaps["waiting"][:MAX_LISTED]
        if not owed and not waiting:
            return "✅ Nothing waiting: no replies owed, and nobody is keeping you waiting.", None
        lines, buttons = [], []
        if waiting:
            lines.append("⏳ Waiting on them:")
            for g in waiting:
                lines.append(f"- {g.counterpart}: \"{g.subject}\" ({g.days} days)")
                if GMAIL_ID.fullmatch(g.message_id):
                    buttons.append([InlineKeyboardButton(f"👋 Nudge {g.counterpart.split('<')[0].strip()[:20]}",
                                                         callback_data=f"rt:nudge:{g.message_id}")])
        if owed:
            lines.append("📥 You owe a reply:")
            for g in owed:
                lines.append(f"- {g.counterpart}: \"{g.subject}\" ({g.days} days)")
                if GMAIL_ID.fullmatch(g.message_id):
                    buttons.append([InlineKeyboardButton(f"✍️ Reply to {g.counterpart.split('<')[0].strip()[:20]}",
                                                         callback_data=f"rt:reply:{g.message_id}")])
        return "\n".join(lines), InlineKeyboardMarkup(buttons) if buttons else None

    async def on_reply_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        _, action, message_id = query.data.split(":")
        await query.answer("✍️ Drafting...")
        # Only the id goes in: the email's own words reach Claude via read_email, as data.
        prompt = (NUDGE_PROMPT if action == "nudge" else REPLY_PROMPT).format(id=message_id)
        async with self._message_order:
            await self._converse([{"type": "text", "text": prompt}],
                                 "Draft a follow-up" if action == "nudge" else "Draft a reply")

    async def on_checkin_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        try:
            gaps = await find_reply_gaps(self.google, self.client, self.tracker, self.config, self.db)
        except Exception:
            log.exception("Reply tracking failed")
            await self.send_to_owner("I couldn't check your email just now. Try /waiting in a minute.")
            return
        await self.send_to_owner(*self._waiting_view(gaps))

    # --- check-ins ---

    async def _heartbeat_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.google.is_connected():
            return
        try:
            checkin = await run_heartbeat(self.google, self.client, self.tracker, self.config, self.db)
        except Exception:
            log.exception("Check-in failed")
            return
        if checkin is None:
            return
        markup = None
        if "replies" in checkin.kinds:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("📬 Show what's waiting", callback_data="chk:waiting")]])
        try:
            await self.send_to_owner(f"👋 {checkin.text}", markup)
        except TelegramError:
            log.warning("Couldn't send a check-in", exc_info=True)

    # --- inbox alerts health ---

    async def _inbox_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        if in_quiet_hours(now, self.config.quiet_hours) or not self.google.is_connected():
            return  # Gmail wasn't asked, so this says nothing about whether alerts work
        # Kept in the database: /settings changes restart the bot, and a count that reset on every
        # restart would never reach the notice.
        failures = int(self.db.get_setting(INBOX_FAILURES_KEY) or 0)
        try:
            await self.watcher.check(now)
        except Exception as e:
            failures += 1
            self.db.set_setting(INBOX_FAILURES_KEY, str(failures))
            log.warning("Inbox check failed (%d in a row): %s", failures, e)
            if failures == INBOX_FAILURE_NOTICE:
                await self._tell_owner(f"⚠️ Inbox alerts are paused. {_reason(e)}")
            return
        if failures >= INBOX_FAILURE_NOTICE:
            await self._tell_owner("✅ Inbox alerts are working again.")
        if failures:
            self.db.delete_setting(INBOX_FAILURES_KEY)

    async def _tell_owner(self, text: str) -> None:
        try:
            await self.send_to_owner(text)
        except TelegramError:
            log.warning("Couldn't tell the owner: %s", text, exc_info=True)
