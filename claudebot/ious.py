"""IOUs: "Alex owes me $20 for dinner", "I owe Sam $15". /owed shows who owes whom, with a Settled
button per person. Amounts are added up by code."""

import json
import secrets
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .db import Database
from .expenses import currency_code

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
                             (person, cents, currency_code(currency), _clean(note, 100),
                              datetime.now(timezone.utc).isoformat()))
        self.db.conn.commit()
        return {"person": person, "amount": amount, "they_owe_you": they_owe_me}

    def balances(self) -> list[dict]:
        rows = self.db.conn.execute(
            "SELECT MIN(person) AS person, currency, SUM(cents) AS cents, COUNT(*) AS n FROM ious WHERE settled = 0 "
            "GROUP BY person COLLATE NOCASE, currency HAVING SUM(cents) != 0 ORDER BY ABS(SUM(cents)) DESC").fetchall()
        return [{"person": r["person"], "currency": r["currency"], "balance": r["cents"] / 100, "entries": r["n"]}
                for r in rows]

    def max_id(self) -> int:
        return self.db.conn.execute("SELECT COALESCE(MAX(id), 0) FROM ious").fetchone()[0]

    def settle(self, person: str, currency: str | None = None, up_to_id: int | None = None) -> int:
        """Settle what a card showed: that person, that currency, nothing added after the card."""
        sql, params = "UPDATE ious SET settled = 1 WHERE person = ? AND settled = 0", [person]
        if currency:
            sql += " AND currency = ?"
            params.append(currency)
        if up_to_id is not None:
            sql += " AND id <= ?"
            params.append(up_to_id)
        cur = self.db.conn.execute(sql, params)
        self.db.conn.commit()
        return cur.rowcount


def iou_view(ious: Ious) -> tuple[str, InlineKeyboardMarkup | None]:
    balances = ious.balances()
    if not balances:
        return "🤝 All square: nobody owes anybody. Tell me \"Alex owes me $20 for dinner\" to start.", None
    lines, rows = ["🤝 Who owes whom"], []
    # Each card stores what it showed under its own id, so an old card settles what it displayed,
    # not whoever is in that position now (and a non-Latin name can't break the 64-byte limit).
    card = secrets.token_hex(3)
    ious.db.set_setting(f"iou_card:{card}", json.dumps(
        {"rows": [[b["person"], b["currency"]] for b in balances], "max_id": ious.max_id()}))
    ious.db.prune_settings("iou_card:", 20)
    for i, b in enumerate(balances):
        amount = f"{abs(b['balance']):,.2f} {b['currency']}"
        lines.append(f"- {b['person']} owes you {amount}" if b["balance"] > 0 else f"- You owe {b['person']} {amount}")
        rows.append([InlineKeyboardButton(f"✅ Settled with {b['person'][:24]}", callback_data=f"iou:{card}:{i}")])
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
        _, card, index = query.data.split(":")
        shown = json.loads(self.db.get_setting(f"iou_card:{card}") or '{"rows": []}')
        if int(index) < len(shown["rows"]):
            person, currency = shown["rows"][int(index)]
            Ious(self.db).settle(person, currency, shown.get("max_id"))
        text, markup = iou_view(Ious(self.db))
        await query.edit_message_text(text, reply_markup=markup)
