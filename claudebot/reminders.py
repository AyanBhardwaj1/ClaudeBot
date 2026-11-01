"""Date arithmetic for repeating reminders."""

import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _add_months(moment: datetime, months: int) -> datetime:
    """Same day next month, or the month's last day when it's shorter (Jan 31 -> Feb 28)."""
    month_index = moment.month - 1 + months
    year, month = moment.year + month_index // 12, month_index % 12 + 1
    return moment.replace(year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))


def previous_window(due: datetime, repeat: str) -> timedelta:
    """How far back a recurring briefing firing at `due` should look: since the last one."""
    if repeat == "daily":
        return timedelta(days=1)
    if repeat == "weekdays":
        return timedelta(days=3) if due.weekday() == 0 else timedelta(days=1)  # Monday covers the weekend
    if repeat == "biweekly":
        return timedelta(weeks=2)
    if repeat == "monthly":
        return due - _add_months(due, -1)
    if repeat == "yearly":
        return due - _add_months(due, -12)
    return timedelta(weeks=1)  # weekly, and a sensible window for one-off briefings


def next_occurrence(due: datetime, repeat: str, now: datetime, tz: ZoneInfo) -> datetime | None:
    """The first run of a repeating reminder strictly after `now`, keeping its local wall-clock time.

    Returns None for one-off reminders.
    """
    if repeat == "none":
        return None
    local = due.astimezone(tz)  # aware arithmetic in the local zone keeps the wall time across DST
    if repeat in ("monthly", "yearly"):
        months = 1 if repeat == "monthly" else 12
        count = 1
        while True:  # counted from the original date, so Jan 31 -> Feb 28 -> Mar 31
            following = _add_months(local, months * count)
            if following > now:
                return following
            count += 1
    step = {"weekly": timedelta(weeks=1), "biweekly": timedelta(weeks=2)}.get(repeat, timedelta(days=1))
    while True:
        local += step
        if repeat == "weekdays":
            while local.weekday() >= 5:
                local += timedelta(days=1)
        if local > now:
            return local
