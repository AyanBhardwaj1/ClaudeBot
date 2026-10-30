"""Inline-button handlers for the owner's chat: the memory list, follow-up suggestions, and the
Archive / Reply / Later buttons on inbox alerts. Mixed into TelegramBot, whose state they use.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .ui import memory_view, take_followup

log = logging.getLogger(__name__)


class ButtonHandlers:
    def _from_owner(self, query) -> bool:
        return bool(query.from_user and query.from_user.id == self.config.owner_id)

    async def on_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text, buttons = memory_view(self.db.list_memories())
        await update.effective_message.reply_text(
            text[:4000], reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )

    async def on_memory_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        self.db.delete_memory(int(query.data.split(":")[2]))
        await query.answer("Forgotten.")
        text, buttons = memory_view(self.db.list_memories())
        try:
            await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
        except TelegramError:
            log.debug("Couldn't refresh the memory list", exc_info=True)

    async def on_followups_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        choice = (context.args or [""])[0].lower()
        if choice in ("on", "off"):
            self.db.set_setting("followups", choice)
        state = "on" if self._followups_on() else "off"
        await update.effective_message.reply_text(
            f"Follow-up suggestions are {state}. /followups on or /followups off to change."
        )

    async def on_followup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        _, key, index = query.data.split(":")
        text = take_followup(self.db, key, int(index))
        if text is None:
            return
        try:
            await query.edit_message_reply_markup(None)  # one tap per set
        except TelegramError:
            pass
        async with self._message_order:
            await self.send_to_owner(f"💬 {text}")
            await self._converse([{"type": "text", "text": text}], text)

    async def on_mail_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        _, action, message_id = query.data.split(":")
        if action == "arch":
            try:
                await asyncio.to_thread(self.google.modify_email, message_id, "archive")
                await query.answer("🗄 Archived")
            except Exception:
                log.exception("Archiving %s failed", message_id)
                await query.answer("Couldn't archive that one.")
        elif action == "later":
            info = json.loads(self.db.get_setting(f"alert:{message_id}") or "{}")
            when = datetime.now(self.config.timezone) + timedelta(hours=3)
            text = f"Follow up on the email from {info.get('from', 'someone')}: {info.get('subject', '')}".strip()
            self.schedule_reminder(self.db.add_reminder(text, when, "none", False))
            await query.answer(f"⏰ I'll remind you at {when:%H:%M}")
        else:  # draft
            await query.answer("✍️ Drafting...")
            # Only the id goes in: the email's own words reach Claude via read_email, as data.
            prompt = (f"Draft a reply to the email with message id {message_id}. Read it first. Show me "
                      "the draft here, and don't send or save it until I say so.")
            async with self._message_order:
                await self._converse([{"type": "text", "text": prompt}], "Draft a reply to that email")
