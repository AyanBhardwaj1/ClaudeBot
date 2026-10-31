"""Settings loaded from environment variables (or a .env file)."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value and value.strip() else None


def _float_or_none(value: str | None) -> float | None:
    return float(value) if value and value.strip() else None


def _flag(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


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
    fast_model: str = "claude-haiku-5-5"
    inbox_alerts: bool = True
    inbox_check_minutes: int = 10
    quiet_hours: str | None = "23:00-07:00"
    monthly_budget_usd: float | None = None
    undo_send_seconds: int = 20
    group_daily_limit: int = 30
    group_monthly_budget_usd: float | None = 5.0
    city: str | None = None
    region: str | None = None
    country: str | None = None
    followups: bool = True

    @property
    def location(self) -> dict | None:
        """Where the owner lives, for local web results (approximate, never coordinates)."""
        fields = {"city": self.city, "region": self.region,
                  "country": self.country.upper() if self.country else None}
        fields = {k: v.strip() for k, v in fields.items() if v and v.strip()}
        return fields or None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "claudebot.db"


def _country(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    if not re.fullmatch(r"[A-Za-z]{2}", value.strip()):
        raise ValueError(f"CLAUDEBOT_COUNTRY must be a two-letter code like US or IN, got {value!r}")
    return value.strip().upper()


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
        owner_name=os.getenv("CLAUDEBOT_OWNER_NAME") or "friend",
        fast_model=os.getenv("CLAUDEBOT_FAST_MODEL", "claude-haiku-5-5"),
        inbox_alerts=_flag(os.getenv("INBOX_ALERTS"), True),
        inbox_check_minutes=max(int(os.getenv("INBOX_CHECK_MINUTES", "10")), 1),
        quiet_hours=os.getenv("QUIET_HOURS", "23:00-07:00") or None,
        monthly_budget_usd=_float_or_none(os.getenv("MONTHLY_BUDGET_USD")),
        undo_send_seconds=max(int(os.getenv("UNDO_SEND_SECONDS", "20")), 0),
        group_daily_limit=max(int(os.getenv("GROUP_DAILY_LIMIT", "30")), 0),
        group_monthly_budget_usd=_float_or_none(os.getenv("GROUP_MONTHLY_BUDGET_USD", "5")),
        city=os.getenv("CLAUDEBOT_CITY") or None,
        region=os.getenv("CLAUDEBOT_REGION") or None,
        country=_country(os.getenv("CLAUDEBOT_COUNTRY")),
        followups=_flag(os.getenv("FOLLOWUPS"), True),
    )
