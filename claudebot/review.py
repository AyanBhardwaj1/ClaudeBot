"""The weekly review (Sunday evening) and feedback buttons that tune the daily brief.

Both run from prompts written by code. Brief feedback is the owner's own words, saved as a memory
the brief already reads; nothing from an email can change how the brief works."""

from datetime import datetime, time

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .habits import habit_lines
from .inbox_watch import in_quiet_hours
from .modes import defang_urls
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
    "prepare, plus bills due (list_bills) and birthdays (list_birthdays) in those 7 days.\n"
    "4. If I logged any expenses, this week's spending by category (spending_summary), in one line.\n"
    "End with one suggestion for next week."
)
DIGEST_KEY = "newsletter_digest"  # "on" to get it (off by default: it reads a lot of email)
DIGEST_TIME = time(10)
DIGEST_DAYS = (6,)  # Saturday
DIGEST_PROMPT = (
    "Read the newsletters in my inbox from the past 7 days for me (search: in:inbox newer_than:7d "
    "(category:promotions OR category:updates OR list:*) and read the ones that look like newsletters, "
    "up to 15). Tell me the 5 things worth knowing, one line each, naming the newsletter. Skip ads and "
    "deals. Don't include links. End with: \"/sweep archives them.\""
)
BRIEF_BUTTONS = InlineKeyboardMarkup([[InlineKeyboardButton("👍 Useful", callback_data="brief:good"),
                                       InlineKeyboardButton("✏️ Change it", callback_data="brief:tune")]])


class ReviewHandlers:
    """Mixed into TelegramBot."""

    async def _weekly_review_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        if (self.db.get_setting(REVIEW_KEY) == "off" or dnd_active(self.db, now)
                or in_quiet_hours(now, self.config.quiet_hours) or not self.google.is_connected()):
            return
        reply, ok = await self._run_agent([{"type": "text", "text": REVIEW_PROMPT}], owner_present=False,
                                          source="review")
        if ok:  # an API or budget error isn't a review
            streaks = habit_lines(self.db, now.date())  # counted by code, not by the model
            await self.send_to_owner(f"🗓 Your week\n\n{defang_urls(reply)}" + (f"\n\n🔥 Habits\n{streaks}" if streaks else ""))

    async def _digest_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        if (self.db.get_setting(DIGEST_KEY) != "on" or dnd_active(self.db, now)
                or in_quiet_hours(now, self.config.quiet_hours) or not self.google.is_connected()):
            return
        reply, ok = await self._run_agent([{"type": "text", "text": DIGEST_PROMPT}], owner_present=False, effort="low",
                                          source="digest")
        if ok:  # newsletters are other people's text: their links arrive unclickable
            await self.send_to_owner(f"📰 Your newsletters this week\n\n{defang_urls(reply)}")

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
        asked = await self.send_to_owner(
            "Reply to this message with what to change in your daily brief, e.g. \"skip the headlines\" or "
            "\"more on the Longhorns\".", ForceReply(input_field_placeholder="What should I change?"))
        self.ask_by_reply(FEEDBACK_AWAIT, getattr(asked, "message_id", None))

    def save_brief_feedback(self, text: str) -> str:
        fact = "Daily brief preference: " + " ".join(text.replace("<", " ").replace(">", " ").split())[:300]
        self.db.add_memory(fact)
        return fact
