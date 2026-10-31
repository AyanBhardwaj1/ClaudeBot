"""Guided setup: `python -m claudebot setup`.

Asks for the two keys, checks that each one works, finds your Telegram account automatically,
and writes .env. Everything else (where you live, your job, brief time, Google) is set up in the
Telegram chat the first time you message the bot.
"""

import getpass
import os
import re
import shutil
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
import httpx
from dotenv import dotenv_values

ENV_FILE = Path(".env")
EXAMPLE_FILE = Path(".env.example")
WAIT_FOR_MESSAGE_SECONDS = 180


class SetupError(RuntimeError):
    pass


# --- checks ---


def check_anthropic(key: str) -> None:
    try:
        anthropic.Anthropic(api_key=key, max_retries=1).models.list(limit=1)
    except anthropic.AuthenticationError as e:
        raise SetupError("That API key didn't work. Copy it again from console.anthropic.com.") from e
    except anthropic.PermissionDeniedError as e:
        raise SetupError("That key can't use the API yet. Add a payment method at console.anthropic.com.") from e


def telegram(token: str, method: str, **params) -> dict | list:
    response = httpx.get(f"https://api.telegram.org/bot{token}/{method}", params=params, timeout=40)
    body = response.json()
    if not body.get("ok"):
        raise SetupError(body.get("description", "Telegram said no."))
    return body["result"]


def check_telegram(token: str) -> str:
    """The bot's @username."""
    if not re.fullmatch(r"\d+:[\w-]{30,}", token.strip()):
        raise SetupError("That doesn't look like a bot token. It looks like 123456789:AAH... and comes from @BotFather.")
    try:
        return telegram(token, "getMe")["username"]
    except SetupError as e:
        raise SetupError("Telegram didn't accept that token. Copy it again from @BotFather.") from e


def wait_for_owner(token: str, timeout: float = WAIT_FOR_MESSAGE_SECONDS) -> dict | None:
    """The first person to message the bot privately: {"id", "first_name", "username"}."""
    telegram(token, "deleteWebhook")
    deadline = time.monotonic() + timeout
    offset = None
    while time.monotonic() < deadline:
        params = {"timeout": 20, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        for update in telegram(token, "getUpdates", **params):
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            if message.get("chat", {}).get("type") == "private" and message.get("from"):
                telegram(token, "getUpdates", offset=offset, timeout=0)  # so the bot doesn't answer it later
                return message["from"]
    return None


def detect_timezone() -> str | None:
    candidates = [os.getenv("TZ", "")]
    try:
        candidates.append(str(Path("/etc/localtime").resolve()).split("zoneinfo/", 1)[1])
    except (IndexError, OSError):
        pass
    for name in candidates:
        try:
            if name:
                ZoneInfo(name)
                return name
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return None


# --- .env ---


def update_env(path: Path, values: dict[str, str]) -> None:
    """Set keys in a .env file, keeping its comments and other settings."""
    if not path.exists():
        if EXAMPLE_FILE.exists():
            shutil.copy(EXAMPLE_FILE, path)
        else:
            path.write_text("")
    lines = path.read_text().splitlines()
    remaining = dict(values)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    lines += [f"{key}={value}" for key, value in remaining.items()]
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)  # it holds your API keys


# --- the conversation ---


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    shown = f" [{default}]" if default and not secret else (" [keep current]" if default else "")
    reader = getpass.getpass if secret else input
    answer = reader(f"{prompt}{shown}: ").strip()
    return answer or default


def yes(prompt: str, default: bool = True) -> bool:
    answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not answer else answer.startswith("y")


def step(n: int, title: str) -> None:
    print(f"\n\033[1m{n}. {title}\033[0m")


def main() -> None:
    current = {k: v for k, v in dotenv_values(ENV_FILE).items() if v} if ENV_FILE.exists() else {}
    values: dict[str, str] = {}
    print("\033[1mClaudeBot setup\033[0m: about 5 minutes. Press Ctrl+C any time to stop.")

    step(1, "Claude API key")
    print("   Create one at https://console.anthropic.com/settings/keys (API use is billed separately")
    print("   from Claude Pro/Max; for one person it's usually a few dollars a month).")
    while True:
        key = ask("   Paste your API key", current.get("ANTHROPIC_API_KEY", ""), secret=True)
        try:
            check_anthropic(key)
            print("   ✓ Key works")
            values["ANTHROPIC_API_KEY"] = key
            break
        except SetupError as e:
            print(f"   ✗ {e}")
        except anthropic.APIConnectionError:
            print("   ! Couldn't reach Anthropic to check it; saving it anyway.")
            values["ANTHROPIC_API_KEY"] = key
            break

    step(2, "Telegram bot")
    print("   In Telegram, message @BotFather, send /newbot, and pick a name and a username")
    print("   ending in 'bot'. It gives you a token.")
    while True:
        token = ask("   Paste the bot token", current.get("TELEGRAM_BOT_TOKEN", ""), secret=True)
        try:
            username = check_telegram(token)
            print(f"   ✓ Connected to @{username}")
            values["TELEGRAM_BOT_TOKEN"] = token
            break
        except SetupError as e:
            print(f"   ✗ {e}")

    step(3, "You")
    owner = None
    if current.get("TELEGRAM_OWNER_ID") and yes(f"   Keep the owner already set ({current['TELEGRAM_OWNER_ID']})?"):
        values["TELEGRAM_OWNER_ID"] = current["TELEGRAM_OWNER_ID"]
    else:
        print(f"   Open https://t.me/{username} and send it any message. Waiting...")
        try:
            owner = wait_for_owner(token)
        except KeyboardInterrupt:
            owner = None
        if owner and yes(f"   Found {owner.get('first_name', '')} (@{owner.get('username', '-')}). Is that you?"):
            values["TELEGRAM_OWNER_ID"] = str(owner["id"])
            print("   ✓ ClaudeBot will only ever talk to you")
        else:
            print("   Skipped. When the bot starts it prints a pairing code; send it /start <code>.")
            values["TELEGRAM_OWNER_ID"] = ""  # clear any old owner, or pairing would never start
            owner = None
    name = ask("   What should ClaudeBot call you?",
               current.get("CLAUDEBOT_OWNER_NAME") or (owner or {}).get("first_name", "") or "friend")
    values["CLAUDEBOT_OWNER_NAME"] = name
    timezone = ask("   Your time zone", current.get("CLAUDEBOT_TIMEZONE") or detect_timezone() or "America/New_York")
    while True:
        try:
            ZoneInfo(timezone)
            break
        except (ZoneInfoNotFoundError, ValueError):
            timezone = ask("   Unknown time zone. Use a name like America/Chicago or Europe/London")
    values["CLAUDEBOT_TIMEZONE"] = timezone

    update_env(ENV_FILE, values)
    print(f"\n✓ Saved to {ENV_FILE.resolve()}")
    print("\nNext: start ClaudeBot and message it. It walks you through the rest (where you live,")
    print("your job, the daily brief) and connects Gmail and Calendar right from the chat (/connect).")
    if yes("\nStart ClaudeBot now?"):
        for key, value in values.items():
            os.environ[key] = value
        from .__main__ import run

        run()
    else:
        print("Start it any time with: python -m claudebot")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nSetup stopped. Run it again any time: python -m claudebot setup")
