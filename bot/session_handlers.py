"""Multiplayer session handlers: lobby, dual game messages, and turn order.

Thin Telegram layer over :mod:`engine.session` (the rules) and
:mod:`storage.sessions` (persistence), same contract as the rest of the bot:
no game logic here. A session lives in one chat and is driven by three
edit-in-place messages:

- the **lobby** message (participant list, refreshed on join/leave),
- the **Setting** message (the shared scene, written once at game start — by
  the local LLM when enabled, else a static text; it rarely changes),
- the **Current Turn** message (active player's hero card + action buttons,
  edited on every turn change).

Access control: every game-turn button checks that the clicker *is* the active
player and rejects everyone else with a popup alert, without executing the
action. Lobby controls are enforced the same way (start/end are creator-only).
An idle player is skipped automatically after :data:`TURN_TIMEOUT` seconds via
the job queue.
"""

from __future__ import annotations

import os
from dataclasses import replace

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot import menu
from bot.handlers import (
    CONVERSATION_TIMEOUT,
    _TIMEOUT_STATE,
    _fire_narration,
    _format_move,
    _format_roll,
    _ids,
    _lang,
    _move_blurb,
    _moves_overview,
    _outcome_hint,
    _schedule_gm_scene,
    _show_typing,
    _store,
    conv_cancel,
)
from bot.i18n import t
from engine import (
    ARCHETYPES,
    MAX_PLAYERS,
    MOVES,
    AlreadyJoined,
    AlreadyStarted,
    SessionError,
    SessionFull,
    SessionPhase,
    WrongPassword,
    active_player,
    advance_turn,
    apply_effects,
    create_session,
    in_session,
    is_active_player,
    join_session,
    leave_session,
    resolve_move,
    roll_action,
    start_session,
    stat_value,
)
from engine.character import STAT_NAMES
from engine.session import MAX_PASSWORD_LENGTH
from gm import GMContext, generate_scene
from gm import is_enabled as gm_enabled
from narrator import NarratorContext
from storage import SessionRecord

# Conversation states (lobby password entry, custom-action flow).
SESSION_PASSWORD, JOIN_PASSWORD, CUSTOM_TEXT, CUSTOM_STAT = range(20, 24)

# An idle active player is skipped after this many seconds.
TURN_TIMEOUT = 600
# A typed custom action is trimmed to this length before echo/narration.
MAX_CUSTOM_ACTION_LENGTH = 200

# English seeds for the LLM Setting prompt (the reply language is steered by
# GMContext.language; these never reach the player directly).
_SETTING_TITLE = "A shared journey begins"
_SETTING_GOAL = "The fellowship sets out into the Ironlands together"
_SETTING_CUE = "The party gathers. Describe the opening setting in 2-3 sentences."


def _sessions(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["sessions"]


def _llm_setting_enabled() -> bool:
    """Whether the Setting message is LLM-written.

    ``SESSION_LLM_SETTING`` overrides explicitly; unset, it follows the GM
    flag. Generation always fails soft to the static localized setting.
    """
    value = os.environ.get("SESSION_LLM_SETTING")
    if value is None:
        return gm_enabled()
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _display_name(user) -> str:
    """A player's display name for the party list and turn announcements."""
    name = (user.full_name or "").strip() if user is not None else ""
    return name or (str(user.id) if user is not None else "?")


async def _deny(query, lang: str, key: str, **kwargs: object) -> None:
    """Reject a button press with a popup alert; the action is not executed."""
    await query.answer(t(lang, key, **kwargs), show_alert=True)


async def _delete_quietly(message) -> None:
    """Best-effort delete (used to hide typed passwords); never raises."""
    try:
        await message.delete()
    except Exception:  # noqa: BLE001 — cosmetic only
        pass


# --- shared edit-in-place messages --------------------------------------------


async def _upsert_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int | None,
    text: str,
    keyboard,
) -> int:
    """Edit the tracked message in place, or send a fresh one; return its id."""
    if message_id is not None:
        try:
            await context.bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id,
                reply_markup=keyboard,
            )
            return message_id
        except BadRequest as error:
            if "not modified" in str(error).lower():
                return message_id
            # deleted or too old to edit — fall through to a new message
        except Exception:  # noqa: BLE001
            pass
    message = await context.bot.send_message(
        chat_id, text, reply_markup=keyboard
    )
    return message.message_id


async def _strip_buttons(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, *message_ids: int | None
) -> None:
    """Remove keyboards from finished session messages (best-effort)."""
    for message_id in message_ids:
        if message_id is None:
            continue
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:  # noqa: BLE001 — cosmetic only
            pass


def _lobby_text(record: SessionRecord) -> str:
    lang = record.lang
    session = record.session
    lines = [
        t(lang, "session_lobby_title"),
        "",
        t(lang, "session_lobby_players", count=len(session.players)),
    ]
    for player in session.players:
        mark = "👑" if player.user_id == session.creator_id else "•"
        lines.append(f"{mark} {player.name}")
    lines += ["", t(lang, "session_lobby_hint")]
    return "\n".join(lines)


async def _render_lobby(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, record: SessionRecord
) -> None:
    """Refresh (or send) the shared lobby message and persist the record."""
    message_id = await _upsert_message(
        context, chat_id, record.lobby_message_id,
        _lobby_text(record), menu.lobby_keyboard(record.lang),
    )
    await _sessions(context).save(
        chat_id, replace(record, lobby_message_id=message_id)
    )


def _turn_text(record: SessionRecord, character) -> str:
    """The Current-Turn message: whose turn plus their extended hero card."""
    lang = record.lang
    player = active_player(record.session)
    lines = [t(lang, "session_turn_header", name=player.name), ""]
    if character is None:
        lines.append(t(lang, "session_turn_no_hero"))
    else:
        lines.append(f"👤 {character.name}")
        archetype = (
            ARCHETYPES.get(character.archetype) if character.archetype else None
        )
        if archetype is not None:
            lines.append(t(lang, "session_card_class", icon=archetype.flavor_icon,
                           name=t(lang, f"arch_{archetype.key}_name")))
        lines.append(" · ".join(
            f"{t(lang, f'stat_{stat}')} {getattr(character, stat)}"
            for stat in STAT_NAMES
        ))
        lines.append(
            f"❤️ {t(lang, 'track_health')} {character.health} · "
            f"🌟 {t(lang, 'track_spirit')} {character.spirit} · "
            f"🎒 {t(lang, 'track_supply')} {character.supply} · "
            f"⚡ {t(lang, 'momentum')} {character.momentum}"
        )
    lines += ["", t(lang, "session_turn_choose")]
    return "\n".join(lines)


async def _render_turn(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, record: SessionRecord
) -> None:
    """Refresh the Current-Turn message, persist, and arm the idle-skip timer."""
    player = active_player(record.session)
    character = await context.bot_data["store"].get(chat_id, player.user_id)
    message_id = await _upsert_message(
        context, chat_id, record.turn_message_id,
        _turn_text(record, character),
        menu.turn_keyboard(record.lang, character is not None),
    )
    await _sessions(context).save(
        chat_id, replace(record, turn_message_id=message_id)
    )
    _schedule_turn_job(context, chat_id, player.user_id)


async def _advance(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, record: SessionRecord
) -> None:
    """Round-robin: pass the turn on and refresh the Current-Turn message."""
    await _render_turn(context, chat_id, record.with_session(
        advance_turn(record.session)
    ))


# --- idle-skip timer -----------------------------------------------------------


def _job_name(chat_id: int) -> str:
    return f"sess-turn:{chat_id}"


def _cancel_turn_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    job_queue = getattr(context, "job_queue", None)
    if job_queue is None:
        return
    for job in job_queue.get_jobs_by_name(_job_name(chat_id)):
        job.schedule_removal()


def _schedule_turn_job(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int
) -> None:
    job_queue = getattr(context, "job_queue", None)
    if job_queue is None:  # job-queue extra not installed — no auto-skip
        return
    _cancel_turn_job(context, chat_id)
    job_queue.run_once(
        _turn_timeout_job, TURN_TIMEOUT,
        chat_id=chat_id, name=_job_name(chat_id), data=user_id,
    )


async def _turn_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Skip the active player if they stayed idle for a whole turn window."""
    job = context.job
    chat_id = job.chat_id
    record = await _sessions(context).get(chat_id)
    if record is None or record.session.phase is not SessionPhase.ACTIVE:
        return
    player = active_player(record.session)
    if player.user_id != job.data:
        return  # the turn already moved on
    try:
        await context.bot.send_message(
            chat_id, t(record.lang, "session_skipped", name=player.name)
        )
    except Exception:  # noqa: BLE001 — the skip itself must still happen
        pass
    await _advance(context, chat_id, record)


# --- /session command & the sess: callback router --------------------------------


async def session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the session hub: create CTA, the lobby, or the running-game view."""
    if update.message is None:
        return
    lang = await _lang(update, context)
    chat_id, _ = _ids(update)
    record = await _sessions(context).get(chat_id)
    if record is None:
        await update.message.reply_text(
            t(lang, "session_hub_none"),
            reply_markup=menu.session_none_keyboard(lang),
        )
    elif record.session.phase is SessionPhase.LOBBY:
        # A fresh lobby message at the bottom; the old one loses its buttons.
        await _strip_buttons(context, chat_id, record.lobby_message_id)
        await _render_lobby(context, chat_id, replace(record, lobby_message_id=None))
    else:
        await update.message.reply_text(
            t(record.lang, "session_status_active",
              name=active_player(record.session).name),
            reply_markup=menu.session_active_keyboard(record.lang),
        )


async def session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route every ``sess:`` button, enforcing per-user access on each action."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "menu":
        await query.answer()
        await _hub_view(update, context, lang)
        return

    record = await _sessions(context).get(chat_id)
    if record is None:
        await _deny(query, lang, "session_no_session")
        return
    session = record.session

    if action == "begin":
        if user_id != session.creator_id:
            await _deny(query, lang, "session_not_creator")
        elif session.phase is not SessionPhase.LOBBY:
            await _deny(query, lang, "session_already_started")
        else:
            await query.answer()
            await _begin_game(update, context, record)
    elif action == "leave":
        if not in_session(session, user_id):
            await _deny(query, lang, "session_not_in")
        else:
            await query.answer()
            await _leave(update, context, record, user_id)
    elif action == "end":
        if user_id != session.creator_id:
            await _deny(query, lang, "session_not_creator")
        else:
            await query.answer()
            await _end(update, context, record)
    elif action in ("turn", "pass", "move", "mv", "st"):
        # Game-turn buttons: only the active player may act; everyone else
        # gets an alert and nothing happens.
        if not is_active_player(session, user_id):
            await _deny(query, lang, "session_not_your_turn")
            return
        await query.answer()
        await _turn_action(update, context, record, action, parts)


async def _hub_view(update, context, lang: str) -> None:
    """The 👥 entry from the main menu: adapt to the chat's session state."""
    query = update.callback_query
    chat_id, _ = _ids(update)
    record = await _sessions(context).get(chat_id)
    if record is None:
        await query.edit_message_text(
            t(lang, "session_hub_none"),
            reply_markup=menu.session_none_keyboard(lang),
        )
    elif record.session.phase is SessionPhase.LOBBY:
        # This message becomes the tracked lobby view; the previous lobby
        # message (if any) loses its now-duplicated buttons.
        message = query.message
        if message is not None and record.lobby_message_id != message.message_id:
            await _strip_buttons(context, chat_id, record.lobby_message_id)
        await query.edit_message_text(
            _lobby_text(record), reply_markup=menu.lobby_keyboard(record.lang)
        )
        if message is not None:
            await _sessions(context).save(
                chat_id, replace(record, lobby_message_id=message.message_id)
            )
    else:
        await query.edit_message_text(
            t(record.lang, "session_status_active",
              name=active_player(record.session).name),
            reply_markup=menu.session_active_keyboard(record.lang),
        )


async def _begin_game(update, context, record: SessionRecord) -> None:
    """Creator starts the game: announce, post Setting, post the first turn."""
    chat_id, _ = _ids(update)
    lang = record.lang
    record = record.with_session(
        start_session(record.session, record.session.creator_id)
    )
    chat = update.effective_chat
    await chat.send_message(t(lang, "session_started"))
    setting = None
    if _llm_setting_enabled():
        await _show_typing(chat)
        setting = await _generate_setting(context, chat_id, record)
    if not setting:
        setting = t(lang, "session_setting_default")
    setting_message = await chat.send_message(
        t(lang, "session_setting_header") + "\n\n" + setting
    )
    await _strip_buttons(context, chat_id, record.lobby_message_id)
    record = replace(
        record,
        setting_message_id=setting_message.message_id,
        setting_text=setting,
        lobby_message_id=None,
    )
    await _render_turn(context, chat_id, record)


async def _generate_setting(
    context, chat_id: int, record: SessionRecord
) -> str | None:
    """Ask the local LLM for the opening setting (fail-soft to None)."""
    heroes = await context.bot_data["store"].list(chat_id)
    names = [c.name for c in heroes] or [p.name for p in record.session.players]
    gm_context = GMContext(
        scenario_title=_SETTING_TITLE,
        scenario_goal=_SETTING_GOAL,
        current_scene=t(record.lang, "session_setting_default"),
        active_characters=names,
        language=record.lang,
    )
    return await generate_scene(gm_context, _SETTING_CUE)


async def _leave(update, context, record: SessionRecord, user_id: int) -> None:
    """A player leaves: reflow the turn order, the lobby, and the creator role."""
    chat_id, _ = _ids(update)
    lang = record.lang
    session = record.session
    leaver = next(p for p in session.players if p.user_id == user_id)
    was_creator = user_id == session.creator_id
    remaining = leave_session(session, user_id)
    chat = update.effective_chat
    await chat.send_message(t(lang, "session_left", name=leaver.name))
    if remaining is None:
        _cancel_turn_job(context, chat_id)
        await _strip_buttons(
            context, chat_id, record.lobby_message_id, record.turn_message_id
        )
        await _sessions(context).delete(chat_id)
        await chat.send_message(t(lang, "session_dissolved"))
        return
    record = record.with_session(remaining)
    if was_creator:
        new_creator = next(
            p for p in remaining.players if p.user_id == remaining.creator_id
        )
        await chat.send_message(
            t(lang, "session_new_creator", name=new_creator.name)
        )
    if remaining.phase is SessionPhase.ACTIVE:
        await _render_turn(context, chat_id, record)
    else:
        await _render_lobby(context, chat_id, record)


async def _end(update, context, record: SessionRecord) -> None:
    """Creator ends the session for everyone."""
    chat_id, _ = _ids(update)
    _cancel_turn_job(context, chat_id)
    await _strip_buttons(
        context, chat_id, record.lobby_message_id, record.turn_message_id
    )
    await _sessions(context).delete(chat_id)
    await update.effective_chat.send_message(t(record.lang, "session_ended"))


async def _turn_action(
    update, context, record: SessionRecord, action: str, parts: list[str]
) -> None:
    """Dispatch an already-authorized game-turn button."""
    query = update.callback_query
    chat_id, user_id = _ids(update)
    lang = record.lang
    if action == "turn":  # back from a picker to the action list
        await _render_turn(context, chat_id, record)
    elif action == "pass":
        await update.effective_chat.send_message(
            t(lang, "session_passed", name=active_player(record.session).name)
        )
        await _advance(context, chat_id, record)
    elif action == "move":
        await query.edit_message_text(
            t(lang, "session_pick_move") + "\n\n" + _moves_overview(lang, MOVES),
            reply_markup=menu.session_moves_keyboard(lang),
        )
    elif action == "mv" and len(parts) >= 3 and parts[2] in MOVES:
        character = await _store(context).get(chat_id, user_id)
        await query.edit_message_text(
            _move_blurb(MOVES[parts[2]], lang),
            reply_markup=menu.session_stat_keyboard(
                lang, f"sess:st:{parts[2]}", character=character
            ),
        )
    elif action == "st" and len(parts) >= 4:
        await _resolve_session_move(update, context, record, parts[2], parts[3])


async def _resolve_session_move(
    update, context, record: SessionRecord, move_key: str, stat_name: str
) -> None:
    """Resolve a named move for the active player, then pass the turn on."""
    chat_id, user_id = _ids(update)
    lang = record.lang
    store = _store(context)
    character = await store.get(chat_id, user_id)
    if character is None:  # sheet vanished mid-flow — just re-show the turn
        await _render_turn(context, chat_id, record)
        return
    try:
        result = resolve_move(move_key, character, stat_name)
    except ValueError:
        return
    updated, applied = apply_effects(character, result.delta)
    if applied:
        await store.update(chat_id, user_id, updated)
    player = active_player(record.session)
    await update.effective_chat.send_message(
        t(lang, "session_action_by", name=player.name)
        + "\n" + _format_move(result, applied, lang)
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
    await _advance(context, chat_id, record)


# --- create-session conversation (button → typed password) --------------------


async def screate_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    lang = await _lang(update, context)
    chat_id, _ = _ids(update)
    if await _sessions(context).get(chat_id) is not None:
        await _deny(query, lang, "session_exists")
        return ConversationHandler.END
    await query.answer()
    await query.edit_message_text(
        t(lang, "screate_ask_password", max=MAX_PASSWORD_LENGTH)
    )
    return SESSION_PASSWORD


async def screate_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return SESSION_PASSWORD
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    if await _sessions(context).get(chat_id) is not None:  # raced by a friend
        await update.message.reply_text(t(lang, "session_exists"))
        return ConversationHandler.END
    try:
        session = create_session(
            user_id, _display_name(update.effective_user),
            update.message.text or "",
        )
    except SessionError:
        await update.message.reply_text(
            t(lang, "session_password_invalid", max=MAX_PASSWORD_LENGTH)
        )
        return SESSION_PASSWORD
    await _delete_quietly(update.message)  # keep the password off-screen
    await _render_lobby(context, chat_id, SessionRecord(session=session, lang=lang))
    return ConversationHandler.END


def build_session_create_handler() -> ConversationHandler:
    """Open a lobby: ➕ button → type the session password."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(screate_start, pattern=r"^screate:start$")
        ],
        states={
            SESSION_PASSWORD: [MessageHandler(text, screate_password)],
            **_TIMEOUT_STATE,
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )


# --- join-session conversation (button → typed password) ----------------------


async def sjoin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    record = await _sessions(context).get(chat_id)
    if record is None:
        await _deny(query, lang, "session_no_session")
        return ConversationHandler.END
    session = record.session
    if in_session(session, user_id):
        await _deny(query, lang, "session_already_joined")
        return ConversationHandler.END
    if session.phase is not SessionPhase.LOBBY:
        await _deny(query, lang, "session_already_started")
        return ConversationHandler.END
    if len(session.players) >= MAX_PLAYERS:
        await _deny(query, lang, "session_full", max=MAX_PLAYERS)
        return ConversationHandler.END
    await query.answer()
    # A fresh prompt message: editing the shared lobby would break it for all.
    await update.effective_chat.send_message(t(lang, "sjoin_ask_password"))
    return JOIN_PASSWORD


async def sjoin_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return JOIN_PASSWORD
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    record = await _sessions(context).get(chat_id)
    if record is None:
        await update.message.reply_text(t(lang, "session_no_session"))
        return ConversationHandler.END
    try:
        session = join_session(
            record.session, user_id, _display_name(update.effective_user),
            update.message.text or "",
        )
    except WrongPassword:
        await update.message.reply_text(t(lang, "session_wrong_password"))
        return JOIN_PASSWORD
    except AlreadyJoined:
        await update.message.reply_text(t(lang, "session_already_joined"))
        return ConversationHandler.END
    except SessionFull:
        await update.message.reply_text(t(lang, "session_full", max=MAX_PLAYERS))
        return ConversationHandler.END
    except AlreadyStarted:
        await update.message.reply_text(t(lang, "session_already_started"))
        return ConversationHandler.END
    await _delete_quietly(update.message)
    record = record.with_session(session)
    await update.effective_chat.send_message(
        t(record.lang, "session_joined", name=session.players[-1].name)
    )
    await _render_lobby(context, chat_id, record)
    return ConversationHandler.END


def build_session_join_handler() -> ConversationHandler:
    """Join a lobby: 🔑 button → type the password (re-asks on a wrong one)."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(sjoin_start, pattern=r"^sjoin:start$")],
        states={
            JOIN_PASSWORD: [MessageHandler(text, sjoin_password)],
            **_TIMEOUT_STATE,
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )


# --- custom-action conversation (active player types what they do) ------------


async def scust_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    record = await _sessions(context).get(chat_id)
    if record is None:
        await _deny(query, lang, "session_no_session")
        return ConversationHandler.END
    if not is_active_player(record.session, user_id):
        await _deny(query, lang, "session_not_your_turn")
        return ConversationHandler.END
    if await _store(context).get(chat_id, user_id) is None:
        await _deny(query, lang, "session_turn_no_hero")
        return ConversationHandler.END
    await query.answer()
    await update.effective_chat.send_message(t(record.lang, "scust_ask_text"))
    return CUSTOM_TEXT


async def scust_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CUSTOM_TEXT
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(t(lang, "scust_empty_text"))
        return CUSTOM_TEXT
    record = await _sessions(context).get(chat_id)
    if record is None or not is_active_player(record.session, user_id):
        await update.message.reply_text(t(lang, "session_not_your_turn"))
        return ConversationHandler.END
    context.user_data["scust_text"] = text[:MAX_CUSTOM_ACTION_LENGTH]
    character = await _store(context).get(chat_id, user_id)
    await update.message.reply_text(
        t(record.lang, "scust_pick_stat"),
        reply_markup=menu.session_stat_keyboard(
            record.lang, "scust:st", back="scust:back", character=character
        ),
    )
    return CUSTOM_STAT


async def scust_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return CUSTOM_STAT
    lang = await _lang(update, context)
    chat_id, user_id = _ids(update)
    record = await _sessions(context).get(chat_id)
    if record is None or not is_active_player(record.session, user_id):
        await _deny(query, lang, "session_not_your_turn")
        return ConversationHandler.END
    character = await _store(context).get(chat_id, user_id)
    if character is None:
        await _deny(query, lang, "session_turn_no_hero")
        return ConversationHandler.END
    await query.answer()
    stat_name = query.data.split(":")[2]
    description = context.user_data.pop("scust_text", "")
    result = roll_action(stat_value(character, stat_name), 0)
    await update.effective_chat.send_message(
        t(record.lang, "session_custom_header",
          name=active_player(record.session).name, text=description)
        + "\n" + _format_roll(result, stat_name, record.lang)
        + "\n" + _outcome_hint(result.outcome, record.lang)
    )
    _fire_narration(
        update,
        context,
        NarratorContext(
            move_name=description or f"action roll ({stat_name})",
            outcome=result.outcome,
            is_match=result.is_match,
            stat_used=stat_name,
            character_name=character.name,
            language=record.lang,
        ),
    )
    _schedule_gm_scene(
        update, context, result, stat_name, character.name, record.lang
    )
    await _advance(context, chat_id, record)
    return ConversationHandler.END


async def scust_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Abandon the custom action and re-show the turn's action list."""
    query = update.callback_query
    if query is not None:
        await query.answer()
    context.user_data.pop("scust_text", None)
    chat_id, _ = _ids(update)
    record = await _sessions(context).get(chat_id)
    if record is not None and record.session.phase is SessionPhase.ACTIVE:
        await _render_turn(context, chat_id, record)
    return ConversationHandler.END


def build_session_custom_handler() -> ConversationHandler:
    """Custom action: ✍️ button → describe it (typed) → pick a stat → roll."""
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(scust_start, pattern=r"^scust:start$")],
        states={
            CUSTOM_TEXT: [MessageHandler(text, scust_text)],
            CUSTOM_STAT: [
                CallbackQueryHandler(scust_stat, pattern=r"^scust:st:"),
                CallbackQueryHandler(scust_back, pattern=r"^scust:back$"),
            ],
            **_TIMEOUT_STATE,
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
    )
