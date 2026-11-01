"""The weekly review (Sunday evening) and feedback buttons that tune the daily brief.

Both run from prompts written by code. Brief feedback is the owner's own words, saved as a memory
the brief already reads; nothing from an email can change how the brief works."""

from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .quiet import dnd_active

REVIEW_KEY = "weekly_review"  # "off" turns it off
REVIEW_TIME = time(18)
REVIEW_DAYS = (0,)  # python-telegram-bot counts days from Sunday = 0
FEEDBACK_AWAIT = "brief:feedback"
REVIEW_PROMPT = (
    "Give me my weekly review, short and skimmable:\n"
    "1. What you did for me this week (use action_log with days=7; count emails, events and so on, "
    "then name the few that mattered).\n"
    "2. What's still open: reminders and tasks coming up (list_reminders), people waiting on a reply "
    "(list_telegram_dms if connected; search my inbox for important unanswered email from this week).\n"
    "3. The week ahead: list_calendar_events for the next 7 days, flagging busy days and anything to "
    "prepare.\n"
    "End with one suggestion for next week."
)
BRIEF_BUTTONS = InlineKeyboardMarkup([[InlineKeyboardButton("👍 Useful", callback_data="brief:good"),
                                       InlineKeyboardButton("✏️ Change it", callback_data="brief:tune")]])


class ReviewHandlers:
    """Mixed into TelegramBot."""

    async def _weekly_review_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        if self.db.get_setting(REVIEW_KEY) == "off" or dnd_active(self.db, now):
            return
        reply = await self._ask_agent([{"type": "text", "text": REVIEW_PROMPT}], owner_present=False)
        await self.send_to_owner(f"🗓 Your week\n\n{reply}")

    async def on_brief_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        if query.data == "brief:good":
            count = int(self.db.get_setting("brief_thumbs_up") or 0) + 1
            self.db.set_setting("brief_thumbs_up", str(count))
            await query.answer("👍 Noted")
            return
        await query.answer()
        self._expect(FEEDBACK_AWAIT)
        await self.send_to_owner(
            "What should I change in your daily brief? e.g. \"skip the headlines\", \"more on the Longhorns\", "
            "\"put my first meeting at the top\".")

    def save_brief_feedback(self, text: str) -> str:
        fact = "Daily brief preference: " + " ".join(text.replace("<", " ").replace(">", " ").split())[:300]
        self.db.add_memory(fact)
        return fact
