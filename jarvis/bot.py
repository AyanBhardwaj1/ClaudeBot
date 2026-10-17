"""Telegram front end: owner-only chat, reminders and the daily brief."""

import asyncio
import base64
import logging
from datetime import datetime, time, timedelta

import anthropic
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .agent import Agent
from .config import Config
from .db import Database
from .google_services import Google
from .reminders import next_occurrence
from .tools import ToolContext

log = logging.getLogger(__name__)

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


class JarvisBot:
    def __init__(self, config: Config):
        self.config = config
        self.db = Database(config.db_path)
        self.agent = Agent(config, self.db, anthropic.AsyncAnthropic())
        self.app = Application.builder().token(config.telegram_token).post_init(self._post_init).build()
        self.agent.tool_context = ToolContext(
            google=Google(config),
            db=self.db,
            tz=config.timezone,
            schedule_reminder=self.schedule_reminder,
            unschedule_reminder=self.unschedule_reminder,
            notify=self.send_to_owner,
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
        self.app.add_handler(MessageHandler(owner & filters.PHOTO, self.on_photo))
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
        log.info("Jarvis is online.")

    def run(self) -> None:
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    # --- messaging helpers ---

    async def send_to_owner(self, text: str) -> None:
        for chunk in split_message(text):
            await self.app.bot.send_message(chat_id=self.config.owner_id, text=chunk)

    async def _ask_agent(self, content: list[dict]) -> str:
        """Run the agent with a typing indicator, turning API failures into a short message."""
        stop = asyncio.Event()
        typing = asyncio.create_task(self._keep_typing(stop))
        try:
            return await self.agent.run(content)
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
            f"At your service, {self.config.owner_name}.\n\n"
            "Just talk to me normally. Try:\n"
            "- what's in my inbox?\n"
            "- reply to Sam saying Thursday works\n"
            "- what's on my calendar tomorrow?\n"
            "- remind me at 6pm to call mom\n\n"
            "/new starts a fresh conversation, /brief gives you the daily brief."
        )

    async def on_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.db.new_thread()
        await update.effective_message.reply_text("Fresh start. I still remember the important things.")

    async def on_brief(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_to_owner(await self._ask_agent([{"type": "text", "text": BRIEF_PROMPT}]))

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply = await self._ask_agent([{"type": "text", "text": update.effective_message.text}])
        await self.send_to_owner(reply)

    async def on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        photo = await message.photo[-1].get_file()  # largest size
        data = base64.standard_b64encode(bytes(await photo.download_as_bytearray())).decode()
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
            {"type": "text", "text": message.caption or "(photo with no caption)"},
        ]
        await self.send_to_owner(await self._ask_agent(content))

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
                await self.send_to_owner(await self._ask_agent([{"type": "text", "text": prompt}]))
            else:
                await self.send_to_owner(f"⏰ {row['text']}")
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
        await self.send_to_owner(await self._ask_agent([{"type": "text", "text": BRIEF_PROMPT}]))
