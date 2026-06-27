"""Bot entrypoint: wire up handlers and run polling.

Loads ``BOT_TOKEN`` from the environment (via a local ``.env`` when present),
builds the python-telegram-bot application, registers command handlers, opens
the character and preference stores, and starts long polling. No webhook.
"""

import os

from dotenv import load_dotenv
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
)

from bot.handlers import (
    ask,
    build_new_handler,
    guide,
    help_command,
    language_callback,
    language_command,
    me,
    oracle,
    roll,
    set_value,
    start,
    track,
    tutorial,
    tutorial_callback,
    vow,
)
from storage import CharacterStore, PreferenceStore, TrackStore, VowStore

DEFAULT_DB_PATH = "ironsworn.db"


async def _post_init(application: Application) -> None:
    """Initialise the stores before polling begins."""
    await application.bot_data["store"].init()
    await application.bot_data["prefs"].init()
    await application.bot_data["vows"].init()
    await application.bot_data["tracks"].init()


def build_application(
    token: str,
    store: CharacterStore | None = None,
    prefs: PreferenceStore | None = None,
    vows: VowStore | None = None,
    tracks: TrackStore | None = None,
) -> Application:
    """Build the Telegram application and register command handlers."""
    db_path = os.environ.get("DB_PATH", DEFAULT_DB_PATH)
    if store is None:
        store = CharacterStore(db_path)
    if prefs is None:
        prefs = PreferenceStore(db_path)
    if vows is None:
        vows = VowStore(db_path)
    if tracks is None:
        tracks = TrackStore(db_path)

    application = ApplicationBuilder().token(token).post_init(_post_init).build()
    application.bot_data["store"] = store
    application.bot_data["prefs"] = prefs
    application.bot_data["vows"] = vows
    application.bot_data["tracks"] = tracks

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("guide", guide))
    application.add_handler(CommandHandler("tutorial", tutorial))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(build_new_handler())
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("set", set_value))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("vow", vow))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang:"))
    application.add_handler(CallbackQueryHandler(tutorial_callback, pattern=r"^tut:"))
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
