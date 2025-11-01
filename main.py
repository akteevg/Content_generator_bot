"""Run the Telegram bot in polling mode."""

from __future__ import annotations

import logging

from content_bot.bot_app import create_app


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    bot = create_app()
    bot.infinity_polling(timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    main()

