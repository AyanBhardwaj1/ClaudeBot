"""Lists: shopping, packing, to-dos. Claude adds to them when asked; the owner checks items off
with a tap (/lists). Stored locally."""

import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .actions import ActionLog
from .db import Database
from .modes import defang_urls

MAX_NAME = 40
MAX_ITEM = 200
MAX_ITEMS = 100
MAX_LISTS = 20
NOTES = "Notes"
MAX_VIEW = 3500  # characters: under Telegram's 4096 per message
SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- never reused: an old button can't hit a new list
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL REFERENCES lists(id),
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
"""


class ListFull(ValueError):
    def __init__(self, message: str, added: list[dict]):
        super().__init__(message)
        self.added = added


def _clean(text: str, limit: int) -> str:
    return " ".join(str(text).replace("<", " ").replace(">", " ").split())[:limit]


class Lists:
    def __init__(self, db: Database):
        self.db = db
        db.conn.executescript(SCHEMA)

    def _list_id(self, name: str, create: bool = False) -> int | None:
        name = _clean(name, MAX_NAME)
        row = self.db.conn.execute("SELECT id FROM lists WHERE name = ?", (name,)).fetchone()
        if row or not create or not name:
            return row["id"] if row else None
        if len(self.names()) >= MAX_LISTS:
            raise ValueError(f"You have {MAX_LISTS} lists already; delete one in /lists first.")
        cur = self.db.conn.execute("INSERT INTO lists (name) VALUES (?)", (name,))
        return cur.lastrowid

    def id_of(self, name: str) -> int | None:
        return self._list_id(name)

    def name_of(self, list_id: int) -> str | None:
        row = self.db.conn.execute("SELECT name FROM lists WHERE id = ?", (list_id,)).fetchone()
        return row["name"] if row else None

    def names(self) -> list[str]:
        return [r["name"] for r in self.db.conn.execute("SELECT name FROM lists ORDER BY id")]

    def items(self, name: str) -> list[dict]:
        list_id = self._list_id(name)
        if list_id is None:
            return []
        rows = self.db.conn.execute("SELECT id, text, done FROM list_items WHERE list_id = ? ORDER BY id", (list_id,))
        return [{"id": r["id"], "text": r["text"], "done": bool(r["done"])} for r in rows]

    def add(self, name: str, texts: list[str]) -> list[dict]:
        list_id = self._list_id(name, create=True)
        if list_id is None:
            raise ValueError("A list needs a name.")
        existing = {i["text"].lower() for i in self.items(name)}
        added = []
        for text in texts:
            text = _clean(text, MAX_ITEM)
            if not text or text.lower() in existing:
                continue
            if len(existing) >= MAX_ITEMS:
                self.db.conn.commit()  # keep what fit
                raise ListFull(f"{name} is full ({MAX_ITEMS} items); clear checked items first.", added)
            cur = self.db.conn.execute("INSERT INTO list_items (list_id, text) VALUES (?, ?)", (list_id, text))
            existing.add(text.lower())
            added.append({"id": cur.lastrowid, "text": text, "done": False})
        self.db.conn.commit()
        return added

    def list_of(self, item_id: int) -> str | None:
        row = self.db.conn.execute(
            "SELECT l.name FROM list_items i JOIN lists l ON l.id = i.list_id WHERE i.id = ?", (item_id,)).fetchone()
        return row["name"] if row else None

    def toggle(self, item_id: int, list_id: int | None = None) -> dict | None:
        """Flip an item. With list_id, only if it still belongs to that list: SQLite reuses ids,
        so an old button must not tick an item on some other list."""
        if list_id is not None and not self.db.conn.execute(
                "SELECT 1 FROM list_items WHERE id = ? AND list_id = ?", (item_id, list_id)).fetchone():
            return None
        self.db.conn.execute("UPDATE list_items SET done = 1 - done WHERE id = ?", (item_id,))
        self.db.conn.commit()
        row = self.db.conn.execute(
            "SELECT i.id, i.text, i.done, l.name FROM list_items i JOIN lists l ON l.id = i.list_id WHERE i.id = ?",
            (item_id,)).fetchone()
        return {"id": row["id"], "text": row["text"], "done": bool(row["done"]), "list": row["name"]} if row else None

    def set_done(self, item_ids: list[int]) -> int:
        cur = self.db.conn.executemany("UPDATE list_items SET done = 1 WHERE id = ?", [(int(i),) for i in item_ids])
        self.db.conn.commit()
        return cur.rowcount

    def clear_done(self, name: str) -> int:
        list_id = self._list_id(name)
        cur = self.db.conn.execute("DELETE FROM list_items WHERE list_id = ? AND done = 1", (list_id,))
        self.db.conn.commit()
        return cur.rowcount

    def delete_list(self, name: str) -> None:
        list_id = self._list_id(name)
        if list_id is not None:
            self.db.conn.execute("DELETE FROM list_items WHERE list_id = ?", (list_id,))
            self.db.conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
            self.db.conn.commit()


def list_view(lists: Lists, name: str) -> tuple[str, InlineKeyboardMarkup | None]:
    items = lists.items(name)
    list_id = lists.id_of(name)
    canonical = next((n for n in lists.names() if n.lower() == name.lower()), name)
    if list_id is None:
        return f"There's no list called {canonical}.", None
    delete = [InlineKeyboardButton("🗑 Delete list", callback_data=f"ld:{list_id}")]
    if not items:
        return f"🗒 {canonical} is empty.", InlineKeyboardMarkup([delete])
    lines = [f"🗒 {canonical}"] + [f"{'✅' if i['done'] else '⬜'} {defang_urls(i['text'])}" for i in items]
    text = "\n".join(lines)
    if len(text) > MAX_VIEW:
        text = text[:MAX_VIEW].rsplit("\n", 1)[0] + f"\n... ({len(items)} items in all)"
    rows = [[InlineKeyboardButton(f"{'✅' if i['done'] else '⬜'} {i['text'][:30]}",
                                  callback_data=f"li:{list_id}:{i['id']}")] for i in items[:40]]
    extra = [InlineKeyboardButton("🧹 Clear checked", callback_data=f"lc:{list_id}")] if any(i["done"] for i in items) else []
    rows.append(extra + delete)
    return text, InlineKeyboardMarkup(rows)


class ListHandlers:
    """Mixed into TelegramBot."""

    async def on_lists(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        lists = Lists(self.db)
        names = [" ".join(context.args)] if context.args else lists.names()[::-1]  # newest first
        if not names:
            await update.effective_message.reply_text(
                "No lists yet. Just ask: \"add milk and eggs to my shopping list\" or \"start a packing list for Austin\".")
            return
        for name in names[:6]:
            text, markup = list_view(lists, name)
            await update.effective_message.reply_text(text, reply_markup=markup)

    async def on_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/note <text>: quick capture into the Notes list."""
        text = " ".join(context.args or [])
        if not text:
            await update.effective_message.reply_text("Jot something down: /note call the landlord about the heater")
            return
        try:
            added = Lists(self.db).add(NOTES, [text])
        except ValueError as e:
            await update.effective_message.reply_text(str(e))
            return
        await update.effective_message.reply_text("🗒 Noted." if added else "🗒 Already in your notes.")

    async def on_list_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        kind, list_id, *rest = query.data.split(":")
        lists = Lists(self.db)
        name = lists.name_of(int(list_id))
        if name is None:
            return
        if kind == "li":
            if lists.toggle(int(rest[0]), list_id=int(list_id)) is None:
                return  # an old button for an item that's gone
            ActionLog(self.db).record("list", f"Ticked an item on {name}")
        elif kind == "lc":
            ActionLog(self.db).record("list", f"Cleared {lists.clear_done(name)} checked items from {name}")
        else:  # "ld": delete the whole list
            lists.delete_list(name)
            ActionLog(self.db).record("list", f"Deleted the list {name}")
            await query.edit_message_text(f"🗑 Deleted {name}.")
            return
        try:
            text, markup = list_view(lists, name)
            await query.edit_message_text(text, reply_markup=markup)
        except TelegramError:
            pass


def list_tool(name: str, a: dict, db: Database) -> dict:
    lists = Lists(db)
    if name == "show_lists":
        names = [a["list"]] if a.get("list") else lists.names()
        return {"lists": [{"name": n, "items": lists.items(n)} for n in names]}
    if name == "add_to_list":
        try:
            added = lists.add(a["list"], list(a.get("items", [])))
        except ListFull as e:
            return {"list": a["list"], "added": [i["text"] for i in e.added], "error": str(e)}
        return {"list": a["list"], "added": [i["text"] for i in added],
                "note": "Already-listed items were skipped. The owner can tap items off in /lists."}
    if name == "check_off":
        return {"checked": lists.set_done(list(a.get("item_ids", [])))}
    raise ValueError(json.dumps({"unknown": name}))
