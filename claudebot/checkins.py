"""Telegram side of ClaudeBot 1.1: /reminders, /waiting (reply tracking with Nudge and Reply
buttons), check-ins, and telling the owner when inbox alerts stop working. Mixed into TelegramBot.
"""

import asyncio
import json
import logging
from datetime import datetime, time, timedelta
from types import SimpleNamespace

from google.auth.exceptions import RefreshError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .actions import ICONS, ActionLog
from .business import dm_signals
from .google_services import GoogleNotConnected
from .heartbeat import record_sent, run_heartbeat
from .inbox_watch import GMAIL_ID, clip, in_quiet_hours
from .modes import defang_urls
from .quiet import dnd_active, next_morning
from .replies import find_reply_gaps
from .shortcuts import bump
from .ui import split_message

log = logging.getLogger(__name__)

NO_REPLY_DAYS = 3
INBOX_FAILURE_NOTICE = 3  # consecutive failed checks before telling the owner
INBOX_FAILURES_KEY = "inbox_failures"
URGENT_WAKES_KEY = "urgent_wakes"  # "on": during quiet time, urgent email still pings; the rest waits
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


def snooze_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done", callback_data=f"rem:done:{reminder_id}"),
                                  InlineKeyboardButton("⏰ 1h", callback_data=f"rem:1h:{reminder_id}"),
                                  InlineKeyboardButton("⏰ Tomorrow", callback_data=f"rem:tmr:{reminder_id}")]])


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
        if snoozed := self.db.get_setting(f"snoozed:{reminder_id}"):  # its snoozed copy goes too
            self.db.deactivate_reminder(int(snoozed))
            self.unschedule_reminder(int(snoozed))
        ActionLog(self.db).record("reminder", f"Cancelled reminder: {row['text']}")
        await query.answer(f"Cancelled: {row['text'][:150]}")

    async def on_reminder_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Done / snooze on a reminder that just fired. Snoozing moves one copy, it doesn't pile up."""
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        _, action, reminder_id = query.data.split(":")
        text = self.db.reminder_text(int(reminder_id))
        if text is None:
            return
        snoozed_key = f"snoozed:{reminder_id}"
        if previous := self.db.get_setting(snoozed_key):  # drop the earlier snooze of the same reminder
            self.db.deactivate_reminder(int(previous))
            self.unschedule_reminder(int(previous))
        if action == "done":
            self.db.delete_setting(snoozed_key)
            row = self.db.get_reminder(int(reminder_id))
            repeat = (f"\nRepeats {row['repeat']}; next "
                      f"{datetime.fromisoformat(row['due_at']).astimezone(self.config.timezone):%a %b %-d %H:%M}. "
                      "/reminders to stop it.") if row and row["repeat"] != "none" else ""
            await query.edit_message_text(f"✅ {defang_urls(text)}{repeat}")
            return
        now = datetime.now(self.config.timezone)
        when = now + timedelta(hours=1) if action == "1h" else next_morning(now, time(9))
        snooze_id = self.db.add_reminder(text, when, "none", False)
        self.schedule_reminder(snooze_id)
        self.db.set_setting(snoozed_key, str(snooze_id))
        self.db.prune_settings("snoozed:", 100)
        await query.edit_message_text(f"⏰ {defang_urls(text)}\nSnoozed until {when:%a %H:%M}.")

    async def on_no_reply_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """On a sent email: in 3 days, check for a reply, and draft a nudge if there's none."""
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        outbox_id = int(query.data.split(":")[1])
        row = self.db.get_outbox(outbox_id)
        if row is None or row["status"] != "sent":
            await query.answer("I can't find that email.")
            return
        if self.db.get_setting(f"noreply:{outbox_id}"):
            await query.answer("Already on it.")
            return
        email = json.loads(row["email_json"])
        now = datetime.now(self.config.timezone)
        when = datetime.combine(now.date() + timedelta(days=NO_REPLY_DAYS), time(9), tzinfo=self.config.timezone)
        # The subject may be someone else's words ("Re: ..."): quoted as a JSON string, as data.
        task = (f"Check whether {email['to']} replied to the email I sent on {now:%b %-d}. Its subject, quoted as "
                f"data: {json.dumps(email.get('subject') or '(reply)', ensure_ascii=False)}. Search my inbox and that "
                "thread. If they replied, tell me in one line. If not, draft a short, polite follow-up and show it "
                "to me; don't send it.")
        self.schedule_reminder(self.db.add_reminder(task, when, "none", True))
        ActionLog(self.db).record("reminder", f"Will check for a reply from {email['to']} on {when:%a %b %-d}")
        self.db.set_setting(f"noreply:{outbox_id}", "1")
        self.db.prune_settings("noreply:", 200)
        await query.answer(f"⏰ I'll check {when:%a} morning")

    async def event_created(self, event_id: str, title: str, start: str, has_attendees: bool = False) -> None:
        """Every event ClaudeBot adds gets a card with a Remove button, like Undo on email."""
        key = str(int(self.db.get_setting("calev_next") or 0) + 1)
        self.db.set_setting("calev_next", key)
        self.db.set_setting(f"calev:{key}", json.dumps({"id": event_id, "title": title[:100], "start": start,
                                                         "guests": has_attendees}))
        self.db.prune_settings("calev:", 100)
        try:
            when = datetime.fromisoformat(start)
            shown = f"{when:%a %b %-d}" if len(start) == 10 else f"{when:%a %b %-d %H:%M}"
        except ValueError:
            shown = start
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Remove", callback_data=f"cu:{key}")]])
        invited = "\nInvites went out to the guests." if has_attendees else ""
        await self.send_to_owner(f"📅 Added: {defang_urls(clip(title, 120))} ({shown}){invited}", markup)

    async def on_event_undo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        key = query.data.split(":")[1]
        raw = self.db.get_setting(f"calev:{key}")
        if raw is None:
            await query.answer("Too old to undo here; delete it in Calendar.")
            return
        event = json.loads(raw)
        try:
            await asyncio.to_thread(self.google.delete_event, event["id"], bool(event.get("guests")))
        except Exception:
            log.exception("Removing event %s failed", event["id"])
            await query.answer("Couldn't remove it; it may already be gone.")
            return
        self.db.delete_setting(f"calev:{key}")
        ActionLog(self.db).record("calendar", f"Removed \"{event['title']}\" (undo)")
        await query.answer("Removed")
        await query.edit_message_text(f"↩️ Removed: {defang_urls(clip(event['title'], 100))}")

    # --- /log ---

    async def on_log(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        week = bool(context.args) and context.args[0].lower() in ("week", "7")
        now = datetime.now(self.config.timezone)
        start = now - timedelta(days=7) if week else now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = ActionLog(self.db).since(start)
        if not rows:
            await update.effective_message.reply_text(
                "Nothing yet today. /log week shows the last 7 days." if not week else "Nothing in the last 7 days.")
            return
        lines = []
        for r in rows[-40:]:
            at = datetime.fromisoformat(r["at"]).astimezone(self.config.timezone)
            stamp = f"{at:%a %H:%M}" if week else f"{at:%H:%M}"
            lines.append(f"{ICONS.get(r['kind'], '•')} {stamp} {defang_urls(r['summary'])}")
        title = "What I did this week:" if week else "What I did today:"
        for chunk in split_message(title + "\n" + "\n".join(lines)):
            await update.effective_message.reply_text(chunk)

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
        text, markup = self._waiting_view(gaps)
        await message.reply_text(text, reply_markup=markup)

    def _waiting_view(self, gaps) -> tuple[str, InlineKeyboardMarkup | None]:
        owed, waiting = gaps["owed"][:MAX_LISTED], gaps["waiting"][:MAX_LISTED]
        if not owed and not waiting:
            return "✅ Nothing waiting: no replies owed, and nobody is keeping you waiting.", None
        self.db.add_notice("Reply list shown to the owner (/waiting): " + json.dumps(
            [{"kind": g.kind, "message_id": g.message_id, "with": g.counterpart, "subject": g.subject, "days": g.days}
             for g in waiting + owed], ensure_ascii=False))
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
                                 "Draft a follow-up" if action == "nudge" else "Draft a reply",
                                 owner_present=False)  # a draft only: a send would wait for ✅ Send

    async def on_checkin_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        bump(self.db, "checkins_tapped")
        if query.data == "chk:dms":
            await self.on_dms(SimpleNamespace(effective_message=SimpleNamespace(
                reply_text=lambda text, reply_markup=None: self.send_to_owner(text, reply_markup))), context)
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
        google = self.google if self.google.is_connected() else None
        if google is None and self.dms.active_connection_id() is None:
            return
        try:
            checkin = await run_heartbeat(google, self.client, self.tracker, self.config, self.db,
                                          extra=dm_signals(self.dms))
        except Exception:
            log.exception("Check-in failed")
            return
        if checkin is None:
            return
        buttons = []
        if "replies" in checkin.kinds:
            buttons.append(InlineKeyboardButton("📬 Email waiting", callback_data="chk:waiting"))
        if "dms" in checkin.kinds:
            buttons.append(InlineKeyboardButton("💬 Telegram DMs", callback_data="chk:dms"))
        markup = InlineKeyboardMarkup([buttons]) if buttons else None
        try:
            await self.send_to_owner(f"👋 {checkin.text}", markup)
        except TelegramError:
            log.warning("Couldn't send a check-in; its items stay for the next one", exc_info=True)
            return
        now = datetime.now(self.config.timezone)
        record_sent(self.db, checkin, now, self.config.timezone)
        bump(self.db, "checkins_sent", now)
        # So "move the dentist" or "nudge her" later knows what the owner was just shown.
        self.db.add_notice("Check-in shown to the owner: " + json.dumps(
            {"items": checkin.text.splitlines(), "signal_keys": list(checkin.keys)}, ensure_ascii=False))

    # --- inbox alerts health ---

    async def _inbox_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        quiet = in_quiet_hours(now, self.config.quiet_hours) or dnd_active(self.db, now)
        urgent_wakes = self.db.get_setting(URGENT_WAKES_KEY) == "on"
        if (quiet and not urgent_wakes) or not self.google.is_connected():
            return  # Gmail wasn't asked, so this says nothing about whether alerts work
        # Kept in the database: /settings changes restart the bot, and a count that reset on every
        # restart would never reach the notice.
        failures = int(self.db.get_setting(INBOX_FAILURES_KEY) or 0)
        try:
            await self.watcher.check(now, urgent_only=quiet)
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

    async def _alert_digest_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        if in_quiet_hours(now, self.config.quiet_hours) or dnd_active(self.db, now):
            return  # held alerts wait for the next hour outside quiet time
        try:
            await self.watcher.flush_digest()
        except TelegramError:
            log.warning("Couldn't send the alert digest; it'll go with the next one", exc_info=True)

    async def _tell_owner(self, text: str) -> None:
        try:
            await self.send_to_owner(text)
        except TelegramError:
            log.warning("Couldn't tell the owner: %s", text, exc_info=True)
