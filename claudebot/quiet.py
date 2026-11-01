"""/quiet: pause everything ClaudeBot sends on its own (inbox alerts, check-ins, meeting prep) for
a while. Reminders the owner set still fire; held email alerts arrive once the pause ends."""

import re
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .db import Database

DND_KEY = "dnd_until"
MORNING = time(8)
MAX_PAUSE = timedelta(days=2)  # inbox alerts catch up on the last 2 days of email, no further


def dnd_until(db: Database, now: datetime) -> datetime | None:
    raw = db.get_setting(DND_KEY)
    if not raw:
        return None
    until = datetime.fromisoformat(raw)
    return until if until > now else None


def dnd_active(db: Database, now: datetime) -> bool:
    return dnd_until(db, now) is not None


def next_morning(now: datetime, at: time = MORNING) -> datetime:
    """The coming morning: today's if it's still before then (tapped at 1am), else tomorrow's."""
    today = datetime.combine(now.date(), at, tzinfo=now.tzinfo)
    return today if now < today else today + timedelta(days=1)


def parse_pause(text: str, now: datetime) -> datetime | None:
    """'2h', '30m', '90 min', '1 day', 'morning'/'tomorrow' (08:00 next day). None if unreadable."""
    text = text.strip().lower()
    if text in ("morning", "tomorrow", "tonight", "night"):
        return next_morning(now)
    match = re.fullmatch(r"(\d{1,3})\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)", text)
    if not match:
        return None
    amount, unit = int(match[1]), match[2][0]
    delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
    return now + min(delta, MAX_PAUSE) if amount > 0 else None


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("1h", callback_data="dnd:60"),
                                  InlineKeyboardButton("2h", callback_data="dnd:120"),
                                  InlineKeyboardButton("Until 8:00", callback_data="dnd:morning"),
                                  InlineKeyboardButton("Resume", callback_data="dnd:off")]])


class QuietHandlers:
    """Mixed into TelegramBot."""

    def _pause(self, until: datetime | None) -> str:
        if until is None:
            self.db.delete_setting(DND_KEY)
            return "🔔 Back on: alerts, check-ins and meeting prep resume."
        self.db.set_setting(DND_KEY, until.isoformat())
        return (f"🔕 Quiet until {until:%a %H:%M}. Reminders you set still come through; email alerts "
                "will catch up afterwards. /quiet off to resume early.")

    async def on_quiet(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        text = " ".join(context.args or [])
        if text.lower() in ("off", "resume", "stop"):
            await update.effective_message.reply_text(self._pause(None))
            return
        if text:
            until = parse_pause(text, now)
            if until is None:
                await update.effective_message.reply_text("Try /quiet 2h, /quiet 30m or /quiet morning.")
                return
            await update.effective_message.reply_text(self._pause(until))
            return
        current = dnd_until(self.db, now)
        status = f"🔕 Quiet until {current:%a %H:%M}." if current else "🔔 Not paused."
        await update.effective_message.reply_text(f"{status} Pause alerts, check-ins and meeting prep for:",
                                                  reply_markup=_keyboard())

    async def on_quiet_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        choice = query.data.split(":")[1]
        now = datetime.now(self.config.timezone)
        until = None if choice == "off" else parse_pause("morning" if choice == "morning" else f"{choice}m", now)
        await self.send_to_owner(self._pause(until))
