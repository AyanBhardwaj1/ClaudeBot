"""Start ClaudeBot.

    python -m claudebot          run the bot
    python -m claudebot setup    guided setup: checks your keys and writes .env
    python -m claudebot google   connect Google from a computer with a browser
    python -m claudebot health   exit 0 if the running bot checked in recently (for Docker)
    python -m claudebot web-login  print a one-time sign-in link for the web and desktop app
"""

import logging
import os
import sys

from .config import load_config


def run() -> None:
    from .bot import TelegramBot

    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every Telegram poll
    log = logging.getLogger("claudebot")

    config = load_config()
    missing = [
        name
        for name, value in [
            ("TELEGRAM_BOT_TOKEN", config.telegram_token),
            ("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY")),
        ]
        if not value
    ]
    if missing:
        sys.exit(f"Missing settings: {', '.join(missing)}. Run `python -m claudebot setup` to set them up.")
    # Settings changed in chat restart the bot in-process, so they apply everywhere.
    while TelegramBot(config).run():
        log.info("Restarting with your new settings...")
        config = load_config()


HEALTH_FILE = "alive"
HEALTH_MAX_AGE = 300  # seconds: the bot writes the file every minute


def healthy(data_dir, now: float | None = None) -> bool:
    """The bot's event loop wrote its heartbeat file recently (it isn't stuck or dead)."""
    import time

    path = data_dir / HEALTH_FILE
    return path.exists() and (now or time.time()) - path.stat().st_mtime < HEALTH_MAX_AGE


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "run":
        run()
    elif command == "setup":
        from .setup_wizard import main as setup

        try:
            setup()
        except KeyboardInterrupt:
            sys.exit("\nSetup stopped. Run it again any time: python -m claudebot setup")
    elif command == "health":
        sys.exit(0 if healthy(load_config().data_dir) else 1)
    elif command == "web-login":
        from .db import Database
        from .web import auth, check_public_url, login_url

        config = load_config()
        if config.web_port is None:
            sys.exit("The web app is off (WEB_PORT=off).")
        try:
            check_public_url(config)
        except RuntimeError as e:
            sys.exit(str(e))
        print("Your one-time sign-in link (works once, for 10 minutes; don't share it):\n")
        print("    " + login_url(config, auth.new_login_token(Database(config.db_path))) + "\n")
    elif command == "google":
        from .google_auth import main as google

        google()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
