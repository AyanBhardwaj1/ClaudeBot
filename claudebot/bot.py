"""Telegram front end: owner-only chat, reminders, inbox alerts, undo-send and the daily brief."""

import asyncio
import logging
from datetime import datetime, time, timedelta

import anthropic
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import Agent, ConversationReset
from .config import Config
from .db import Database
from .files import MAX_FILE_BYTES, FileUploader, UnsupportedFile, clean_up_uploads
from .google_services import Google, GoogleNotConnected
from .inbox_watch import InboxWatcher
from .outbox import Outbox
from .reminders import next_occurrence
from .tools import ToolContext
from .usage import BudgetExceeded, UsageTracker

log = logging.getLogger(__name__)

UPLOAD_CLEANUP_HOURS = 6

BRIEF_PROMPT = (
    "Give me my daily brief: today's calendar, anything in my inbox from the last day that "
    "needs me (unread first), and any reminders coming up today. Keep it tight."
)


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Split text into Telegram-sized chunks, preferring paragraph and line breaks."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    if text.strip():
        chunks.append(text)
    return chunks


class TelegramOutboxUI:
    """How the outbox talks to the owner: a message with an Undo button, later edited."""

    def __init__(self, bot: "TelegramBot"):
        self.bot = bot

    async def announce(self, outbox_id: int, text: str, needs_approval: bool = False) -> int | None:
        if needs_approval:
            buttons = [InlineKeyboardButton("✅ Send", callback_data=f"send:{outbox_id}"),
                       InlineKeyboardButton("✖️ Cancel", callback_data=f"undo:{outbox_id}")]
        else:
            buttons = [InlineKeyboardButton("↩️ Undo", callback_data=f"undo:{outbox_id}")]
        message = await self.bot.app.bot.send_message(
            chat_id=self.bot.config.owner_id, text=text, reply_markup=InlineKeyboardMarkup([buttons])
        )
        return message.message_id

    async def edit(self, message_id: int, text: str) -> None:
        try:
            await self.bot.app.bot.edit_message_text(
                text, chat_id=self.bot.config.owner_id, message_id=message_id, reply_markup=None
            )
        except TelegramError:
            log.warning("Couldn't edit outbox message %s", message_id, exc_info=True)

    async def notify(self, text: str) -> None:
        await self.bot.send_to_owner(text)


class TelegramBot:
    def __init__(self, config: Config):
        self.config = config
        self.db = Database(config.db_path)
        client = anthropic.AsyncAnthropic()
        self.client = client
        self.uploader = FileUploader(client, self.db)
        google = Google(config)
        self.tracker = UsageTracker(self.db, config.timezone, config.monthly_budget_usd)
        self.agent = Agent(config, self.db, client, self.tracker)
        # Concurrent updates so an Undo tap is handled while a reply is still being written;
        # the agent's lock keeps conversation turns in order.
        self.app = (
            Application.builder()
            .token(config.telegram_token)
            .concurrent_updates(True)
            .post_init(self._post_init)
            .build()
        )
        self.outbox = Outbox(
            self.db, google, config.undo_send_seconds, self.schedule_outbox, TelegramOutboxUI(self)
        )
        self.watcher = InboxWatcher(self.db, google, client, self.tracker, config, self.send_to_owner)
        self._warned_google_missing = False
        # Updates are handled concurrently (so button taps aren't stuck behind a reply), but the
        # owner's messages must reach the agent in the order sent: a file, then "what's due in this?".
        # Each message handler takes this FIFO lock before its first await.
        self._message_order = asyncio.Lock()
        self.agent.tool_context = ToolContext(
            google=google,
            db=self.db,
            tz=config.timezone,
            schedule_reminder=self.schedule_reminder,
            unschedule_reminder=self.unschedule_reminder,
            send_email=self.outbox.submit,
            approve_email=self.outbox.approve,
            prepare_file=self.uploader.to_block,
        )
        self._register_handlers()

    # --- setup ---

    def _register_handlers(self) -> None:
        if self.config.owner_id is None:
            self.app.add_handler(MessageHandler(filters.ALL, self.on_unconfigured))
            return
        owner = filters.User(user_id=self.config.owner_id)
        self.app.add_handler(CommandHandler("start", self.on_start, filters=owner))
        self.app.add_handler(CommandHandler("new", self.on_new, filters=owner))
        self.app.add_handler(CommandHandler("brief", self.on_brief, filters=owner))
        self.app.add_handler(CommandHandler("usage", self.on_usage, filters=owner))
        self.app.add_handler(CallbackQueryHandler(self.on_outbox_button, pattern=r"^(undo|send):\d+$"))
        self.app.add_handler(MessageHandler(owner & filters.PHOTO, self.on_photo))
        self.app.add_handler(MessageHandler(owner & filters.Document.ALL, self.on_document))
        self.app.add_handler(MessageHandler(owner & (filters.VOICE | filters.AUDIO), self.on_voice))
        self.app.add_handler(MessageHandler(owner & filters.TEXT & ~filters.COMMAND, self.on_text))
        # Everyone else is ignored silently.

    async def _post_init(self, app: Application) -> None:
        if self.config.owner_id is None:
            return
        now = datetime.now(self.config.timezone)
        for row in self.db.active_reminders():
            due = datetime.fromisoformat(row["due_at"])
            if due <= now and row["repeat"] != "none":
                due = next_occurrence(due, row["repeat"], now, self.config.timezone)
                self.db.reschedule_reminder(row["id"], due)
            self.schedule_reminder(row["id"])  # overdue one-offs fire right away
        if self.config.daily_brief_time:
            hour, minute = map(int, self.config.daily_brief_time.split(":"))
            app.job_queue.run_daily(
                self._brief_job, time=time(hour, minute, tzinfo=self.config.timezone), name="daily-brief"
            )
        if self.config.inbox_alerts:
            app.job_queue.run_repeating(
                self._inbox_job, interval=self.config.inbox_check_minutes * 60, first=30, name="inbox-watch"
            )
        app.job_queue.run_repeating(
            self._cleanup_job, interval=UPLOAD_CLEANUP_HOURS * 3600, first=60, name="file-cleanup"
        )
        await self.outbox.resume()
        log.info("ClaudeBot is online.")

    def run(self) -> None:
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    # --- messaging helpers ---

    async def send_to_owner(self, text: str) -> None:
        for chunk in split_message(text):
            await self.app.bot.send_message(chat_id=self.config.owner_id, text=chunk)

    async def _ask_agent(self, content: list[dict], owner_present: bool = True) -> str:
        """Run the agent with a typing indicator, turning API failures into a short message."""
        stop = asyncio.Event()
        typing = asyncio.create_task(self._keep_typing(stop))
        try:
            return await self.agent.run(content, owner_present=owner_present)
        except BudgetExceeded as e:
            return str(e)
        except ConversationReset:
            log.exception("Conversation reset")
            return (
                "That conversation got too big for me (usually from large files), so I've started a "
                "fresh one. Please send that again."
            )
        except anthropic.AuthenticationError:
            return "My Anthropic API key isn't working. Check ANTHROPIC_API_KEY."
        except anthropic.RateLimitError:
            return "I'm being rate-limited by the Claude API. Try again in a minute."
        except anthropic.APIStatusError as e:
            log.exception("Claude API error")
            return f"The Claude API returned an error ({e.status_code}). Try again shortly."
        except anthropic.APIConnectionError:
            return "I can't reach the Claude API right now. Network trouble?"
        finally:
            stop.set()
            await typing

    async def _keep_typing(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.app.bot.send_chat_action(self.config.owner_id, ChatAction.TYPING)
            except Exception:
                log.debug("typing indicator failed", exc_info=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=4)
            except asyncio.TimeoutError:
                pass

    # --- handlers ---

    async def on_unconfigured(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user and update.effective_message:
            await update.effective_message.reply_text(
                f"Your Telegram user ID is {update.effective_user.id}.\n"
                "Put it in TELEGRAM_OWNER_ID in your .env and restart me. "
                "Until then I won't talk to anyone."
            )

    async def on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            f"ClaudeBot at your service, {self.config.owner_name}.\n\n"
            "Just talk to me normally. Try:\n"
            "- what's in my inbox?\n"
            "- reply to Sam saying Thursday works\n"
            "- what's on my calendar tomorrow?\n"
            "- remind me at 6pm to call mom\n"
            "- (send a PDF) what's due in this syllabus?\n\n"
            "I'll also ping you when important email arrives.\n\n"
            "/new starts a fresh conversation, /brief gives you the daily brief, "
            "/usage shows what I've cost you."
        )

    async def on_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:  # after any messages already queued, not before them
            self.db.new_thread(self.agent.config_hash)
        await update.effective_message.reply_text("Fresh start. I still remember the important things.")

    async def on_brief(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            await self._send_brief()

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            reply = await self._ask_agent([{"type": "text", "text": update.effective_message.text}])
            await self.send_to_owner(reply)

    async def on_usage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(self.tracker.summary())

    async def on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            message = update.effective_message
            photo = await message.photo[-1].get_file()  # largest size
            data = bytes(await photo.download_as_bytearray())
            try:
                block = await self.uploader.to_block(data, "image/jpeg", "photo.jpg")
            except UnsupportedFile as e:
                await message.reply_text(str(e))
                return
            await self._ask_about_file(block, message.caption)

    async def on_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            message = update.effective_message
            document = message.document
            if (document.file_size or 0) > MAX_FILE_BYTES:
                await message.reply_text(f"{document.file_name} is too big for me (10 MB max).")
                return
            data = bytes(await (await document.get_file()).download_as_bytearray())
            try:
                block = await self.uploader.to_block(data, document.mime_type or "", document.file_name or "file")
            except UnsupportedFile as e:
                await message.reply_text(str(e))
                return
            await self._ask_about_file(block, message.caption)

    async def _ask_about_file(self, block: dict, caption: str | None) -> None:
        question = caption or "(sent with no message: say briefly what it is and anything I need to act on)"
        await self.send_to_owner(await self._ask_agent([block, {"type": "text", "text": question}]))

    async def on_outbox_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query.from_user.id != self.config.owner_id:
            await query.answer()
            return
        action, outbox_id = query.data.split(":")
        if action == "send":
            result = await self.outbox.approve(int(outbox_id))
        else:
            result = await self.outbox.undo(int(outbox_id))
        await query.answer(result)

    async def on_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            "I can't listen to voice notes yet. Use your keyboard's dictation (the mic key) "
            "and send it as text instead."
        )

    # --- reminders and scheduled tasks ---

    def schedule_reminder(self, reminder_id: int) -> None:
        row = self.db.get_reminder(reminder_id)
        if row is None:
            return
        self.unschedule_reminder(reminder_id)
        due = datetime.fromisoformat(row["due_at"])
        when = max(due, datetime.now(due.tzinfo) + timedelta(seconds=5))
        self.app.job_queue.run_once(
            self._reminder_job, when=when, data=reminder_id, name=f"reminder-{reminder_id}"
        )

    def unschedule_reminder(self, reminder_id: int) -> None:
        for job in self.app.job_queue.get_jobs_by_name(f"reminder-{reminder_id}"):
            job.schedule_removal()

    async def _reminder_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        reminder_id = context.job.data
        row = self.db.get_reminder(reminder_id)
        if row is None:
            return
        try:
            if row["run_as_task"]:
                prompt = f"[Scheduled task #{reminder_id} that I set earlier - do it now]\n{row['text']}"
                reply = await self._ask_agent([{"type": "text", "text": prompt}], owner_present=False)
                await self.send_to_owner(reply)
            else:
                await self.send_to_owner(f"⏰ {row['text']}")
                self.db.add_notice(f"Reminder #{reminder_id} fired: {row['text']}")
        finally:
            now = datetime.now(self.config.timezone)
            following = next_occurrence(
                datetime.fromisoformat(row["due_at"]), row["repeat"], now, self.config.timezone
            )
            if following is None:
                self.db.deactivate_reminder(reminder_id)
            else:
                self.db.reschedule_reminder(reminder_id, following)
                self.schedule_reminder(reminder_id)

    async def _brief_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_brief()

    async def _send_brief(self) -> None:
        # The brief reads untrusted email with nobody necessarily watching: no unattended sends.
        reply = await self._ask_agent([{"type": "text", "text": BRIEF_PROMPT}], owner_present=False)
        await self.send_to_owner(reply)

    # --- outbox and inbox alerts ---

    def schedule_outbox(self, outbox_id: int, when: datetime) -> None:
        when = max(when, datetime.now(when.tzinfo) + timedelta(seconds=1))
        self.app.job_queue.run_once(self._outbox_job, when=when, data=outbox_id, name=f"outbox-{outbox_id}")

    async def _outbox_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.outbox.deliver(context.job.data)

    async def _cleanup_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self.agent.busy:
            # A brief or task may still be replaying a conversation /new just retired; its files
            # aren't safe to delete yet. The next run picks them up.
            return
        try:
            deleted = await clean_up_uploads(self.client, self.db)
        except Exception:
            log.exception("Uploaded-file cleanup failed")
            return
        if deleted:
            log.info("Deleted %d uploaded files from finished conversations", deleted)

    async def _inbox_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            await self.watcher.check()
        except GoogleNotConnected:
            if not self._warned_google_missing:
                log.warning("Inbox alerts are on but Google isn't connected yet.")
                self._warned_google_missing = True
        except Exception:
            log.exception("Inbox check failed")
