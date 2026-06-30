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
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
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
    MOVES,
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
    apply_effects,
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
    STAT_MAX,
    STAT_MIN,
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
from narrator import NarratorContext, is_enabled as narrator_enabled, narrate
from storage import CharacterExists

# Conversation states for /new (character creation).
NAME, EDGE, HEART, IRON, SHADOW, WITS = range(6)
# Conversation states for vow / track creation.
VOW_RANK, VOW_TITLE, TRACK_TYPE, TRACK_RANK, TRACK_TITLE = range(6, 11)
# Conversation states for inventory / background editing.
ITEM_NAME, BG_TEXT = range(11, 13)

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
    await update.message.reply_text(
        t(lang, "menu_title"), reply_markup=menu.main_menu(lang)
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    lang = await _lang(update, context)
    await update.message.reply_text(
        t(lang, "menu_title"), reply_markup=menu.main_menu(lang)
    )


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
        await query.edit_message_text(
            t(lang, "menu_title"), reply_markup=menu.main_menu(lang)
        )
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
            t(lang, "move_pick_title"),
            reply_markup=menu.moves_keyboard(lang, category),
        )
    elif sub == "mv":
        spec = MOVES.get(parts[2])
        if spec is None:
            return
        await query.edit_message_text(
            t(lang, "move_stat_title"),
            reply_markup=menu.stat_keyboard(
                lang, f"move:st:{spec.key}", f"move:cat:{spec.category.value}"
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
            t(lang, "no_character"), reply_markup=menu.home_only(lang)
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
    return "\n".join(lines)


# --- roll flow ---------------------------------------------------------------


async def _menu_roll(update, context, lang: str, parts: list[str]) -> None:
    query = update.callback_query
    sub = parts[1] if len(parts) > 1 else ""
    if sub == "menu":
        await query.edit_message_text(
            t(lang, "roll_pick_title"),
            reply_markup=menu.stat_keyboard(lang, "roll:st", menu.HOME),
        )
    elif sub == "st" and len(parts) >= 3:
        stat_name = parts[2]
        chat_id, user_id = _ids(update)
        character = await _store(context).get(chat_id, user_id)
        if character is None:
            await query.edit_message_text(
                t(lang, "no_character"), reply_markup=menu.home_only(lang)
            )
            return
        result = roll_action(stat_value(character, stat_name), 0)
        await update.effective_chat.send_message(
            _format_roll(result, stat_name, lang), reply_markup=menu.home_only(lang)
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
        if new_value != current:
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


async def _render_stepper(query, character, field: str, lang: str) -> None:
    await query.edit_message_text(
        t(lang, "char_field_now",
          field=_field_label(field, lang), value=getattr(character, field)),
        reply_markup=menu.char_stepper(lang, field),
    )


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
        if not vows:
            await query.edit_message_text(
                t(lang, "vow_list_empty"),
                reply_markup=menu.back_home(lang, "vow:menu"),
            )
            return
        await query.edit_message_text(
            t(lang, "vow_list_title"),
            reply_markup=menu.vow_list_keyboard(lang, vows),
        )
    elif sub == "act" and len(parts) >= 3:
        await query.edit_message_text(
            t(lang, "vow_act_title"),
            reply_markup=menu.vow_actions(lang, int(parts[2])),
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
        if not tracks:
            await query.edit_message_text(
                t(lang, "track_list_empty"),
                reply_markup=menu.back_home(lang, "track:menu"),
            )
            return
        await query.edit_message_text(
            t(lang, "track_list_title"),
            reply_markup=menu.track_list_keyboard(lang, tracks),
        )
    elif sub == "act" and len(parts) >= 3:
        await query.edit_message_text(
            t(lang, "track_act_title"),
            reply_markup=menu.track_actions(lang, int(parts[2])),
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
    context.user_data["new_char"] = {}
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
    context.user_data.setdefault("new_char", {})["name"] = name
    await update.message.reply_text(
        _stat_prompt("edge", lang), reply_markup=menu.stat_value_keyboard("cnew:edge")
    )
    return EDGE


def _stat_step(stat_name: str, this_state: int, next_prompt: str, next_state):
    """Build a typed conversation step that collects one stat in range 1-3."""

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

        context.user_data.setdefault("new_char", {})[stat_name] = value
        if next_state is None:
            return await _finish_new(update, context)
        await update.message.reply_text(
            _stat_prompt(next_prompt, lang),
            reply_markup=menu.stat_value_keyboard(f"cnew:{next_prompt}"),
        )
        return next_state

    return step


def _stat_button_step(stat_name: str, this_state: int, next_prompt: str, next_state):
    """Build a button conversation step (1/2/3 taps) that collects one stat."""

    async def step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        if query is None or query.data is None:
            return this_state
        await query.answer()
        lang = await _lang(update, context)
        try:
            value = int(query.data.split(":")[2])
        except (ValueError, IndexError):
            return this_state
        if not STAT_MIN <= value <= STAT_MAX:
            return this_state

        context.user_data.setdefault("new_char", {})[stat_name] = value
        if next_state is None:
            await query.edit_message_reply_markup(reply_markup=None)
            return await _finish_new(update, context)
        await query.edit_message_text(
            _stat_prompt(next_prompt, lang),
            reply_markup=menu.stat_value_keyboard(f"cnew:{next_prompt}"),
        )
        return next_state

    return step


new_edge = _stat_step("edge", EDGE, "heart", HEART)
new_heart = _stat_step("heart", HEART, "iron", IRON)
new_iron = _stat_step("iron", IRON, "shadow", SHADOW)
new_shadow = _stat_step("shadow", SHADOW, "wits", WITS)
new_wits = _stat_step("wits", WITS, "", None)

new_edge_btn = _stat_button_step("edge", EDGE, "heart", HEART)
new_heart_btn = _stat_button_step("heart", HEART, "iron", IRON)
new_iron_btn = _stat_button_step("iron", IRON, "shadow", SHADOW)
new_shadow_btn = _stat_button_step("shadow", SHADOW, "wits", WITS)
new_wits_btn = _stat_button_step("wits", WITS, "", None)


async def _finish_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create and persist the hero, then send the sheet (works from text or button)."""
    lang = await _lang(update, context)
    data = context.user_data.pop("new_char", {})
    chat = update.effective_chat
    try:
        character = new_character(
            data["name"], data["edge"], data["heart"],
            data["iron"], data["shadow"], data["wits"],
        )
    except (KeyError, ValueError) as error:
        await chat.send_message(t(lang, "new_failed", error=error))
        return ConversationHandler.END

    chat_id, user_id = _ids(update)
    try:
        await _store(context).create(chat_id, user_id, character)
    except CharacterExists:
        await chat.send_message(t(lang, "new_already_exists"))
        return ConversationHandler.END

    await chat.send_message(
        t(lang, "new_created") + "\n\n" + _format_sheet(character, lang),
        reply_markup=menu.home_only(lang),
    )
    return ConversationHandler.END


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shared /cancel for every guided creation flow."""
    lang = await _lang(update, context)
    for key in ("new_char", "new_vow", "new_track"):
        context.user_data.pop(key, None)
    if update.message is not None:
        await update.message.reply_text(t(lang, "new_cancelled"))
    return ConversationHandler.END


def build_new_handler() -> ConversationHandler:
    """Build the /new conversation handler (command and button entry points)."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[
            CommandHandler("new", new_start),
            CallbackQueryHandler(new_start_cb, pattern=r"^cnew:start$"),
        ],
        states={
            NAME: [MessageHandler(text, new_name)],
            EDGE: [CallbackQueryHandler(new_edge_btn, pattern=r"^cnew:edge:"),
                   MessageHandler(text, new_edge)],
            HEART: [CallbackQueryHandler(new_heart_btn, pattern=r"^cnew:heart:"),
                    MessageHandler(text, new_heart)],
            IRON: [CallbackQueryHandler(new_iron_btn, pattern=r"^cnew:iron:"),
                   MessageHandler(text, new_iron)],
            SHADOW: [CallbackQueryHandler(new_shadow_btn, pattern=r"^cnew:shadow:"),
                     MessageHandler(text, new_shadow)],
            WITS: [CallbackQueryHandler(new_wits_btn, pattern=r"^cnew:wits:"),
                   MessageHandler(text, new_wits)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
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
        t(lang, "vow_created") + "\n\n" + _format_vow(created, lang),
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
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
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
        t(lang, "track_created") + "\n\n" + _format_track(created, lang),
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
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
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
            t(lang, "no_character"), reply_markup=menu.home_only(lang)
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
        await update.message.reply_text(t(lang, "no_character"))
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
        states={ITEM_NAME: [MessageHandler(text, item_add_save)]},
        fallbacks=[CommandHandler("cancel", conv_cancel)],
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
            t(lang, "no_character"), reply_markup=menu.home_only(lang)
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
        await update.message.reply_text(t(lang, "no_character"))
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
        states={BG_TEXT: [MessageHandler(text, bg_save)]},
        fallbacks=[CommandHandler("cancel", conv_cancel)],
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
    return "\n".join([
        base,
        t(lang, "sheet_items", items=items),
        t(lang, "sheet_background", text=story),
    ])


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
