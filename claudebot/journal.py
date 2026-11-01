"""Journal: optional. "/journal on" and each evening ClaudeBot asks how the day went; the next
message is saved as that day's entry (the owner's own words, kept locally)."""

from datetime import datetime, time, timedelta, timezone

from telegram import ForceReply, Update
from telegram.ext import ContextTypes

from .db import Database
from .quiet import dnd_active

JOURNAL_KEY = "journal"  # "on" to be asked each evening
ASK_TIME = time(21, 30)
AWAIT = "journal:entry"
MAX_ENTRY = 4000
SCHEMA = """
CREATE TABLE IF NOT EXISTS journal (
    day TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
"""


class Journal:
    def __init__(self, db: Database):
        self.db = db
        db.conn.executescript(SCHEMA)

    def write(self, day: str, text: str) -> None:
        """One entry per day; writing again the same day adds to it."""
        text = text.strip()[:MAX_ENTRY]
        row = self.db.conn.execute("SELECT text FROM journal WHERE day = ?", (day,)).fetchone()
        full = f"{row['text']}\n\n{text}"[:MAX_ENTRY * 2] if row else text
        self.db.conn.execute("INSERT OR REPLACE INTO journal (day, text, at) VALUES (?, ?, ?)",
                             (day, full, datetime.now(timezone.utc).isoformat()))
        self.db.conn.commit()

    def recent(self, days: int, today: str) -> list[dict]:
        start = (datetime.fromisoformat(today) - timedelta(days=days - 1)).date().isoformat()
        return [dict(r) for r in self.db.conn.execute(
            "SELECT day, text FROM journal WHERE day >= ? AND day <= ? ORDER BY day", (start, today))]


class JournalHandlers:
    """Mixed into TelegramBot."""

    async def on_journal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = " ".join(context.args or []).strip()
        today = datetime.now(self.config.timezone).date().isoformat()
        if arg.lower() in ("on", "off"):
            self.db.set_setting(JOURNAL_KEY, arg.lower())
            await update.effective_message.reply_text(
                f"📓 Journal on: I'll ask how your day went at {ASK_TIME:%H:%M}. It stays on your server."
                if arg.lower() == "on" else "Journal prompts off. Your entries are kept; /journal shows them.")
            return
        if arg:  # "/journal great run today" writes directly
            Journal(self.db).write(today, arg)
            await update.effective_message.reply_text("📓 Saved.")
            return
        entries = Journal(self.db).recent(7, today)
        if not entries:
            await update.effective_message.reply_text(
                "No entries this week. /journal on to be asked each evening, or write one now: /journal <text>")
            return
        text = "\n\n".join(f"{e['day']}\n{e['text']}" for e in entries)
        await update.effective_message.reply_text(("📓 This week\n\n" + text)[:4000])

    async def _journal_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        if self.db.get_setting(JOURNAL_KEY) != "on" or dnd_active(self.db, now):
            return
        asked = await self.send_to_owner("📓 How was your day? Reply to this message with a few lines (or ignore it).",
                                         ForceReply(input_field_placeholder="How was your day?"))
        self._expect(AWAIT, reply_to=getattr(asked, "message_id", None))

    def save_journal_answer(self, text: str) -> None:
        Journal(self.db).write(datetime.now(self.config.timezone).date().isoformat(), text)
