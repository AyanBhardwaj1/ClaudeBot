"""SQLite storage for conversation history, long-term memories and reminders."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES threads(id),
    role TEXT NOT NULL,
    content_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    repeat TEXT NOT NULL DEFAULT 'none',
    run_as_task INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Database:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- conversation threads ---

    def current_thread(self, idle_hours: float) -> tuple[int, bool]:
        """Return (thread_id, is_new). Starts a new thread after `idle_hours` of silence."""
        row = self.conn.execute(
            "SELECT id, last_active_at FROM threads ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            last = datetime.fromisoformat(row["last_active_at"])
            if _now() - last < timedelta(hours=idle_hours):
                return row["id"], False
        return self.new_thread(), True

    def new_thread(self) -> int:
        now = _now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO threads (started_at, last_active_at) VALUES (?, ?)", (now, now)
        )
        self.conn.commit()
        return cur.lastrowid

    def append_message(self, thread_id: int, message: dict) -> None:
        self.conn.execute(
            "INSERT INTO messages (thread_id, role, content_json) VALUES (?, ?, ?)",
            (thread_id, message["role"], json.dumps(message["content"])),
        )
        self.conn.execute(
            "UPDATE threads SET last_active_at = ? WHERE id = ?", (_now().isoformat(), thread_id)
        )
        self.conn.commit()

    def load_messages(self, thread_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content_json FROM messages WHERE thread_id = ? ORDER BY id", (thread_id,)
        ).fetchall()
        return [{"role": r["role"], "content": json.loads(r["content_json"])} for r in rows]

    # --- memories ---

    def add_memory(self, text: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO memories (text, created_at) VALUES (?, ?)", (text, _now().isoformat())
        )
        self.conn.commit()
        return cur.lastrowid

    def list_memories(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT id, text FROM memories ORDER BY id").fetchall()

    def delete_memory(self, memory_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- reminders ---

    def add_reminder(self, text: str, due_at: datetime, repeat: str, run_as_task: bool) -> int:
        cur = self.conn.execute(
            "INSERT INTO reminders (text, due_at, repeat, run_as_task) VALUES (?, ?, ?, ?)",
            (text, due_at.astimezone(timezone.utc).isoformat(), repeat, int(run_as_task)),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_reminder(self, reminder_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM reminders WHERE id = ? AND active = 1", (reminder_id,)
        ).fetchone()

    def active_reminders(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM reminders WHERE active = 1 ORDER BY due_at"
        ).fetchall()

    def reschedule_reminder(self, reminder_id: int, due_at: datetime) -> None:
        self.conn.execute(
            "UPDATE reminders SET due_at = ? WHERE id = ?",
            (due_at.astimezone(timezone.utc).isoformat(), reminder_id),
        )
        self.conn.commit()

    def deactivate_reminder(self, reminder_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE reminders SET active = 0 WHERE id = ? AND active = 1", (reminder_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0
