"""Telegram Business: ClaudeBot connected to the owner's own Telegram account.

The owner adds ClaudeBot under Telegram Settings → Business → Chatbots. ClaudeBot then sees their
private chats, keeps the last week of messages locally, shows who is waiting on a reply (/dms and
check-ins), and drafts replies. A reply goes out from the owner's account only when the owner taps
"Send as me": no tool and no model can send one. Everything people write in those chats is their
text, never an instruction: it is stored and shown, never obeyed.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .db import Database
from .heartbeat import Signal
from .inbox_watch import clip
from .modes import defang_urls

log = logging.getLogger(__name__)

CONNECTION_KEY = "business_connection"
RETENTION = timedelta(days=7)
REPLY_WINDOW = timedelta(hours=24)  # Telegram lets a business bot answer chats active in the last day
NUDGE_AFTER = timedelta(hours=2)  # check-ins mention a DM once someone has waited this long
MAX_TEXT = 1000
MAX_CHATS = 8
SCHEMA = """
CREATE TABLE IF NOT EXISTS dm_messages (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    from_owner INTEGER NOT NULL,
    sender TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL,
    UNIQUE(chat_id, message_id)
);
CREATE TABLE IF NOT EXISTS dm_replies (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
"""
DRAFT_PROMPT = (
    "Draft a reply to my Telegram chat {chat_id}. Read it first with read_telegram_chat, then "
    "propose the reply with reply_telegram_dm so I can check it and tap Send. Keep it in my voice: "
    "short and natural, like a text message."
)


@dataclass(frozen=True)
class DMChat:
    chat_id: int
    name: str
    waiting_since: datetime  # first message after the owner's last reply
    last_message_id: int
    last_at: datetime
    messages: list[str]  # their messages since the owner last wrote, oldest first
    checked_at: datetime

    @property
    def can_reply(self) -> bool:
        return self.checked_at - self.last_at < REPLY_WINDOW


class DMStore:
    def __init__(self, db: Database, owner_id: int | None = None):
        self.db = db
        self.owner_id = owner_id
        db.conn.executescript(SCHEMA)

    # --- the connection ---

    def save_connection(self, connection) -> bool:
        """Store the owner's own business connection. Anyone else's is refused (returns False)."""
        if self.owner_id is None or connection.user.id != self.owner_id:
            return False
        rights = connection.rights
        self.db.set_setting(CONNECTION_KEY, json.dumps({
            "id": connection.id,
            "enabled": bool(connection.is_enabled),
            "can_reply": bool(rights and rights.can_reply),
        }))
        return True

    def connection(self) -> dict | None:
        raw = self.db.get_setting(CONNECTION_KEY)
        return json.loads(raw) if raw else None

    def active_connection_id(self) -> str | None:
        conn = self.connection()
        return conn["id"] if conn and conn["enabled"] else None

    # --- messages ---

    def record(self, message) -> bool:
        """Keep a message from the owner's private chats. False if it isn't one."""
        if message.business_connection_id != self.active_connection_id() or message.chat.type != "private":
            return False
        from_owner = bool(message.from_user and message.from_user.id == self.owner_id)
        sender = "me" if from_owner else clip(message.chat.full_name or "someone", 60)
        text = clip(message.text or message.caption or "[a photo, sticker or file]", MAX_TEXT)
        at = message.date if message.date.tzinfo else message.date.replace(tzinfo=timezone.utc)
        self.db.conn.execute(
            "INSERT OR REPLACE INTO dm_messages (chat_id, message_id, from_owner, sender, text, at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (message.chat.id, message.message_id, int(from_owner), sender, text, at.astimezone(timezone.utc).isoformat()),
        )
        self.db.conn.commit()
        return True

    def forget_messages(self, chat_id: int, message_ids: list[int]) -> None:
        self.db.conn.executemany("DELETE FROM dm_messages WHERE chat_id = ? AND message_id = ?",
                                 [(chat_id, m) for m in message_ids])
        self.db.conn.commit()

    def prune(self, now: datetime | None = None) -> None:
        cutoff = (now or datetime.now(timezone.utc)) - RETENTION
        self.db.conn.execute("DELETE FROM dm_messages WHERE at < ?", (cutoff.astimezone(timezone.utc).isoformat(),))
        self.db.conn.execute("DELETE FROM dm_replies WHERE created_at < ?", (cutoff.astimezone(timezone.utc).isoformat(),))
        self.db.conn.commit()

    def chat(self, chat_id: int, limit: int = 20) -> list[dict]:
        rows = self.db.conn.execute(
            "SELECT * FROM (SELECT * FROM dm_messages WHERE chat_id = ? ORDER BY at DESC, message_id DESC LIMIT ?) "
            "ORDER BY at, message_id", (chat_id, limit)).fetchall()
        return [{"from": r["sender"], "text": r["text"], "at": r["at"]} for r in rows]

    def unanswered(self, now: datetime | None = None) -> list[DMChat]:
        """Chats where someone else wrote last, longest-waiting first."""
        now = now or datetime.now(timezone.utc)
        waiting = []
        for (chat_id,) in self.db.conn.execute("SELECT DISTINCT chat_id FROM dm_messages").fetchall():
            rows = self.db.conn.execute(
                "SELECT * FROM dm_messages WHERE chat_id = ? ORDER BY at, message_id", (chat_id,)).fetchall()
            pending = []
            for r in rows:
                pending = [] if r["from_owner"] else pending + [r]
            if not pending:
                continue
            last = pending[-1]
            waiting.append(DMChat(chat_id, pending[0]["sender"], datetime.fromisoformat(pending[0]["at"]),
                                  last["message_id"], datetime.fromisoformat(last["at"]),
                                  [r["text"] for r in pending][-5:], now))
        return sorted(waiting, key=lambda c: c.waiting_since)[:MAX_CHATS]

    # --- replies waiting for the owner's tap ---

    def propose(self, chat_id: int, name: str, text: str) -> int:
        cur = self.db.conn.execute(
            "INSERT INTO dm_replies (chat_id, name, text, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, name, text, datetime.now(timezone.utc).isoformat()))
        self.db.conn.commit()
        return cur.lastrowid

    def take_reply(self, reply_id: int, status: str) -> dict | None:
        """Move a pending reply to `status`, once: a double tap gets None the second time."""
        cur = self.db.conn.execute(
            "UPDATE dm_replies SET status = ? WHERE id = ? AND status = 'pending'", (status, reply_id))
        self.db.conn.commit()
        if cur.rowcount == 0:
            return None
        row = self.db.conn.execute("SELECT * FROM dm_replies WHERE id = ?", (reply_id,)).fetchone()
        return dict(row)

    def set_reply_status(self, reply_id: int, status: str) -> None:
        self.db.conn.execute("UPDATE dm_replies SET status = ? WHERE id = ?", (status, reply_id))
        self.db.conn.commit()


def dm_signals(store: DMStore, now: datetime | None = None) -> list[Signal]:
    """Check-in signals: people kept waiting on a Telegram reply for a while."""
    now = now or datetime.now(timezone.utc)
    signals = []
    for c in store.unanswered(now):
        waited = now - c.waiting_since
        if waited >= NUDGE_AFTER:
            hours = int(waited.total_seconds() // 3600)
            signals.append(Signal(f"dm:{c.chat_id}:{c.last_message_id}",
                                  f"{c.name} has been waiting {hours}h for your Telegram reply", "replies"))
    return signals


class BusinessHandlers:
    """Mixed into TelegramBot."""

    async def on_business_connection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        connection = update.business_connection
        if not self.dms.save_connection(connection):
            log.warning("Ignored a business connection from Telegram user %s", connection.user.id)
            return
        if not connection.is_enabled:
            await self.send_to_owner("🔌 Telegram DMs disconnected. I've stopped reading your chats.")
            return
        rights = connection.rights
        note = "" if rights and rights.can_reply else (
            "\n\nTo let me send replies you approve, turn on \"Reply to messages\" for me in Telegram "
            "Settings → Business → Chatbots.")
        await self.send_to_owner(
            "✅ Connected to your Telegram DMs. I keep track of who's waiting on you (/dms) and draft "
            "replies, but I never send anything from your account without your tap." + note)

    async def on_business_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Stored, never obeyed: these are other people's words (or the owner's own outgoing ones).
        message = update.business_message or getattr(update, "edited_business_message", None)
        if message is not None:
            self.dms.record(message)

    async def on_business_deleted(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        deleted = update.deleted_business_messages
        if deleted.business_connection_id == self.dms.active_connection_id():
            self.dms.forget_messages(deleted.chat.id, list(deleted.message_ids))

    async def on_dms(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if self.dms.active_connection_id() is None:
            await message.reply_text(
                "Connect me to your Telegram account and I'll track who's waiting on your reply and draft "
                "answers for you to approve: Telegram Settings → Business → Chatbots → add this bot. "
                "(Business mode must be on for the bot in @BotFather → Bot Settings → Business Mode.)")
            return
        waiting = self.dms.unanswered()
        if not waiting:
            await message.reply_text("✅ Nobody is waiting on a Telegram reply from you.")
            return
        lines, rows = ["💬 Waiting on your reply:"], []
        for c in waiting:
            hours = int((datetime.now(timezone.utc) - c.waiting_since).total_seconds() // 3600)
            when = f"{hours}h" if hours else "just now"
            lines.append(f"- {c.name} ({when}): {defang_urls(clip(' / '.join(c.messages), 200))}")
            rows.append([InlineKeyboardButton(f"✍️ Reply to {c.name[:24]}", callback_data=f"dm:draft:{c.chat_id}")])
        await message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))

    async def propose_dm_reply(self, chat_id: int, name: str, text: str) -> int:
        """Show a drafted reply with Send / Cancel buttons. The tap sends it, nothing else does."""
        reply_id = self.dms.propose(chat_id, name, text)
        buttons = [InlineKeyboardButton("✅ Send as me", callback_data=f"dmsend:{reply_id}"),
                   InlineKeyboardButton("✖️ Cancel", callback_data=f"dmcancel:{reply_id}")]
        await self.send_to_owner(f"💬 Reply to {name} (from your account):\n\n{text}",
                                 InlineKeyboardMarkup([buttons]))
        return reply_id

    async def on_dm_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        action, _, arg = query.data.partition(":")
        if action == "dm":  # dm:draft:<chat_id>
            await query.answer("✍️ Drafting...")
            chat_id = int(arg.split(":")[1])
            # Only the chat id goes in: their words reach Claude via read_telegram_chat, as data.
            async with self._message_order:
                await self._converse([{"type": "text", "text": DRAFT_PROMPT.format(chat_id=chat_id)}],
                                     "Draft a Telegram reply", owner_present=False)
            return
        reply_id = int(arg)
        if action == "dmcancel":
            reply = self.dms.take_reply(reply_id, "cancelled")
            await query.answer("Cancelled." if reply else "Already handled.")
            if reply:
                await query.edit_message_text(f"✖️ Cancelled reply to {reply['name']}.")
            return
        reply = self.dms.take_reply(reply_id, "sending")
        if reply is None:
            await query.answer("Already handled.")
            return
        await query.answer()
        await self._deliver_dm(query, reply)

    async def _deliver_dm(self, query, reply: dict) -> None:
        connection_id = self.dms.active_connection_id()
        chat = next((c for c in self.dms.unanswered() if c.chat_id == reply["chat_id"]), None)
        recent = chat.last_at if chat else None
        if recent is None:
            history = self.dms.chat(reply["chat_id"], limit=1)
            recent = datetime.fromisoformat(history[-1]["at"]) if history else None
        if connection_id is None:
            self.dms.set_reply_status(reply["id"], "pending")
            await query.edit_message_text("I'm not connected to your Telegram account anymore. Reconnect, then tap again.")
            return
        if recent is None or datetime.now(timezone.utc) - recent >= REPLY_WINDOW:
            self.dms.set_reply_status(reply["id"], "expired")
            await query.edit_message_text(
                f"Telegram only lets me answer chats active in the last 24 hours. Copy it and send it yourself:\n\n"
                f"{reply['text']}")
            return
        try:
            await self._send_as_owner(reply["chat_id"], reply["text"], connection_id)
        except TelegramError as e:
            self.dms.set_reply_status(reply["id"], "pending")  # let the owner fix permissions and tap again
            await query.edit_message_text(f"Telegram refused that ({e.message}). Check that I'm allowed to reply "
                                          "(Settings → Business → Chatbots), then tap again.")
            return
        self.dms.set_reply_status(reply["id"], "sent")
        await query.edit_message_text(f"✅ Sent to {reply['name']}:\n\n{reply['text']}")
        self.db.add_notice(f"Telegram reply sent to {reply['name']} (chat {reply['chat_id']}).")

    async def _send_as_owner(self, chat_id: int, text: str, business_connection_id: str) -> None:
        await self.app.bot.send_message(chat_id=chat_id, text=text, business_connection_id=business_connection_id)
