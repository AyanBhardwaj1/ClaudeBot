"""One short "what's new" message the first time a new version starts (not on fresh installs)."""

from . import __version__

SEEN_KEY = "seen_version"
NOTES = (
    "✨ What's new in ClaudeBot 1.3\n"
    "- 🌐 A web app and a desktop app (macOS, Windows, Linux): send /web for your sign-in link\n"
    "- /week: the next 7 days at a glance\n"
    "- /bills with ✅ Paid, /birthdays with a heads-up the day before\n"
    "- ⚡ Quick replies and ⏰ 3h reminders in /dms\n"
    "- Optional: urgent email can wake you in quiet hours (/settings)\n"
    "/help has everything."
)


def notes_to_show(db, onboarded: bool) -> str | None:
    """The notes if this owner hasn't seen this version yet; records that they now have."""
    seen = db.get_setting(SEEN_KEY)
    db.set_setting(SEEN_KEY, __version__)
    if not onboarded or seen == __version__:
        return None
    return NOTES
