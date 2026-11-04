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
from .ui import split_message

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

    async def today_data(self) -> dict:
        """Today at a glance, as data: /today renders it for Telegram, the web app as cards."""
        tz = self.config.timezone
        now = datetime.now(tz)
        day_start = datetime.combine(now.date(), time(0), tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        until = dnd_until(self.db, now)
        data: dict = {"date": now.date().isoformat(), "title": f"{now:%A, %B %-d}",
                      "quiet_until": until.strftime("%H:%M") if until else None,
                      "calendar": {"status": "disconnected", "events": []}}
        if self.google.is_connected():
            try:
                events = await asyncio.to_thread(self.google.list_events, day_start.isoformat(), day_end.isoformat(), 50)
                rows = []
                for e in events:
                    title = clip(defang_urls(e.get("summary") or "(no title)"), 60)
                    if len(e["start"]) == 10:
                        rows.append({"all_day": True, "start": None, "end": None, "title": title, "declined": False})
                        continue
                    start, _ = _parse(e["start"], tz)
                    end, _ = _parse(e["end"], tz)
                    rows.append({"all_day": False, "start": f"{start:%H:%M}", "end": f"{end:%H:%M}", "title": title,
                                 "declined": bool(e.get("declined"))})
                data["calendar"] = {"status": "ok", "events": rows}
            except Exception:
                log.exception("Reading today's calendar failed")
                data["calendar"] = {"status": "error", "events": []}
        data["reminders"] = [
            {"id": r["id"], "time": f"{datetime.fromisoformat(r['due_at']).astimezone(tz):%H:%M}",
             "text": clip(defang_urls(r["text"]), 70)}
            for r in self.db.active_reminders() if datetime.fromisoformat(r["due_at"]).astimezone(tz) < day_end][:8]
        due_bills = sorted(((b, next_due(b["day"], now.date())) for b in Bills(self.db).all()), key=lambda x: x[1])
        data["bills"] = [{"id": b["id"], "name": clip(defang_urls(b["name"]), 40), "amount": b["amount"],
                          "currency": b["currency"], "when": "today" if d == now.date() else "tomorrow"}
                         for b, d in due_bills if (d - now.date()).days <= 1 and d.isoformat() not in paid_dates(b)][:6]
        data["birthdays"] = [{"name": clip(defang_urls(b["name"]), 40), "date": when.isoformat(),
                              "when": "today" if when == now.date() else f"{when:%a %b %-d}"}
                             for b, when in Birthdays(self.db).upcoming(now.date(), 7)][:6]
        data["dms_waiting"] = len(self.dms.unanswered()) if self.dms.active_connection_id() else 0
        lists = Lists(self.db)
        data["lists"] = [{"name": n, "open": k} for n in lists.names()
                         if (k := sum(not i["done"] for i in lists.items(n)))]
        return data

    async def on_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        d = await self.today_data()
        parts = [f"📆 {d['title']}"]
        if d["quiet_until"]:
            parts.append(f"🔕 Quiet until {d['quiet_until']}")
        cal = d["calendar"]
        if cal["status"] == "ok":
            lines = [f"  all day  {e['title']}" if e["all_day"] else
                     f"  {e['start']}–{e['end']}  {e['title']}{' (declined)' if e['declined'] else ''}"
                     for e in cal["events"]]
            if len(lines) > 25:
                lines = lines[:25] + [f"  ...and {len(lines) - 25} more"]
            parts.append("📅 Calendar\n" + ("\n".join(lines) if lines else "  nothing scheduled"))
        elif cal["status"] == "error":
            parts.append("📅 Calendar: couldn't read it just now")
        else:
            parts.append("📅 Calendar: not connected (/connect)")
        if d["reminders"]:
            parts.append("⏰ Reminders\n" + "\n".join(f"  {r['time']}  {r['text']}" for r in d["reminders"]))
        if d["bills"]:
            parts.append("🧾 " + ", ".join(f"{b['name']} {b['amount']:,.2f} {b['currency']} {b['when']}"
                                         for b in d["bills"]) + " (/bills)")
        if d["birthdays"]:
            parts.append("🎂 " + ", ".join(f"{b['name']} {'today!' if b['when'] == 'today' else b['when']}"
                                         for b in d["birthdays"]))
        if n := d["dms_waiting"]:
            parts.append(f"💬 {n} Telegram chat{'s' if n != 1 else ''} waiting on you (/dms)")
        if d["lists"]:
            parts.append("🗒 " + ", ".join(f"{x['name']}: {x['open']}" for x in d["lists"]) + " (/lists)")
        parts.append("Replies you owe: /waiting")
        await update.effective_message.reply_text("\n\n".join(parts))

    async def week_data(self) -> dict:
        """The next 7 days as data, items in time order: events, reminders (repeats on each day they
        fire), unpaid bills and birthdays. No model call."""
        tz = self.config.timezone
        now = datetime.now(tz)
        start = datetime.combine(now.date(), time(0), tzinfo=tz)
        days = [now.date() + timedelta(days=i) for i in range(7)]
        per_day: dict = {d: [] for d in days}
        status = "disconnected"
        if self.google.is_connected():
            try:
                events = await asyncio.to_thread(self.google.list_events, start.isoformat(),
                                                 (start + timedelta(days=7)).isoformat(), 100)
                for e in events:
                    begin, all_day = _parse(e["start"], tz)
                    if e.get("declined"):
                        continue
                    end, _ = _parse(e.get("end") or e["start"], tz)
                    title = clip(defang_urls(e.get("summary") or "(no title)"), 40)  # defanging grows text
                    last = (end - timedelta(seconds=1)).date() if all_day else begin.date()
                    for d in days:  # a trip that started before today still shows on each of its days
                        if begin.date() <= d <= last:
                            per_day[d].append({"kind": "event", "time": None if all_day else f"{begin:%H:%M}",
                                               "text": title})
                status = "ok"
            except Exception:
                log.exception("Reading the week's calendar failed")
                status = "error"
        for r in self.db.active_reminders():
            if r["briefing"] or r["run_as_task"]:
                continue  # scheduled briefings and tasks aren't things to do
            due = datetime.fromisoformat(r["due_at"]).astimezone(tz)
            anchor = datetime.fromisoformat(r["anchor"]) if r["anchor"] else None
            for _ in range(7):  # a daily or weekday reminder shows on each day it fires
                if due is None or due.date() > days[-1]:
                    break
                if due.date() in per_day:
                    per_day[due.date()].append({"kind": "reminder", "time": f"{due:%H:%M}",
                                                "text": clip(defang_urls(r["text"]), 40)})
                due = next_occurrence(due, r["repeat"], due, tz, anchor)
        for b in Bills(self.db).all():
            due = next_due(b["day"], now.date())
            if due in per_day and due.isoformat() not in paid_dates(b):
                per_day[due].append({"kind": "bill", "time": None,
                                     "text": f"{clip(defang_urls(b['name']), 40)} {b['amount']:,.2f} {b['currency']}"})
        for b, when in Birthdays(self.db).upcoming(now.date(), 6):
            per_day[when].append({"kind": "birthday", "time": None, "text": clip(defang_urls(b["name"]), 40)})
        out = []
        for d in days:
            items = sorted(per_day[d], key=lambda i: (i["time"] is not None, i["time"] or ""))  # all-day first
            label = "Today" if d == now.date() else "Tomorrow" if d == days[1] else f"{d:%a %b %-d}"
            out.append({"date": d.isoformat(), "label": label, "items": items})
        return {"calendar": status, "days": out}

    async def on_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        data = await self.week_data()
        icons = {"event": "", "reminder": "⏰ ", "bill": "🧾 ", "birthday": "🎂 "}
        note = {"error": "📅 Couldn't read your calendar just now.",
                "disconnected": "📅 Calendar not connected (/connect)."}.get(data["calendar"])
        lines = ["🗓 Your week"] + ([note] if note else [])
        for day in data["days"]:
            items = [f"{icons[i['kind']]}{i['time'] + ' ' if i['time'] else ''}{i['text']}" for i in day["items"]]
            if not items:
                lines.append(f"{day['label']}: free")
                continue
            shown = items[:6] + ([f"...and {len(items) - 6} more"] if len(items) > 6 else [])
            lines.append(f"{day['label']} ({len(items)}):\n" + "\n".join(f"  {i}" for i in shown))
        for chunk in split_message("\n".join(lines)):  # always under Telegram's 4096 characters
            await update.effective_message.reply_text(chunk)
