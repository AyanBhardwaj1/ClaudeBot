"""SQLite storage for conversations, memories, reminders, notices, usage and the email outbox."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    config_hash TEXT NOT NULL DEFAULT ''
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
CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    source TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    web_searches INTEGER NOT NULL,
    cost_usd REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_created_at ON usage(created_at);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seen_emails (
    message_id TEXT PRIMARY KEY,
    seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    email_json TEXT NOT NULL,
    send_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    telegram_message_id INTEGER,
    detail TEXT NOT NULL DEFAULT ''
);
"""

SEEN_EMAIL_RETENTION = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Database:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(threads)")}
        if "config_hash" not in columns:
            self.conn.execute("ALTER TABLE threads ADD COLUMN config_hash TEXT NOT NULL DEFAULT ''")

    # --- conversation threads ---

    def current_thread(self, idle_hours: float, config_hash: str = "") -> tuple[int, bool]:
        """Return (thread_id, is_new).

        Starts a new thread after `idle_hours` of silence, or when the system prompt, tools or
        model changed (`config_hash`): replaying old thinking blocks against a changed prompt fails.
        """
        row = self.conn.execute(
            "SELECT id, last_active_at, config_hash FROM threads ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row["config_hash"] == config_hash:
            last = datetime.fromisoformat(row["last_active_at"])
            if _now() - last < timedelta(hours=idle_hours):
                return row["id"], False
        return self.new_thread(config_hash), True

    def new_thread(self, config_hash: str = "") -> int:
        now = _now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO threads (started_at, last_active_at, config_hash) VALUES (?, ?, ?)",
            (now, now, config_hash),
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

    # --- notices: things the owner was told outside a conversation turn ---

    def add_notice(self, text: str) -> None:
        self.conn.execute(
            "INSERT INTO notices (text, created_at) VALUES (?, ?)", (text, _now().isoformat())
        )
        self.conn.commit()

    def take_notices(self) -> list[str]:
        """Return undelivered notices, oldest first, and mark them delivered."""
        rows = self.conn.execute(
            "SELECT id, text FROM notices WHERE delivered = 0 ORDER BY id"
        ).fetchall()
        if rows:
            self.conn.execute(
                f"UPDATE notices SET delivered = 1 WHERE id IN ({','.join('?' * len(rows))})",
                [r["id"] for r in rows],
            )
            self.conn.commit()
        return [r["text"] for r in rows]

    # --- usage ---

    def record_usage(
        self,
        model: str,
        source: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
        web_searches: int,
        cost_usd: float,
    ) -> None:
        self.conn.execute(
            "INSERT INTO usage (created_at, model, source, input_tokens, output_tokens, "
            "cache_read_tokens, cache_write_tokens, web_searches, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _now().isoformat(), model, source, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens, web_searches, cost_usd,
            ),
        )
        self.conn.commit()

    def usage_totals(self, since: datetime) -> tuple[int, float]:
        """(request count, total estimated cost in USD) since `since`."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS cost FROM usage WHERE created_at >= ?",
            (since.astimezone(timezone.utc).isoformat(),),
        ).fetchone()
        return row["n"], row["cost"]

    # --- settings ---

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # --- emails the inbox watcher has already looked at ---

    def mark_emails_seen(self, message_ids: list[str]) -> list[str]:
        """Record message ids as seen; return the ones that were not seen before."""
        now = _now()
        fresh = []
        for message_id in message_ids:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO seen_emails (message_id, seen_at) VALUES (?, ?)",
                (message_id, now.isoformat()),
            )
            if cur.rowcount:
                fresh.append(message_id)
        self.conn.execute(
            "DELETE FROM seen_emails WHERE seen_at < ?", ((now - SEEN_EMAIL_RETENTION).isoformat(),)
        )
        self.conn.commit()
        return fresh

    # --- outbox (emails waiting out their undo window) ---

    def queue_email(self, email: dict, send_at: datetime) -> int:
        cur = self.conn.execute(
            "INSERT INTO outbox (email_json, send_at) VALUES (?, ?)",
            (json.dumps(email), send_at.astimezone(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_outbox(self, outbox_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone()

    def set_outbox_message(self, outbox_id: int, telegram_message_id: int | None) -> None:
        self.conn.execute(
            "UPDATE outbox SET telegram_message_id = ? WHERE id = ?", (telegram_message_id, outbox_id)
        )
        self.conn.commit()

    def transition_outbox(self, outbox_id: int, from_status: str, to_status: str, detail: str = "") -> sqlite3.Row | None:
        """Atomically move an email from one status to another.

        Returns the row if this call made the change, None if the email was not in `from_status`
        (e.g. Undo raced with sending). The single conditional UPDATE is what prevents doubles.
        """
        cur = self.conn.execute(
            "UPDATE outbox SET status = ?, detail = ? WHERE id = ? AND status = ?",
            (to_status, detail, outbox_id, from_status),
        )
        self.conn.commit()
        return self.get_outbox(outbox_id) if cur.rowcount else None

    def outbox_with_status(self, status: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM outbox WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
