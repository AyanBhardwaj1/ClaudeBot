"""Outgoing email with an undo window, or a Send tap when the owner wasn't there to ask for it.

Statuses: pending (waiting out the undo window) -> sending -> sent | failed
          held (waiting for a Send tap) -> pending -> ...
          pending | held -> cancelled;  sending at a restart -> unknown
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .db import Database

log = logging.getLogger(__name__)

PREVIEW_CHARS = 3000  # Telegram messages max out at 4096 characters


class OutboxUI(Protocol):
    async def announce(self, outbox_id: int, text: str, needs_approval: bool = False) -> int | None:
        """Show `text` with Undo (or Send/Cancel) buttons; return the chat message id."""

    async def edit(self, message_id: int, text: str) -> None: ...

    async def notify(self, text: str) -> None: ...


def _describe(email: dict) -> str:
    """Every recipient, so a hidden cc/bcc can't slip past the owner's look at the card."""
    copies = "".join(f" ({kind}: {email[kind]})" for kind in ("cc", "bcc") if email.get(kind))
    return f"{email['to']}{copies}: {email.get('subject') or '(reply)'}"


def _preview(body: str) -> str:
    if len(body) <= PREVIEW_CHARS:
        return body
    return f"{body[:PREVIEW_CHARS]}\n[... {len(body) - PREVIEW_CHARS} more characters not shown]"


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

    async def submit(self, email: dict, needs_approval: bool = False) -> dict:
        """Called by the send_email tool."""
        now = datetime.now(timezone.utc)
        if needs_approval:
            outbox_id = self.db.queue_email(email, now, status="held")
            await self._announce(outbox_id, "held", f"✉️ Ready to send to {_describe(email)}\n\n{_preview(email['body'])}", True)
            return {
                "status": "awaiting_approval",
                "outbox_id": outbox_id,
                "note": "Not sent yet: the owner didn't start this turn, so they must tap Send.",
            }
        if self.undo_seconds <= 0:
            result = await asyncio.to_thread(self.google.send_email, **email)
            await self.ui.notify(f"📤 Sent email to {_describe(email)}")
            return result
        send_at = now + timedelta(seconds=self.undo_seconds)
        outbox_id = self.db.queue_email(email, send_at)
        await self._announce(outbox_id, "pending", f"📤 Sending to {_describe(email)} in {self.undo_seconds}s")
        self.schedule(outbox_id, send_at)
        return {
            "status": "queued",
            "outbox_id": outbox_id,
            "sends_in_seconds": self.undo_seconds,
            "note": "Goes out automatically unless the owner taps Undo.",
        }

    async def _announce(self, outbox_id: int, status: str, text: str, needs_approval: bool = False) -> None:
        # Never leave an email the owner can't see or stop: if the buttons can't be shown, fail it.
        try:
            message_id = await self.ui.announce(outbox_id, text, needs_approval)
        except Exception as e:
            self.db.transition_outbox(outbox_id, status, "failed", f"couldn't show buttons: {e!r}")
            raise
        self.db.set_outbox_message(outbox_id, message_id)

    async def approve(self, outbox_id: int) -> str:
        """The owner tapped Send on a held email."""
        if self.db.transition_outbox(outbox_id, "held", "pending") is None:
            current = self.db.get_outbox(outbox_id)
            return f"That email was already {current['status']}." if current else "I can't find that email."
        await self.deliver(outbox_id)
        return "Sending."

    async def undo(self, outbox_id: int) -> str:
        row = self.db.transition_outbox(outbox_id, "pending", "cancelled") or self.db.transition_outbox(
            outbox_id, "held", "cancelled"
        )
        if row is None:
            current = self.db.get_outbox(outbox_id)
            if current is None:
                return "I can't find that email."
            return f"Too late, that email was already {current['status']}."
        email = json.loads(row["email_json"])
        self.db.add_notice(f"The owner cancelled the email to {_describe(email)}; it was not sent.")
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
        """After a restart: keep waiting emails waiting, and never send anything stale or twice."""
        now = datetime.now(timezone.utc)
        for row in self.db.outbox_with_status("pending"):
            if datetime.fromisoformat(row["send_at"]) > now:
                self.schedule(row["id"], datetime.fromisoformat(row["send_at"]))
                continue
            # Its undo window passed while we were down (an Undo tap may be waiting unprocessed).
            self.db.transition_outbox(row["id"], "pending", "held")
            email = json.loads(row["email_json"])
            try:
                await self._announce(
                    row["id"], "held", f"⏸ I restarted before this went out. Still send it to {_describe(email)}?", True
                )
            except Exception:
                log.exception("Couldn't re-announce held email %s", row["id"])
                self.db.add_notice(
                    f"After a restart, the email to {_describe(email)} was not sent and is now cancelled; "
                    "the owner may want to send it again."
                )
        for row in self.db.outbox_with_status("sending"):
            # It may or may not have reached Gmail; resending could send it twice.
            self.db.transition_outbox(row["id"], "sending", "unknown")
            email = json.loads(row["email_json"])
            self.db.add_notice(f"The email to {_describe(email)} may not have gone out (restart mid-send).")
            await self.ui.notify(
                f"⚠️ I restarted while sending to {_describe(email)}. It may not have gone out; "
                "check Gmail's Sent folder."
            )
