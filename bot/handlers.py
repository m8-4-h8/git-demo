"""Telegram command handlers.

Thin layer only: parse the command, delegate game logic to ``engine``,
persistence to ``storage``, and render replies via the ``i18n`` text catalog.
All user-facing strings are localized (RU/EN); the language is resolved per
player from their stored preference, falling back to their Telegram client
language. No game logic lives here.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.i18n import (
    BURN_WORDS,
    LANGS,
    ODDS_ALIASES,
    STAT_ALIASES,
    TRACK_ALIASES,
    resolve_lang,
    t,
)
from engine import (
    ActionRoll,
    Answer,
    Character,
    Odds,
    Outcome,
    YesNoResult,
    ask_yes_no,
    bounds_for,
    burn_momentum,
    draw_from,
    list_tables,
    new_character,
    random_table,
    reset_momentum,
    roll_action,
    set_field,
    stat_value,
    table_title,
)
from engine.character import MOMENTUM_RESET, STAT_MAX, STAT_MIN
from storage import CharacterExists

# Conversation states for /new.
NAME, EDGE, HEART, IRON, SHADOW, WITS = range(6)

_OUTCOME_KEYS = {
    Outcome.STRONG: "outcome_strong",
    Outcome.WEAK: "outcome_weak",
    Outcome.MISS: "outcome_miss",
}

_TUTORIAL_PAGES = ("tut_1", "tut_2", "tut_3", "tut_4")


# --- shared helpers ----------------------------------------------------------


def _store(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["store"]


def _prefs(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["prefs"]


def _ids(update: Update) -> tuple[int, int]:
    return update.effective_chat.id, update.effective_user.id


async def _lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Resolve the player's language (cached per session in user_data)."""
    cached = context.user_data.get("lang")
    if cached:
        return cached
    chat_id, user_id = _ids(update)
    stored = await _prefs(context).get_language(chat_id, user_id)
    code = update.effective_user.language_code if update.effective_user else None
    lang = resolve_lang(stored, code)
    context.user_data["lang"] = lang
    return lang


# --- informational commands --------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    await update.message.reply_text(t(lang, "start"), parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    await update.message.reply_text(t(lang, "help"))


async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    await update.message.reply_text(t(lang, "guide"), parse_mode=ParseMode.MARKDOWN)


# --- character commands ------------------------------------------------------


async def me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    character = await _store(context).get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(t(lang, "no_character"))
        return
    await update.message.reply_text(_format_sheet(character, lang))


async def set_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)

    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text(t(lang, "set_usage"))
        return

    field = TRACK_ALIASES.get(args[0].strip().lower())
    if field is None:
        await update.message.reply_text(t(lang, "set_unknown", field=args[0]))
        return
    try:
        value = int(args[1])
    except ValueError:
        await update.message.reply_text(t(lang, "set_usage"))
        return

    low, high = bounds_for(field)
    if not low <= value <= high:
        await update.message.reply_text(
            t(lang, "set_out_of_bounds", field=_field_label(field, lang),
              low=low, high=high)
        )
        return

    chat_id, user_id = _ids(update)
    store = _store(context)
    character = await store.get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(t(lang, "no_character"))
        return

    updated = set_field(character, field, value)
    await store.update(chat_id, user_id, updated)
    await update.message.reply_text(
        t(lang, "set_done", field=_field_label(field, lang), value=value)
        + "\n\n"
        + _format_sheet(updated, lang)
    )


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)

    parsed = _parse_roll_args(context.args or [])
    if parsed is None:
        await update.message.reply_text(t(lang, "roll_usage"))
        return
    stat_token, adds, burn = parsed

    stat_name = STAT_ALIASES.get(stat_token.strip().lower())
    if stat_name is None:
        await update.message.reply_text(t(lang, "roll_usage"))
        return

    chat_id, user_id = _ids(update)
    store = _store(context)
    character = await store.get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(t(lang, "no_character"))
        return

    result = roll_action(stat_value(character, stat_name), adds)
    if burn:
        result = burn_momentum(result, character.momentum)
        await store.update(chat_id, user_id, reset_momentum(character))

    await update.message.reply_text(_format_roll(result, stat_name, lang))


# --- oracle commands ---------------------------------------------------------


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)

    args = context.args or []
    if not args:
        await update.message.reply_text(t(lang, "ask_usage"))
        return

    odds_name = ODDS_ALIASES.get(args[0].strip().lower())
    if odds_name is None:
        await update.message.reply_text(t(lang, "ask_usage"))
        return

    question = " ".join(args[1:]).strip()
    result = ask_yes_no(odds_name)
    await update.message.reply_text(_format_ask(result, question, lang))


async def oracle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)

    args = context.args or []
    tables = list_tables()
    if not tables:
        await update.message.reply_text(t(lang, "oracle_none"))
        return

    if args:
        table = args[0]
        if table not in tables:
            await update.message.reply_text(
                t(lang, "oracle_unknown_table", table=table,
                  available=", ".join(tables))
            )
            return
    else:
        table = random_table()

    await update.message.reply_text(
        t(lang, "oracle_line", title=table_title(table), entry=draw_from(table))
    )


# --- language ----------------------------------------------------------------


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = context.args or []
    if args and args[0].strip().lower() in LANGS:
        await _set_language(update, context, args[0].strip().lower())
        return
    lang = await _lang(update, context)
    await update.message.reply_text(
        t(lang, "language_current", lang=lang.upper()),
        reply_markup=_language_keyboard(lang),
    )


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    choice = query.data.split(":", 1)[1]
    if choice not in LANGS:
        return
    chat_id, user_id = _ids(update)
    await _prefs(context).set_language(chat_id, user_id, choice)
    context.user_data["lang"] = choice
    await query.edit_message_text(t(choice, "language_set", lang=choice.upper()))


async def _set_language(
    update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str
) -> None:
    chat_id, user_id = _ids(update)
    await _prefs(context).set_language(chat_id, user_id, choice)
    context.user_data["lang"] = choice
    await update.message.reply_text(t(choice, "language_set", lang=choice.upper()))


def _language_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(t(lang, "btn_ru"), callback_data="lang:ru"),
            InlineKeyboardButton(t(lang, "btn_en"), callback_data="lang:en"),
        ]]
    )


# --- tutorial (inline paged walkthrough) -------------------------------------


async def tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    await update.message.reply_text(
        t(lang, _TUTORIAL_PAGES[0]),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_tutorial_keyboard(0, lang),
    )


async def tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    lang = await _lang(update, context)
    try:
        page = int(query.data.split(":", 1)[1])
    except ValueError:
        return
    page = max(0, min(page, len(_TUTORIAL_PAGES) - 1))
    await query.edit_message_text(
        t(lang, _TUTORIAL_PAGES[page]),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_tutorial_keyboard(page, lang),
    )


def _tutorial_keyboard(page: int, lang: str) -> InlineKeyboardMarkup | None:
    last = len(_TUTORIAL_PAGES) - 1
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"tut:{page - 1}"))
    if page < last:
        key = "btn_play" if page == last - 1 else "btn_next"
        row.append(InlineKeyboardButton(t(lang, key), callback_data=f"tut:{page + 1}"))
    return InlineKeyboardMarkup([row]) if row else None


# --- /new conversation -------------------------------------------------------


async def new_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    if await _store(context).get(chat_id, user_id) is not None:
        await update.message.reply_text(t(lang, "new_already_exists"))
        return ConversationHandler.END
    context.user_data["new_char"] = {}
    await update.message.reply_text(t(lang, "new_intro"))
    return NAME


async def new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return NAME
    lang = await _lang(update, context)
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text(t(lang, "new_empty_name"))
        return NAME
    context.user_data["new_char"]["name"] = name
    await update.message.reply_text(_stat_prompt("edge", lang))
    return EDGE


def _stat_step(stat_name: str, this_state: int, next_prompt: str, next_state):
    """Build a conversation step that collects one stat in range 1-3."""

    async def step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.message is None:
            return this_state
        lang = await _lang(update, context)
        try:
            value = int((update.message.text or "").strip())
        except ValueError:
            await update.message.reply_text(_bad_stat(stat_name, lang))
            return this_state
        if not STAT_MIN <= value <= STAT_MAX:
            await update.message.reply_text(_bad_stat(stat_name, lang))
            return this_state

        context.user_data["new_char"][stat_name] = value
        if next_state is None:
            return await _finish_new(update, context)
        await update.message.reply_text(_stat_prompt(next_prompt, lang))
        return next_state

    return step


new_edge = _stat_step("edge", EDGE, "heart", HEART)
new_heart = _stat_step("heart", HEART, "iron", IRON)
new_iron = _stat_step("iron", IRON, "shadow", SHADOW)
new_shadow = _stat_step("shadow", SHADOW, "wits", WITS)
new_wits = _stat_step("wits", WITS, "", None)


async def _finish_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = await _lang(update, context)
    data = context.user_data.pop("new_char", {})
    try:
        character = new_character(
            data["name"], data["edge"], data["heart"],
            data["iron"], data["shadow"], data["wits"],
        )
    except (KeyError, ValueError) as error:
        await update.message.reply_text(t(lang, "new_failed", error=error))
        return ConversationHandler.END

    chat_id, user_id = _ids(update)
    try:
        await _store(context).create(chat_id, user_id, character)
    except CharacterExists:
        await update.message.reply_text(t(lang, "new_already_exists"))
        return ConversationHandler.END

    await update.message.reply_text(
        t(lang, "new_created") + "\n\n" + _format_sheet(character, lang)
    )
    return ConversationHandler.END


async def new_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = await _lang(update, context)
    context.user_data.pop("new_char", None)
    if update.message is not None:
        await update.message.reply_text(t(lang, "new_cancelled"))
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


def _stat_prompt(stat_name: str, lang: str) -> str:
    return t(lang, "new_ask_stat", stat=t(lang, f"stat_{stat_name}"),
             lo=STAT_MIN, hi=STAT_MAX)


def _bad_stat(stat_name: str, lang: str) -> str:
    return t(lang, "new_bad_stat", stat=t(lang, f"stat_{stat_name}"),
             lo=STAT_MIN, hi=STAT_MAX)


def _field_label(field: str, lang: str) -> str:
    key = "momentum" if field == "momentum" else f"track_{field}"
    return t(lang, key)


def _outcome_label(outcome: Outcome, lang: str) -> str:
    return t(lang, _OUTCOME_KEYS[outcome])


def _odds_label(odds: Odds, lang: str) -> str:
    return t(lang, f"odds_{odds.name.lower()}")


def _parse_roll_args(args: list[str]) -> tuple[str, int, bool] | None:
    """Parse /roll args into (stat_token, adds, burn), or None if malformed."""
    if not args:
        return None
    stat_token = args[0]
    adds = 0
    burn = False
    for token in args[1:]:
        if token.lower() in BURN_WORDS:
            burn = True
            continue
        try:
            adds = int(token)
        except ValueError:
            return None
        if adds < 0:
            return None
    return stat_token, adds, burn


def _format_roll(result: ActionRoll, stat_name: str, lang: str) -> str:
    natural = result.action_die + result.stat + result.adds
    natural_line = t(lang, "roll_natural", die=result.action_die, stat=result.stat)
    if result.adds:
        natural_line += t(lang, "roll_adds", adds=result.adds)

    lines = [t(lang, "roll_header", stat=t(lang, f"stat_{stat_name}"))]
    if result.burned:
        lines.append(natural_line + t(lang, "roll_natural_only", total=natural))
        lines.append(t(lang, "roll_burn", score=result.action_score,
                       reset=MOMENTUM_RESET))
    else:
        score_line = natural_line + t(lang, "roll_score", score=result.action_score)
        if natural > result.action_score:
            score_line += t(lang, "roll_capped")
        lines.append(score_line)

    challenge_a, challenge_b = result.challenge_dice
    lines.append(t(lang, "roll_challenge", a=challenge_a, b=challenge_b))
    lines.append(t(lang, "roll_result", label=_outcome_label(result.outcome, lang)))
    if result.is_match:
        lines.append(t(lang, "match_note"))
    return "\n".join(lines)


def _format_sheet(character: Character, lang: str) -> str:
    return t(
        lang, "sheet",
        name=character.name,
        edge_l=t(lang, "stat_edge"), edge=character.edge,
        heart_l=t(lang, "stat_heart"), heart=character.heart,
        iron_l=t(lang, "stat_iron"), iron=character.iron,
        shadow_l=t(lang, "stat_shadow"), shadow=character.shadow,
        wits_l=t(lang, "stat_wits"), wits=character.wits,
        health_l=t(lang, "track_health"), health=character.health,
        spirit_l=t(lang, "track_spirit"), spirit=character.spirit,
        supply_l=t(lang, "track_supply"), supply=character.supply,
        momentum_l=t(lang, "momentum"), momentum=character.momentum,
        reset_l=t(lang, "reset"), reset=MOMENTUM_RESET,
    )


def _format_ask(result: YesNoResult, question: str, lang: str) -> str:
    lines = [t(lang, "ask_header")]
    if question:
        lines.append(t(lang, "ask_question", question=question))
    lines.append(t(lang, "ask_odds", label=_odds_label(result.odds, lang),
                   chance=result.chance, roll=result.roll))
    answer_key = "answer_yes" if result.answer is Answer.YES else "answer_no"
    lines.append(t(lang, "ask_answer", label=t(lang, answer_key)))
    if result.is_extreme:
        lines.append(t(lang, "extreme_note"))
    return "\n".join(lines)
