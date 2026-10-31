"""Start ClaudeBot.

    python -m claudebot          run the bot
    python -m claudebot setup    guided setup: checks your keys and writes .env
    python -m claudebot google   connect Google from a computer with a browser
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
    budget, group_budget = config.monthly_budget_usd, config.group_monthly_budget_usd
    if budget is not None and (group_budget is None or group_budget >= budget):
        log.warning(
            "GROUP_MONTHLY_BUDGET_USD should be below MONTHLY_BUDGET_USD, or group answers can use up "
            "the whole budget and lock you out of your own assistant."
        )
    # Settings changed in chat restart the bot in-process, so they apply everywhere.
    while TelegramBot(config).run():
        log.info("Restarting with your new settings...")
        config = load_config()


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
    elif command == "google":
        from .google_auth import main as google

        google()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
