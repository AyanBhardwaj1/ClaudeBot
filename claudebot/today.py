"""/today: a one-glance dashboard, built straight from the calendar and ClaudeBot's own data. No
model call, so it's instant and free."""

import asyncio
import logging
from datetime import datetime, time, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from .bills import Bills, next_due, paid_dates
from .birthdays import Birthdays
from .inbox_watch import clip
from .lists import Lists
from .modes import defang_urls
from .quiet import dnd_until
from .reminders import next_occurrence
from .scheduling import _parse

log = logging.getLogger(__name__)


def calendar_lines(events: list[dict], tz) -> list[str]:
    lines = []
    for e in events:
        title = defang_urls(clip(e.get("summary") or "(no title)", 60))
        if len(e["start"]) == 10:
            lines.append(f"  all day  {title}")
            continue
        start, _ = _parse(e["start"], tz)
        end, _ = _parse(e["end"], tz)
        declined = " (declined)" if e.get("declined") else ""
        lines.append(f"  {start:%H:%M}–{end:%H:%M}  {title}{declined}")
    return lines


class TodayHandlers:
    """Mixed into TelegramBot."""

    async def on_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        day_end = datetime.combine(now.date() + timedelta(days=1), time(0), tzinfo=self.config.timezone)
        parts = [f"📆 {now:%A, %B %-d}"]
        if until := dnd_until(self.db, now):
            parts.append(f"🔕 Quiet until {until:%H:%M}")
        if self.google.is_connected():
            try:
                start = datetime.combine(now.date(), time(0), tzinfo=self.config.timezone)
                events = await asyncio.to_thread(self.google.list_events, start.isoformat(), day_end.isoformat(), 50)
                lines = calendar_lines(events, self.config.timezone)
                if len(lines) > 25:
                    lines = lines[:25] + [f"  ...and {len(lines) - 25} more"]
                parts.append("📅 Calendar\n" + ("\n".join(lines) if lines else "  nothing scheduled"))
            except Exception:
                log.exception("Reading today's calendar failed")
                parts.append("📅 Calendar: couldn't read it just now")
        else:
            parts.append("📅 Calendar: not connected (/connect)")
        due = [r for r in self.db.active_reminders()
               if datetime.fromisoformat(r["due_at"]).astimezone(self.config.timezone) < day_end]
        if due:
            parts.append("⏰ Reminders\n" + "\n".join(
                f"  {datetime.fromisoformat(r['due_at']).astimezone(self.config.timezone):%H:%M}  "
                f"{defang_urls(clip(r['text'], 70))}" for r in due[:8]))
        due_bills = sorted(((b, next_due(b["day"], now.date())) for b in Bills(self.db).all()), key=lambda x: x[1])
        due_bills = [(b, d) for b, d in due_bills if (d - now.date()).days <= 1 and d.isoformat() not in paid_dates(b)]
        if due_bills:
            parts.append("🧾 " + ", ".join(
                f"{defang_urls(b['name'])} {b['amount']:,.2f} {b['currency']} {'today' if d == now.date() else 'tomorrow'}"
                for b, d in due_bills[:6]) + " (/bills)")
        soon = Birthdays(self.db).upcoming(now.date(), 7)
        if soon:
            parts.append("🎂 " + ", ".join(
                f"{defang_urls(b['name'])} {'today!' if when == now.date() else f'{when:%a %b %-d}'}"
                for b, when in soon[:6]))
        if self.dms.active_connection_id() and (waiting := self.dms.unanswered()):
            parts.append(f"💬 {len(waiting)} Telegram chat{'s' if len(waiting) != 1 else ''} waiting on you (/dms)")
        lists = Lists(self.db)
        open_items = {n: sum(not i["done"] for i in lists.items(n)) for n in lists.names()}
        if any(open_items.values()):
            parts.append("🗒 " + ", ".join(f"{n}: {k}" for n, k in open_items.items() if k) + " (/lists)")
        parts.append("Replies you owe: /waiting")
        await update.effective_message.reply_text("\n\n".join(parts))

    async def on_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """The next 7 days at a glance: events per day, reminders, bills and birthdays. No model call."""
        now = datetime.now(self.config.timezone)
        tz = self.config.timezone
        start = datetime.combine(now.date(), time(0), tzinfo=tz)
        days = [now.date() + timedelta(days=i) for i in range(7)]
        per_day: dict = {d: [] for d in days}
        calendar_note = ""
        if self.google.is_connected():
            try:
                events = await asyncio.to_thread(self.google.list_events, start.isoformat(),
                                                 (start + timedelta(days=7)).isoformat(), 100)
                for e in events:
                    begin, all_day = _parse(e["start"], tz)
                    if begin.date() in per_day and not e.get("declined"):
                        title = defang_urls(clip(e.get("summary") or "(no title)", 40))
                        per_day[begin.date()].append(title if all_day else f"{begin:%H:%M} {title}")
            except Exception:
                log.exception("Reading the week's calendar failed")
                calendar_note = "📅 Couldn't read your calendar just now."
        else:
            calendar_note = "📅 Calendar not connected (/connect)."
        for r in self.db.active_reminders():
            due = datetime.fromisoformat(r["due_at"]).astimezone(tz)
            anchor = datetime.fromisoformat(r["anchor"]) if r["anchor"] else None
            for _ in range(7):  # a daily or weekday reminder shows on each day it fires
                if due is None or due.date() > days[-1]:
                    break
                if due.date() in per_day:
                    per_day[due.date()].append(f"⏰ {due:%H:%M} {defang_urls(clip(r['text'], 40))}")
                due = next_occurrence(due, r["repeat"], due, tz, anchor)
        for b in Bills(self.db).all():
            due = next_due(b["day"], now.date())
            if due in per_day and due.isoformat() not in paid_dates(b):
                per_day[due].append(f"🧾 {defang_urls(b['name'])} {b['amount']:,.2f} {b['currency']}")
        for b, when in Birthdays(self.db).upcoming(now.date(), 6):
            per_day[when].append(f"🎂 {defang_urls(b['name'])}")
        lines = ["🗓 Your week"] + ([calendar_note] if calendar_note else [])
        for d in days:
            items = per_day[d]
            label = "Today" if d == now.date() else "Tomorrow" if d == days[1] else f"{d:%a %b %-d}"
            if not items:
                lines.append(f"{label}: free")
                continue
            shown = items[:6] + ([f"...and {len(items) - 6} more"] if len(items) > 6 else [])
            lines.append(f"{label} ({len(items)}):\n" + "\n".join(f"  {i}" for i in shown))
        await update.effective_message.reply_text("\n".join(lines))
