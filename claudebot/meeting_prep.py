"""Meeting prep: about an hour before a meeting with other people, a short brief on who's coming,
your recent email with them, and anything you should know or bring.

Code picks the meetings (timed, accepted, with other attendees, starting 30-75 minutes from now);
the agent writes the brief from tools, given only the event id, never the invite's text. Each
meeting is prepped once, at most a few a day, and it can be turned off in /settings.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from telegram.ext import ContextTypes

from .inbox_watch import in_quiet_hours
from .quiet import dnd_active
from .scheduling import _parse

log = logging.getLogger(__name__)

PREP_KEY = "prep:"
SWITCH_KEY = "meeting_prep"  # "off" turns it off
COUNT_PREFIX = "prep_count:"
EARLIEST = timedelta(minutes=30)
LATEST = timedelta(minutes=75)
JOB_MINUTES = 15
MAX_PER_DAY = 4
PREP_PROMPT = (
    "Prepare me for my meeting with calendar event id {event_id}, which starts in about {minutes} minutes. "
    "Look it up with list_calendar_events, then search my email for recent threads with the other "
    "attendees, and check what you remember about them. Give me a short brief: who they are to me, "
    "where we left things, open questions or promises, and anything to bring or read. Five lines or so. "
    "If there's nothing useful to say, just say the meeting is coming up."
)


def meetings_to_prep(events: list[dict], now: datetime, tz) -> list[dict]:
    """Timed meetings with other people that start 30-75 minutes from now, soonest first."""
    picked = []
    for e in events:
        if len(e["start"]) == 10 or e.get("declined") or not e.get("attendees"):
            continue
        start, _ = _parse(e["start"], tz)
        if now + EARLIEST <= start <= now + LATEST:
            picked.append((start, e))
    return [e for _, e in sorted(picked, key=lambda p: p[0])]


class MeetingPrepHandlers:
    """Mixed into TelegramBot."""

    async def _meeting_prep_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        count_key = f"{COUNT_PREFIX}{now.date().isoformat()}"
        if (self.db.get_setting(SWITCH_KEY) == "off" or not self.google.is_connected()
                or in_quiet_hours(now, self.config.quiet_hours) or dnd_active(self.db, now)):
            return
        try:
            events = await asyncio.to_thread(
                self.google.list_events, (now + EARLIEST).isoformat(), (now + LATEST + timedelta(hours=1)).isoformat(), 50)
        except Exception:
            log.exception("Couldn't check the calendar for meeting prep")
            return
        for e in meetings_to_prep(events, now, self.config.timezone):
            if int(self.db.get_setting(count_key) or 0) >= MAX_PER_DAY:
                return
            if self.db.get_setting(PREP_KEY + e["id"]):
                continue
            self.db.set_setting(PREP_KEY + e["id"], now.isoformat())  # once, even if the brief fails
            self.db.set_setting(count_key, str(int(self.db.get_setting(count_key) or 0) + 1))
            start, _ = _parse(e["start"], self.config.timezone)
            minutes = max(int((start - now).total_seconds() // 60), 0)
            # Only the id: the invite's title and description are someone else's text, read via tools.
            prompt = PREP_PROMPT.format(event_id=e["id"], minutes=minutes)
            reply = await self._ask_agent([{"type": "text", "text": prompt}], owner_present=False, effort="low")
            await self.send_to_owner(reply)
        self.db.prune_settings(PREP_KEY, 200)
        self.db.prune_settings(COUNT_PREFIX, 7)
