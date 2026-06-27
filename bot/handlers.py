"""Telegram command handlers.

Thin layer only: parse the command, delegate any game logic to ``engine``, and
format the reply. No game logic lives here.
"""

from telegram import Update
from telegram.ext import ContextTypes

from engine import ActionRoll, Outcome, greeting, roll_action
from engine.rolls import STAT_MAX, STAT_MIN

START_TEXT = (
    "Welcome to the Ironsworn bot.\n"
    "{greeting}\n\n"
    "This is v0 — you can already make action rolls.\n"
    "Use /help to see available commands."
)

HELP_TEXT = (
    "Ironsworn bot — available commands:\n"
    "/start - introduction\n"
    "/help - this help message\n"
    "/roll <stat> [adds] - make an action roll\n\n"
    f"  stat: 0-{STAT_MAX}    adds: optional bonus (default 0)\n"
    "  example: /roll 2 1"
)

ROLL_USAGE = (
    "Usage: /roll <stat> [adds]\n"
    f"  stat must be {STAT_MIN}-{STAT_MAX}, adds is an optional non-negative bonus.\n"
    "  example: /roll 2 1"
)

_OUTCOME_LABELS = {
    Outcome.STRONG: "💪 Strong hit",
    Outcome.WEAK: "👍 Weak hit",
    Outcome.MISS: "💥 Miss",
}

_MATCH_NOTE = (
    "⚡ Match! A dramatic twist — a boost on a hit, a complication on a miss."
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


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /roll <stat> [adds]: resolve an action roll via the engine."""
    if update.message is None:
        return

    parsed = _parse_roll_args(context.args or [])
    if parsed is None:
        await update.message.reply_text(ROLL_USAGE)
        return

    stat, adds = parsed
    try:
        result = roll_action(stat, adds)
    except ValueError as error:
        await update.message.reply_text(f"{error}\n\n{ROLL_USAGE}")
        return

    await update.message.reply_text(_format_roll(result))


def _parse_roll_args(args: list[str]) -> tuple[int, int] | None:
    """Parse the /roll arguments into (stat, adds), or None if malformed."""
    if not 1 <= len(args) <= 2:
        return None
    try:
        stat = int(args[0])
        adds = int(args[1]) if len(args) == 2 else 0
    except ValueError:
        return None
    return stat, adds


def _format_roll(result: ActionRoll) -> str:
    """Render an action roll as a readable Telegram message."""
    raw_total = result.action_die + result.stat + result.adds
    capped = " (capped at 10)" if raw_total > result.action_score else ""
    challenge_a, challenge_b = result.challenge_dice

    lines = [
        "🎲 Action roll",
        (
            f"Action die {result.action_die} + stat {result.stat} "
            f"+ adds {result.adds} = score {result.action_score}{capped}"
        ),
        f"Challenge dice: {challenge_a} | {challenge_b}",
        f"Result: {_OUTCOME_LABELS[result.outcome]}",
    ]
    if result.is_match:
        lines.append(_MATCH_NOTE)
    return "\n".join(lines)
