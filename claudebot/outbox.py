"""Outgoing email with an undo window: queue, show an Undo button, send when the window closes."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .db import Database

log = logging.getLogger(__name__)


class OutboxUI(Protocol):
    async def announce(self, outbox_id: int, text: str) -> int | None:
        """Show `text` with an Undo button; return the chat message id."""

    async def edit(self, message_id: int, text: str) -> None: ...

    async def notify(self, text: str) -> None: ...


def _describe(email: dict) -> str:
    return f"{email['to']}: {email.get('subject') or '(reply)'}"


class Outbox:
    def __init__(
        self,
        db: Database,
        google,
        undo_seconds: int,
        schedule: Callable[[int, datetime], None],
        ui: OutboxUI,
    ):
        self.db = db
        self.google = google
        self.undo_seconds = undo_seconds
        self.schedule = schedule
        self.ui = ui

    async def submit(self, email: dict) -> dict:
        """Called by the send_email tool."""
        if self.undo_seconds <= 0:
            result = await asyncio.to_thread(self.google.send_email, **email)
            await self.ui.notify(f"📤 Sent email to {_describe(email)}")
            return result
        send_at = datetime.now(timezone.utc) + timedelta(seconds=self.undo_seconds)
        outbox_id = self.db.queue_email(email, send_at)
        message_id = await self.ui.announce(
            outbox_id, f"📤 Sending to {_describe(email)} in {self.undo_seconds}s"
        )
        self.db.set_outbox_message(outbox_id, message_id)
        self.schedule(outbox_id, send_at)
        return {
            "status": "queued",
            "outbox_id": outbox_id,
            "sends_in_seconds": self.undo_seconds,
            "note": "Goes out automatically unless the owner taps Undo.",
        }

    async def undo(self, outbox_id: int) -> str:
        row = self.db.transition_outbox(outbox_id, "pending", "cancelled")
        if row is None:
            current = self.db.get_outbox(outbox_id)
            if current is None:
                return "I can't find that email."
            return f"Too late, that email was already {current['status']}."
        email = json.loads(row["email_json"])
        self.db.add_notice(f"The owner tapped Undo: the email to {_describe(email)} was cancelled, not sent.")
        if row["telegram_message_id"]:
            await self.ui.edit(row["telegram_message_id"], f"↩️ Cancelled email to {_describe(email)}")
        return "Cancelled."

    async def deliver(self, outbox_id: int) -> None:
        """Send a queued email unless it was undone. Safe to call more than once."""
        row = self.db.transition_outbox(outbox_id, "pending", "sending")
        if row is None:
            return
        email = json.loads(row["email_json"])
        try:
            await asyncio.to_thread(self.google.send_email, **email)
        except Exception as e:
            log.exception("Sending outbox email %s failed", outbox_id)
            self.db.transition_outbox(outbox_id, "sending", "failed", repr(e))
            self.db.add_notice(f"The email to {_describe(email)} FAILED to send: {e}")
            await self.ui.notify(f"⚠️ Couldn't send the email to {_describe(email)}: {e}")
            return
        self.db.transition_outbox(outbox_id, "sending", "sent")
        if row["telegram_message_id"]:
            await self.ui.edit(row["telegram_message_id"], f"📤 Sent to {_describe(email)}")

    async def resume(self) -> None:
        """After a restart: reschedule queued emails, and flag any send a crash interrupted."""
        for row in self.db.outbox_with_status("pending"):
            self.schedule(row["id"], datetime.fromisoformat(row["send_at"]))
        for row in self.db.outbox_with_status("sending"):
            # It may or may not have reached Gmail; resending could send it twice.
            self.db.transition_outbox(row["id"], "sending", "unknown")
            email = json.loads(row["email_json"])
            self.db.add_notice(f"The email to {_describe(email)} may not have gone out (restart mid-send).")
            await self.ui.notify(
                f"⚠️ I restarted while sending to {_describe(email)}. It may not have gone out; "
                "check Gmail's Sent folder."
            )
