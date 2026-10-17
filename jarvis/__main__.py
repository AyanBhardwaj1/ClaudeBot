"""Start Jarvis: `python -m jarvis`."""

import logging
import os
import sys

from .bot import JarvisBot
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
    if config.owner_id is None:
        logging.warning(
            "TELEGRAM_OWNER_ID is not set. Message the bot once to get your ID, then set it and restart."
        )
    JarvisBot(config).run()


if __name__ == "__main__":
    main()
