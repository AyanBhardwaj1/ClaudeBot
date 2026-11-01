"""Habits: "/habit workout" and ClaudeBot asks each evening, with a tap to mark it done, and keeps
your streak. No model involved."""

from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .db import Database
from .quiet import dnd_active

CHECK_TIME = time(20, 30)
MAX_HABITS = 10
SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS habit_days (
    habit_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (habit_id, day)
);
"""


class Habits:
    def __init__(self, db: Database):
        self.db = db
        db.conn.executescript(SCHEMA)

    def add(self, name: str) -> dict:
        name = " ".join(name.replace("<", " ").replace(">", " ").split())[:40]
        if not name:
            raise ValueError("Name the habit, e.g. /habit workout")
        if len(self.active()) >= MAX_HABITS:
            raise ValueError(f"That's {MAX_HABITS} habits already; drop one first.")
        self.db.conn.execute("INSERT INTO habits (name) VALUES (?) ON CONFLICT(name) DO UPDATE SET active = 1", (name,))
        self.db.conn.commit()
        row = self.db.conn.execute("SELECT id, name FROM habits WHERE name = ?", (name,)).fetchone()
        return {"id": row["id"], "name": row["name"]}

    def active(self) -> list[dict]:
        return [dict(r) for r in self.db.conn.execute("SELECT id, name FROM habits WHERE active = 1 ORDER BY id")]

    def stop(self, habit_id: int) -> None:
        self.db.conn.execute("UPDATE habits SET active = 0 WHERE id = ?", (habit_id,))
        self.db.conn.commit()

    def mark(self, habit_id: int, day: date) -> bool:
        """Mark a day done; True if it wasn't already."""
        cur = self.db.conn.execute("INSERT OR IGNORE INTO habit_days (habit_id, day) VALUES (?, ?)",
                                   (habit_id, day.isoformat()))
        self.db.conn.commit()
        return cur.rowcount > 0

    def done(self, habit_id: int, day: date) -> bool:
        return self.db.conn.execute("SELECT 1 FROM habit_days WHERE habit_id = ? AND day = ?",
                                    (habit_id, day.isoformat())).fetchone() is not None

    def streak(self, habit_id: int, today: date) -> int:
        """Days in a row ending today (or yesterday, if today isn't marked yet)."""
        day = today if self.done(habit_id, today) else today - timedelta(days=1)
        count = 0
        while self.done(habit_id, day):
            count += 1
            day -= timedelta(days=1)
        return count

    def export(self) -> list[dict]:
        return [{"name": h["name"], "days_done": [r["day"] for r in self.db.conn.execute(
            "SELECT day FROM habit_days WHERE habit_id = ? ORDER BY day", (h["id"],))]} for h in self.active()]


def habit_lines(db: Database, today: date) -> str:
    """'- workout: 5 of the last 7 days (streak 3)' per habit, for the weekly review."""
    habits = Habits(db)
    lines = []
    for h in habits.active():
        week = sum(habits.done(h["id"], today - timedelta(days=i)) for i in range(7))
        lines.append(f"- {h['name']}: {week} of the last 7 days (streak {habits.streak(h['id'], today)})")
    return "\n".join(lines)


def habit_view(habits: Habits, today: date) -> tuple[str, InlineKeyboardMarkup | None]:
    items = habits.active()
    if not items:
        return "No habits yet. Start one: /habit workout (I'll ask each evening at 20:30).", None
    lines, rows = [f"🔥 Habits for {today:%a %b %-d}"], []
    for h in items:
        done = habits.done(h["id"], today)
        streak = habits.streak(h["id"], today)
        lines.append(f"{'✅' if done else '⬜'} {h['name']} · {streak} day streak")
        if not done:
            rows.append([InlineKeyboardButton(f"✅ {h['name'][:30]}", callback_data=f"hab:{h['id']}:{today:%Y%m%d}")])
    return "\n".join(lines), InlineKeyboardMarkup(rows) if rows else None


class HabitHandlers:
    """Mixed into TelegramBot."""

    async def on_habit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        habits = Habits(self.db)
        words = context.args or []
        today = datetime.now(self.config.timezone).date()
        if words and words[0].lower() in ("stop", "drop", "remove") and len(words) > 1:
            name = " ".join(words[1:]).lower()
            match = next((h for h in habits.active() if h["name"].lower() == name), None)
            if match:
                habits.stop(match["id"])
            await update.effective_message.reply_text(f"Stopped tracking {name}." if match else f"No habit called {name}.")
            return
        if words:
            try:
                habit = habits.add(" ".join(words))
            except ValueError as e:
                await update.effective_message.reply_text(str(e))
                return
            await update.effective_message.reply_text(
                f"🔥 Tracking {habit['name']}. I'll ask each evening at {CHECK_TIME:%H:%M}; tap to mark it done. "
                f"/habit stop {habit['name']} to drop it.")
            return
        text, markup = habit_view(habits, today)
        await update.effective_message.reply_text(text, reply_markup=markup)

    async def on_habit_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._from_owner(query):
            return
        _, habit_id, day = query.data.split(":")
        habits = Habits(self.db)
        if int(habit_id) not in {h["id"] for h in habits.active()}:
            return
        marked = datetime.strptime(day, "%Y%m%d").date()
        today = datetime.now(self.config.timezone).date()
        if not today - timedelta(days=2) <= marked <= today:
            return  # an old card: only the last couple of days can be ticked
        habits.mark(int(habit_id), marked)
        text, markup = habit_view(habits, marked)  # the card stays on its own day, even after midnight
        await query.edit_message_text(text, reply_markup=markup)

    async def _habit_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        habits = Habits(self.db)
        now = datetime.now(self.config.timezone)
        if dnd_active(self.db, now):
            return
        pending = [h for h in habits.active() if not habits.done(h["id"], now.date())]
        if pending:
            await self.send_to_owner(*habit_view(habits, now.date()))
