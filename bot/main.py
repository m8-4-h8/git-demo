"""Bot entrypoint: wire up handlers and run polling.

Loads ``BOT_TOKEN`` from the environment (via a local ``.env`` when present),
builds the python-telegram-bot application, registers command handlers, opens
the character and preference stores, and starts long polling. No webhook.
"""

import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from bot.i18n import resolve_lang, t

logger = logging.getLogger(__name__)

from bot.handlers import (
    ask,
    build_background_handler,
    build_item_handler,
    build_new_handler,
    build_track_handler,
    build_vow_handler,
    gm,
    gm_callback,
    guide,
    help_command,
    language_callback,
    language_command,
    me,
    menu_callback,
    menu_command,
    oracle,
    roll,
    set_value,
    start,
    track,
    tutorial,
    tutorial_callback,
    vow,
)
from bot.session_handlers import (
    build_session_create_handler,
    build_session_custom_handler,
    build_session_join_handler,
    session_callback,
    session_command,
)
from storage import (
    CharacterStore,
    GMStateStore,
    PreferenceStore,
    SessionStore,
    TrackStore,
    VowStore,
)

DEFAULT_DB_PATH = "ironsworn.db"


# Commands surfaced in Telegram's native "/" menu. Deliberately short: the UX
# is button-first, so only the essentials are advertised — the rest keep
# working as a hidden power-user fallback.
_MENU_COMMANDS = (
    "menu", "new", "me", "session", "help", "tutorial", "language", "cancel"
)


async def _register_commands(application: Application) -> None:
    """Publish the command menu (EN default + RU), without blocking startup."""
    for language_code in (None, "ru"):
        lang = language_code or "en"
        commands = [
            BotCommand(name, t(lang, f"cmd_{name}")) for name in _MENU_COMMANDS
        ]
        try:
            await application.bot.set_my_commands(
                commands, language_code=language_code
            )
        except Exception:  # noqa: BLE001 — cosmetic; never block startup
            logger.warning("Could not register the bot command menu", exc_info=True)


async def _post_init(application: Application) -> None:
    """Initialise the stores and the command menu before polling begins."""
    await application.bot_data["store"].init()
    await application.bot_data["prefs"].init()
    await application.bot_data["vows"].init()
    await application.bot_data["tracks"].init()
    await application.bot_data["gm_state"].init()
    await application.bot_data["sessions"].init()
    await _register_commands(application)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log any unhandled handler error and tell the player something broke.

    The player's language is taken from their Telegram client (no DB call, so
    this stays robust even if the failure was storage-related).
    """
    logger.error("Unhandled error while processing an update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        user = update.effective_user
        lang = resolve_lang(None, user.language_code if user else None)
        try:
            await update.effective_message.reply_text(t(lang, "error_generic"))
        except Exception:  # noqa: BLE001 — never let the error handler raise
            pass


def build_application(
    token: str,
    store: CharacterStore | None = None,
    prefs: PreferenceStore | None = None,
    vows: VowStore | None = None,
    tracks: TrackStore | None = None,
    gm_state: GMStateStore | None = None,
    sessions: SessionStore | None = None,
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
    if gm_state is None:
        gm_state = GMStateStore(db_path)
    if sessions is None:
        sessions = SessionStore(db_path)

    application = ApplicationBuilder().token(token).post_init(_post_init).build()
    application.bot_data["store"] = store
    application.bot_data["prefs"] = prefs
    application.bot_data["vows"] = vows
    application.bot_data["tracks"] = tracks
    application.bot_data["gm_state"] = gm_state
    application.bot_data["sessions"] = sessions

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("guide", guide))
    application.add_handler(CommandHandler("tutorial", tutorial))
    application.add_handler(CommandHandler("language", language_command))
    # Guided creation flows (command + button entry points).
    application.add_handler(build_new_handler())
    application.add_handler(build_vow_handler())
    application.add_handler(build_track_handler())
    application.add_handler(build_item_handler())
    application.add_handler(build_background_handler())
    # Multiplayer sessions: lobby password flows + the custom-action flow.
    application.add_handler(build_session_create_handler())
    application.add_handler(build_session_join_handler())
    application.add_handler(build_session_custom_handler())
    application.add_handler(CommandHandler("session", session_command))
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("set", set_value))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("vow", vow))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("gm", gm))
    # Inline-keyboard navigation (the button-first UX).
    application.add_handler(
        CallbackQueryHandler(
            menu_callback, pattern=r"^(menu|move|roll|oracle|char|vow|track|help):"
        )
    )
    application.add_handler(CallbackQueryHandler(session_callback, pattern=r"^sess:"))
    application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang:"))
    application.add_handler(CallbackQueryHandler(tutorial_callback, pattern=r"^tut:"))
    application.add_handler(CallbackQueryHandler(gm_callback, pattern=r"^gm:"))
    application.add_error_handler(_on_error)
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
