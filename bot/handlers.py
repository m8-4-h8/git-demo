"""Telegram command handlers.

Thin layer only: parse the command, delegate any game logic to ``engine``, and
format the reply. No game logic lives here.
"""

from telegram import Update
from telegram.ext import ContextTypes

from engine import greeting

START_TEXT = (
    "Welcome to the Ironsworn bot.\n"
    "{greeting}\n\n"
    "This is v0 — only /start and /help work for now.\n"
    "Use /help to see available commands."
)

HELP_TEXT = (
    "Ironsworn bot — available commands:\n"
    "/start - introduction\n"
    "/help - this help message\n\n"
    "More commands will arrive in future versions."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start: greet the player with engine-owned text."""
    if update.message is None:
        return
    await update.message.reply_text(START_TEXT.format(greeting=greeting()))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help: list available commands."""
    if update.message is None:
        return
    await update.message.reply_text(HELP_TEXT)
