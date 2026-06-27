"""Telegram command handlers.

Thin layer only: parse the command, delegate any game logic to ``engine``, and
format the reply. Persistence goes through the injected ``CharacterStore`` (kept
in ``application.bot_data["store"]``). No game logic lives here.
"""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from engine import (
    ActionRoll,
    Answer,
    Character,
    Odds,
    Outcome,
    YesNoResult,
    ask_yes_no,
    burn_momentum,
    draw_from,
    greeting,
    list_tables,
    new_character,
    random_table,
    reset_momentum,
    roll_action,
    set_field,
    stat_value,
    table_title,
)
from engine.character import (
    MOMENTUM_RESET,
    SETTABLE_FIELDS,
    STAT_MAX,
    STAT_MIN,
    STAT_NAMES,
)
from storage import CharacterExists, CharacterStore

START_TEXT = (
    "Welcome to the Ironsworn bot.\n"
    "{greeting}\n\n"
    "Create a character with /new, then /roll <stat> to act.\n"
    "Use /help to see all commands."
)

_ODDS_NAMES = ", ".join(o.name.lower() for o in Odds)

HELP_TEXT = (
    "Ironsworn bot — available commands:\n"
    "/start - introduction\n"
    "/help - this help message\n"
    "/new - create your character (step by step)\n"
    "/me - show your character sheet\n"
    "/set <track> <value> - change health/spirit/supply/momentum\n"
    "/roll <stat> [adds] [burn] - action roll using your character\n"
    "/ask <odds> <question> - ask the Oracle a yes/no question\n"
    "/oracle [table] - draw a spark of inspiration\n\n"
    f"  stat: {', '.join(STAT_NAMES)}\n"
    f"  odds: {_ODDS_NAMES}\n"
    "  examples: /roll iron   /roll iron burn   /ask likely Are we noticed?"
)

ROLL_USAGE = (
    "Usage: /roll <stat> [adds] [burn]\n"
    f"  stat: {', '.join(STAT_NAMES)}\n"
    "  adds: optional non-negative bonus; burn: spend momentum\n"
    "  examples: /roll iron   /roll heart 1   /roll iron burn"
)

ASK_USAGE = (
    "Usage: /ask <odds> <question>\n"
    f"  odds: {_ODDS_NAMES}\n"
    "  example: /ask likely Are we noticed?"
)

SET_USAGE = (
    "Usage: /set <track> <value>\n"
    f"  track: {', '.join(SETTABLE_FIELDS)}\n"
    "  example: /set supply 3"
)

NO_CHARACTER = "You don't have a character yet. Use /new to create one."

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

# Conversation states for /new.
NAME, EDGE, HEART, IRON, SHADOW, WITS = range(6)


def _store(context: ContextTypes.DEFAULT_TYPE) -> CharacterStore:
    """Return the character store injected at application startup."""
    return context.bot_data["store"]


def _signed(value: int) -> str:
    """Format an integer with an explicit sign (e.g. +2, -3)."""
    return f"{value:+d}"


# --- simple commands ---------------------------------------------------------


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


async def me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /me: show the caller's character sheet."""
    if update.message is None:
        return
    character = await _store(context).get(
        update.effective_chat.id, update.effective_user.id
    )
    if character is None:
        await update.message.reply_text(NO_CHARACTER)
        return
    await update.message.reply_text(_format_sheet(character))


async def set_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set <track> <value>: update a track or momentum within bounds."""
    if update.message is None:
        return

    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text(SET_USAGE)
        return

    field = args[0].strip().lower()
    if field not in SETTABLE_FIELDS:
        await update.message.reply_text(SET_USAGE)
        return
    try:
        value = int(args[1])
    except ValueError:
        await update.message.reply_text(SET_USAGE)
        return

    store = _store(context)
    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    character = await store.get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(NO_CHARACTER)
        return

    try:
        updated = set_field(character, field, value)
    except ValueError as error:
        await update.message.reply_text(str(error))
        return

    await store.update(chat_id, user_id, updated)
    await update.message.reply_text(
        f"{field} set to {value}.\n\n{_format_sheet(updated)}"
    )


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /roll <stat> [adds] [burn]: roll using the caller's character."""
    if update.message is None:
        return

    parsed = _parse_roll_args(context.args or [])
    if parsed is None:
        await update.message.reply_text(ROLL_USAGE)
        return
    stat_name, adds, burn = parsed

    store = _store(context)
    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    character = await store.get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(NO_CHARACTER)
        return

    try:
        value = stat_value(character, stat_name)
    except ValueError as error:
        await update.message.reply_text(f"{error}\n\n{ROLL_USAGE}")
        return

    result = roll_action(value, adds)
    if burn:
        result = burn_momentum(result, character.momentum)
        await store.update(chat_id, user_id, reset_momentum(character))

    await update.message.reply_text(_format_roll(result, stat_name))


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


# --- /new conversation -------------------------------------------------------


async def new_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin character creation, unless one already exists."""
    if update.message is None:
        return ConversationHandler.END

    existing = await _store(context).get(
        update.effective_chat.id, update.effective_user.id
    )
    if existing is not None:
        await update.message.reply_text(
            "You already have a character. Use /me to view it or /set to change it."
        )
        return ConversationHandler.END

    context.user_data["new_char"] = {}
    await update.message.reply_text(
        "Let's forge a character! What is their name? (/cancel to abort)"
    )
    return NAME


async def new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect the character name."""
    if update.message is None:
        return NAME
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Please enter a non-empty name.")
        return NAME
    context.user_data["new_char"]["name"] = name
    await update.message.reply_text(_stat_prompt("edge"))
    return EDGE


def _stat_step(stat_name: str, this_state: int, next_prompt: str, next_state):
    """Build a conversation step that collects one stat in range 1-3."""

    async def step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.message is None:
            return this_state
        try:
            value = int((update.message.text or "").strip())
        except ValueError:
            await update.message.reply_text(_bad_stat_msg(stat_name))
            return this_state
        if not STAT_MIN <= value <= STAT_MAX:
            await update.message.reply_text(_bad_stat_msg(stat_name))
            return this_state

        context.user_data["new_char"][stat_name] = value
        if next_state is None:
            return await _finish_new(update, context)
        await update.message.reply_text(_stat_prompt(next_prompt))
        return next_state

    return step


new_edge = _stat_step("edge", EDGE, "heart", HEART)
new_heart = _stat_step("heart", HEART, "iron", IRON)
new_iron = _stat_step("iron", IRON, "shadow", SHADOW)
new_shadow = _stat_step("shadow", SHADOW, "wits", WITS)
new_wits = _stat_step("wits", WITS, "", None)


async def _finish_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Build, persist, and confirm the new character."""
    data = context.user_data.pop("new_char", {})
    try:
        character = new_character(
            data["name"],
            data["edge"],
            data["heart"],
            data["iron"],
            data["shadow"],
            data["wits"],
        )
    except (KeyError, ValueError) as error:
        await update.message.reply_text(f"Could not create character: {error}")
        return ConversationHandler.END

    try:
        await _store(context).create(
            update.effective_chat.id, update.effective_user.id, character
        )
    except CharacterExists:
        await update.message.reply_text(
            "You already have a character. Use /me to view it."
        )
        return ConversationHandler.END

    await update.message.reply_text("Character created!\n\n" + _format_sheet(character))
    return ConversationHandler.END


async def new_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Abort character creation."""
    context.user_data.pop("new_char", None)
    if update.message is not None:
        await update.message.reply_text("Character creation cancelled.")
    return ConversationHandler.END


def build_new_handler() -> ConversationHandler:
    """Build the /new conversation handler (keyed per chat and per user)."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CommandHandler("new", new_start)],
        states={
            NAME: [MessageHandler(text, new_name)],
            EDGE: [MessageHandler(text, new_edge)],
            HEART: [MessageHandler(text, new_heart)],
            IRON: [MessageHandler(text, new_iron)],
            SHADOW: [MessageHandler(text, new_shadow)],
            WITS: [MessageHandler(text, new_wits)],
        },
        fallbacks=[CommandHandler("cancel", new_cancel)],
    )


# --- formatting helpers ------------------------------------------------------


def _stat_prompt(stat_name: str) -> str:
    return f"Set {stat_name} ({STAT_MIN}-{STAT_MAX}):"


def _bad_stat_msg(stat_name: str) -> str:
    return (
        f"Please enter a whole number from {STAT_MIN} to {STAT_MAX} "
        f"for {stat_name}."
    )


def _parse_roll_args(args: list[str]) -> tuple[str, int, bool] | None:
    """Parse /roll args into (stat_name, adds, burn), or None if malformed."""
    if not args:
        return None
    stat_name = args[0]
    adds = 0
    burn = False
    for token in args[1:]:
        if token.lower() == "burn":
            burn = True
            continue
        try:
            adds = int(token)
        except ValueError:
            return None
        if adds < 0:
            return None
    return stat_name, adds, burn


def _format_roll(result: ActionRoll, stat_name: str) -> str:
    """Render an action roll as a readable Telegram message."""
    challenge_a, challenge_b = result.challenge_dice
    natural = result.action_die + result.stat + result.adds

    natural_line = f"Action die {result.action_die} + stat {result.stat}"
    if result.adds:
        natural_line += f" + adds {result.adds}"

    lines = [f"🎲 Action roll — {stat_name}"]
    if result.burned:
        lines.append(f"{natural_line} = {natural}")
        lines.append(
            f"🔥 Burned momentum → score {result.action_score} "
            f"(momentum reset to {_signed(MOMENTUM_RESET)})"
        )
    else:
        capped = " (capped at 10)" if natural > result.action_score else ""
        lines.append(f"{natural_line} = score {result.action_score}{capped}")

    lines.append(f"Challenge dice: {challenge_a} | {challenge_b}")
    lines.append(f"Result: {_OUTCOME_LABELS[result.outcome]}")
    if result.is_match:
        lines.append(_MATCH_NOTE)
    return "\n".join(lines)


def _format_sheet(character: Character) -> str:
    """Render a character sheet as a readable Telegram message."""
    return "\n".join(
        [
            f"📜 {character.name}",
            (
                f"Edge {character.edge}  Heart {character.heart}  "
                f"Iron {character.iron}  Shadow {character.shadow}  "
                f"Wits {character.wits}"
            ),
            (
                f"Health {character.health}/5   Spirit {character.spirit}/5   "
                f"Supply {character.supply}/5"
            ),
            f"Momentum {_signed(character.momentum)} (reset {_signed(MOMENTUM_RESET)})",
        ]
    )


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
