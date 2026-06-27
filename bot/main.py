"""Bot entrypoint: wire up handlers and run polling.

Loads ``BOT_TOKEN`` from the environment (via a local ``.env`` when present),
builds the python-telegram-bot application, registers command handlers, and
starts long polling. No webhook.
"""

import os

from dotenv import load_dotenv
from telegram.ext import Application, ApplicationBuilder, CommandHandler

from bot.handlers import help_command, roll, start


def build_application(token: str) -> Application:
    """Build the Telegram application and register command handlers."""
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("roll", roll))
    return application


def main() -> None:
    """Load configuration and run the bot via long polling."""
    load_dotenv()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "BOT_TOKEN is not set. Copy .env.example to .env and set BOT_TOKEN, "
            "or export it in your environment."
        )

    application = build_application(token)
    application.run_polling()


if __name__ == "__main__":
    main()
