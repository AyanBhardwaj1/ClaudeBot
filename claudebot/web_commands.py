"""/web in Telegram: a one-time sign-in link for the web app and the desktop app."""

from telegram import Update
from telegram.ext import ContextTypes

from .actions import ActionLog


class WebHandlers:
    """Mixed into TelegramBot."""

    async def on_web(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from .web import auth, login_url

        message = update.effective_message
        if self.config.web_port is None:
            await message.reply_text("The web app is off. Set WEB_PORT=8765 (or any port) and restart to turn it on.")
            return
        if (context.args or [""])[0].lower() in ("signout", "logout", "off"):
            ended = auth.end_all_sessions(self.db)
            ActionLog(self.db).record("security", f"Signed out of the web app everywhere ({ended} sessions)")
            await message.reply_text(f"🔒 Signed out everywhere ({ended} session{'s' if ended != 1 else ''}).")
            return
        if getattr(self, "web", None) is None:
            await message.reply_text("The web app didn't start (is the port in use?). Check the server log.")
            return
        link = login_url(self.config, auth.new_login_token(self.db))
        where = ("" if self.config.web_public_url else
                 "\n\nThis address works on the computer running ClaudeBot. To use it from your phone or "
                 "another computer, put it behind HTTPS and set WEB_PUBLIC_URL.")
        await message.reply_text(
            f"🌐 Your sign-in link for the web and desktop app. It works once, for 10 minutes. "
            f"Don't forward it: whoever opens it is signed in as you.\n\n{link}{where}\n\n"
            "Sign out everywhere: /web signout")
