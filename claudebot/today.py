"""/today: a one-glance dashboard, built straight from the calendar and ClaudeBot's own data. No
model call, so it's instant and free."""

import asyncio
import logging
from datetime import datetime, time, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from .inbox_watch import clip
from .lists import Lists
from .modes import defang_urls
from .quiet import dnd_until
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
        if self.dms.active_connection_id() and (waiting := self.dms.unanswered()):
            parts.append(f"💬 {len(waiting)} Telegram chat{'s' if len(waiting) != 1 else ''} waiting on you (/dms)")
        lists = Lists(self.db)
        open_items = {n: sum(not i["done"] for i in lists.items(n)) for n in lists.names()}
        if any(open_items.values()):
            parts.append("🗒 " + ", ".join(f"{n}: {k}" for n, k in open_items.items() if k) + " (/lists)")
        parts.append("Replies you owe: /waiting")
        await update.effective_message.reply_text("\n\n".join(parts))
