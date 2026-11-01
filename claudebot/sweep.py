"""/sweep: one-tap inbox cleanup. Old promotions, social and update emails get archived (never
deleted: they stay in All Mail). Counted and done with plain Gmail queries, no model call."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .actions import ActionLog
from .google_services import GoogleNotConnected

log = logging.getLogger(__name__)

MAX_SWEEP = 500
KEEP = "-is:starred -is:important"  # bills and statements in Updates are often marked important
SWEEPS = {
    "promo": ("promotions", f"in:inbox category:promotions older_than:3d {KEEP}"),
    "social": ("social updates", f"in:inbox category:social older_than:3d {KEEP}"),
    "updates": ("automatic updates", f"in:inbox category:updates older_than:7d {KEEP}"),
}


class SweepHandlers:
    """Mixed into TelegramBot."""

    async def on_sweep(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        try:
            counts = {key: len(await asyncio.to_thread(self.google.message_ids, query, MAX_SWEEP))
                      for key, (_, query) in SWEEPS.items()}
        except GoogleNotConnected:
            await message.reply_text("Connect Gmail first: /connect")
            return
        except Exception:
            log.exception("Counting the inbox failed")
            await message.reply_text("I couldn't read your inbox just now. Try again in a minute.")
            return
        rows = [[InlineKeyboardButton(f"🧹 Archive {n}{'+' if n >= MAX_SWEEP else ''} {SWEEPS[k][0]}",
                                      callback_data=f"sweep:{k}")] for k, n in counts.items() if n]
        if not rows:
            await message.reply_text("✨ Your inbox is already clean: no old promotions, social or update emails.")
            return
        await message.reply_text("Inbox cleanup. Archiving keeps everything in All Mail; nothing is deleted.",
                                 reply_markup=InlineKeyboardMarkup(rows))

    async def on_sweep_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        label, gmail_query = SWEEPS[query.data.split(":")[1]]
        await query.answer("🧹 Archiving...")
        try:
            ids = await asyncio.to_thread(self.google.message_ids, gmail_query, MAX_SWEEP)
            await asyncio.to_thread(self.google.archive_many, ids)
        except Exception:
            log.exception("Sweeping %s failed", label)
            await self.send_to_owner(f"Archiving {label} failed. Nothing was deleted; try again in a minute.")
            return
        ActionLog(self.db).record("email", f"Archived {len(ids)} {label} (/sweep)")
        await self.send_to_owner(f"🧹 Archived {len(ids)} {label}. They're still in All Mail if you need one.")
