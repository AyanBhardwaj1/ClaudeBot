"""IOUs: "Alex owes me $20 for dinner", "I owe Sam $15". /owed shows who owes whom, with a Settled
button per person. Amounts are added up by code."""

import json
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS ious (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person TEXT NOT NULL COLLATE NOCASE,
    cents INTEGER NOT NULL,          -- positive: they owe the owner; negative: the owner owes them
    currency TEXT NOT NULL,
    note TEXT NOT NULL,
    at TEXT NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0
);
"""


def _clean(text: str, limit: int) -> str:
    return " ".join(str(text).replace("<", " ").replace(">", " ").split())[:limit]


class Ious:
    def __init__(self, db: Database):
        self.db = db
        db.conn.executescript(SCHEMA)

    def add(self, person: str, amount: float, they_owe_me: bool, note: str = "", currency: str = "USD") -> dict:
        person = _clean(person, 40)
        if not person or not 0 < amount <= 1_000_000:
            raise ValueError("Say who and how much, e.g. Alex owes me $20.")
        cents = round(amount * 100) * (1 if they_owe_me else -1)
        self.db.conn.execute("INSERT INTO ious (person, cents, currency, note, at) VALUES (?, ?, ?, ?, ?)",
                             (person, cents, (currency or "USD").upper()[:3], _clean(note, 100),
                              datetime.now(timezone.utc).isoformat()))
        self.db.conn.commit()
        return {"person": person, "amount": amount, "they_owe_you": they_owe_me}

    def balances(self) -> list[dict]:
        rows = self.db.conn.execute(
            "SELECT MIN(person) AS person, currency, SUM(cents) AS cents, COUNT(*) AS n FROM ious WHERE settled = 0 "
            "GROUP BY person COLLATE NOCASE, currency HAVING SUM(cents) != 0 ORDER BY ABS(SUM(cents)) DESC").fetchall()
        return [{"person": r["person"], "currency": r["currency"], "balance": r["cents"] / 100, "entries": r["n"]}
                for r in rows]

    def settle(self, person: str) -> int:
        cur = self.db.conn.execute("UPDATE ious SET settled = 1 WHERE person = ? AND settled = 0", (person,))
        self.db.conn.commit()
        return cur.rowcount


def iou_view(ious: Ious) -> tuple[str, InlineKeyboardMarkup | None]:
    balances = ious.balances()
    if not balances:
        return "🤝 All square: nobody owes anybody. Tell me \"Alex owes me $20 for dinner\" to start.", None
    lines, rows = ["🤝 Who owes whom"], []
    # Buttons carry an index, not the name: a non-Latin name could pass Telegram's 64-byte limit.
    ious.db.set_setting("iou_names", json.dumps([b["person"] for b in balances]))
    for i, b in enumerate(balances):
        amount = f"{abs(b['balance']):,.2f} {b['currency']}"
        lines.append(f"- {b['person']} owes you {amount}" if b["balance"] > 0 else f"- You owe {b['person']} {amount}")
        rows.append([InlineKeyboardButton(f"✅ Settled with {b['person'][:24]}", callback_data=f"iou:{i}")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def iou_tool(name: str, a: dict, db: Database) -> dict:
    ious = Ious(db)
    if name == "record_iou":
        return {"recorded": ious.add(a["person"], float(a["amount"]), bool(a["they_owe_me"]), a.get("note", ""),
                                     a.get("currency", "USD"))}
    return {"balances": ious.balances(), "note": "Balances are summed by code; quote them as given."}


class IouHandlers:
    """Mixed into TelegramBot."""

    async def on_owed(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text, markup = iou_view(Ious(self.db))
        await update.effective_message.reply_text(text, reply_markup=markup)

    async def on_iou_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        names = json.loads(self.db.get_setting("iou_names") or "[]")
        index = int(query.data.split(":")[1])
        if index < len(names):
            Ious(self.db).settle(names[index])
        text, markup = iou_view(Ious(self.db))
        await query.edit_message_text(text, reply_markup=markup)
