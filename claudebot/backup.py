"""Nightly database backups: SQLite's online backup API copies a consistent snapshot while the
bot keeps running. The last 7 are kept next to the database (in the Docker volume)."""

import os
import sqlite3
from datetime import datetime, time
from pathlib import Path

from telegram.ext import ContextTypes

BACKUP_TIME = time(3, 0)
KEEP = 7


def backup(db_conn: sqlite3.Connection, data_dir: Path, today: str, keep: int = KEEP) -> Path:
    folder = data_dir / "backups"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    target = folder / f"claudebot-{today}.db"
    os.close(os.open(target, os.O_WRONLY | os.O_CREAT, 0o600))  # private from the first byte
    target.chmod(0o600)
    out = sqlite3.connect(target)
    try:
        db_conn.backup(out)
    finally:
        out.close()
    for old in sorted(folder.glob("claudebot-????-??-??.db"))[:-keep]:  # only the nightly ones rotate
        old.unlink()
    return target


class BackupHandlers:
    """Mixed into TelegramBot."""

    async def _backup_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = datetime.now(self.config.timezone).date().isoformat()
        backup(self.db.conn, self.config.data_dir, today)
