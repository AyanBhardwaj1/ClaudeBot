"""Birthdays: "/birthday Mom Mar 14" saves it with a yearly heads-up the day before at 9:00
(the text names the date, so a Feb 29 birthday in a short year still reads right).
/birthdays lists them by how soon they are. Each birthday keeps the id of its own reminder, so
removing or replacing one cancels exactly that reminder and nothing else."""

import calendar
import json
import re
from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .actions import ActionLog
from .db import Database

BIRTHDAYS_KEY = "birthdays"
MAX_BIRTHDAYS = 200
MAX_BUTTONS = 20
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9


def parse_birthday(text: str) -> tuple[str, int, int] | None:
    """'Mom Mar 14', 'Aunt Sue 14 March', 'Dad 1961-03-14' or 'Dad 03-14' -> (name, month, day)."""
    words = " ".join(str(text).replace("<", " ").replace(">", " ").split())
    patterns = (
        r"^(?P<name>.+?)\s+(?:(?P<y>\d{4})-)?(?P<m>\d{1,2})-(?P<d>\d{1,2})$",
        r"^(?P<name>.+?)\s+(?P<mon>[a-z]+)\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+\d{4})?$",
        r"^(?P<name>.+?)\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon>[a-z]+)\.?(?:,?\s+\d{4})?$",
    )
    for pattern in patterns:
        match = re.match(pattern, words, re.IGNORECASE)
        if not match:
            continue
        groups = match.groupdict()
        month = int(groups["m"]) if groups.get("m") else MONTHS.get((groups.get("mon") or "").lower())
        day = int(groups["d"])
        if month and 1 <= month <= 12 and 1 <= day <= calendar.monthrange(2024, month)[1]:  # 2024: Feb 29 allowed
            name = match.group("name").strip(" ,:-")[:40]
            return (name, month, day) if name else None
    return None


def next_birthday(month: int, day: int, today: date) -> date:
    """This year's or next year's date; Feb 29 is Feb 28 in other years."""
    for year in (today.year, today.year + 1):
        when = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if when >= today:
            return when
    raise AssertionError("unreachable")


class Birthdays:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> list[dict]:
        return json.loads(self.db.get_setting(BIRTHDAYS_KEY) or "[]")

    def _save(self, items: list[dict]) -> None:
        self.db.set_setting(BIRTHDAYS_KEY, json.dumps(items))

    def find(self, birthday_id: int) -> dict | None:
        return next((b for b in self.all() if b["id"] == birthday_id), None)

    def add(self, name: str, month: int, day: int, reminder_id: int | None = None) -> tuple[dict, dict | None]:
        """Returns (the birthday, the one it replaced with the same name, if any)."""
        items = self.all()
        replaced = next((b for b in items if b["name"].lower() == name.lower()), None)
        kept = [b for b in items if b is not replaced]
        if len(kept) >= MAX_BIRTHDAYS:
            raise ValueError(f"That's {MAX_BIRTHDAYS} birthdays already.")
        item = {"id": max((b["id"] for b in items), default=0) + 1, "name": name, "month": month, "day": day,
                "reminder_id": reminder_id}
        self._save(kept + [item])
        return item, replaced

    def remove(self, birthday_id: int) -> dict | None:
        items = self.all()
        gone = next((b for b in items if b["id"] == birthday_id), None)
        self._save([b for b in items if b["id"] != birthday_id])
        return gone

    def upcoming(self, today: date, days: int) -> list[tuple[dict, date]]:
        soon = [(b, next_birthday(b["month"], b["day"], today)) for b in self.all()]
        return sorted([(b, when) for b, when in soon if (when - today).days <= days], key=lambda x: x[1])


def birthdays_view(birthdays: Birthdays, today: date) -> tuple[str, InlineKeyboardMarkup | None]:
    items = sorted(birthdays.all(), key=lambda b: next_birthday(b["month"], b["day"], today))
    if not items:
        return "No birthdays yet. Add one: /birthday Mom Mar 14", None
    lines, rows = ["🎂 Birthdays"], []
    for b in items:
        when = next_birthday(b["month"], b["day"], today)
        away = (when - today).days
        soon = "today! 🎉" if away == 0 else "tomorrow" if away == 1 else f"in {away} days"
        lines.append(f"- {b['name']}: {when:%b %-d} ({soon})")
        if len(rows) < MAX_BUTTONS:
            rows.append([InlineKeyboardButton(f"🗑 {b['name'][:24]}", callback_data=f"bday:del:{b['id']}")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


class BirthdayHandlers:
    """Mixed into TelegramBot."""

    def _cancel_birthday_reminder(self, item: dict | None) -> None:
        if item and item.get("reminder_id"):
            self.db.deactivate_reminder(item["reminder_id"])
            self.unschedule_reminder(item["reminder_id"])

    def add_birthday(self, name: str, month: int, day: int) -> dict:
        """Save it with a yearly reminder the day before at 9:00, replacing one with the same name."""
        birthdays = Birthdays(self.db)
        if len(birthdays.all()) >= MAX_BIRTHDAYS and not any(b["name"].lower() == name.lower() for b in birthdays.all()):
            raise ValueError(f"That's {MAX_BIRTHDAYS} birthdays already.")
        now = datetime.now(self.config.timezone)
        when = next_birthday(month, day, now.date())
        remind = datetime.combine(when - timedelta(days=1), time(9), tzinfo=self.config.timezone)
        if remind <= now:
            when = next_birthday(month, day, when + timedelta(days=1))
            remind = datetime.combine(when - timedelta(days=1), time(9), tzinfo=self.config.timezone)
        reminder_id = self.db.add_reminder(f"🎂 {name}'s birthday is on {calendar.month_abbr[month]} {day}",
                                           remind, "yearly", False)
        item, replaced = birthdays.add(name, month, day, reminder_id)
        self._cancel_birthday_reminder(replaced)
        self.schedule_reminder(reminder_id)
        ActionLog(self.db).record("reminder", f"Birthday saved: {name}, {calendar.month_abbr[month]} {day}")
        return item

    async def on_birthdays(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        args = " ".join(context.args or []) if context else ""
        today = datetime.now(self.config.timezone).date()
        if args:
            parsed = parse_birthday(args)
            if parsed is None:
                await message.reply_text("I didn't get that date. Try: /birthday Mom Mar 14")
                return
            try:
                item = self.add_birthday(*parsed)
            except ValueError as error:
                await message.reply_text(str(error))
                return
            when = next_birthday(item["month"], item["day"], today)
            await message.reply_text(f"🎂 Saved {item['name']}: {when:%b %-d}. I'll remind you the day before.")
            return
        text, markup = birthdays_view(Birthdays(self.db), today)
        await message.reply_text(text, reply_markup=markup)

    async def on_birthday_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        birthdays = Birthdays(self.db)
        gone = birthdays.remove(int(query.data.split(":")[2]))
        if gone is None:
            await query.answer("Already removed.")
        else:
            self._cancel_birthday_reminder(gone)
            ActionLog(self.db).record("reminder", f"Birthday removed: {gone['name']}")
            await query.answer("Removed")
        text, markup = birthdays_view(birthdays, datetime.now(self.config.timezone).date())
        await query.edit_message_text(text, reply_markup=markup)
