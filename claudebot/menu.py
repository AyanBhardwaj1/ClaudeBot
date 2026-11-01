"""/menu: a keyboard of everyday buttons under the chat box. Tapping one sends its label, which is
matched here exactly (a forward or any other text never is)."""

from types import SimpleNamespace

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

BUTTONS = {
    "📆 Today": ("on_today", []),
    "📰 Catch up": ("on_catchup", []),
    "📥 Triage": ("on_triage", []),
    "⏳ Waiting": ("on_waiting", []),
    "🗒 Lists": ("on_lists", []),
    "🔕 Quiet 1h": ("on_quiet", ["1h"]),
}
KEYBOARD = ReplyKeyboardMarkup([[KeyboardButton(label) for label in list(BUTTONS)[i : i + 3]] for i in (0, 3)],
                               resize_keyboard=True, is_persistent=True)


class MenuHandlers:
    """Mixed into TelegramBot."""

    async def on_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if context.args and context.args[0].lower() == "off":
            await update.effective_message.reply_text("Menu hidden. /menu brings it back.", reply_markup=ReplyKeyboardRemove())
            return
        await update.effective_message.reply_text("Here's your menu. /menu off hides it.", reply_markup=KEYBOARD)

    async def handle_menu_button(self, update: Update) -> bool:
        """True if the message was a menu button (then it has been handled)."""
        message = update.effective_message
        if message.forward_origin or message.text not in BUTTONS:
            return False
        handler, args = BUTTONS[message.text]
        await getattr(self, handler)(update, SimpleNamespace(args=list(args)))
        return True
