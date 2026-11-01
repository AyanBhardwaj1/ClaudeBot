"""Expenses: "spent $12 on lunch" goes in a small ledger; "how much on food this month?" is
answered by adding up the ledger, not by the model's arithmetic. /spent shows the month."""

from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from .db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    category TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS expenses_at ON expenses(at);
"""
MAX_AMOUNT = 1_000_000  # in whole currency units: a typo guard


def _clean(text: str, limit: int) -> str:
    return " ".join(str(text).replace("<", " ").replace(">", " ").split())[:limit]


class Expenses:
    def __init__(self, db: Database):
        self.db = db
        db.conn.executescript(SCHEMA)

    def log(self, amount: float, category: str, note: str = "", currency: str = "USD",
            at: datetime | None = None) -> dict:
        if not 0 < amount <= MAX_AMOUNT:
            raise ValueError(f"Amount must be between 0 and {MAX_AMOUNT:,}.")
        currency = (currency or "USD").strip().upper()[:3]
        category = _clean(category or "other", 30).lower() or "other"
        when = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cur = self.db.conn.execute(
            "INSERT INTO expenses (at, cents, currency, category, note) VALUES (?, ?, ?, ?, ?)",
            (when.isoformat(), round(amount * 100), currency, category, _clean(note, 120)))
        self.db.conn.commit()
        return {"id": cur.lastrowid, "amount": round(amount, 2), "currency": currency, "category": category}

    def delete(self, expense_id: int) -> bool:
        cur = self.db.conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        self.db.conn.commit()
        return cur.rowcount > 0

    def summary(self, start: datetime, end: datetime, category: str | None = None) -> dict:
        params = [start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()]
        where = "at >= ? AND at < ?"
        if category:
            where += " AND category = ?"
            params.append(_clean(category, 30).lower())
        totals = self.db.conn.execute(
            f"SELECT currency, category, SUM(cents) AS cents, COUNT(*) AS n FROM expenses WHERE {where} "
            "GROUP BY currency, category ORDER BY cents DESC", params).fetchall()
        items = self.db.conn.execute(
            f"SELECT id, at, cents, currency, category, note FROM expenses WHERE {where} ORDER BY at DESC LIMIT 50",
            params).fetchall()
        by_currency: dict[str, int] = {}
        for r in totals:
            by_currency[r["currency"]] = by_currency.get(r["currency"], 0) + r["cents"]
        return {
            "total": {c: cents / 100 for c, cents in by_currency.items()},
            "by_category": [{"category": r["category"], "currency": r["currency"], "amount": r["cents"] / 100,
                             "count": r["n"]} for r in totals],
            "recent": [{"id": r["id"], "at": r["at"], "amount": r["cents"] / 100, "currency": r["currency"],
                        "category": r["category"], "note": r["note"]} for r in items],
        }


def expense_tool(name: str, a: dict, db: Database, tz) -> dict:
    expenses = Expenses(db)
    if name == "log_expense":
        when = datetime.fromisoformat(a["date"]).replace(tzinfo=tz) if a.get("date") else None
        return {"logged": expenses.log(float(a["amount"]), a.get("category", "other"), a.get("note", ""),
                                       a.get("currency", "USD"), when)}
    if name == "spending_summary":
        start = datetime.fromisoformat(a["start"])
        end = datetime.fromisoformat(a["end"])
        start, end = (d if d.tzinfo else d.replace(tzinfo=tz) for d in (start, end))
        return {**expenses.summary(start, end, a.get("category")),
                "note": "Totals are summed from the owner's logged expenses; quote them as given."}
    if name == "delete_expense":
        return {"deleted": expenses.delete(int(a["expense_id"]))}
    raise ValueError(name)


class ExpenseHandlers:
    """Mixed into TelegramBot."""

    async def on_spent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        data = Expenses(self.db).summary(start, now + timedelta(days=1))
        if not data["by_category"]:
            await update.effective_message.reply_text(
                "No expenses this month. Just tell me: \"spent $12 on lunch\" or \"$54 groceries yesterday\".")
            return
        lines = [f"💸 {now:%B} so far"]
        lines += [f"- {c['category']}: {c['amount']:,.2f} {c['currency']} ({c['count']})" for c in data["by_category"]]
        lines.append("Total: " + ", ".join(f"{v:,.2f} {k}" for k, v in data["total"].items()))
        await update.effective_message.reply_text("\n".join(lines))
