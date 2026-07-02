"""Telegram command handlers.

Thin layer only: parse the command, delegate game logic to ``engine``,
persistence to ``storage``, and render replies via the ``i18n`` text catalog.
All user-facing strings are localized (RU/EN); the language is resolved per
player from their stored preference, falling back to their Telegram client
language. No game logic lives here.
"""

from __future__ import annotations

import html
from collections import Counter

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from bot.i18n import (
    BURN_WORDS,
    GM_ACTIONS,
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
from bot import menu
from engine import (
    ARCHETYPES,
    MOVES,
    STARTING_ALLOCATION,
    ActionRoll,
    Answer,
    Character,
    MoveCategory,
    Odds,
    Outcome,
    Rank,
    TrackType,
    YesNoResult,
    add_item,
    apply_archetype_bonus,
    apply_effects,
    ask_yes_no,
    bounds_for,
    burn_momentum,
    clear_progress,
    complete,
    create_with_archetype,
    draw_from,
    end_encounter,
    forsake,
    fulfillment_roll,
    get_archetype,
    list_tables,
    mark_track_progress,
    mark_vow_progress,
    moves_in,
    random_table,
    remove_item,
    reset_momentum,
    resolve_move,
    roll_action,
    set_background,
    set_field,
    stat_value,
    table_title,
)
from engine.character import (
    MAX_BACKGROUND_LENGTH,
    MAX_ITEM_LENGTH,
    MAX_ITEMS,
    MOMENTUM_RESET,
    STAT_NAMES,
    TRACK_MIN,
)
from gm import (
    GMContext,
    generate_complication,
    generate_scene,
    generate_scenario_options,
    is_enabled as gm_enabled,
    push_scene,
)
from narrator import (
    NarratorContext,
    is_enabled as narrator_enabled,
    narrate,
    narrate_intro,
)
from storage import CharacterExists

# Conversation states for /new (guided hero creation: name → path → stats).
NAME, NEW_ARCH, NEW_ALLOC, NEW_ASSIGN, NEW_CONFIRM = range(5)
# Conversation states for vow / track creation.
VOW_RANK, VOW_TITLE, TRACK_TYPE, TRACK_RANK, TRACK_TITLE = range(5, 10)
# Conversation states for inventory / background editing.
ITEM_NAME, BG_TEXT = range(10, 12)

# Abandoned guided dialogs expire after this many seconds, so a later plain
# message isn't silently swallowed as, say, an item name.
CONVERSATION_TIMEOUT = 600

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


def _gm_store(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["gm_state"]


def _ids(update: Update) -> tuple[int, int]:
    return update.effective_chat.id, update.effective_user.id


async def _lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Resolve the player's language, cached per chat.

    The preference is stored per (chat, user), so the in-memory cache must be
    keyed by chat too — ``user_data`` alone is shared across all of a user's
    chats.
    """
    chat_id, user_id = _ids(update)
    cache = context.user_data.setdefault("lang", {})
    cached = cache.get(chat_id)
    if cached:
        return cached
    stored = await _prefs(context).get_language(chat_id, user_id)
    code = update.effective_user.language_code if update.effective_user else None
    lang = resolve_lang(stored, code)
    cache[chat_id] = lang
    return lang


# --- informational commands --------------------------------------------------


async def _main_menu_view(update, context, lang: str) -> tuple[str, object]:
    """Title + keyboard for the main menu, nudging newcomers to create a hero."""
    chat_id, user_id = _ids(update)
    has_character = await _store(context).get(chat_id, user_id) is not None
    title_key = "menu_title" if has_character else "menu_title_no_hero"
    return t(lang, title_key), menu.main_menu(lang, has_character)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    await update.message.reply_text(t(lang, "start"), parse_mode=ParseMode.MARKDOWN)
    title, keyboard = await _main_menu_view(update, context, lang)
    await update.message.reply_text(title, reply_markup=keyboard)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    title, keyboard = await _main_menu_view(update, context, lang)
    await update.message.reply_text(title, reply_markup=keyboard)


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
        await update.message.reply_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
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
        await update.message.reply_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
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
        await update.message.reply_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
        return

    result = roll_action(stat_value(character, stat_name), adds)
    if burn:
        result = burn_momentum(result, character.momentum)
        await store.update(chat_id, user_id, reset_momentum(character))

    await update.message.reply_text(
        _format_roll(result, stat_name, lang)
        + "\n" + _outcome_hint(result.outcome, lang)
    )
    _schedule_narration(update, context, result, stat_name, character.name, lang)
    _schedule_gm_scene(update, context, result, stat_name, character.name, lang)


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
    if not narrator_enabled():
        return
    chat = update.effective_chat

    async def _run() -> None:
        await _show_typing(chat)
        prose = await narrate(narrator_context)
        if prose:
            await chat.send_message(
                f"<i>{html.escape(prose)}</i>", parse_mode=ParseMode.HTML
            )

    context.application.create_task(_run())


async def _show_typing(chat) -> None:
    """Show a typing indicator while an LLM reply is on its way (fail-soft).

    The indicator clears on its own after ~5s or when the message arrives, so a
    single fire-and-forget action is enough for our short generations.
    """
    try:
        await chat.send_action(ChatAction.TYPING)
    except Exception:  # noqa: BLE001 — cosmetic only, never break the flow
        pass


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


_GM_OUTCOME_WORDS = {
    Outcome.STRONG: "strong hit",
    Outcome.WEAK: "weak hit",
    Outcome.MISS: "miss",
}


def _schedule_gm_scene(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    result: ActionRoll,
    stat_name: str,
    character_name: str,
    lang: str,
) -> None:
    """If a campaign is active, let the GM describe the next scene (non-blocking).

    Fires only when the GM is enabled and the chat has a campaign. A miss draws a
    complication; otherwise the world simply moves on. The new scene is sent as
    its own message and persisted (sliding 5-scene history).
    """
    if not gm_enabled():
        return
    chat = update.effective_chat
    chat_id, user_id = _ids(update)
    gm_store = _gm_store(context)
    char_store = _store(context)
    outcome = result.outcome

    async def _run() -> None:
        state = await gm_store.get(chat_id)
        if state is None:
            return  # no active campaign in this chat
        await _show_typing(chat)
        party = [c.name for c in await char_store.list(chat_id)]
        actor = await char_store.get(chat_id, user_id)
        gm_context = GMContext(
            scenario_title=state["scenario_title"],
            scenario_goal=state["scenario_goal"],
            current_scene=state["current_scene"],
            scene_history=state["scene_history"],
            active_characters=party or ([character_name] if character_name else []),
            active_vows=[state["scenario_goal"]],
            npc_memory=state["npc_memory"],
            language=lang,
            background=actor.background if actor else None,
            items=list(actor.items) if actor else [],
        )
        if outcome is Outcome.MISS:
            scene = await generate_complication(gm_context)
        else:
            who = character_name or "A hero"
            last = f"{who} acted with {stat_name} — {_GM_OUTCOME_WORDS[outcome]}"
            scene = await generate_scene(gm_context, last)
        if not scene:
            return
        await chat.send_message(scene)
        await gm_store.save(
            chat_id,
            scenario_title=state["scenario_title"],
            scenario_goal=state["scenario_goal"],
            current_scene=scene,
            scene_history=push_scene(state["scene_history"], scene),
            npc_memory=state["npc_memory"],
        )

    context.application.create_task(_run())


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
        + "\n\n" + t(lang, "vow_created_hint")
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
        + "\n\n" + t(lang, "track_created_hint")
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


# --- AI Game Master ----------------------------------------------------------


async def gm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch /gm <start|scene|npcs|stop>."""
    if update.message is None:
        return
    lang = await _lang(update, context)
    if not gm_enabled():
        await update.message.reply_text(t(lang, "gm_disabled"))
        return
    args = context.args or []
    action = GM_ACTIONS.get(args[0].strip().lower()) if args else None
    if action == "start":
        await _gm_start(update, context, lang)
    elif action == "scene":
        await _gm_scene(update, context, lang)
    elif action == "npcs":
        await _gm_npcs(update, context, lang)
    elif action == "stop":
        await _gm_stop(update, context, lang)
    else:
        await update.message.reply_text(t(lang, "gm_usage"))


async def _gm_start(update, context, lang: str) -> None:
    options = await generate_scenario_options(lang)
    if not options:
        await update.message.reply_text(t(lang, "gm_pick_failed"))
        return
    context.chat_data["gm_options"] = options
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(opt.title, callback_data=f"gm:pick:{i}")]
         for i, opt in enumerate(options)]
    )
    await update.message.reply_text(t(lang, "gm_pick_header"), reply_markup=keyboard)


async def _gm_scene(update, context, lang: str) -> None:
    chat_id, _ = _ids(update)
    state = await _gm_store(context).get(chat_id)
    if state is None:
        await update.message.reply_text(t(lang, "gm_no_campaign"))
        return
    await update.message.reply_text(
        t(lang, "gm_scene_header") + "\n" + state["current_scene"]
    )


async def _gm_npcs(update, context, lang: str) -> None:
    chat_id, _ = _ids(update)
    state = await _gm_store(context).get(chat_id)
    if state is None:
        await update.message.reply_text(t(lang, "gm_no_campaign"))
        return
    npcs = state["npc_memory"]
    if not npcs:
        await update.message.reply_text(t(lang, "gm_npcs_empty"))
        return
    lines = [t(lang, "gm_npcs_header")] + [
        t(lang, "gm_npc_item", name=name, description=desc)
        for name, desc in npcs.items()
    ]
    await update.message.reply_text("\n".join(lines))


async def _gm_stop(update, context, lang: str) -> None:
    chat_id, _ = _ids(update)
    if await _gm_store(context).get(chat_id) is None:
        await update.message.reply_text(t(lang, "gm_no_campaign"))
        return
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(t(lang, "gm_yes"), callback_data="gm:stop:yes"),
            InlineKeyboardButton(t(lang, "gm_no"), callback_data="gm:stop:no"),
        ]]
    )
    await update.message.reply_text(t(lang, "gm_stop_confirm"), reply_markup=keyboard)


async def gm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle every ``gm:`` callback (submenu, scenario pick, stop confirmation)."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    lang = await _lang(update, context)
    parts = query.data.split(":")
    kind = parts[1] if len(parts) > 1 else ""
    # Arg-bearing callbacks (gm:pick:<i>, gm:stop:<yes|no>) come first.
    if kind == "pick" and len(parts) >= 3:
        await _gm_pick(update, context, lang, parts[2])
        return
    if kind == "stop" and len(parts) >= 3:
        await _gm_stop_confirm(update, context, lang, parts[2])
        return
    # Submenu navigation requires the GM to be enabled.
    if not gm_enabled():
        await query.edit_message_text(
            t(lang, "gm_disabled"), reply_markup=menu.home_only(lang)
        )
        return
    if kind == "menu":
        await query.edit_message_text(
            t(lang, "gm_menu_title"), reply_markup=menu.gm_menu(lang)
        )
    elif kind == "start":
        await _gm_start_cb(update, context, lang)
    elif kind == "scene":
        await _gm_scene_cb(update, context, lang)
    elif kind == "npcs":
        await _gm_npcs_cb(update, context, lang)
    elif kind == "stop":
        await _gm_stop_cb(update, context, lang)


async def _gm_start_cb(update, context, lang: str) -> None:
    query = update.callback_query
    options = await generate_scenario_options(lang)
    if not options:
        await query.edit_message_text(
            t(lang, "gm_pick_failed"), reply_markup=menu.back_home(lang, "gm:menu")
        )
        return
    context.chat_data["gm_options"] = options
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(opt.title, callback_data=f"gm:pick:{i}")]
         for i, opt in enumerate(options)]
    )
    await query.edit_message_text(t(lang, "gm_pick_header"), reply_markup=keyboard)


async def _gm_scene_cb(update, context, lang: str) -> None:
    query = update.callback_query
    chat_id, _ = _ids(update)
    state = await _gm_store(context).get(chat_id)
    if state is None:
        await query.edit_message_text(
            t(lang, "gm_no_campaign"), reply_markup=menu.back_home(lang, "gm:menu")
        )
        return
    await query.edit_message_text(
        t(lang, "gm_scene_header") + "\n" + state["current_scene"],
        reply_markup=menu.back_home(lang, "gm:menu"),
    )


async def _gm_npcs_cb(update, context, lang: str) -> None:
    query = update.callback_query
    chat_id, _ = _ids(update)
    state = await _gm_store(context).get(chat_id)
    if state is None:
        await query.edit_message_text(
            t(lang, "gm_no_campaign"), reply_markup=menu.back_home(lang, "gm:menu")
        )
        return
    npcs = state["npc_memory"]
    if not npcs:
        await query.edit_message_text(
            t(lang, "gm_npcs_empty"), reply_markup=menu.back_home(lang, "gm:menu")
        )
        return
    lines = [t(lang, "gm_npcs_header")] + [
        t(lang, "gm_npc_item", name=name, description=desc)
        for name, desc in npcs.items()
    ]
    await query.edit_message_text(
        "\n".join(lines), reply_markup=menu.back_home(lang, "gm:menu")
    )


async def _gm_stop_cb(update, context, lang: str) -> None:
    query = update.callback_query
    chat_id, _ = _ids(update)
    if await _gm_store(context).get(chat_id) is None:
        await query.edit_message_text(
            t(lang, "gm_no_campaign"), reply_markup=menu.back_home(lang, "gm:menu")
        )
        return
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(t(lang, "gm_yes"), callback_data="gm:stop:yes"),
            InlineKeyboardButton(t(lang, "gm_no"), callback_data="gm:stop:no"),
        ]]
    )
    await query.edit_message_text(t(lang, "gm_stop_confirm"), reply_markup=keyboard)


async def _gm_pick(update, context, lang: str, idx_str: str) -> None:
    options = context.chat_data.get("gm_options")
    try:
        idx = int(idx_str)
    except ValueError:
        idx = -1
    if not options or not (0 <= idx < len(options)):
        await update.callback_query.edit_message_text(t(lang, "gm_pick_expired"))
        return
    option = options[idx]
    context.chat_data.pop("gm_options", None)

    chat_id, user_id = _ids(update)
    await _gm_store(context).save(
        chat_id,
        scenario_title=option.title,
        scenario_goal=option.goal,
        current_scene=option.opening_scene,
        scene_history=[],
        npc_memory={},
    )
    # The chosen goal becomes the picker's sworn quest.
    await _vow_store(context).create(chat_id, user_id, option.goal, Rank.FORMIDABLE)

    await update.callback_query.edit_message_text(
        t(lang, "gm_started", title=option.title, goal=option.goal)
        + "\n\n"
        + option.opening_scene
    )


async def _gm_stop_confirm(update, context, lang: str, choice: str) -> None:
    chat_id, _ = _ids(update)
    if choice == "yes":
        await _gm_store(context).delete(chat_id)
        await update.callback_query.edit_message_text(t(lang, "gm_stopped"))
    else:
        await update.callback_query.edit_message_text(t(lang, "gm_stop_cancelled"))


# --- button menu (inline-keyboard UX) ----------------------------------------

# Character tracks the player may adjust via the ±1 stepper.
SETTABLE_FIELDS = ("health", "spirit", "supply", "momentum")


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route every ``menu|move|roll|oracle|char|vow|track|help:`` callback.

    Navigation edits the current message in place; action results (a roll, a
    move, an oracle answer) are sent as a fresh message carrying a 🏠 Home
    button. Conversation flows own their own (``cnew|vnew|tnew:``) prefixes.
    """
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    lang = await _lang(update, context)
    parts = query.data.split(":")
    area = parts[0]
    if area == "menu":
        title, keyboard = await _main_menu_view(update, context, lang)
        await query.edit_message_text(title, reply_markup=keyboard)
    elif area == "help":
        await query.edit_message_text(
            t(lang, "help"), reply_markup=menu.help_keyboard(lang)
        )
    elif area == "move":
        await _menu_move(update, context, lang, parts)
    elif area == "roll":
        await _menu_roll(update, context, lang, parts)
    elif area == "oracle":
        await _menu_oracle(update, context, lang, parts)
    elif area == "char":
        await _menu_char(update, context, lang, parts)
    elif area == "vow":
        await _menu_vow(update, context, lang, parts)
    elif area == "track":
        await _menu_track(update, context, lang, parts)


# --- move flow ---------------------------------------------------------------


async def _menu_move(update, context, lang: str, parts: list[str]) -> None:
    query = update.callback_query
    sub = parts[1] if len(parts) > 1 else ""
    if sub == "cat" and len(parts) == 2:
        await query.edit_message_text(
            t(lang, "move_cat_title"), reply_markup=menu.move_categories(lang)
        )
    elif sub == "cat":
        try:
            category = MoveCategory(parts[2])
        except ValueError:
            return
        await query.edit_message_text(
            t(lang, "move_pick_title") + "\n\n"
            + _moves_overview(lang, moves_in(category)),
            reply_markup=menu.moves_keyboard(lang, category),
        )
    elif sub == "mv":
        spec = MOVES.get(parts[2])
        if spec is None:
            return
        chat_id, user_id = _ids(update)
        character = await _store(context).get(chat_id, user_id)
        if character is None:
            await query.edit_message_text(
                t(lang, "no_character"),
                reply_markup=menu.no_character_keyboard(lang),
            )
            return
        await query.edit_message_text(
            _move_blurb(spec, lang),
            reply_markup=menu.stat_keyboard(
                lang, f"move:st:{spec.key}", f"move:cat:{spec.category.value}",
                character=character,
            ),
        )
    elif sub == "st" and len(parts) >= 4:
        await _do_move(update, context, lang, parts[2], parts[3])


async def _do_move(update, context, lang: str, move_key: str, stat_name: str) -> None:
    query = update.callback_query
    chat_id, user_id = _ids(update)
    store = _store(context)
    character = await store.get(chat_id, user_id)
    if character is None:
        await query.edit_message_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
        return
    try:
        result = resolve_move(move_key, character, stat_name)
    except ValueError:
        return
    updated, applied = apply_effects(character, result.delta)
    if applied:
        await store.update(chat_id, user_id, updated)
    await update.effective_chat.send_message(
        _format_move(result, applied, lang), reply_markup=menu.home_only(lang)
    )
    _fire_narration(
        update,
        context,
        NarratorContext(
            move_name=move_key.replace("_", " "),
            outcome=result.roll.outcome,
            is_match=result.roll.is_match,
            stat_used=stat_name,
            character_name=character.name,
            language=lang,
        ),
    )
    _schedule_gm_scene(update, context, result.roll, stat_name, character.name, lang)


def _format_move(result, applied, lang: str) -> str:
    lines = [
        t(lang, "move_result_header", move=t(lang, f"move_{result.move_key}")),
        _format_roll(result.roll, result.stat_name, lang),
    ]
    if applied:
        changes = ", ".join(
            f"{_field_label(field, lang)} {change:+d}"
            for field, change in applied.changes.items()
        )
        lines.append(t(lang, "move_effect_header") + " " + changes)
    else:
        lines.append(t(lang, "move_no_effect"))
    lines.append(_outcome_hint(result.roll.outcome, lang))
    return "\n".join(lines)


# --- roll flow ---------------------------------------------------------------


async def _menu_roll(update, context, lang: str, parts: list[str]) -> None:
    query = update.callback_query
    sub = parts[1] if len(parts) > 1 else ""
    if sub == "menu":
        chat_id, user_id = _ids(update)
        character = await _store(context).get(chat_id, user_id)
        if character is None:
            await query.edit_message_text(
                t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
            )
            return
        await query.edit_message_text(
            t(lang, "roll_pick_title"),
            reply_markup=menu.stat_keyboard(
                lang, "roll:st", menu.HOME, character=character
            ),
        )
    elif sub == "st" and len(parts) >= 3:
        stat_name = parts[2]
        chat_id, user_id = _ids(update)
        character = await _store(context).get(chat_id, user_id)
        if character is None:
            await query.edit_message_text(
                t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
            )
            return
        result = roll_action(stat_value(character, stat_name), 0)
        await update.effective_chat.send_message(
            _format_roll(result, stat_name, lang)
            + "\n" + _outcome_hint(result.outcome, lang),
            reply_markup=menu.home_only(lang),
        )
        _schedule_narration(update, context, result, stat_name, character.name, lang)
        _schedule_gm_scene(update, context, result, stat_name, character.name, lang)


# --- oracle flow -------------------------------------------------------------


async def _menu_oracle(update, context, lang: str, parts: list[str]) -> None:
    query = update.callback_query
    sub = parts[1] if len(parts) > 1 else ""
    if sub == "menu":
        await query.edit_message_text(
            t(lang, "oracle_pick_title"), reply_markup=menu.oracle_keyboard(lang)
        )
    elif sub == "do" and len(parts) >= 3:
        result = ask_yes_no(parts[2])
        await update.effective_chat.send_message(
            _format_ask(result, "", lang), reply_markup=menu.home_only(lang)
        )


# --- character flow ----------------------------------------------------------


async def _menu_char(update, context, lang: str, parts: list[str]) -> None:
    query = update.callback_query
    sub = parts[1] if len(parts) > 1 else ""
    chat_id, user_id = _ids(update)
    store = _store(context)
    if sub == "menu":
        character = await store.get(chat_id, user_id)
        await query.edit_message_text(
            t(lang, "char_menu_title"),
            reply_markup=menu.character_menu(lang, character is not None),
        )
    elif sub == "show":
        character = await store.get(chat_id, user_id)
        if character is None:
            await query.edit_message_text(
                t(lang, "no_character"),
                reply_markup=menu.character_menu(lang, False),
            )
            return
        await query.edit_message_text(
            _format_sheet(character, lang),
            reply_markup=menu.back_home(lang, "char:menu"),
        )
    elif sub == "set":
        character = await store.get(chat_id, user_id)
        if character is None:
            await query.edit_message_text(
                t(lang, "no_character"),
                reply_markup=menu.character_menu(lang, False),
            )
            return
        await query.edit_message_text(
            t(lang, "char_set_title"),
            reply_markup=menu.char_set_fields(lang, SETTABLE_FIELDS),
        )
    elif sub == "setf" and len(parts) >= 3:
        character = await store.get(chat_id, user_id)
        if character is not None:
            await _render_stepper(query, character, parts[2], lang)
    elif sub == "adj" and len(parts) >= 4:
        field = parts[2]
        try:
            delta = int(parts[3])
        except ValueError:
            return
        character = await store.get(chat_id, user_id)
        if character is None:
            return
        low, high = bounds_for(field)
        current = getattr(character, field)
        new_value = max(low, min(high, current + delta))
        if new_value == current:  # already at the bound — explain, don't error
            await _render_stepper(query, character, field, lang, at_limit=True)
            return
        character = set_field(character, field, new_value)
        await store.update(chat_id, user_id, character)
        await _render_stepper(query, character, field, lang)
    elif sub == "delitem":
        character = await store.get(chat_id, user_id)
        if character is None:
            return
        if len(parts) >= 3:
            try:
                index = int(parts[2])
            except ValueError:
                return
            try:
                character = remove_item(character, index)
            except ValueError:
                return
            await store.update(chat_id, user_id, character)
        await _render_item_removal(query, character, lang)


async def _render_item_removal(query, character, lang: str) -> None:
    """Show the remove-item picker, or a 'back' note when the inventory is empty."""
    if not character.items:
        await query.edit_message_text(
            t(lang, "inventory_empty"), reply_markup=menu.back_home(lang, "char:menu")
        )
        return
    await query.edit_message_text(
        t(lang, "item_remove_title"),
        reply_markup=menu.item_remove_keyboard(lang, character.items),
    )


async def _render_stepper(
    query, character, field: str, lang: str, *, at_limit: bool = False
) -> None:
    """Show a track's stepper: current value, bounds, and what the track is for."""
    low, high = bounds_for(field)
    lines = [
        t(lang, "char_field_now", field=_field_label(field, lang),
          value=getattr(character, field), low=low, high=high),
        t(lang, f"field_desc_{field}"),
    ]
    if at_limit:
        lines.append(t(lang, "char_at_limit"))
    await _edit_quietly(query, "\n".join(lines), menu.char_stepper(lang, field))


async def _edit_quietly(query, text: str, reply_markup) -> None:
    """Edit a message, swallowing Telegram's 'message is not modified' error.

    Repeated taps that change nothing (e.g. +1 at a track's maximum) would
    otherwise bubble up as a scary generic error to the player.
    """
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as error:
        if "not modified" not in str(error).lower():
            raise


# --- vow flow ----------------------------------------------------------------


async def _menu_vow(update, context, lang: str, parts: list[str]) -> None:
    query = update.callback_query
    sub = parts[1] if len(parts) > 1 else ""
    chat_id, user_id = _ids(update)
    store = _vow_store(context)
    if sub == "menu":
        await query.edit_message_text(
            t(lang, "vow_menu_title"), reply_markup=menu.vow_menu(lang)
        )
    elif sub == "list":
        vows = await store.list(chat_id, user_id)
        title_key = "vow_list_title" if vows else "vow_list_empty"
        await query.edit_message_text(
            t(lang, title_key),
            reply_markup=menu.vow_list_keyboard(lang, vows),
        )
    elif sub == "act" and len(parts) >= 3:
        vow_id = int(parts[2])
        target = await store.get(chat_id, user_id, vow_id)
        if target is None:
            await query.edit_message_text(
                t(lang, "vow_not_found", ref=f"#{vow_id}"),
                reply_markup=menu.back_home(lang, "vow:menu"),
            )
            return
        await query.edit_message_text(
            "\n\n".join([
                t(lang, "vow_act_title"),
                _format_vow(target, lang),
                t(lang, "vow_act_help"),
            ]),
            reply_markup=menu.vow_actions(lang, vow_id),
        )
    elif sub == "do" and len(parts) >= 4:
        await _vow_do(update, context, lang, parts[2], int(parts[3]))


async def _vow_do(update, context, lang: str, action: str, vow_id: int) -> None:
    query = update.callback_query
    chat_id, user_id = _ids(update)
    store = _vow_store(context)
    target = await store.get(chat_id, user_id, vow_id)
    if target is None:
        await query.edit_message_text(
            t(lang, "vow_not_found", ref=f"#{vow_id}"),
            reply_markup=menu.back_home(lang, "vow:menu"),
        )
        return
    if action == "progress":
        updated = mark_vow_progress(target, 1)
        await store.update(chat_id, user_id, updated)
        await query.edit_message_text(
            t(lang, "vow_progress_done", title=updated.title,
              bar=_progress_bar(updated.progress), progress=updated.progress),
            reply_markup=menu.back_home(lang, "vow:list"),
        )
    elif action == "fulfill":
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
        await query.edit_message_text(
            "\n".join(lines), reply_markup=menu.back_home(lang, "vow:menu")
        )
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
    elif action == "forsake":
        await store.update(chat_id, user_id, forsake(target))
        char_store = _store(context)
        character = await char_store.get(chat_id, user_id)
        if character is None:
            await query.edit_message_text(
                t(lang, "vow_forsaken_no_char", title=target.title),
                reply_markup=menu.back_home(lang, "vow:menu"),
            )
            return
        new_spirit = max(TRACK_MIN, character.spirit - 1)
        await char_store.update(
            chat_id, user_id, set_field(character, "spirit", new_spirit)
        )
        await query.edit_message_text(
            t(lang, "vow_forsaken_spirit", title=target.title, spirit=new_spirit),
            reply_markup=menu.back_home(lang, "vow:menu"),
        )


# --- track flow --------------------------------------------------------------


async def _menu_track(update, context, lang: str, parts: list[str]) -> None:
    query = update.callback_query
    sub = parts[1] if len(parts) > 1 else ""
    chat_id, _ = _ids(update)
    store = _track_store(context)
    if sub == "menu":
        await query.edit_message_text(
            t(lang, "track_menu_title"), reply_markup=menu.track_menu(lang)
        )
    elif sub == "list":
        tracks = await store.list(chat_id)
        title_key = "track_list_title" if tracks else "track_list_empty"
        await query.edit_message_text(
            t(lang, title_key),
            reply_markup=menu.track_list_keyboard(lang, tracks),
        )
    elif sub == "act" and len(parts) >= 3:
        track_id = int(parts[2])
        target = await store.get(chat_id, track_id)
        if target is None:
            await query.edit_message_text(
                t(lang, "track_not_found", ref=f"#{track_id}"),
                reply_markup=menu.back_home(lang, "track:menu"),
            )
            return
        await query.edit_message_text(
            "\n\n".join([
                t(lang, "track_act_title"),
                _format_track(target, lang),
                t(lang, "track_act_help"),
            ]),
            reply_markup=menu.track_actions(lang, track_id),
        )
    elif sub == "do" and len(parts) >= 4:
        await _track_do(update, context, lang, parts[2], int(parts[3]))


async def _track_do(update, context, lang: str, action: str, track_id: int) -> None:
    query = update.callback_query
    chat_id, user_id = _ids(update)
    store = _track_store(context)
    target = await store.get(chat_id, track_id)
    if target is None:
        await query.edit_message_text(
            t(lang, "track_not_found", ref=f"#{track_id}"),
            reply_markup=menu.back_home(lang, "track:menu"),
        )
        return
    if action == "hit":
        updated = mark_track_progress(target, 1)
        await store.update(chat_id, updated)
        await query.edit_message_text(
            t(lang, "track_hit_done", title=updated.title,
              bar=_progress_bar(updated.progress), progress=updated.progress),
            reply_markup=menu.back_home(lang, "track:list"),
        )
    elif action == "end":
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
        await query.edit_message_text(
            "\n".join(lines), reply_markup=menu.back_home(lang, "track:menu")
        )
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
    elif action == "clear":
        await store.update(chat_id, clear_progress(target))
        await query.edit_message_text(
            t(lang, "track_cleared", title=target.title),
            reply_markup=menu.back_home(lang, "track:list"),
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
    context.user_data.setdefault("lang", {})[chat_id] = choice
    await query.edit_message_text(t(choice, "language_set", lang=choice.upper()))


async def _set_language(
    update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str
) -> None:
    chat_id, user_id = _ids(update)
    await _prefs(context).set_language(chat_id, user_id, choice)
    context.user_data.setdefault("lang", {})[chat_id] = choice
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


_HERO_KEY = "newhero"


def _fresh_hero() -> dict:
    return {"name": None, "archetype": None, "assigned": {}}


def _hero(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault(_HERO_KEY, _fresh_hero())


def _alloc_pool(assigned: dict[str, int]) -> list[int]:
    """The values from 1,1,2,2,3 not yet placed, ascending."""
    remaining = Counter(STARTING_ALLOCATION)
    for value in assigned.values():
        remaining[value] -= 1
    pool: list[int] = []
    for value in sorted(remaining):
        pool.extend([value] * max(0, remaining[value]))
    return pool


def _unassigned_stats(assigned: dict[str, int]) -> list[str]:
    return [stat for stat in STAT_NAMES if stat not in assigned]


def _archetype_detail_text(lang: str, archetype) -> str:
    return "\n\n".join([
        f"{archetype.flavor_icon} {t(lang, f'arch_{archetype.key}_name')}",
        t(lang, f"arch_{archetype.key}_desc"),
        t(lang, "new_arch_boost", stat=t(lang, f"stat_{archetype.primary_stat}")),
    ])


def _alloc_text(lang: str, hero: dict) -> str:
    archetype = get_archetype(hero["archetype"])
    lines = [t(lang, "new_alloc_intro"), ""]
    for stat in STAT_NAMES:
        value = hero["assigned"].get(stat)
        shown = str(value) if value is not None else t(lang, "new_alloc_unassigned")
        star = " ⭐" if stat == archetype.primary_stat else ""
        lines.append(
            f"{t(lang, f'stat_{stat}')}{star} "
            f"({t(lang, f'stat_{stat}_desc')}): {shown}"
        )
    lines += ["", t(lang, "new_alloc_tap_value")]
    return "\n".join(lines)


def _confirm_text(lang: str, hero: dict) -> str:
    archetype = get_archetype(hero["archetype"])
    boosted = apply_archetype_bonus(hero["assigned"], archetype)
    stat_bits = []
    for stat in STAT_NAMES:
        mark = t(lang, "new_boost_mark") if stat == archetype.primary_stat else ""
        stat_bits.append(f"{t(lang, f'stat_{stat}')} {boosted[stat]}{mark}")
    items = ", ".join(t(lang, f"item_{key}") for key in archetype.suggested_items)
    return "\n".join([
        t(lang, "new_confirm_title"),
        "",
        f"📜 {hero['name']}",
        t(lang, "new_confirm_archetype_line",
          icon=archetype.flavor_icon, name=t(lang, f"arch_{archetype.key}_name")),
        " · ".join(stat_bits),
        t(lang, "new_confirm_items_line", items=items),
    ])


async def new_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    if await _store(context).get(chat_id, user_id) is not None:
        await update.message.reply_text(t(lang, "new_already_exists"))
        return ConversationHandler.END
    context.user_data[_HERO_KEY] = _fresh_hero()
    await update.message.reply_text(t(lang, "new_intro"))
    return NAME


async def new_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for character creation via the 👤 Character → ✨ button."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    if await _store(context).get(chat_id, user_id) is not None:
        await query.edit_message_text(
            t(lang, "new_already_exists"),
            reply_markup=menu.back_home(lang, "char:menu"),
        )
        return ConversationHandler.END
    context.user_data[_HERO_KEY] = _fresh_hero()
    await query.edit_message_text(t(lang, "new_intro"))
    return NAME


async def new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return NAME
    lang = await _lang(update, context)
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text(t(lang, "new_empty_name"))
        return NAME
    _hero(context)["name"] = name
    await update.message.reply_text(
        t(lang, "new_pick_archetype"), reply_markup=menu.archetype_keyboard(lang)
    )
    return NEW_ARCH


async def new_arch_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show a chosen path's blurb plus Confirm / Another-path."""
    query = update.callback_query
    if query is None or query.data is None:
        return NEW_ARCH
    await query.answer()
    lang = await _lang(update, context)
    key = query.data.split(":")[2]
    try:
        archetype = get_archetype(key)
    except ValueError:
        return NEW_ARCH
    await query.edit_message_text(
        _archetype_detail_text(lang, archetype),
        reply_markup=menu.archetype_detail_keyboard(lang, key),
    )
    return NEW_ARCH


async def new_arch_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = await _lang(update, context)
    await query.edit_message_text(
        t(lang, "new_pick_archetype"), reply_markup=menu.archetype_keyboard(lang)
    )
    return NEW_ARCH


async def new_arch_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lock in the path and move to stat allocation."""
    query = update.callback_query
    if query is None or query.data is None:
        return NEW_ARCH
    await query.answer()
    lang = await _lang(update, context)
    key = query.data.split(":")[2]
    try:
        get_archetype(key)
    except ValueError:
        return NEW_ARCH
    hero = _hero(context)
    hero["archetype"] = key
    hero["assigned"] = {}
    await query.edit_message_text(
        _alloc_text(lang, hero),
        reply_markup=menu.allocation_keyboard(lang, _alloc_pool(hero["assigned"])),
    )
    return NEW_ALLOC


async def new_alloc_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """A pool value was tapped — ask which stat receives it."""
    query = update.callback_query
    if query is None or query.data is None:
        return NEW_ALLOC
    await query.answer()
    lang = await _lang(update, context)
    try:
        value = int(query.data.split(":")[2])
    except (ValueError, IndexError):
        return NEW_ALLOC
    hero = _hero(context)
    if value not in _alloc_pool(hero["assigned"]):
        return NEW_ALLOC  # stale tap; that value is already spent
    hero["pending_value"] = value
    await query.edit_message_text(
        t(lang, "new_assign_prompt", value=value),
        reply_markup=menu.assign_stat_keyboard(lang, _unassigned_stats(hero["assigned"])),
    )
    return NEW_ASSIGN


async def new_alloc_assign(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Place the pending value onto the chosen stat, back to allocation."""
    query = update.callback_query
    if query is None or query.data is None:
        return NEW_ASSIGN
    await query.answer()
    lang = await _lang(update, context)
    stat = query.data.split(":")[2]
    hero = _hero(context)
    value = hero.pop("pending_value", None)
    if value is not None and stat in STAT_NAMES and stat not in hero["assigned"]:
        hero["assigned"][stat] = value
    await query.edit_message_text(
        _alloc_text(lang, hero),
        reply_markup=menu.allocation_keyboard(lang, _alloc_pool(hero["assigned"])),
    )
    return NEW_ALLOC


async def new_alloc_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = await _lang(update, context)
    hero = _hero(context)
    if _alloc_pool(hero["assigned"]):
        return NEW_ALLOC  # not everything placed yet
    await query.edit_message_text(
        _confirm_text(lang, hero), reply_markup=menu.new_confirm_keyboard(lang)
    )
    return NEW_CONFIRM


async def new_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear the allocation and start placing values again (keeps name & path)."""
    query = update.callback_query
    await query.answer()
    lang = await _lang(update, context)
    hero = _hero(context)
    hero["assigned"] = {}
    hero.pop("pending_value", None)
    await query.edit_message_text(
        _alloc_text(lang, hero),
        reply_markup=menu.allocation_keyboard(lang, _alloc_pool(hero["assigned"])),
    )
    return NEW_ALLOC


async def new_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Build, persist, and present the finished hero (plus an optional intro line)."""
    query = update.callback_query
    await query.answer()
    lang = await _lang(update, context)
    hero = context.user_data.get(_HERO_KEY, {})
    try:
        archetype = get_archetype(hero.get("archetype"))
        items = [t(lang, f"item_{key}") for key in archetype.suggested_items]
        character = create_with_archetype(
            hero.get("name") or "", hero.get("assigned", {}), archetype, items=items
        )
    except (ValueError, TypeError) as error:
        context.user_data.pop(_HERO_KEY, None)
        await query.edit_message_text(
            t(lang, "new_failed", error=error), reply_markup=menu.home_only(lang)
        )
        return ConversationHandler.END

    chat_id, user_id = _ids(update)
    try:
        await _store(context).create(chat_id, user_id, character)
    except CharacterExists:
        context.user_data.pop(_HERO_KEY, None)
        await query.edit_message_text(
            t(lang, "new_already_exists"), reply_markup=menu.home_only(lang)
        )
        return ConversationHandler.END

    context.user_data.pop(_HERO_KEY, None)
    await query.edit_message_reply_markup(reply_markup=None)
    await update.effective_chat.send_message(
        t(lang, "new_created") + "\n\n" + _format_sheet(character, lang)
        + "\n\n" + t(lang, "new_next_hint"),
        reply_markup=menu.home_only(lang),
    )
    _schedule_intro(update, context, character.name,
                    t(lang, f"arch_{archetype.key}_name"), lang)
    return ConversationHandler.END


def _schedule_intro(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    name: str,
    archetype_label: str,
    lang: str,
) -> None:
    """Optionally send one GM-style opening line after creation (fails soft)."""
    if not narrator_enabled():
        return
    chat = update.effective_chat

    async def _run() -> None:
        await _show_typing(chat)
        prose = await narrate_intro(name, archetype_label, lang)
        if prose:
            await chat.send_message(
                f"<i>{html.escape(prose)}</i>", parse_mode=ParseMode.HTML
            )

    context.application.create_task(_run())


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shared /cancel for every guided creation flow."""
    lang = await _lang(update, context)
    for key in (_HERO_KEY, "new_vow", "new_track", "scust_text"):
        context.user_data.pop(key, None)
    if update.message is not None:
        await update.message.reply_text(t(lang, "new_cancelled"))
    return ConversationHandler.END


async def conv_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Expire an abandoned dialog: drop its state and point back to the menu."""
    lang = await _lang(update, context)
    for key in (_HERO_KEY, "new_vow", "new_track", "scust_text"):
        context.user_data.pop(key, None)
    message = update.effective_message
    if message is not None:
        try:
            await message.reply_text(
                t(lang, "conv_expired"), reply_markup=menu.home_only(lang)
            )
        except Exception:  # noqa: BLE001 — expiry is best-effort
            pass
    return ConversationHandler.END


_TIMEOUT_STATE = {ConversationHandler.TIMEOUT: [TypeHandler(Update, conv_timeout)]}


def build_new_handler() -> ConversationHandler:
    """The guided /new flow: name → path → stat allocation → confirm."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[
            CommandHandler("new", new_start),
            CallbackQueryHandler(new_start_cb, pattern=r"^cnew:start$"),
        ],
        states={
            NAME: [MessageHandler(text, new_name)],
            NEW_ARCH: [
                CallbackQueryHandler(new_arch_confirm, pattern=r"^cnew:archok:"),
                CallbackQueryHandler(new_arch_back, pattern=r"^cnew:archback$"),
                CallbackQueryHandler(new_arch_detail, pattern=r"^cnew:arch:"),
            ],
            NEW_ALLOC: [
                CallbackQueryHandler(new_alloc_value, pattern=r"^cnew:val:"),
                CallbackQueryHandler(new_alloc_done, pattern=r"^cnew:done$"),
            ],
            NEW_ASSIGN: [
                CallbackQueryHandler(new_alloc_assign, pattern=r"^cnew:assign:"),
            ],
            NEW_CONFIRM: [
                CallbackQueryHandler(new_create, pattern=r"^cnew:create$"),
                CallbackQueryHandler(new_restart, pattern=r"^cnew:restart$"),
            ],
            **_TIMEOUT_STATE,
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )


# --- vow / track creation conversations (button-driven) ----------------------


async def vnew_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    lang = await _lang(update, context)
    context.user_data["new_vow"] = {}
    await query.edit_message_text(
        t(lang, "vnew_pick_rank"), reply_markup=menu.rank_keyboard(lang, "vnew:rank")
    )
    return VOW_RANK


async def vnew_rank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return VOW_RANK
    await query.answer()
    lang = await _lang(update, context)
    context.user_data.setdefault("new_vow", {})["rank"] = query.data.split(":")[2]
    await query.edit_message_text(t(lang, "vnew_ask_title"))
    return VOW_TITLE


async def vnew_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return VOW_TITLE
    lang = await _lang(update, context)
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text(t(lang, "vnew_ask_title"))
        return VOW_TITLE
    data = context.user_data.pop("new_vow", {})
    chat_id, user_id = _ids(update)
    created = await _vow_store(context).create(
        chat_id, user_id, title, Rank(data.get("rank", "troublesome"))
    )
    await update.message.reply_text(
        t(lang, "vow_created") + "\n\n" + _format_vow(created, lang)
        + "\n\n" + t(lang, "vow_created_hint"),
        reply_markup=menu.home_only(lang),
    )
    return ConversationHandler.END


def build_vow_handler() -> ConversationHandler:
    """Vow creation: pick rank (buttons) → type title."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(vnew_start, pattern=r"^vnew:start$")],
        states={
            VOW_RANK: [CallbackQueryHandler(vnew_rank, pattern=r"^vnew:rank:")],
            VOW_TITLE: [MessageHandler(text, vnew_title)],
            **_TIMEOUT_STATE,
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )


async def tnew_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    lang = await _lang(update, context)
    context.user_data["new_track"] = {}
    await query.edit_message_text(
        t(lang, "tnew_pick_type"),
        reply_markup=menu.track_type_keyboard(lang, "tnew:type"),
    )
    return TRACK_TYPE


async def tnew_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return TRACK_TYPE
    await query.answer()
    lang = await _lang(update, context)
    context.user_data.setdefault("new_track", {})["type"] = query.data.split(":")[2]
    await query.edit_message_text(
        t(lang, "tnew_pick_rank"), reply_markup=menu.rank_keyboard(lang, "tnew:rank")
    )
    return TRACK_RANK


async def tnew_rank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return TRACK_RANK
    await query.answer()
    lang = await _lang(update, context)
    context.user_data.setdefault("new_track", {})["rank"] = query.data.split(":")[2]
    await query.edit_message_text(t(lang, "tnew_ask_title"))
    return TRACK_TITLE


async def tnew_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return TRACK_TITLE
    lang = await _lang(update, context)
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text(t(lang, "tnew_ask_title"))
        return TRACK_TITLE
    data = context.user_data.pop("new_track", {})
    chat_id, _ = _ids(update)
    created = await _track_store(context).create(
        chat_id, title,
        TrackType(data.get("type", "custom")),
        Rank(data.get("rank", "troublesome")),
    )
    await update.message.reply_text(
        t(lang, "track_created") + "\n\n" + _format_track(created, lang)
        + "\n\n" + t(lang, "track_created_hint"),
        reply_markup=menu.home_only(lang),
    )
    return ConversationHandler.END


def build_track_handler() -> ConversationHandler:
    """Track creation: pick type (buttons) → rank (buttons) → type title."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(tnew_start, pattern=r"^tnew:start$")],
        states={
            TRACK_TYPE: [CallbackQueryHandler(tnew_type, pattern=r"^tnew:type:")],
            TRACK_RANK: [CallbackQueryHandler(tnew_rank, pattern=r"^tnew:rank:")],
            TRACK_TITLE: [MessageHandler(text, tnew_title)],
            **_TIMEOUT_STATE,
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )


# --- inventory / background editing (button entry → typed input) -------------


async def item_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    if await _store(context).get(chat_id, user_id) is None:
        await query.edit_message_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
        return ConversationHandler.END
    await query.edit_message_text(t(lang, "item_add_prompt"))
    return ITEM_NAME


async def item_add_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ITEM_NAME
    lang = await _lang(update, context)
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text(t(lang, "item_empty_name"))
        return ITEM_NAME
    if len(name) > MAX_ITEM_LENGTH:
        await update.message.reply_text(t(lang, "item_too_long", max=MAX_ITEM_LENGTH))
        return ITEM_NAME

    chat_id, user_id = _ids(update)
    store = _store(context)
    character = await store.get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
        return ConversationHandler.END
    if len(character.items) >= MAX_ITEMS:
        await update.message.reply_text(t(lang, "inventory_full", max=MAX_ITEMS))
        return ConversationHandler.END

    updated = add_item(character, name)
    await store.update(chat_id, user_id, updated)
    await update.message.reply_text(
        t(lang, "item_added", item=name) + "\n\n" + _format_sheet(updated, lang),
        reply_markup=menu.home_only(lang),
    )
    return ConversationHandler.END


def build_item_handler() -> ConversationHandler:
    """Add an inventory item: button entry → typed item name."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(item_add_start, pattern=r"^iadd:start$")],
        states={ITEM_NAME: [MessageHandler(text, item_add_save)], **_TIMEOUT_STATE},
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )


async def bg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    if await _store(context).get(chat_id, user_id) is None:
        await query.edit_message_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
        return ConversationHandler.END
    await query.edit_message_text(t(lang, "bg_prompt", max=MAX_BACKGROUND_LENGTH))
    return BG_TEXT


async def bg_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return BG_TEXT
    lang = await _lang(update, context)
    text_in = (update.message.text or "").strip()
    if len(text_in) > MAX_BACKGROUND_LENGTH:
        await update.message.reply_text(t(lang, "bg_too_long", max=MAX_BACKGROUND_LENGTH))
        return BG_TEXT

    chat_id, user_id = _ids(update)
    store = _store(context)
    character = await store.get(chat_id, user_id)
    if character is None:
        await update.message.reply_text(
            t(lang, "no_character"), reply_markup=menu.no_character_keyboard(lang)
        )
        return ConversationHandler.END

    updated = set_background(character, text_in)
    await store.update(chat_id, user_id, updated)
    await update.message.reply_text(
        t(lang, "bg_set") + "\n\n" + _format_sheet(updated, lang),
        reply_markup=menu.home_only(lang),
    )
    return ConversationHandler.END


def build_background_handler() -> ConversationHandler:
    """Set the hero's background story: button entry → typed prose."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(bg_start, pattern=r"^bgset:start$")],
        states={BG_TEXT: [MessageHandler(text, bg_save)], **_TIMEOUT_STATE},
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )


# --- formatting helpers ------------------------------------------------------


def _field_label(field: str, lang: str) -> str:
    key = "momentum" if field == "momentum" else f"track_{field}"
    return t(lang, key)


def _outcome_label(outcome: Outcome, lang: str) -> str:
    return t(lang, _OUTCOME_KEYS[outcome])


_HINT_KEYS = {
    Outcome.STRONG: "hint_strong",
    Outcome.WEAK: "hint_weak",
    Outcome.MISS: "hint_miss",
}


def _outcome_hint(outcome: Outcome, lang: str) -> str:
    """One 💡 line telling the player what to do after this outcome."""
    return t(lang, _HINT_KEYS[outcome])


def _moves_overview(lang: str, keys) -> str:
    """One '• name: what it's for' line per move key, for pick screens."""
    return "\n".join(
        f"• {t(lang, f'move_{key}')}: {t(lang, f'move_{key}_desc')}"
        for key in keys
    )


def _move_blurb(spec, lang: str) -> str:
    """What a move is for and what each outcome does, ending in a stat prompt."""
    lines = [
        t(lang, "move_result_header", move=t(lang, f"move_{spec.key}")),
        t(lang, f"move_{spec.key}_desc"),
        "",
        t(lang, "move_effects_header"),
    ]
    for outcome in (Outcome.STRONG, Outcome.WEAK, Outcome.MISS):
        effects = spec.effects.get(outcome, {})
        changes = ", ".join(
            f"{_field_label(field, lang)} {change:+d}"
            for field, change in effects.items()
        ) or t(lang, "move_no_effect")
        lines.append(f"{_outcome_label(outcome, lang)}: {changes}")
    lines += ["", t(lang, "move_stat_title")]
    return "\n".join(lines)


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
    base = t(
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
    items = ", ".join(character.items) if character.items else t(lang, "sheet_items_empty")
    story = character.background or t(lang, "sheet_background_empty")
    lines = [base]
    archetype = ARCHETYPES.get(character.archetype) if character.archetype else None
    if archetype is not None:
        lines.append(t(lang, "sheet_archetype", icon=archetype.flavor_icon,
                       name=t(lang, f"arch_{archetype.key}_name")))
    lines.append(t(lang, "sheet_items", items=items))
    lines.append(t(lang, "sheet_background", text=story))
    return "\n".join(lines)


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
