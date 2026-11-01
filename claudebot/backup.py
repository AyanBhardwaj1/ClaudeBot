"""Nightly database backups: SQLite's online backup API copies a consistent snapshot while the
bot keeps running. The last 7 are kept next to the database (in the Docker volume)."""

import sqlite3
from datetime import datetime, time
from pathlib import Path

from telegram.ext import ContextTypes

BACKUP_TIME = time(3, 0)
KEEP = 7


def backup(db_conn: sqlite3.Connection, data_dir: Path, today: str, keep: int = KEEP) -> Path:
    folder = data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"claudebot-{today}.db"
    with sqlite3.connect(target) as out:
        db_conn.backup(out)
    target.chmod(0o600)  # it holds your conversations and memories
    for old in sorted(folder.glob("claudebot-*.db"))[:-keep]:
        old.unlink()
    return target


class BackupHandlers:
    """Mixed into TelegramBot."""

    async def _backup_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = datetime.now(self.config.timezone).date().isoformat()
        backup(self.db.conn, self.config.data_dir, today)
