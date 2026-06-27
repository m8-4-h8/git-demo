"""Telegram command handlers.

Thin layer only: parse the command, delegate any game logic to ``engine``, and
format the reply. No game logic lives here.
"""

from telegram import Update
from telegram.ext import ContextTypes

from engine import (
    ActionRoll,
    Answer,
    Odds,
    Outcome,
    YesNoResult,
    ask_yes_no,
    draw_from,
    greeting,
    list_tables,
    random_table,
    roll_action,
    table_title,
)
from engine.rolls import STAT_MAX, STAT_MIN

START_TEXT = (
    "Welcome to the Ironsworn bot.\n"
    "{greeting}\n\n"
    "This is v0 — you can already make action rolls.\n"
    "Use /help to see available commands."
)

_ODDS_NAMES = ", ".join(o.name.lower() for o in Odds)

HELP_TEXT = (
    "Ironsworn bot — available commands:\n"
    "/start - introduction\n"
    "/help - this help message\n"
    "/roll <stat> [adds] - make an action roll\n"
    "/ask <odds> <question> - ask the Oracle a yes/no question\n"
    "/oracle [table] - draw a spark of inspiration\n\n"
    f"  stat: 0-{STAT_MAX}    adds: optional bonus (default 0)\n"
    f"  odds: {_ODDS_NAMES}\n"
    "  examples: /roll 2 1   /ask likely Are we noticed?   /oracle npc"
)

ROLL_USAGE = (
    "Usage: /roll <stat> [adds]\n"
    f"  stat must be {STAT_MIN}-{STAT_MAX}, adds is an optional non-negative bonus.\n"
    "  example: /roll 2 1"
)

ASK_USAGE = (
    "Usage: /ask <odds> <question>\n"
    f"  odds: {_ODDS_NAMES}\n"
    "  example: /ask likely Are we noticed?"
)

_ANSWER_LABELS = {
    Answer.YES: "✅ Yes",
    Answer.NO: "❌ No",
}

_EXTREME_NOTE = "⚡ Extreme result — an unexpected, dramatic twist!"

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


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ask <odds> <question>: answer with the yes/no Oracle."""
    if update.message is None:
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(ASK_USAGE)
        return

    odds_name, question = args[0], " ".join(args[1:]).strip()
    try:
        result = ask_yes_no(odds_name)
    except ValueError as error:
        await update.message.reply_text(f"{error}\n\n{ASK_USAGE}")
        return

    await update.message.reply_text(_format_ask(result, question))


async def oracle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /oracle [table]: draw a random spark of inspiration."""
    if update.message is None:
        return

    args = context.args or []
    tables = list_tables()
    if not tables:
        await update.message.reply_text("No oracle tables are available.")
        return

    if args:
        table = args[0]
        if table not in tables:
            available = ", ".join(tables)
            await update.message.reply_text(
                f"Unknown table '{table}'. Available: {available}"
            )
            return
    else:
        table = random_table()

    await update.message.reply_text(_format_oracle(table))


def _format_ask(result: YesNoResult, question: str) -> str:
    """Render a yes/no oracle answer as a readable Telegram message."""
    odds_label = result.odds.name.replace("_", " ").title()
    lines = ["🔮 Oracle"]
    if question:
        lines.append(f"Q: {question}")
    lines.append(f"Odds: {odds_label} ({result.chance}% yes) — rolled {result.roll}")
    lines.append(f"Answer: {_ANSWER_LABELS[result.answer]}")
    if result.is_extreme:
        lines.append(_EXTREME_NOTE)
    return "\n".join(lines)


def _format_oracle(table: str) -> str:
    """Render an inspiration draw as a readable Telegram message."""
    return f"🔮 {table_title(table)}: {draw_from(table)}"
