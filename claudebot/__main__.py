"""Start ClaudeBot: `python -m claudebot`."""

import logging
import os
import sys

from .bot import TelegramBot
from .config import load_config


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every Telegram poll

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
        sys.exit(f"Missing settings: {', '.join(missing)}. Copy .env.example to .env and fill them in.")
    budget, group_budget = config.monthly_budget_usd, config.group_monthly_budget_usd
    if budget is not None and (group_budget is None or group_budget >= budget):
        logging.warning(
            "GROUP_MONTHLY_BUDGET_USD should be below MONTHLY_BUDGET_USD, or group answers can use up "
            "the whole budget and lock you out of your own assistant."
        )
    if config.owner_id is None:
        logging.warning(
            "TELEGRAM_OWNER_ID is not set. Message the bot once to get your ID, then set it and restart."
        )
    TelegramBot(config).run()


if __name__ == "__main__":
    main()
