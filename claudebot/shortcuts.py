"""One-word shortcuts for things people ask all the time (/catchup, /trips), and small usage
counters that show whether proactive features earn their place (/status)."""

from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from .db import Database

METRIC_PREFIX = "m:"
CATCHUP_KEY = "last_catchup"
CATCHUP_PROMPT = (
    "Catch me up on the last {hours} hours, as a short list, most important first: new email that matters "
    "(search my inbox with newer_than:{hours}h, skipping promotions and newsletters), Telegram chats waiting on me "
    "(list_telegram_dms, if connected), and anything you did for me (action_log). Skip sections with nothing new."
)
SUBSCRIPTIONS_PROMPT = (
    "Audit my subscriptions. Search my email from the last 90 days for receipts and renewal notices "
    "(e.g. \"receipt\", \"subscription\", \"renewal\", \"your plan\", \"billed\"). List each recurring charge once: "
    "service, amount, how often, last charge date. Flag ones that look forgotten (nothing else from them, or a "
    "free trial that converted) and duplicates. Give the monthly total. Then ask if I'd like any added as bills "
    "(add_bill) so I'm reminded before they charge. Don't cancel or email anyone."
)
PLAN_PROMPT = (
    "Plan my day. Look at today's calendar, reminders due today (list_reminders), my lists (show_lists) and "
    "important email I still owe a reply. Suggest a realistic time-blocked plan around my fixed events, "
    "with the 3 things that matter most first, and say what can wait. Use find_free_time for the gaps. "
    "Offer to put the blocks on my calendar; don't add anything until I say so."
)
PREP_PROMPT = (
    "Prepare me for my next meeting with other people today or tomorrow (list_calendar_events). Look up "
    "recent email threads with the attendees and what you remember about them. Brief: who they are to me, "
    "where we left things, open questions or promises, what to bring. Five lines or so."
)
PACKAGES_PROMPT = (
    "What deliveries are on the way? Search my email from the last 14 days for order and shipping "
    "confirmations (\"shipped\", \"out for delivery\", \"tracking\", \"your order\"). For each package not yet "
    "delivered: what it is, the store, the carrier and tracking number, and the expected date. Skip delivered ones. "
    "Don't open links from the emails."
)
WHO_PROMPT = (
    "What do I know about {name}? Check what you remember (list_memories), my recent email with them "
    "(search_emails), upcoming meetings with them (list_calendar_events for the next 30 days), money between "
    "us (list_ious) and our Telegram chat if connected. Give me a short profile: who they are to me, the "
    "last thing between us, anything open, and one thing worth remembering."
)
TRIPS_PROMPT = (
    "List my upcoming trips in the next 60 days. Search my email for flight, train, hotel and car rental "
    "confirmations and check my calendar. For each trip: dates, times, confirmation numbers, and anything that "
    "looks missing (a night with no hotel, no way back). Keep it short."
)


def bump(db: Database, name: str, now: datetime | None = None) -> None:
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    key = f"{METRIC_PREFIX}{name}:{day}"
    db.set_setting(key, str(int(db.get_setting(key) or 0) + 1))
    db.prune_settings(METRIC_PREFIX, 400)


def last_days(db: Database, name: str, days: int = 7, now: datetime | None = None) -> int:
    today = (now or datetime.now(timezone.utc)).date()
    return sum(int(db.get_setting(f"{METRIC_PREFIX}{name}:{(today - timedelta(days=i)).isoformat()}") or 0)
               for i in range(days))


class ShortcutHandlers:
    """Mixed into TelegramBot."""

    async def on_catchup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(timezone.utc)
        last = self.db.get_setting(CATCHUP_KEY)
        hours = 12 if last is None else max(1, min(72, int((now - datetime.fromisoformat(last)).total_seconds() // 3600)))
        self.db.set_setting(CATCHUP_KEY, now.isoformat())
        async with self._message_order:
            await self._converse([{"type": "text", "text": CATCHUP_PROMPT.format(hours=hours)}], "/catchup")

    async def on_subscriptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            await self._converse([{"type": "text", "text": SUBSCRIPTIONS_PROMPT}], "/subscriptions")

    async def on_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            await self._converse([{"type": "text", "text": PLAN_PROMPT}], "/plan")

    async def on_prep(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            await self._converse([{"type": "text", "text": PREP_PROMPT}], "/prep")

    async def on_packages(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            await self._converse([{"type": "text", "text": PACKAGES_PROMPT}], "/packages")

    async def on_who(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        name = " ".join(" ".join(context.args or []).replace("<", " ").replace(">", " ").split())[:60]
        if not name:
            await update.effective_message.reply_text("Who? e.g. /who Alex Kim")
            return
        async with self._message_order:
            await self._converse([{"type": "text", "text": WHO_PROMPT.format(name=name)}], f"/who {name}")

    async def on_trips(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            await self._converse([{"type": "text", "text": TRIPS_PROMPT}], "/trips")
