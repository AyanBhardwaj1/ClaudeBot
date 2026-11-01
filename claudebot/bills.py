"""Bills: "rent is $1200 on the 1st" becomes a bill with a monthly reminder two days before.
/bills lists them with the next due date and the monthly total; ✅ Paid logs it as an expense."""

import calendar
import json
from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .actions import ActionLog
from .db import Database
from .expenses import Expenses, currency_code

BILLS_KEY = "bills"
MAX_BILLS = 30
REMIND_DAYS_BEFORE = 2


def next_due(day: int, today: date) -> date:
    """The next date with that day of the month (the 31st becomes the month's last day)."""
    for months in (0, 1, 2):
        year, month = today.year + (today.month - 1 + months) // 12, (today.month - 1 + months) % 12 + 1
        due = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if due >= today:
            return due
    raise AssertionError("unreachable")


class Bills:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> list[dict]:
        return json.loads(self.db.get_setting(BILLS_KEY) or "[]")

    def add(self, name: str, amount: float, day: int, currency: str = "USD") -> dict:
        name = " ".join(str(name).replace("<", " ").replace(">", " ").split())[:40]
        if not name or not 0 < amount <= 1_000_000_000 or not 1 <= day <= 31:
            raise ValueError("A bill needs a name, an amount and a day of the month (1-31).")
        bills = [b for b in self.all() if b["name"].lower() != name.lower()]
        if len(bills) >= MAX_BILLS:
            raise ValueError(f"That's {MAX_BILLS} bills already.")
        bill = {"id": max((b["id"] for b in self.all()), default=0) + 1, "name": name, "amount": round(amount, 2),
                "currency": currency_code(currency), "day": day}
        self.db.set_setting(BILLS_KEY, json.dumps(bills + [bill]))
        return bill

    def remove(self, bill_id: int) -> dict | None:
        bills = self.all()
        gone = next((b for b in bills if b["id"] == bill_id), None)
        self.db.set_setting(BILLS_KEY, json.dumps([b for b in bills if b["id"] != bill_id]))
        return gone


def bills_view(bills: Bills, today: date) -> tuple[str, InlineKeyboardMarkup | None]:
    items = bills.all()
    if not items:
        return "No bills yet. Tell me: \"rent is $1200 on the 1st\" or \"Netflix $15.49 on the 20th\".", None
    items = sorted(items, key=lambda b: next_due(b["day"], today))
    totals: dict[str, float] = {}
    lines, rows = ["🧾 Bills"], []
    for b in items:
        due = next_due(b["day"], today)
        totals[b["currency"]] = totals.get(b["currency"], 0) + b["amount"]
        soon = " ⚠️" if (due - today).days <= REMIND_DAYS_BEFORE else ""
        lines.append(f"- {b['name']}: {b['amount']:,.2f} {b['currency']}, due {due:%b %-d}{soon}")
        rows.append([InlineKeyboardButton(f"✅ Paid {b['name'][:20]}", callback_data=f"bill:paid:{b['id']}"),
                     InlineKeyboardButton("🗑", callback_data=f"bill:del:{b['id']}")])
    lines.append("Each month: " + ", ".join(f"{v:,.2f} {k}" for k, v in totals.items()))
    return "\n".join(lines), InlineKeyboardMarkup(rows)


class BillHandlers:
    """Mixed into TelegramBot."""

    def add_bill(self, name: str, amount: float, day: int, currency: str = "USD") -> dict:
        """Store the bill and its monthly reminder (two days before, 9:00)."""
        bill = Bills(self.db).add(name, amount, day, currency)
        now = datetime.now(self.config.timezone)
        due = next_due(bill["day"], now.date())
        remind = datetime.combine(due - timedelta(days=REMIND_DAYS_BEFORE), time(9), tzinfo=self.config.timezone)
        if remind <= now:
            remind = datetime.combine(next_due(bill["day"], due + timedelta(days=1)) - timedelta(days=REMIND_DAYS_BEFORE),
                                      time(9), tzinfo=self.config.timezone)
        text = f"{bill['name']} ({bill['amount']:,.2f} {bill['currency']}) is due in {REMIND_DAYS_BEFORE} days"
        self.schedule_reminder(self.db.add_reminder(text, remind, "monthly", False))
        ActionLog(self.db).record("money", f"New bill: {bill['name']}, {bill['amount']:,.2f} {bill['currency']} "
                                           f"on day {bill['day']}")
        return bill

    async def on_bills(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text, markup = bills_view(Bills(self.db), datetime.now(self.config.timezone).date())
        await update.effective_message.reply_text(text, reply_markup=markup)

    async def on_bill_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        _, action, bill_id = query.data.split(":")
        bills = Bills(self.db)
        bill = next((b for b in bills.all() if b["id"] == int(bill_id)), None)
        if bill is None:
            await query.answer("That bill is gone.")
            return
        if action == "paid":
            Expenses(self.db).log(bill["amount"], "bills", bill["name"], bill["currency"])
            ActionLog(self.db).record("money", f"Paid {bill['name']}: {bill['amount']:,.2f} {bill['currency']}")
            await query.answer(f"✅ Logged {bill['name']} as paid")
        else:
            bills.remove(bill["id"])
            for row in self.db.active_reminders():  # its monthly reminder goes too
                if row["repeat"] == "monthly" and row["text"].startswith(f"{bill['name']} ("):
                    self.db.deactivate_reminder(row["id"])
                    self.unschedule_reminder(row["id"])
            await query.answer("Removed")
        text, markup = bills_view(bills, datetime.now(self.config.timezone).date())
        await query.edit_message_text(text, reply_markup=markup)
