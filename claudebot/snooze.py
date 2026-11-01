"""Email snooze: archive now, back in the inbox (unread) at a set time, with a ping. Gmail's API has
no snooze, so ClaudeBot keeps the list and moves the email back itself."""

import asyncio
import json
import logging
from datetime import datetime

from googleapiclient.errors import HttpError
from telegram.ext import ContextTypes

from .actions import ActionLog
from .db import Database
from .inbox_watch import clip
from .modes import defang_urls

log = logging.getLogger(__name__)

KEY = "snoozed_mail"
MAX_SNOOZED = 100


def snooze(db: Database, message_id: str, label: str, until: datetime) -> None:
    held = [s for s in json.loads(db.get_setting(KEY) or "[]") if s["id"] != message_id]
    if len(held) >= MAX_SNOOZED:
        raise ValueError("Too many snoozed emails already.")
    db.set_setting(KEY, json.dumps(held + [{"id": message_id, "label": label, "until": until.isoformat()}]))


def due(db: Database, now: datetime) -> list[dict]:
    return [s for s in json.loads(db.get_setting(KEY) or "[]") if datetime.fromisoformat(s["until"]) <= now]


def done(db: Database, message_id: str) -> None:
    held = json.loads(db.get_setting(KEY) or "[]")
    db.set_setting(KEY, json.dumps([s for s in held if s["id"] != message_id]))


class SnoozeHandlers:
    """Mixed into TelegramBot."""

    async def _snooze_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(self.config.timezone)
        for item in due(self.db, now):
            try:
                await asyncio.to_thread(self.google.modify_email, item["id"], "inbox")
            except HttpError as e:
                if e.status_code in (404, 400):  # deleted meanwhile: say so once, stop retrying
                    done(self.db, item["id"])
                    await self.send_to_owner(f"💤 A snoozed email is gone from Gmail: {defang_urls(clip(item['label'], 150))}")
                else:
                    log.warning("Unsnoozing %s failed; will retry", item["id"])
                continue
            except Exception:
                log.exception("Unsnoozing %s failed; will retry", item["id"])
                continue
            done(self.db, item["id"])
            ActionLog(self.db).record("email", f"Brought back a snoozed email: {item['label']}")
            await self.send_to_owner(f"💤 Back in your inbox: {defang_urls(clip(item['label'], 150))}")
