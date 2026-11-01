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

    async def on_trips(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with self._message_order:
            await self._converse([{"type": "text", "text": TRIPS_PROMPT}], "/trips")
