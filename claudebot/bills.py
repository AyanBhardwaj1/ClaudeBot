"""Bills: "rent is $1200 on the 1st" becomes a bill with a monthly reminder two days before.
/bills lists them with the next due date and the monthly total; ✅ Paid logs it as an expense."""

import calendar
import json
from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .actions import ActionLog
from .db import Database
from .expenses import Expenses, currency_code

BILLS_KEY = "bills"
NEXT_ID_KEY = "bills_next_id"
MAX_BILLS = 30
REMIND_DAYS_BEFORE = 2
EARLY_DAYS = 20  # how far ahead a Paid tap can settle the next bill


def next_due(day: int, today: date) -> date:
    """The next date with that day of the month (the 31st becomes the month's last day)."""
    for months in (0, 1, 2):
        year, month = today.year + (today.month - 1 + months) // 12, (today.month - 1 + months) % 12 + 1
        due = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if due >= today:
            return due
    raise AssertionError("unreachable")


def paid_dates(bill: dict) -> set[str]:
    """The due dates already settled (an older bill stored just one, as a string)."""
    paid = bill.get("paid") or []
    return {paid} if isinstance(paid, str) else set(paid)


def paying_for(day: int, today: date) -> date:
    """The due date a Paid tap today settles: whichever of the last and next due dates is nearer
    (paying a Nov 1 bill on Oct 30 settles Nov 1; a late Oct 3 payment still settles Oct 1)."""
    upcoming = next_due(day, today)
    if upcoming == today:
        return today
    this_month = date(today.year, today.month, min(day, calendar.monthrange(today.year, today.month)[1]))
    if this_month < today:
        previous = this_month
    else:
        last = today.replace(day=1) - timedelta(days=1)
        previous = date(last.year, last.month, min(day, calendar.monthrange(last.year, last.month)[1]))
    return previous if (today - previous) < (upcoming - today) else upcoming


class Bills:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> list[dict]:
        return json.loads(self.db.get_setting(BILLS_KEY) or "[]")

    def _save(self, bills: list[dict]) -> None:
        self.db.set_setting(BILLS_KEY, json.dumps(bills))

    def add(self, name: str, amount: float, day: int, currency: str = "USD",
            reminder_id: int | None = None) -> tuple[dict, dict | None]:
        """Returns (the bill, the one with the same name it replaced, if any). Ids are never reused,
        so a button on an old card can't act on a newer bill."""
        name = clean_name(name)
        if not name or not 0 < amount <= 1_000_000_000 or not 1 <= day <= 31:
            raise ValueError("A bill needs a name, an amount and a day of the month (1-31).")
        bills = self.all()
        replaced = next((b for b in bills if b["name"].lower() == name.lower()), None)
        kept = [b for b in bills if b is not replaced]
        if len(kept) >= MAX_BILLS:
            raise ValueError(f"That's {MAX_BILLS} bills already.")
        last = max([int(self.db.get_setting(NEXT_ID_KEY) or 0)] + [b["id"] for b in bills])
        self.db.set_setting(NEXT_ID_KEY, str(last + 1))
        bill = {"id": last + 1, "name": name, "amount": round(amount, 2), "currency": currency_code(currency),
                "day": day, "reminder_id": reminder_id}
        self._save(kept + [bill])
        return bill, replaced

    def remove(self, bill_id: int) -> dict | None:
        bills = self.all()
        gone = next((b for b in bills if b["id"] == bill_id), None)
        self._save([b for b in bills if b["id"] != bill_id])
        return gone

    def mark_paid(self, bill_id: int, today: date) -> date | None:
        """Once per due date: a second tap doesn't log the expense twice. Returns the due date it settled."""
        bills = self.all()
        bill = next((b for b in bills if b["id"] == bill_id), None)
        if bill is None:
            return None
        settled = paid_dates(bill)
        if bill.get("paid_on") == today.isoformat():
            return None  # a double tap, or a second tap the same day
        cycle = paying_for(bill["day"], today).isoformat()
        upcoming = next_due(bill["day"], today)
        if cycle in settled and (upcoming - today).days <= EARLY_DAYS:
            cycle = upcoming.isoformat()  # the last one is settled: this pays the next one early
        if cycle in settled:
            return None
        bill["paid"] = sorted(settled | {cycle})[-3:]
        bill["paid_on"] = today.isoformat()
        self._save(bills)
        return date.fromisoformat(cycle)


def clean_name(name: str) -> str:
    return " ".join(str(name).replace("<", " ").replace(">", " ").split())[:40]


def ordinal(day: int) -> str:
    return f"{day}{'th' if 11 <= day % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')}"


def reminder_text(bill: dict) -> str:
    """Names the due day rather than "in 2 days": a monthly reminder lands on its own day of the month,
    which in short months isn't exactly two days before the bill."""
    shorter = " (or the month's last day)" if bill["day"] > 28 else ""
    return f"🧾 {bill['name']} ({bill['amount']:,.2f} {bill['currency']}) is due on the {ordinal(bill['day'])}{shorter}"


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
        paid = " ✅ paid" if due.isoformat() in paid_dates(b) else ""  # the date shown, not an earlier one
        lines.append(f"- {b['name']}: {b['amount']:,.2f} {b['currency']}, due {due:%b %-d}{soon}{paid}")
        rows.append([InlineKeyboardButton(f"✅ Paid {b['name'][:20]}", callback_data=f"bill:paid:{b['id']}"),
                     InlineKeyboardButton("🗑", callback_data=f"bill:del:{b['id']}")])
    lines.append("Each month: " + ", ".join(f"{v:,.2f} {k}" for k, v in totals.items()))
    return "\n".join(lines), InlineKeyboardMarkup(rows)


class BillHandlers:
    """Mixed into TelegramBot."""

    def add_bill(self, name: str, amount: float, day: int, currency: str = "USD") -> dict:
        """Store the bill and its monthly reminder (two days before, 9:00). Replacing a bill with the
        same name cancels the old one's reminder, by its id."""
        bills = Bills(self.db)
        now = datetime.now(self.config.timezone)
        due = next_due(day, now.date())
        remind = datetime.combine(due - timedelta(days=REMIND_DAYS_BEFORE), time(9), tzinfo=self.config.timezone)
        if remind <= now:
            remind = datetime.combine(next_due(day, due + timedelta(days=1)) - timedelta(days=REMIND_DAYS_BEFORE),
                                      time(9), tzinfo=self.config.timezone)
        bill, replaced = bills.add(name, amount, day, currency)  # validates before any reminder exists
        reminder_id = self.db.add_reminder(reminder_text(bill), remind, "monthly", False)
        bill["reminder_id"] = reminder_id
        bills._save([bill if b["id"] == bill["id"] else b for b in bills.all()])
        self._cancel_bill_reminder(replaced)
        self.schedule_reminder(reminder_id)
        ActionLog(self.db).record("money", f"New bill: {bill['name']}, {bill['amount']:,.2f} {bill['currency']} "
                                           f"on day {bill['day']}")
        return bill

    def _cancel_bill_reminder(self, bill: dict | None) -> None:
        if not bill:
            return
        ids = [bill["reminder_id"]] if bill.get("reminder_id") else [
            # bills saved before reminder ids: their exact old text, never a prefix
            r["id"] for r in self.db.active_reminders() if r["repeat"] == "monthly" and r["text"] ==
            f"{bill['name']} ({bill['amount']:,.2f} {bill['currency']}) is due in {REMIND_DAYS_BEFORE} days"]
        for reminder_id in ids:
            self.db.deactivate_reminder(reminder_id)
            self.unschedule_reminder(reminder_id)

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
        today = datetime.now(self.config.timezone).date()
        if action == "paid":
            settled = bills.mark_paid(bill["id"], today)
            if settled is None:
                await query.answer(f"{bill['name']} is already logged as paid (see /bills).")
                return
            Expenses(self.db).log(bill["amount"], "bills", bill["name"], bill["currency"])
            ActionLog(self.db).record("money", f"Paid {bill['name']}: {bill['amount']:,.2f} {bill['currency']}")
            await query.answer(f"✅ Logged {bill['name']} as paid for {settled:%b %-d}")
        else:
            bills.remove(bill["id"])
            self._cancel_bill_reminder(bill)  # its own reminder, by id, and no other
            await query.answer("Removed")
        text, markup = bills_view(bills, today)
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest:  # "message is not modified": the card already shows this
            pass
