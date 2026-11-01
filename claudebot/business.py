"""Telegram Business: ClaudeBot connected to the owner's own Telegram account.

The owner adds ClaudeBot under Telegram Settings → Business → Chatbots. ClaudeBot then sees their
private chats, keeps the last week of messages locally, shows who is waiting on a reply (/dms and
check-ins), and drafts replies. A reply goes out from the owner's account only when the owner taps
"Send as me": no tool and no model can send one. Everything people write in those chats is their
text, never an instruction: it is stored and shown, never obeyed.
"""

import json
import logging
import unicodedata
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)
from telegram.ext import ContextTypes

from .actions import ActionLog
from .db import Database
from .heartbeat import Signal
from .inbox_watch import clip, in_quiet_hours
from .modes import defang_urls
from .quiet import next_morning

log = logging.getLogger(__name__)

CONNECTION_KEY = "business_connection"
RETENTION = timedelta(days=7)
REPLY_WINDOW = timedelta(hours=24)  # Telegram lets a business bot answer chats active in the last day
NUDGE_AFTER = timedelta(hours=2)  # check-ins mention a DM once someone has waited this long
MAX_TEXT = 1000
MAX_CHATS = 8
QUICK_KEY = "dm_quick_replies"
DM_LATER_PREFIX = "dm_later_rid:"
DEFAULT_QUICK = ["On it 👍", "Can I get back to you later today?", "Thanks!"]
MAX_QUICK, MAX_QUICK_LEN = 3, 60  # short enough that a button shows all of it


def quick_replies(db: Database) -> list[str]:
    saved = json.loads(db.get_setting(QUICK_KEY) or "null") or []
    # Ones saved under the old 100-character cap are dropped, not cut mid-sentence (/quickreplies shows the rest).
    saved = [clean_quick(t) for t in saved if isinstance(t, str) and len(t) <= MAX_QUICK_LEN]
    saved = [t for t in saved if t][:MAX_QUICK]  # older, longer ones too
    return saved or DEFAULT_QUICK


def contact_label(name: str) -> str:
    """A contact's display name inside the bot's own text: links defanged, no tappable /commands."""
    return defang_urls(clip(name, 40)).replace("/", "⁄")


BLANKS = {"\u034f", "\u115f", "\u1160", "\u2800", "\u3164", "\uffa0"}  # look like nothing, aren't spaces


def clean_quick(text: str) -> str:
    """One line with nothing invisible in it, so a hidden tail can't ride behind what the button shows.
    Emoji joiners, presentation selectors and flag tags are kept only where they shape an emoji."""
    chars, kept = list(str(text)), []
    for i, ch in enumerate(chars):
        cp, before = ord(ch), (kept[-1] if kept else "")
        after = chars[i + 1] if i + 1 < len(chars) else ""
        is_emoji = lambda c: bool(c) and unicodedata.category(c) == "So"  # noqa: E731
        if ch in BLANKS or 0xE0100 <= cp <= 0xE01EF:  # filler and variation selectors supplement
            continue
        if ch == "\u200d":
            if is_emoji(before) or (before in ("\ufe0f",) and len(kept) > 1 and is_emoji(kept[-2])):
                if is_emoji(after):
                    kept.append(ch)
            continue
        if 0xFE00 <= cp <= 0xFE0F:
            if before and before != "\ufe0f" and unicodedata.category(before) in ("So", "Nd", "Po", "Sm"):
                kept.append(ch)
            continue
        if 0xE0020 <= cp <= 0xE007F:  # flag tags: only right after 🏴 or another tag
            if before == "\U0001F3F4" or (before and 0xE0020 <= ord(before) <= 0xE007F):
                kept.append(ch)
            continue
        if unicodedata.category(ch) == "Cf":
            continue
        kept.append(ch)
    return " ".join("".join(kept).split())[:MAX_QUICK_LEN]


def set_quick_replies(db: Database, text: str) -> list[str]:
    """'/quickreplies On it | Running late | Call you soon': up to 3, each short."""
    items = [clean_quick(t) for t in text.split("|")]
    items = [t for t in items if t][:MAX_QUICK]
    if not items:
        raise ValueError("Give up to 3 replies separated by |, e.g. /quickreplies On it 👍 | Running late | Thanks!")
    db.set_setting(QUICK_KEY, json.dumps(items))
    return items


def quick_tag(text: str) -> str:
    """Ties a button to the exact text it showed: editing the list later can't change what a tap sends."""
    return f"{zlib.crc32(text.encode()):08x}"
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
            "user_id": connection.user.id,
            "enabled": bool(connection.is_enabled),
            "can_reply": bool(rights and rights.can_reply),
        }))
        if not connection.is_enabled:
            self.clear()  # "I've stopped reading your chats" means their messages go too
        return True

    def connection(self) -> dict | None:
        raw = self.db.get_setting(CONNECTION_KEY)
        return json.loads(raw) if raw else None

    def active_connection_id(self) -> str | None:
        """The connection to use, only while enabled and only for the current owner (the owner can
        change: an ID in .env beats a paired one)."""
        conn = self.connection()
        if not conn or not conn["enabled"] or conn.get("user_id") != self.owner_id or self.owner_id is None:
            return None
        return conn["id"]

    def can_reply(self) -> bool:
        conn = self.connection()
        return bool(conn and conn.get("can_reply"))

    def clear(self) -> None:
        self.db.conn.execute("DELETE FROM dm_messages")
        self.db.conn.execute("UPDATE dm_replies SET status = 'cancelled' WHERE status = 'pending'")
        self.db.conn.commit()

    # --- messages ---

    def record(self, message, edited: bool = False) -> bool:
        """Keep a message from the owner's private chats. False if it isn't one. An edit only
        updates a message already kept (an old message edited later isn't news)."""
        if message.business_connection_id != self.active_connection_id() or message.chat.type != "private":
            return False
        if edited:
            cur = self.db.conn.execute(
                "UPDATE dm_messages SET text = ? WHERE chat_id = ? AND message_id = ?",
                (clip(message.text or message.caption or "[a photo, sticker or file]", MAX_TEXT),
                 message.chat.id, message.message_id))
            self.db.conn.commit()
            return cur.rowcount > 0
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

    def record_sent(self, chat_id: int, message_id: int, text: str, at: datetime) -> None:
        """A reply sent by tap: the chat is answered now, whether or not Telegram echoes it back."""
        self.db.conn.execute(
            "INSERT OR REPLACE INTO dm_messages (chat_id, message_id, from_owner, sender, text, at) "
            "VALUES (?, ?, 1, 'me', ?, ?)",
            (chat_id, message_id, clip(text, MAX_TEXT), at.astimezone(timezone.utc).isoformat()))
        self.db.conn.commit()

    def last_incoming_at(self, chat_id: int) -> datetime | None:
        """Telegram's 24-hour reply window counts from their last message, not the owner's."""
        row = self.db.conn.execute(
            "SELECT MAX(at) AS at FROM dm_messages WHERE chat_id = ? AND from_owner = 0", (chat_id,)).fetchone()
        return datetime.fromisoformat(row["at"]) if row and row["at"] else None

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
        return [{"from": "OWNER (you are drafting for them)" if r["from_owner"] else r["sender"],
                 "is_owner": bool(r["from_owner"]), "text": r["text"], "at": r["at"]} for r in rows]

    def unanswered(self, now: datetime | None = None, limit: int | None = MAX_CHATS) -> list[DMChat]:
        """Chats where someone else wrote last, longest-waiting first."""
        now = now or datetime.now(timezone.utc)
        waiting = []
        for (chat_id,) in self.db.conn.execute("SELECT DISTINCT chat_id FROM dm_messages").fetchall():
            rows = self.db.conn.execute(
                "SELECT * FROM dm_messages WHERE chat_id = ? ORDER BY at, message_id", (chat_id,)).fetchall()
            pending: list = []
            for r in rows:
                pending = [] if r["from_owner"] else pending + [r]
            if not pending:
                continue
            last = pending[-1]
            waiting.append(DMChat(chat_id, pending[0]["sender"], datetime.fromisoformat(pending[0]["at"]),
                                  last["message_id"], datetime.fromisoformat(last["at"]),
                                  [r["text"] for r in pending][-5:], now))
        # Chats that can still be answered first, newest first: last week's spam shouldn't hide today's Mom.
        return sorted(waiting, key=lambda c: (not c.can_reply, -c.last_at.timestamp()))[:limit]

    # --- replies waiting for the owner's tap ---

    def propose(self, chat_id: int, name: str, text: str) -> int:
        cur = self.db.conn.execute(
            "INSERT INTO dm_replies (chat_id, name, text, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, name, text, datetime.now(timezone.utc).isoformat()))
        self.db.conn.commit()
        return int(cur.lastrowid or 0)

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
    """Check-in signals: people kept waiting on a Telegram reply for a while (still answerable)."""
    now = now or datetime.now(timezone.utc)
    if store.active_connection_id() is None:
        return []
    signals = []
    for c in store.unanswered(now):
        waited = now - c.waiting_since
        if waited >= NUDGE_AFTER and c.can_reply:
            hours = int(waited.total_seconds() // 3600)
            signals.append(Signal(f"dm:{c.chat_id}:{c.last_message_id}",
                                  f"{defang_urls(c.name)} has been waiting {hours}h for your Telegram reply", "dms"))
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
        if update.business_message is not None:
            self.dms.record(update.business_message)
        elif getattr(update, "edited_business_message", None) is not None:
            self.dms.record(update.edited_business_message, edited=True)

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
            lines.append(f"- {defang_urls(c.name)} ({when}): {defang_urls(clip(' / '.join(c.messages), 200))}")
            row = [InlineKeyboardButton(f"✍️ Reply to {c.name[:24]}", callback_data=f"dm:draft:{c.chat_id}")]
            if c.can_reply:  # past Telegram's 24-hour window a quick reply can't go out anyway
                row.append(InlineKeyboardButton("⚡ Quick", callback_data=f"dm:quick:{c.chat_id}"))
            row.append(InlineKeyboardButton("⏰ 3h", callback_data=f"dm:later:{c.chat_id}"))
            rows.append(row)
        await message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))

    async def propose_dm_reply(self, chat_id: int, name: str, text: str) -> int:
        """Show a drafted reply with Send / Cancel buttons. The tap sends it, nothing else does."""
        reply_id = self.dms.propose(chat_id, name, text)
        buttons = [InlineKeyboardButton("✅ Send as me", callback_data=f"dmsend:{reply_id}"),
                   InlineKeyboardButton("✖️ Cancel", callback_data=f"dmcancel:{reply_id}")]
        await self.send_to_owner(f"💬 To: {defang_urls(name)} (sent from your account)\n\n{text}",
                                 InlineKeyboardMarkup([buttons]))
        return reply_id

    async def on_dm_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        action, _, arg = query.data.partition(":")
        if action == "dm" and arg.startswith("later:"):  # dm:later:<chat_id>
            await self._dm_later(query, int(arg.split(":")[1]))
            return
        if action == "dm" and arg.startswith("quick:"):  # dm:quick:<chat_id>
            await self._quick_card(query, int(arg.split(":")[1]))
            return
        if action == "dmq":  # dmq:<chat_id>:<i>:<tag>
            await self._quick_send(query, *arg.split(":"))
            return
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
                await query.edit_message_text(f"✖️ Cancelled reply to {defang_urls(reply['name'])}.")
            return
        reply = self.dms.take_reply(reply_id, "sending")
        if reply is None:
            await query.answer("Already handled.")
            return
        await query.answer()
        await self._deliver_dm(query, reply)

    def _waiting_chat(self, chat_id: int) -> DMChat | None:
        return next((c for c in self.dms.unanswered(limit=None) if c.chat_id == chat_id), None)

    async def _dm_later(self, query, chat_id: int) -> None:
        """A plain reminder to answer them yourself in 3 hours: nothing is sent to anyone."""
        chat = self._waiting_chat(chat_id)
        if chat is None:
            await query.answer("Nobody is waiting there now.")
            return
        key = f"dm_later:{chat_id}:{chat.last_message_id}"
        if self.db.get_setting(key):  # one reminder per message, however many taps
            await query.answer("Already set.")
            return
        self.db.set_setting(key, "1")
        self.db.prune_settings("dm_later:", 50)
        when = datetime.now(self.config.timezone) + timedelta(hours=3)
        if in_quiet_hours(when, self.config.quiet_hours):  # 3h from 10pm is 1am: the morning instead
            when = next_morning(when)
        reminder_id = self.db.add_reminder(f"💬 Reply to “{contact_label(chat.name)}” on Telegram (/dms)", when, "none", False)
        self.db.set_setting(f"{DM_LATER_PREFIX}{reminder_id}", str(chat_id))  # skipped if you reply first
        self.db.prune_settings(DM_LATER_PREFIX, 50)
        self.schedule_reminder(reminder_id)
        ActionLog(self.db).record("reminder", f"Reminder to reply to {chat.name} at {when:%H:%M}")
        await query.answer(f"⏰ I'll remind you at {when:%H:%M}.")

    async def _quick_card(self, query, chat_id: int) -> None:
        chat = self._waiting_chat(chat_id)
        if chat is None:
            await query.answer("Nobody is waiting there now.")
            return
        await query.answer()
        options = quick_replies(self.db)
        # Tied to their latest message: if they write again, this card stops working.
        rows = [[InlineKeyboardButton(f"{i + 1}. {text}",
                                      callback_data=f"dmq:{chat_id}:{chat.last_message_id}:{i}:{quick_tag(text)}")]
                for i, text in enumerate(options)]
        listed = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(options))  # in full, whatever the button shows
        await self.send_to_owner(
            f"⚡ Quick reply to {defang_urls(chat.name)}, who wrote: "
            f"{defang_urls(clip(chat.messages[-1] if chat.messages else '', 200))}\n\n{listed}\n\n"
            "One tap sends that reply from your account. Change them with /quickreplies.", InlineKeyboardMarkup(rows))

    async def _quick_send(self, query, chat_id: str, message_id: str, index: str, tag: str) -> None:
        options = quick_replies(self.db)
        text = options[int(index)] if int(index) < len(options) else None
        chat = self._waiting_chat(int(chat_id))
        if text is None or quick_tag(text) != tag:
            await query.answer("Those replies changed; tap ⚡ Quick again.")
            return
        if chat is None:
            await query.answer("Nobody is waiting there now.")
            return
        if chat.last_message_id != int(message_id):
            await query.answer("They wrote again since this card; tap ⚡ Quick in /dms for a fresh one.")
            return
        claim = f"dmq_sent:{chat.chat_id}:{chat.last_message_id}"
        if self.db.get_setting(claim):
            await query.answer("A quick reply to that message already went (or is waiting on a retry above).")
            return
        self.db.set_setting(claim, "1")  # claimed before any await: a fast double tap sends once
        self.db.prune_settings("dmq_sent:", 50)
        reply = self.dms.take_reply(self.dms.propose(chat.chat_id, chat.name, text), "sending")
        await query.answer()
        await self._deliver_dm(query, reply)

    async def on_quick_replies(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if context.args:
            try:
                items = set_quick_replies(self.db, " ".join(context.args))
            except ValueError as e:
                await message.reply_text(str(e))
                return
            await message.reply_text("⚡ Quick replies saved:\n" + "\n".join(f"- {t}" for t in items))
            return
        await message.reply_text("⚡ Your quick replies (tap ⚡ Quick in /dms):\n" +
                                 "\n".join(f"- {t}" for t in quick_replies(self.db)) +
                                 "\n\nChange them: /quickreplies On it 👍 | Running late | Thanks!")

    async def _deliver_dm(self, query, reply: dict) -> None:
        connection_id = self.dms.active_connection_id()
        recent = self.dms.last_incoming_at(reply["chat_id"])
        retry = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Send as me", callback_data=f"dmsend:{reply['id']}"),
                                       InlineKeyboardButton("✖️ Cancel", callback_data=f"dmcancel:{reply['id']}")]])
        if connection_id is None or not self.dms.can_reply():
            self.dms.set_reply_status(reply["id"], "pending")
            await query.edit_message_text(
                "I can't reply from your account right now: connect me in Telegram Settings → Business → Chatbots "
                f"and allow \"Reply to messages\". Then tap Send again.\n\n{reply['text']}", reply_markup=retry)
            return
        if recent is None or datetime.now(timezone.utc) - recent >= REPLY_WINDOW:
            self.dms.set_reply_status(reply["id"], "expired")
            await query.edit_message_text(
                f"Telegram only lets me answer chats active in the last 24 hours. Copy it and send it yourself:\n\n"
                f"{reply['text']}")
            return
        try:
            sent = await self._send_as_owner(reply["chat_id"], reply["text"], connection_id)
        except (BadRequest, Forbidden, RetryAfter) as e:  # refused: nothing was sent (checked first:
            # in python-telegram-bot, BadRequest is a subclass of NetworkError)
            self.dms.set_reply_status(reply["id"], "pending")
            await query.edit_message_text(f"Telegram refused that ({e.message}). Nothing was sent; tap Send to try "
                                          f"again.\n\n{reply['text']}", reply_markup=retry)
            return
        except (TimedOut, NetworkError) as e:
            # It may have gone out anyway: no Send button, or a second tap could send it twice.
            self.dms.set_reply_status(reply["id"], "unknown")
            ActionLog(self.db).record("telegram", f"MAY have sent a Telegram reply to {reply['name']} (connection dropped)")
            log.warning("Telegram reply may or may not have been sent: %s", e)
            await query.edit_message_text(
                f"⚠️ The connection dropped while sending to {defang_urls(reply['name'])}. It may have gone out: check the chat "
                f"before sending again.\n\n{reply['text']}")
            return
        except TelegramError as e:  # anything else Telegram raised before sending
            self.dms.set_reply_status(reply["id"], "pending")
            await query.edit_message_text(f"Telegram said no ({e.message}). Tap Send to try again.\n\n{reply['text']}",
                                          reply_markup=retry)
            return
        self.dms.set_reply_status(reply["id"], "sent")
        now = datetime.now(timezone.utc)
        self.dms.record_sent(reply["chat_id"], getattr(sent, "message_id", None) or -reply["id"], reply["text"], now)
        ActionLog(self.db).record("telegram", f"Sent a Telegram reply to {reply['name']}: {reply['text']}")
        await query.edit_message_text(f"✅ Sent to {defang_urls(reply['name'])}:\n\n{reply['text']}")
        self.db.add_notice(f"Telegram reply sent to {reply['name']} (chat {reply['chat_id']}).")

    async def _send_as_owner(self, chat_id: int, text: str, business_connection_id: str):
        return await self.app.bot.send_message(chat_id=chat_id, text=text, business_connection_id=business_connection_id)
