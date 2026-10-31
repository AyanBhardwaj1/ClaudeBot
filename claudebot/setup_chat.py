"""Setup inside the chat: first-run onboarding, /settings, /connect (Google), /status and /help.
Mixed into TelegramBot, whose state they use.

When ClaudeBot asks a question ("What should I call you?"), the next plain text message answers
it instead of going to Claude. The question expires after a while, and forwards never answer it.
"""

import asyncio
import json
import logging
import time
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import __version__
from .google_connect import (
    ConnectError,
    client_file,
    finish,
    is_sign_in_reply,
    save_client,
    start,
)
from .modes import MODES, current_mode
from .roles import ROLES, current_profile, pick_role, set_role
from .settings import FIELDS, ONBOARDED_KEY, InvalidSetting, resolve_place, save

log = logging.getLogger(__name__)

AWAIT_KEY = "await"
AWAIT_SECONDS = 15 * 60
ONBOARDING_OFFERED_KEY = "onboarding_offered"
ONBOARDING = ("name", "place", "role", "brief", "google")

WELCOME = (
    "Just talk to me normally. Try:\n"
    "- what's in my inbox?\n"
    "- reply to Sam saying Thursday works\n"
    "- what's on my calendar tomorrow?\n"
    "- remind me at 6pm to call mom\n"
    "- every Friday at 5pm, brief me on AI news\n"
    "- (send a PDF or photo) what's due in this?\n"
    "- (forward any message) is this true?\n\n"
    "I'll ping you when important email arrives. /help lists everything I can do."
)

HELP = (
    "Talk to me like a person: ask, tell me to do things, send files, photos or voice notes.\n\n"
    "Everyday\n"
    "/brief – your daily brief now\n"
    "/briefings – scheduled news briefings\n"
    "/memory – what I remember (tap to forget)\n"
    "/new – start a fresh conversation\n\n"
    "Harder questions\n"
    "/think – think as hard as possible about one question\n"
    "/research – deep research with sources\n\n"
    "Make it yours\n"
    "/settings – name, location, brief time, alerts, budget\n"
    "/role – your job, so I tailor everything to it\n"
    "/mode – personality (fun, brief, deep)\n"
    "/connect – connect Gmail and Calendar\n"
    "/followups – suggestion buttons on or off\n\n"
    "Check on me\n"
    "/status – what's connected and working\n"
    "/usage – what I've cost you\n\n"
    "Groups: add me to a group and send /enable there; people can tag me to ask or fact-check."
)

CLIENT_STEPS = (
    "To connect Gmail and Calendar I need a Google OAuth client (free, about 5 minutes, once):\n\n"
    "1. Open console.cloud.google.com and create a project.\n"
    "2. APIs & Services → Library: enable Gmail API and Google Calendar API.\n"
    "3. OAuth consent screen: External, add your email as a test user, then Publish app.\n"
    "4. Credentials → Create credentials → OAuth client ID → Desktop app → Download JSON.\n\n"
    "Then send that JSON file here."
)

SIGN_IN_STEPS = (
    "1. Tap Sign in with Google and allow access to Gmail and Calendar. (Google warns the app "
    "isn't verified: it's your own app, so tap Advanced → Go to it.)\n"
    "2. You'll land on a page that won't load (localhost). That's expected.\n"
    "3. Copy that page's whole address and paste it here.\n\n"
    "The link works for 15 minutes."
)

BRIEF_CHOICES = (("☀️ 7:00", "0700"), ("☀️ 8:00", "0800"), ("☀️ 9:00", "0900"), ("No brief", "off"))
QUIET_CHOICES = (("23:00–07:00", "2300-0700"), ("22:00–08:00", "2200-0800"), ("Off", "off"))
UNDO_CHOICES = (("Instant", "0"), ("10s", "10"), ("20s", "20"), ("60s", "60"))
BUDGET_CHOICES = (("$10", "10"), ("$20", "20"), ("$50", "50"), ("No cap", "off"))
CHOICES = {"brief": ("daily_brief_time", BRIEF_CHOICES), "quiet": ("quiet_hours", QUIET_CHOICES),
           "undo": ("undo_send_seconds", UNDO_CHOICES), "budget": ("monthly_budget_usd", BUDGET_CHOICES)}
PROMPTS = {
    "owner_name": "What should I call you?",
    "place": "Where do you live? A city is enough (e.g. Austin, or London).",
    "daily_brief_time": "When should your daily brief arrive? Tap one or type a time like 7:30.",
    "quiet_hours": "When should I hold inbox alerts? Tap one or type a range like 23:00-07:00.",
    "undo_send_seconds": "How long should you have to tap Undo before an email goes out?",
    "monthly_budget_usd": "Stop using Claude once this month's spend reaches... (type an amount or tap one)",
    "role": "What do you do? Pick one or describe it (e.g. nurse in the ER, product manager).",
}


def _decode_choice(value: str) -> str:
    """Callback values: "0730" -> "07:30", "2300-0700" -> "23:00-07:00"."""
    return "-".join(f"{p[:2]}:{p[2:]}" if len(p) == 4 and p.isdigit() else p for p in value.split("-"))


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in row]
                                 for row in rows])


def _choices(prefix: str, choices) -> list[list[tuple[str, str]]]:
    return [[(label, f"{prefix}:{value}") for label, value in choices]]


class SetupHandlers:
    # --- pending questions ---

    def _expect(self, what: str) -> None:
        self.db.set_setting(AWAIT_KEY, json.dumps({"what": what, "at": time.time()}))

    def _awaiting(self) -> str | None:
        raw = self.db.get_setting(AWAIT_KEY)
        if not raw:
            return None
        pending = json.loads(raw)
        if time.time() - pending["at"] > AWAIT_SECONDS:
            self.db.delete_setting(AWAIT_KEY)
            return None
        return pending["what"]

    def _stop_expecting(self) -> None:
        self.db.delete_setting(AWAIT_KEY)

    async def handle_answer(self, message: Message) -> bool:
        """If this text answers a question ClaudeBot asked (or is a Google sign-in address),
        handle it and return True. Otherwise it's a normal message for Claude."""
        text = message.text or ""
        what = self._awaiting()
        # Never let a sign-in code reach Claude or the history.
        if is_sign_in_reply(self.db, text, expecting_code=what == "google:code"):
            await self._finish_connect(message, text)
            return True
        if what is None or what == "google:code" or what == "google:client":
            return False
        self._stop_expecting()
        try:
            if what == "ob:name":
                save(self.db, "owner_name", text)
            elif what in ("ob:place", "set:place"):
                if not await self._save_place(text):
                    self._expect(what)
                    await self.send_to_owner("I couldn't place that. Try a city name, or tap Skip.",
                                             _keyboard([[("Skip", "ob:skip" if what == "ob:place" else "set:cancel")]]))
                    return True
            elif what in ("ob:role", "set:role"):
                profile = set_role(self.db, text)
                if profile is None:
                    self._expect(what)
                    await self.send_to_owner("Tell me your job in a few words, or tap Skip.")
                    return True
                if what == "set:role":
                    await self._role_set(profile)
                    return True
            elif what == "ob:brief":
                save(self.db, "daily_brief_time", text)
            elif what.startswith("set:") and what[4:] in FIELDS:
                stored = save(self.db, what[4:], text)
                await self._applied(what[4:], stored)
                return True
            else:
                return False
        except InvalidSetting as e:
            self._expect(what)
            await self.send_to_owner(str(e))
            return True
        if what.startswith("ob:"):
            await self._onboard_next(what[3:])
        else:
            await self._applied("place", "")
        return True

    async def _save_place(self, text: str) -> bool:
        place = await resolve_place(self.client, self.tracker, self.config, text)
        if place is None:
            return False
        for field in ("city", "region", "country", "timezone"):
            save(self.db, field, place[field])
        where = ", ".join(p for p in (place["city"], place["region"], place["country"]) if p)
        await self.send_to_owner(f"📍 {where} ({place['timezone']})")
        return True

    # --- first-run onboarding ---

    def onboarded(self) -> bool:
        return self.db.get_setting(ONBOARDED_KEY) is not None

    async def begin_onboarding(self) -> None:
        await self.send_to_owner(
            "👋 Hi! I'm ClaudeBot, your personal assistant, powered by Claude.\n\n"
            "I can handle your email and calendar, remember things, remind you, search the web, "
            "read your files and brief you every morning. Four quick questions to set me up "
            "(skip any of them)."
        )
        await self._ask("name")

    async def _ask(self, step: str) -> None:
        skip = ("Skip", "ob:skip")
        if step == "name":
            self._expect("ob:name")
            await self.send_to_owner("1/4 · What should I call you?", _keyboard([[("Use my Telegram name", "ob:tgname"), skip]]))
        elif step == "place":
            self._expect("ob:place")
            await self.send_to_owner(
                "2/4 · Where do you live? A city is enough. I use it for your time zone, local "
                "searches and the weather in your brief.", _keyboard([[skip]]))
        elif step == "role":
            self._expect("ob:role")
            buttons = [(role.label, f"ob:role:{key}") for key, role in ROLES.items()]
            rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)] + [[skip]]
            await self.send_to_owner(
                "3/4 · What do you do? I'll tailor inbox alerts, your brief and my answers to it. "
                "Pick one or describe it (e.g. nurse in the ER).", _keyboard(rows))
        elif step == "brief":
            self._expect("ob:brief")
            await self.send_to_owner(
                "4/4 · When should I send your daily brief (calendar, inbox, reminders, news)? "
                "Tap one or type a time.", _keyboard(_choices("ob:brief", BRIEF_CHOICES)))
        elif step == "google":
            await self._finish_onboarding()

    async def _onboard_next(self, done_step: str) -> None:
        index = ONBOARDING.index(done_step)
        await self._ask(ONBOARDING[index + 1])

    async def _finish_onboarding(self) -> None:
        """Save, offer Google, and restart so the answers apply everywhere. The Google buttons
        keep working after the restart: they don't depend on a pending question."""
        self._stop_expecting()
        self.db.set_setting(ONBOARDED_KEY, datetime.now().isoformat())
        name = self.db.get_setting("cfg:owner_name") or self.config.owner_name
        await self.send_to_owner(f"✅ All set, {name}.\n\n{WELCOME}")
        if not self.google.is_connected():
            await self.send_to_owner(
                "Last thing: connect Gmail and Google Calendar so I can handle your email and "
                "schedule? You can do it any time with /connect.",
                _keyboard([[("🔗 Connect now", "ob:google:now"), ("Later", "ob:google:later")]]))
        self.request_restart()  # apply name, time zone and brief time everywhere

    async def on_onboard_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        parts = query.data.split(":")
        what = self._awaiting()
        step = what[3:] if what and what.startswith("ob:") else None
        try:
            await query.edit_message_reply_markup(None)
        except TelegramError:
            pass
        if parts[1] == "google":
            if parts[2] == "now":
                await self._connect_start()
            else:
                await self.send_to_owner("OK. Send /connect whenever you're ready.")
            return
        if step is None:
            return  # an old question's button
        if parts[1] == "skip":
            self._stop_expecting()
        elif parts[1] == "tgname" and step == "name":
            save(self.db, "owner_name", query.from_user.first_name or "friend")
        elif parts[1] == "role" and step == "role" and parts[2] in ROLES:
            pick_role(self.db, parts[2])
        elif parts[1] == "brief" and step == "brief":
            save(self.db, "daily_brief_time", _decode_choice(parts[2]))
        else:
            return
        self._stop_expecting()
        await self._onboard_next(step)

    # --- /settings ---

    def settings_text(self) -> str:
        c = self.config
        where = ", ".join(p for p in (c.city, c.region, c.country) if p) or "not set"
        profile = current_profile(self.db)
        budget = f"${c.monthly_budget_usd:g}/month" if c.monthly_budget_usd is not None else "no cap"
        alerts = f"on (quiet {c.quiet_hours})" if c.inbox_alerts and c.quiet_hours else ("on" if c.inbox_alerts else "off")
        return (
            "⚙️ Settings\n\n"
            f"👤 Name: {c.owner_name}\n"
            f"📍 Location: {where} · {c.timezone.key}\n"
            f"💼 Job: {profile.describe() if profile else 'not set'}\n"
            f"🎭 Mode: {MODES[current_mode(self.db)][0]}\n"
            f"☀️ Daily brief: {c.daily_brief_time or 'off'}\n"
            f"📬 Inbox alerts: {alerts}\n"
            f"↩️ Undo window: {c.undo_send_seconds}s\n"
            f"💰 Budget: {budget}\n"
            f"💬 Suggestions: {'on' if self._followups_on() else 'off'}\n"
            f"🔗 Google: {'connected' if self.google.is_connected() else 'not connected'}\n\n"
            "Tap to change:"
        )

    def settings_keyboard(self) -> InlineKeyboardMarkup:
        return _keyboard([
            [("👤 Name", "set:name"), ("📍 Location", "set:place"), ("💼 Job", "set:role")],
            [("🎭 Mode", "set:mode"), ("☀️ Brief", "set:brief"), ("🌙 Quiet hours", "set:quiet")],
            [("📬 Alerts on/off", "set:alerts"), ("↩️ Undo", "set:undo"), ("💰 Budget", "set:budget")],
            [("💬 Suggestions on/off", "set:followups"), ("🔗 Google", "set:google")],
        ])

    async def on_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._stop_expecting()
        await update.effective_message.reply_text(self.settings_text(), reply_markup=self.settings_keyboard())

    async def on_settings_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        kind, key, *rest = query.data.split(":", 2)
        if kind == "setv":
            if key not in CHOICES or not rest:
                return
            field = CHOICES[key][0]
            try:
                stored = save(self.db, field, _decode_choice(rest[0]))
            except InvalidSetting:
                return
            self._stop_expecting()
            await self._applied(field, stored)
            return
        if key == "cancel":
            self._stop_expecting()
            await self.send_to_owner("OK, unchanged.")
        elif key == "name":
            self._expect("set:owner_name")
            await self.send_to_owner(PROMPTS["owner_name"])
        elif key == "place":
            self._expect("set:place")
            await self.send_to_owner(PROMPTS["place"])
        elif key == "role":
            self._expect("set:role")
            from .roles import role_keyboard

            await self.send_to_owner(PROMPTS["role"], role_keyboard())
        elif key == "mode":
            buttons = [(label, f"mode:{name}") for name, (label, _) in MODES.items()]
            await self.send_to_owner("Pick a personality:", _keyboard([buttons[:2], buttons[2:]]))
        elif key in CHOICES:
            field, choices = CHOICES[key]
            self._expect(f"set:{field}")
            await self.send_to_owner(PROMPTS[field], _keyboard(_choices(f"setv:{key}", choices)))
        elif key == "alerts":
            stored = save(self.db, "inbox_alerts", "off" if self.config.inbox_alerts else "on")
            await self._applied("inbox_alerts", stored)
        elif key == "followups":
            self.db.set_setting("followups", "off" if self._followups_on() else "on")
            await self.send_to_owner(f"Suggestions {'on' if self._followups_on() else 'off'}.")
        elif key == "google":
            await self._connect_start()

    async def _applied(self, field: str, stored: str) -> None:
        """Confirm a saved setting, then restart so every part of the bot uses it."""
        if field == "place":
            label, shown = "Location", "saved"
        else:
            label = FIELDS[field].label
            shown = {"true": "on", "false": "off", "": "off"}.get(stored, stored)
            if field == "undo_send_seconds":
                shown += "s"
            elif field == "monthly_budget_usd" and stored:
                shown = f"${stored}"
        await self.send_to_owner(f"✅ {label}: {shown}")
        self.request_restart()

    # --- Google ---

    async def on_connect(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._connect_start()

    async def _connect_start(self) -> None:
        if self.config.google_token_json:
            await self.send_to_owner(
                "Google is set through GOOGLE_TOKEN_JSON in your server settings. Remove it there "
                "to connect a different account here.")
            return
        if client_file(self.config) is None:
            self._expect("google:client")
            await self.send_to_owner(CLIENT_STEPS)
            return
        try:
            url = await asyncio.to_thread(start, self.config, self.db)
        except Exception:
            log.exception("Couldn't start Google sign-in")
            self._expect("google:client")
            await self.send_to_owner("That Google client file doesn't work. " + CLIENT_STEPS)
            return
        self._expect("google:code")
        await self.send_to_owner(
            SIGN_IN_STEPS,
            InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Sign in with Google", url=url)]]),
        )

    async def handle_client_file(self, message: Message) -> bool:
        """A Google OAuth client JSON sent in chat: saved for /connect, never shown to Claude."""
        document = message.document
        name = (document.file_name or "").lower()
        # Only right after /connect asked for it, and never a forward: a file someone sent the
        # owner must not be able to replace how sign-in works.
        if message.forward_origin or not name.endswith(".json") or self._awaiting() != "google:client":
            return False
        data = bytes(await (await document.get_file()).download_as_bytearray())
        await self._delete(message)  # it holds the client secret
        try:
            save_client(self.config, data)
        except ConnectError as e:
            await self.send_to_owner(str(e))
            return True
        await self.send_to_owner("Got the Google client file. Now sign in:")
        await self._connect_start()
        return True

    async def handle_sign_in_caption(self, message: Message) -> bool:
        """A sign-in address pasted as a photo or file caption: handled here, not sent to Claude."""
        caption = message.caption or ""
        if message.forward_origin or not caption or not is_sign_in_reply(self.db, caption):
            return False
        await self._finish_connect(message, caption)
        return True

    async def _finish_connect(self, message: Message, text: str) -> None:
        await self._delete(message)  # the address holds a one-time code
        try:
            await asyncio.to_thread(finish, self.config, self.db, text)
        except ConnectError as e:
            await self.send_to_owner(str(e))
            return
        self._stop_expecting()
        self.google.reset()
        try:
            email = await asyncio.to_thread(self.google.account_email)
        except Exception:
            log.warning("Connected, but couldn't read the Gmail profile", exc_info=True)
            email = "your Google account"
        await self.send_to_owner(
            f"✅ Connected to {email}. Try: what's in my inbox? or what's on my calendar this week?")

    async def _delete(self, message: Message) -> None:
        try:
            await message.delete()
        except TelegramError:
            log.info("Couldn't delete a message with a secret in it; delete it yourself.")

    # --- /status and /help ---

    async def on_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        c = self.config
        if c.google_token_json or self.google.is_connected():
            try:
                email = await asyncio.to_thread(self.google.account_email)
                google = f"✅ Google: {email}"
            except Exception as e:
                google = f"⚠️ Google: connected but not working ({type(e).__name__}). /connect to fix"
        else:
            google = "⚪ Google: not connected. /connect"
        uptime = datetime.now() - self.started_at
        hours, rem = divmod(int(uptime.total_seconds()), 3600)
        brief = f"☀️ Daily brief: {c.daily_brief_time} ({c.timezone.key})" if c.daily_brief_time else "☀️ Daily brief: off"
        alerts = f"📬 Inbox alerts: every {c.inbox_check_minutes} min" if c.inbox_alerts else "📬 Inbox alerts: off"
        await update.effective_message.reply_text(
            f"🟢 ClaudeBot {__version__}, up {hours}h {rem // 60}m\n"
            f"🧠 Claude: {c.model} (effort {c.effort})\n"
            f"{google}\n{alerts}\n{brief}\n"
            f"⏰ Reminders and briefings: {len(self.db.active_reminders())} active\n\n"
            f"{self.tracker.summary()}"
        )

    async def on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(HELP)
