"""/style: learn the owner's writing style, show it, and use it only once they approve.
Mixed into TelegramBot."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .google_services import GoogleNotConnected
from .style import (
    PENDING_KEY,
    STYLE_KEY,
    StyleUnavailable,
    clean_style,
    current_style,
    learn_style,
)

log = logging.getLogger(__name__)


class StyleHandlers:
    async def on_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        text = " ".join(context.args or [])
        if text.lower() in ("off", "clear", "none"):
            self.db.delete_setting(STYLE_KEY)
            await message.reply_text("Writing style cleared. I'll draft in a neutral, friendly voice.")
            return
        if text and not clean_style(text):
            await message.reply_text("Describe it in words, e.g. /style short, warm, sign off -A")
            return
        if text:  # the owner's own description of how they write
            self.db.set_setting(STYLE_KEY, clean_style(text))
            await message.reply_text(f"✍️ Got it. I'll write like this:\n\n{current_style(self.db)}")
            return
        style = current_style(self.db)
        intro = (f"✍️ Your writing style:\n\n{style}\n\nRelearn it from your sent email, or describe it: "
                 "/style short, warm, sign off -A" if style else
                 "I can learn how you write from your recent sent emails, so drafts sound like you. "
                 "You'll see what I learned before I use it. Or describe it yourself: /style short, warm, sign off -A")
        await message.reply_text(intro, reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📝 Learn from my sent email", callback_data="style:learn")]]))

    async def on_style_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        action = query.data.split(":")[1]
        version = query.data.split(":")[2] if query.data.count(":") >= 2 else ""
        try:
            await query.edit_message_reply_markup(None)
        except TelegramError:
            pass
        if action == "learn":
            await self._learn_style()
        elif action == "use":
            pending = self.db.get_setting(PENDING_KEY)
            if pending and version != self.db.get_setting(PENDING_KEY + "_version"):
                await self.send_to_owner("That's an older suggestion. Use the newest one, or tap Learn again.")
                return
            if pending:
                self.db.set_setting(STYLE_KEY, pending)
                self.db.delete_setting(PENDING_KEY)
                await self.send_to_owner("✅ I'll write in your style from now on. /style to see or change it.")
        else:
            self.db.delete_setting(PENDING_KEY)
            await self.send_to_owner("Discarded. Describe it yourself any time: /style short, warm, sign off -A")

    async def _learn_style(self) -> None:
        await self.send_to_owner("Reading your recent sent emails (just the parts you wrote)...")
        try:
            style = await learn_style(self.google, self.client, self.tracker, self.config)
        except StyleUnavailable:
            await self.send_to_owner("I can't reach Claude right now (or the monthly budget is used up). Try later.")
            return
        except GoogleNotConnected:
            await self.send_to_owner("Connect Gmail first: /connect")
            return
        except Exception:
            log.exception("Learning the writing style failed")
            await self.send_to_owner("That didn't work this time. Try again in a minute.")
            return
        if style is None:
            await self.send_to_owner("I couldn't find enough sent email to learn from. Describe your style instead: "
                                     "/style short, warm, sign off -A")
            return
        self.db.set_setting(PENDING_KEY, style)
        version = str(int(self.db.get_setting(PENDING_KEY + "_version") or 0) + 1)
        self.db.set_setting(PENDING_KEY + "_version", version)  # an older card can't approve a newer guide
        buttons = [InlineKeyboardButton("✅ Use this", callback_data=f"style:use:{version}"),
                   InlineKeyboardButton("✖️ Discard", callback_data="style:discard")]
        await self.send_to_owner(f"Here's how you write, as far as I can tell:\n\n{style}",
                                 InlineKeyboardMarkup([buttons]))
