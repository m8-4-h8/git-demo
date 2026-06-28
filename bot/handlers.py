"""Telegram command handlers.

Thin layer only: parse the command, delegate game logic to ``engine``,
persistence to ``storage``, and render replies via the ``i18n`` text catalog.
All user-facing strings are localized (RU/EN); the language is resolved per
player from their stored preference, falling back to their Telegram client
language. No game logic lives here.
"""

from __future__ import annotations

import html

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
    RANK_ALIASES,
    STAT_ALIASES,
    TRACK_ACTIONS,
    TRACK_ALIASES,
    TRACK_TYPE_ALIASES,
    VOW_ACTIONS,
    resolve_lang,
    t,
)
from engine import (
    ActionRoll,
    Answer,
    Character,
    Odds,
    Outcome,
    Rank,
    TrackType,
    YesNoResult,
    ask_yes_no,
    bounds_for,
    burn_momentum,
    clear_progress,
    complete,
    draw_from,
    end_encounter,
    forsake,
    fulfillment_roll,
    list_tables,
    mark_track_progress,
    mark_vow_progress,
    new_character,
    random_table,
    reset_momentum,
    roll_action,
    set_field,
    stat_value,
    table_title,
)
from engine.character import MOMENTUM_RESET, STAT_MAX, STAT_MIN, TRACK_MIN
from narrator import NarratorContext, narrate
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


def _vow_store(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["vows"]


def _track_store(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["tracks"]


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
    _schedule_narration(update, context, result, stat_name, character.name, lang)


def _fire_narration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    narrator_context: NarratorContext,
) -> None:
    """Fire the narrator without blocking the mechanical reply.

    The mechanics have already been sent; the prose (if any) arrives as a
    follow-up message 0-8s later. If the narrator is disabled or fails, nothing
    is sent and no error surfaces to the player.
    """
    chat = update.effective_chat

    async def _run() -> None:
        prose = await narrate(narrator_context)
        if prose:
            await chat.send_message(
                f"<i>{html.escape(prose)}</i>", parse_mode=ParseMode.HTML
            )

    context.application.create_task(_run())


def _schedule_narration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    result: ActionRoll,
    stat_name: str,
    character_name: str,
    lang: str,
) -> None:
    """Narrate the outcome of an action roll."""
    _fire_narration(
        update,
        context,
        NarratorContext(
            move_name=f"action roll ({stat_name})",
            outcome=result.outcome,
            is_match=result.is_match,
            stat_used=stat_name,
            character_name=character_name,
            language=lang,
        ),
    )


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


# --- vows --------------------------------------------------------------------


async def vow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch /vow <new|list|progress|fulfill|forsake> ...."""
    if update.message is None:
        return
    lang = await _lang(update, context)
    args = context.args or []
    action = VOW_ACTIONS.get(args[0].strip().lower()) if args else None
    rest = args[1:]
    if action == "new":
        await _vow_new(update, context, lang, rest)
    elif action == "list":
        await _vow_list(update, context, lang)
    elif action == "progress":
        await _vow_progress(update, context, lang, rest)
    elif action == "fulfill":
        await _vow_fulfill(update, context, lang, rest)
    elif action == "forsake":
        await _vow_forsake(update, context, lang, rest)
    else:
        await update.message.reply_text(t(lang, "vow_usage"))


async def _vow_new(update, context, lang: str, rest: list[str]) -> None:
    canonical = RANK_ALIASES.get(rest[0].strip().lower()) if rest else None
    if canonical is None:
        if rest:
            await update.message.reply_text(t(lang, "vow_unknown_rank", rank=rest[0]))
        else:
            await update.message.reply_text(t(lang, "vow_new_usage"))
        return
    title = " ".join(rest[1:]).strip()
    if not title:
        await update.message.reply_text(t(lang, "vow_new_usage"))
        return
    chat_id, user_id = _ids(update)
    created = await _vow_store(context).create(chat_id, user_id, title, Rank(canonical))
    await update.message.reply_text(
        t(lang, "vow_created") + "\n\n" + _format_vow(created, lang)
    )


async def _vow_list(update, context, lang: str) -> None:
    chat_id, user_id = _ids(update)
    vows = await _vow_store(context).list(chat_id, user_id)
    if not vows:
        await update.message.reply_text(t(lang, "vow_list_empty"))
        return
    lines = [t(lang, "vow_list_header")] + [_format_vow(v, lang) for v in vows]
    await update.message.reply_text("\n".join(lines))


async def _vow_progress(update, context, lang: str, rest: list[str]) -> None:
    ref, hits = _split_ref_hits(rest)
    if not ref:
        await update.message.reply_text(t(lang, "vow_usage"))
        return
    chat_id, user_id = _ids(update)
    store = _vow_store(context)
    target = _match_target(await store.list(chat_id, user_id), ref)
    if target is None:
        await update.message.reply_text(t(lang, "vow_not_found", ref=ref))
        return
    updated = mark_vow_progress(target, hits)
    await store.update(chat_id, user_id, updated)
    await update.message.reply_text(
        t(lang, "vow_progress_done", title=updated.title,
          bar=_progress_bar(updated.progress), progress=updated.progress)
    )


async def _vow_fulfill(update, context, lang: str, rest: list[str]) -> None:
    ref = " ".join(rest).strip()
    if not ref:
        await update.message.reply_text(t(lang, "vow_usage"))
        return
    chat_id, user_id = _ids(update)
    store = _vow_store(context)
    target = _match_target(await store.list(chat_id, user_id), ref)
    if target is None:
        await update.message.reply_text(t(lang, "vow_not_found", ref=ref))
        return
    result = fulfillment_roll(target)
    if result.vow.fulfilled:
        await store.update(chat_id, user_id, result.vow)
    challenge_a, challenge_b = result.roll.challenge_dice
    note_key = {
        Outcome.STRONG: "vow_fulfilled_strong",
        Outcome.WEAK: "vow_fulfilled_weak",
        Outcome.MISS: "vow_fulfill_miss",
    }[result.roll.outcome]
    lines = [
        t(lang, "vow_fulfill_header", title=target.title),
        t(lang, "vow_fulfill_line", score=result.roll.action_score,
          a=challenge_a, b=challenge_b,
          result=_outcome_label(result.roll.outcome, lang)),
        t(lang, note_key),
    ]
    await update.message.reply_text("\n".join(lines))
    character = await _store(context).get(chat_id, user_id)
    _fire_narration(
        update,
        context,
        NarratorContext(
            move_name="fulfill your vow",
            outcome=result.roll.outcome,
            is_match=result.roll.is_match,
            stat_used="heart",
            character_name=character.name if character else "",
            active_vow=target.title,
            language=lang,
        ),
    )


async def _vow_forsake(update, context, lang: str, rest: list[str]) -> None:
    ref = " ".join(rest).strip()
    if not ref:
        await update.message.reply_text(t(lang, "vow_usage"))
        return
    chat_id, user_id = _ids(update)
    store = _vow_store(context)
    target = _match_target(await store.list(chat_id, user_id), ref)
    if target is None:
        await update.message.reply_text(t(lang, "vow_not_found", ref=ref))
        return
    await store.update(chat_id, user_id, forsake(target))
    # Forsaking a vow costs 1 spirit, if the player has a character.
    char_store = _store(context)
    character = await char_store.get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(t(lang, "vow_forsaken_no_char", title=target.title))
        return
    new_spirit = max(TRACK_MIN, character.spirit - 1)
    await char_store.update(chat_id, user_id, set_field(character, "spirit", new_spirit))
    await update.message.reply_text(
        t(lang, "vow_forsaken_spirit", title=target.title, spirit=new_spirit)
    )


# --- progress tracks ---------------------------------------------------------


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch /track <new|list|hit|end|clear> ...."""
    if update.message is None:
        return
    lang = await _lang(update, context)
    args = context.args or []
    action = TRACK_ACTIONS.get(args[0].strip().lower()) if args else None
    rest = args[1:]
    if action == "new":
        await _track_new(update, context, lang, rest)
    elif action == "list":
        await _track_list(update, context, lang)
    elif action == "hit":
        await _track_hit(update, context, lang, rest)
    elif action == "end":
        await _track_end(update, context, lang, rest)
    elif action == "clear":
        await _track_clear(update, context, lang, rest)
    else:
        await update.message.reply_text(t(lang, "track_usage"))


async def _track_new(update, context, lang: str, rest: list[str]) -> None:
    type_canonical = TRACK_TYPE_ALIASES.get(rest[0].strip().lower()) if rest else None
    if type_canonical is None:
        if rest:
            await update.message.reply_text(t(lang, "track_unknown_type", type=rest[0]))
        else:
            await update.message.reply_text(t(lang, "track_new_usage"))
        return
    rank_canonical = RANK_ALIASES.get(rest[1].strip().lower()) if len(rest) > 1 else None
    if rank_canonical is None:
        if len(rest) > 1:
            await update.message.reply_text(t(lang, "track_unknown_rank", rank=rest[1]))
        else:
            await update.message.reply_text(t(lang, "track_new_usage"))
        return
    title = " ".join(rest[2:]).strip()
    if not title:
        await update.message.reply_text(t(lang, "track_new_usage"))
        return
    chat_id, _ = _ids(update)
    created = await _track_store(context).create(
        chat_id, title, TrackType(type_canonical), Rank(rank_canonical)
    )
    await update.message.reply_text(
        t(lang, "track_created") + "\n\n" + _format_track(created, lang)
    )


async def _track_list(update, context, lang: str) -> None:
    chat_id, _ = _ids(update)
    tracks = await _track_store(context).list(chat_id)
    if not tracks:
        await update.message.reply_text(t(lang, "track_list_empty"))
        return
    lines = [t(lang, "track_list_header")] + [_format_track(tr, lang) for tr in tracks]
    await update.message.reply_text("\n".join(lines))


async def _track_hit(update, context, lang: str, rest: list[str]) -> None:
    ref, hits = _split_ref_hits(rest)
    if not ref:
        await update.message.reply_text(t(lang, "track_usage"))
        return
    chat_id, _ = _ids(update)
    store = _track_store(context)
    target = _match_target(await store.list(chat_id), ref)
    if target is None:
        await update.message.reply_text(t(lang, "track_not_found", ref=ref))
        return
    updated = mark_track_progress(target, hits)
    await store.update(chat_id, updated)
    await update.message.reply_text(
        t(lang, "track_hit_done", title=updated.title,
          bar=_progress_bar(updated.progress), progress=updated.progress)
    )


async def _track_end(update, context, lang: str, rest: list[str]) -> None:
    ref = " ".join(rest).strip()
    if not ref:
        await update.message.reply_text(t(lang, "track_usage"))
        return
    chat_id, user_id = _ids(update)
    store = _track_store(context)
    target = _match_target(await store.list(chat_id), ref)
    if target is None:
        await update.message.reply_text(t(lang, "track_not_found", ref=ref))
        return
    outcome = end_encounter(target)
    await store.update(chat_id, complete(target))
    note_key = {
        Outcome.STRONG: "track_end_strong",
        Outcome.WEAK: "track_end_weak",
        Outcome.MISS: "track_end_miss",
    }[outcome]
    lines = [
        t(lang, "track_end_header", title=target.title),
        t(lang, "track_end_line", bar=_progress_bar(target.progress),
          progress=target.progress, result=_outcome_label(outcome, lang)),
        t(lang, note_key),
    ]
    await update.message.reply_text("\n".join(lines))
    character = await _store(context).get(chat_id, user_id)
    _fire_narration(
        update,
        context,
        NarratorContext(
            move_name="resolve the encounter",
            outcome=outcome,
            is_match=False,
            stat_used="",
            character_name=character.name if character else "",
            active_track=target.title,
            language=lang,
        ),
    )


async def _track_clear(update, context, lang: str, rest: list[str]) -> None:
    ref = " ".join(rest).strip()
    if not ref:
        await update.message.reply_text(t(lang, "track_usage"))
        return
    chat_id, _ = _ids(update)
    store = _track_store(context)
    target = _match_target(await store.list(chat_id), ref)
    if target is None:
        await update.message.reply_text(t(lang, "track_not_found", ref=ref))
        return
    await store.update(chat_id, clear_progress(target))
    await update.message.reply_text(t(lang, "track_cleared", title=target.title))


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


_BAR_SEGMENTS = 10


def _progress_bar(progress: float, segments: int = _BAR_SEGMENTS) -> str:
    """Render a progress track as a 10-segment bar (▓ full, ▒ half, ░ empty)."""
    full = int(progress)
    bar = "▓" * full
    if progress - full >= 0.5 and full < segments:
        bar += "▒"
        full += 1
    return bar + "░" * (segments - full)


def _rank_label(rank: Rank, lang: str) -> str:
    return t(lang, f"rank_{rank.value}")


def _type_label(track_type: TrackType, lang: str) -> str:
    return t(lang, f"type_{track_type.value}")


def _format_vow(vow_obj, lang: str) -> str:
    return t(lang, "vow_item", id=vow_obj.id, title=vow_obj.title,
             rank=_rank_label(vow_obj.rank, lang),
             bar=_progress_bar(vow_obj.progress), progress=vow_obj.progress)


def _format_track(track_obj, lang: str) -> str:
    return t(lang, "track_item", id=track_obj.id, title=track_obj.title,
             type=_type_label(track_obj.track_type, lang),
             rank=_rank_label(track_obj.rank, lang),
             bar=_progress_bar(track_obj.progress), progress=track_obj.progress)


def _match_target(items, ref: str):
    """Find an item (vow/track) by numeric id, then exact title, then unique substring."""
    ref = ref.strip()
    if ref.isdigit():
        wanted = int(ref)
        return next((item for item in items if item.id == wanted), None)
    low = ref.lower()
    for item in items:
        if item.title.lower() == low:
            return item
    matches = [item for item in items if low in item.title.lower()]
    return matches[0] if len(matches) == 1 else None


def _split_ref_hits(tokens: list[str]) -> tuple[str, int]:
    """Split tokens into (reference, hits); a trailing integer is taken as hits."""
    if not tokens:
        return "", 1
    if len(tokens) > 1 and tokens[-1].isdigit():
        return " ".join(tokens[:-1]).strip(), max(1, int(tokens[-1]))
    return " ".join(tokens).strip(), 1


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
