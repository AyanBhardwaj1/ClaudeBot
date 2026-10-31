"""Free time from calendar events: exact arithmetic, so "when am I free Thursday?" is never a guess."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SLOT_STEP_MINUTES = 15  # proposed slots start on a quarter hour
SPREAD = timedelta(hours=2)  # at most one option every two hours of a long free stretch


def _parse(value: str, tz: ZoneInfo) -> tuple[datetime, bool]:
    """(datetime, is_all_day) from an event's start or end."""
    if len(value) == 10:  # YYYY-MM-DD: an all-day event
        return datetime.combine(date.fromisoformat(value), time(0), tzinfo=tz), True
    parsed = datetime.fromisoformat(value)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)).astimezone(tz), False


def busy_from_events(events: list[dict], tz: ZoneInfo) -> list[tuple[datetime, datetime]]:
    """Busy intervals. Events marked free ("transparent") and invites the owner declined never
    block; everything else does, all-day events included (Calendar's default is busy)."""
    busy = []
    for event in events:
        if event.get("transparency") == "transparent" or event.get("declined"):
            continue
        start, _ = _parse(event["start"], tz)
        end, _ = _parse(event["end"], tz)
        if end > start:
            busy.append((start, end))
    return busy


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _round_up(moment: datetime) -> datetime:
    extra = (-moment.minute) % SLOT_STEP_MINUTES
    rounded = moment.replace(second=0, microsecond=0) + timedelta(minutes=extra)
    return rounded if rounded >= moment else rounded + timedelta(minutes=SLOT_STEP_MINUTES)


def free_slots(
    busy: list[tuple[datetime, datetime]],
    start: datetime,
    end: datetime,
    duration: timedelta,
    day_start: time,
    day_end: time,
    tz: ZoneInfo,
    limit: int = 3,
    now: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Up to `limit` slots of `duration` inside working hours, between start and end, that miss
    every busy interval and start after now, spread out rather than back to back."""
    now = now or datetime.now(tz)
    blocked = _merge(busy)
    slots = []
    day = start.astimezone(tz).date()
    while day <= end.astimezone(tz).date() and len(slots) < limit:
        window_start = max(datetime.combine(day, day_start, tzinfo=tz), start, now)
        window_end = min(datetime.combine(day, day_end, tzinfo=tz), end)
        cursor = _round_up(window_start)
        for busy_start, busy_end in blocked + [(window_end, window_end)]:
            if busy_end <= cursor:
                continue
            gap_end = min(busy_start, window_end)
            while gap_end - cursor >= duration and len(slots) < limit:
                slots.append((cursor, cursor + duration))
                cursor = _round_up(cursor + max(duration, SPREAD))  # spread options out
            if len(slots) == limit:
                break
            cursor = _round_up(max(cursor, busy_end))
            if cursor >= window_end:
                break
        day += timedelta(days=1)
    return slots
