"""What ClaudeBot actually did: a log written where things happen (an email delivered, an event
created), never from what the model says it did. /log shows it, and the action_log tool lets the
agent check before claiming "done"."""

from datetime import datetime, timedelta, timezone

from .db import Database

RETENTION = timedelta(days=60)
MAX_SUMMARY = 200
SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS actions_at ON actions(at);
"""
ICONS = {"email": "📤", "calendar": "📅", "reminder": "⏰", "briefing": "🗞", "memory": "🧠", "telegram": "💬",
         "list": "🗒", "rule": "📏", "money": "💸"}


class ActionLog:
    def __init__(self, db: Database):
        self.db = db
        db.conn.executescript(SCHEMA)

    def record(self, kind: str, summary: str, now: datetime | None = None) -> None:
        at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        text = " ".join(summary.split())[:MAX_SUMMARY]
        self.db.conn.execute("INSERT INTO actions (at, kind, summary) VALUES (?, ?, ?)", (at.isoformat(), kind, text))
        self.db.conn.commit()

    def since(self, start: datetime) -> list[dict]:
        rows = self.db.conn.execute(
            "SELECT at, kind, summary FROM actions WHERE at >= ? ORDER BY at, id",
            (start.astimezone(timezone.utc).isoformat(),)).fetchall()
        return [dict(r) for r in rows]

    def prune(self, now: datetime | None = None) -> None:
        cutoff = (now or datetime.now(timezone.utc)) - RETENTION
        self.db.conn.execute("DELETE FROM actions WHERE at < ?", (cutoff.astimezone(timezone.utc).isoformat(),))
        self.db.conn.commit()


MODIFY_WORDS = {"archive": "Archived", "trash": "Trashed", "mark_read": "Marked read", "mark_unread": "Marked unread",
                "star": "Starred", "unstar": "Unstarred", "mark_important": "Marked important"}


def describe_tool_action(name: str, args: dict, result) -> tuple[str, str] | None:
    """(kind, summary) for a tool call that changed something, judged from its result."""
    if not isinstance(result, dict):
        return None
    if name == "create_draft" or (name == "send_email" and "draft" in str(result.get("status", ""))):
        return "email", f"Saved a draft to {args.get('to', '')}: {args.get('subject', '')}"
    if name == "modify_email" and result.get("status"):
        return "email", f"{MODIFY_WORDS.get(str(args.get('action')), 'Changed')} an email"
    if name == "create_calendar_event" and result.get("status") == "created":
        invited = f", invited {', '.join(args['attendees'])}" if args.get("attendees") else ""
        return "calendar", f"Added \"{args.get('summary', '')}\" ({args.get('start', '')}){invited}"
    if name == "update_calendar_event" and result.get("status") == "updated":
        return "calendar", "Changed an event" + (f" to {args['start']}" if args.get("start") else "")
    if name == "delete_calendar_event" and result.get("status") == "deleted":
        return "calendar", "Deleted an event"
    if name == "set_reminder" and result.get("scheduled"):
        return "reminder", f"Set a reminder: {args.get('text', '')} ({args.get('when', '')})"
    if name == "cancel_reminder" and result.get("cancelled"):
        return "reminder", f"Cancelled reminder #{args.get('reminder_id')}"
    if name == "create_briefing" and result.get("scheduled"):
        return "briefing", f"New briefing: {args.get('topic', '')}"
    if name == "remember" and result.get("saved"):
        return "memory", f"Remembered: {args.get('fact', '')}"
    if name == "add_to_list" and result.get("added"):
        return "list", f"Added to {args.get('list', '')}: {', '.join(result['added'])}"
    if name == "check_off" and result.get("checked"):
        return "list", f"Ticked {result['checked']} list item(s)"
    if name == "log_expense" and result.get("logged"):
        e = result["logged"]
        return "money", f"Logged {e['amount']:.2f} {e['currency']} for {e['category']}"
    if name == "add_alert_rule" and result.get("saved"):
        return "rule", f"New alert rule: {result['saved']}"
    if name == "forget" and result.get("deleted"):
        return "memory", f"Forgot memory #{args.get('memory_id')}"
    return None
