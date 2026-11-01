"""/privacy: what ClaudeBot keeps, and buttons to clear it. Every clear asks once more first."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .actions import ActionLog
from .business import DMStore
from .journal import Journal

WHAT = {
    "chat": "conversation history",
    "dms": "stored Telegram DMs",
    "journal": "journal entries",
    "log": "the action log",
}


def counts(db) -> dict[str, int]:
    def n(sql: str) -> int:
        return db.conn.execute(sql).fetchone()[0]

    DMStore(db), Journal(db), ActionLog(db)  # make sure their tables exist
    return {"chat": n("SELECT COUNT(*) FROM messages"), "dms": n("SELECT COUNT(*) FROM dm_messages"),
            "journal": n("SELECT COUNT(*) FROM journal"), "log": n("SELECT COUNT(*) FROM actions"),
            "memories": n("SELECT COUNT(*) FROM memories")}


def clear(db, what: str) -> None:
    if what == "chat":
        db.conn.execute("DELETE FROM messages")
        db.conn.execute("DELETE FROM settings WHERE key LIKE 'thread_%'")  # re-announce mode, role, style
    elif what == "dms":
        db.conn.execute("DELETE FROM dm_messages")
    elif what == "journal":
        db.conn.execute("DELETE FROM journal")
    elif what == "log":
        db.conn.execute("DELETE FROM actions")
    db.conn.commit()


class PrivacyHandlers:
    """Mixed into TelegramBot."""

    async def on_privacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        c = counts(self.db)
        text = (
            "🔒 What I keep, on your server only:\n"
            f"- {c['chat']} conversation messages\n- {c['memories']} memories (/memory)\n"
            f"- {c['dms']} Telegram DM messages (last 7 days)\n- {c['journal']} journal entries\n"
            f"- {c['log']} action log entries (60 days)\n"
            "Plus reminders, lists, expenses and settings. /export downloads it all.\n\nClear:"
        )
        rows = [[InlineKeyboardButton(f"🧹 {label.capitalize()}", callback_data=f"priv:ask:{key}")]
                for key, label in WHAT.items()]
        await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))

    async def on_privacy_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        _, step, what = query.data.split(":")
        if what not in WHAT:
            return
        if step == "ask":
            await query.edit_message_text(
                f"Clear all {WHAT[what]}? This can't be undone.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes, clear", callback_data=f"priv:do:{what}"),
                                                    InlineKeyboardButton("Keep it", callback_data="priv:no:chat")]]))
            return
        if step == "no":
            await query.edit_message_text("Kept. Nothing was cleared.")
            return
        async with self._message_order:  # not in the middle of a conversation turn
            clear(self.db, what)
            if what == "chat":
                self.db.new_thread(self.agent.config_hash)
        await query.edit_message_text(f"🧹 Cleared {WHAT[what]}.")
