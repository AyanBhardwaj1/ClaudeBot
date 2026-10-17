"""Date arithmetic for repeating reminders."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def next_occurrence(due: datetime, repeat: str, now: datetime, tz: ZoneInfo) -> datetime | None:
    """The first run of a repeating reminder strictly after `now`, keeping its local wall-clock time.

    Returns None for one-off reminders.
    """
    if repeat == "none":
        return None
    local = due.astimezone(tz)  # aware arithmetic in the local zone keeps the wall time across DST
    step = timedelta(weeks=1) if repeat == "weekly" else timedelta(days=1)
    while True:
        local += step
        if repeat == "weekdays":
            while local.weekday() >= 5:
                local += timedelta(days=1)
        if local > now:
            return local
