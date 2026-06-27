"""Bot entrypoint: wire up handlers and run polling.

Loads ``BOT_TOKEN`` from the environment (via a local ``.env`` when present),
builds the python-telegram-bot application, registers command handlers, opens
the character store, and starts long polling. No webhook.
"""

import os

from dotenv import load_dotenv
from telegram.ext import Application, ApplicationBuilder, CommandHandler

from bot.handlers import (
    ask,
    build_new_handler,
    help_command,
    me,
    oracle,
    roll,
    set_value,
    start,
)
from storage import CharacterStore

DEFAULT_DB_PATH = "ironsworn.db"


async def _post_init(application: Application) -> None:
    """Initialise the character store before polling begins."""
    await application.bot_data["store"].init()


def build_application(
    token: str, store: CharacterStore | None = None
) -> Application:
    """Build the Telegram application and register command handlers."""
    if store is None:
        store = CharacterStore(os.environ.get("DB_PATH", DEFAULT_DB_PATH))

    application = (
        ApplicationBuilder().token(token).post_init(_post_init).build()
    )
    application.bot_data["store"] = store

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(build_new_handler())
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("set", set_value))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("oracle", oracle))
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
