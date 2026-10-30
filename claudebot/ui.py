"""Telegram presentation helpers: live reply previews, follow-up buttons, the memory view."""

import json
import logging
import secrets
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from .db import Database
from .modes import defang_urls, fence_external

log = logging.getLogger(__name__)

PREVIEW_INTERVAL = 0.9  # seconds between draft updates (Telegram rate-limits edits)
PREVIEW_KEEPALIVE = 20  # drafts vanish after ~30s without an update
PREVIEW_MAX_CHARS = 4000
MEMORY_BUTTONS = 30
REPLY_QUOTE_CHARS = 1_500


class LivePreview:
    """Streams a reply into the chat as a Telegram draft while Claude writes it.

    The draft shows "Thinking..." until the first words arrive, then the text so far. The final
    message (with sources and buttons) is sent normally and replaces it. Any Telegram error just
    turns the preview off: it's a nicety, never a reason to fail a reply.
    """

    def __init__(self, bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.draft_id = secrets.randbelow(2**31 - 1) + 1  # must be non-zero
        self.text = ""
        self._sent_at = 0.0
        self._enabled = True

    async def _push(self) -> None:
        if not self._enabled:
            return
        try:
            await self.bot.send_message_draft(self.chat_id, self.draft_id, text=self.text[:PREVIEW_MAX_CHARS])
            self._sent_at = time.monotonic()
        except TelegramError:
            log.debug("Live preview unavailable; falling back to the final message only", exc_info=True)
            self._enabled = False

    async def start(self) -> None:
        await self._push()  # empty text: Telegram shows a "Thinking..." placeholder

    async def update(self, text: str) -> None:
        self.text = text
        if time.monotonic() - self._sent_at >= PREVIEW_INTERVAL:
            await self._push()

    async def keepalive(self) -> None:
        if time.monotonic() - self._sent_at >= PREVIEW_KEEPALIVE:
            await self._push()


def followup_keyboard(db: Database, suggestions: list[str]) -> InlineKeyboardMarkup:
    """Buttons for suggestions; their text is stored server-side (callback data is capped at 64 bytes)."""
    key = secrets.token_hex(4)
    db.set_setting(f"followups:{key}", json.dumps(suggestions))
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=f"fu:{key}:{i}")] for i, text in enumerate(suggestions)]
    )


def take_followup(db: Database, key: str, index: int) -> str | None:
    raw = db.get_setting(f"followups:{key}")
    if raw is None:
        return None
    suggestions = json.loads(raw)
    return suggestions[index] if 0 <= index < len(suggestions) else None


def memory_view(memories) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """The /memory message: what ClaudeBot remembers, with a delete button per fact."""
    if not memories:
        return ("Nothing saved yet. Tell me things worth remembering, like \"my mom's email is ...\" "
                "or \"I'm vegetarian\", and I'll keep them across conversations.", [])
    lines = [f"{i}. {m['text']}" for i, m in enumerate(memories, start=1)]
    buttons = [
        [InlineKeyboardButton(f"✖️ {i}. {m['text'][:40]}", callback_data=f"mem:del:{m['id']}")]
        for i, m in enumerate(memories[:MEMORY_BUTTONS], start=1)
    ]
    return "🧠 What I remember about you:\n" + "\n".join(lines) + "\n\nTap one to forget it.", buttons


def reply_context(quoted: str, from_bot: bool, forwarded_from: str | None = None) -> str:
    """Context for a swipe-reply. The bot's own earlier text keeps its links unfetchable, and a
    message someone else wrote (a forward) stays fenced as theirs."""
    text = " ".join(quoted.split())[:REPLY_QUOTE_CHARS]
    if forwarded_from:
        return "[Replying to this forwarded message:]\n" + fence_external("forwarded_message", forwarded_from, text)
    if from_bot:
        # The bot's own words may quote email or web text (an inbox alert, a summary): fenced as data.
        return "[Replying to your earlier message:]\n" + fence_external("quoted_message", "ClaudeBot", defang_urls(text))
    return f'[Replying to my earlier message: "{text}"]'
