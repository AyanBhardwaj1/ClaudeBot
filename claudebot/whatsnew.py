"""One short "what's new" message the first time a new version starts (not on fresh installs)."""

from . import __version__

SEEN_KEY = "seen_version"
NOTES = (
    "✨ What's new in ClaudeBot 1.2\n"
    "- /dms: your Telegram DMs, with replies sent from your account when you tap\n"
    "- /triage: unread email one card at a time, with 💤 snooze\n"
    "- Meeting prep, a Sunday review, and a 📅 Times button for meeting requests\n"
    "- /style: drafts that sound like you\n"
    "- /log: what I actually did; Remove cards for calendar events\n"
    "- /lists, /spent, /owed, /habit, /journal, /note\n"
    "- /today, /catchup, /quiet, /focus, /rules, /sweep, /privacy, /export\n"
    "/help has everything."
)


def notes_to_show(db, onboarded: bool) -> str | None:
    """The notes if this owner hasn't seen this version yet; records that they now have."""
    seen = db.get_setting(SEEN_KEY)
    db.set_setting(SEEN_KEY, __version__)
    if not onboarded or seen == __version__:
        return None
    return NOTES
