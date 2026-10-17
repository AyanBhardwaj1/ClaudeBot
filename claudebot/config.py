"""Settings loaded from environment variables (or a .env file)."""

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value and value.strip() else None


@dataclass(frozen=True)
class Config:
    telegram_token: str
    owner_id: int | None
    model: str
    effort: str
    timezone: ZoneInfo
    data_dir: Path
    google_credentials_file: Path
    google_token_file: Path
    google_token_json: str | None
    daily_brief_time: str | None
    new_thread_after_hours: float
    owner_name: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "claudebot.db"


def load_config() -> Config:
    data_dir = Path(os.getenv("CLAUDEBOT_DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        owner_id=_int_or_none(os.getenv("TELEGRAM_OWNER_ID")),
        model=os.getenv("CLAUDEBOT_MODEL", "claude-opus-5-5"),
        effort=os.getenv("CLAUDEBOT_EFFORT", "medium"),
        timezone=ZoneInfo(os.getenv("CLAUDEBOT_TIMEZONE", "America/Chicago")),
        data_dir=data_dir,
        google_credentials_file=Path(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")),
        google_token_file=Path(os.getenv("GOOGLE_TOKEN_FILE", str(data_dir / "google_token.json"))),
        google_token_json=os.getenv("GOOGLE_TOKEN_JSON") or None,
        daily_brief_time=os.getenv("DAILY_BRIEF_TIME") or None,
        new_thread_after_hours=float(os.getenv("NEW_THREAD_AFTER_HOURS", "8")),
        owner_name=os.getenv("CLAUDEBOT_OWNER_NAME", "sir"),
    )
