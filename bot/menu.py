"""Inline-keyboard builders and the callback-data scheme.

Every screen the player navigates is built here. ``callback_data`` strings are
namespaced (``area:action[:arg…]``) and produced only through these builders, so
there are no magic strings scattered across the handlers. The conversation flows
(character/vow/track creation) own the ``cnew:`` / ``vnew:`` / ``tnew:`` prefixes;
everything else is routed by the single menu callback.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton as _Btn
from telegram import InlineKeyboardMarkup as _Kb

from bot.i18n import t
from engine.character import STAT_NAMES
from engine.classes import ARCHETYPES
from engine.moves import MOVES, MoveCategory, moves_in
from engine.oracles import Odds
from engine.progress import Rank, progress_per_hit
from engine.tracks import TrackType

HOME = "menu:main"


def _nav(lang: str, back: str) -> list[_Btn]:
    """A 🔙 Back (to ``back``) + 🏠 Home row."""
    return [
        _Btn(t(lang, "btn_back"), callback_data=back),
        _Btn(t(lang, "btn_home"), callback_data=HOME),
    ]


def main_menu(lang: str, has_character: bool = True) -> _Kb:
    """The main menu; newcomers get a Create-hero CTA on top."""
    rows = []
    if not has_character:
        rows.append([_Btn(t(lang, "char_create_btn"), callback_data="cnew:start")])
    rows += [
        [_Btn(t(lang, "menu_move"), callback_data="move:cat"),
         _Btn(t(lang, "menu_roll"), callback_data="roll:menu")],
        [_Btn(t(lang, "menu_vows"), callback_data="vow:menu"),
         _Btn(t(lang, "menu_tracks"), callback_data="track:menu")],
        [_Btn(t(lang, "menu_character"), callback_data="char:menu"),
         _Btn(t(lang, "menu_oracle"), callback_data="oracle:menu")],
        [_Btn(t(lang, "menu_session"), callback_data="sess:menu")],
        [_Btn(t(lang, "menu_gm"), callback_data="gm:menu"),
         _Btn(t(lang, "menu_help"), callback_data="help:show")],
    ]
    return _Kb(rows)


def no_character_keyboard(lang: str) -> _Kb:
    """Shown with 'you have no hero yet' — a way forward, not a dead end."""
    return _Kb([
        [_Btn(t(lang, "char_create_btn"), callback_data="cnew:start")],
        [_Btn(t(lang, "btn_home"), callback_data=HOME)],
    ])


# --- moves -------------------------------------------------------------------


def move_categories(lang: str) -> _Kb:
    rows = [
        [_Btn(t(lang, f"cat_{cat.value}"), callback_data=f"move:cat:{cat.value}")]
        for cat in MoveCategory
    ]
    rows.append(_nav(lang, HOME))
    return _Kb(rows)


def moves_keyboard(lang: str, category: MoveCategory) -> _Kb:
    rows = [
        [_Btn(t(lang, f"move_{key}"), callback_data=f"move:mv:{key}")]
        for key in moves_in(category)
    ]
    rows.append(_nav(lang, "move:cat"))
    return _Kb(rows)


def _stat_label(lang: str, stat: str, character) -> str:
    """A stat button label, carrying the hero's value when one is given."""
    label = t(lang, f"stat_{stat}")
    if character is not None:
        label += f" · {getattr(character, stat)}"
    return label


def stat_keyboard(lang: str, prefix: str, back: str, character=None) -> _Kb:
    """Stat picker; each button is ``{prefix}:{stat}``.

    With ``character`` given, every button also shows the hero's value for
    that stat, so the pick is an informed one.
    """
    rows = [
        [_Btn(_stat_label(lang, stat, character), callback_data=f"{prefix}:{stat}")]
        for stat in STAT_NAMES
    ]
    rows.append(_nav(lang, back))
    return _Kb(rows)


# --- oracle ------------------------------------------------------------------


def oracle_keyboard(lang: str) -> _Kb:
    rows = [
        [_Btn(t(lang, f"odds_{o.name.lower()}"),
              callback_data=f"oracle:do:{o.name.lower()}")]
        for o in Odds
    ]
    rows.append(_nav(lang, HOME))
    return _Kb(rows)


# --- character ---------------------------------------------------------------


def character_menu(lang: str, has_character: bool) -> _Kb:
    if has_character:
        rows = [
            [_Btn(t(lang, "char_show_btn"), callback_data="char:show")],
            [_Btn(t(lang, "char_set_btn"), callback_data="char:set")],
            [_Btn(t(lang, "item_add_btn"), callback_data="iadd:start"),
             _Btn(t(lang, "item_del_btn"), callback_data="char:delitem")],
            [_Btn(t(lang, "bg_set_btn"), callback_data="bgset:start")],
        ]
    else:
        rows = [[_Btn(t(lang, "char_create_btn"), callback_data="cnew:start")]]
    rows.append(_nav(lang, HOME))
    return _Kb(rows)


def item_remove_keyboard(lang: str, items: list[str]) -> _Kb:
    """One button per inventory item; tapping removes it (``char:delitem:<idx>``)."""
    rows = [
        [_Btn(f"➖ {item}", callback_data=f"char:delitem:{index}")]
        for index, item in enumerate(items)
    ]
    rows.append(_nav(lang, "char:menu"))
    return _Kb(rows)


def char_set_fields(lang: str, fields: tuple[str, ...]) -> _Kb:
    rows = [
        [_Btn(t(lang, _field_label_key(f)), callback_data=f"char:setf:{f}")]
        for f in fields
    ]
    rows.append(_nav(lang, "char:menu"))
    return _Kb(rows)


def char_stepper(lang: str, field: str) -> _Kb:
    return _Kb([
        [_Btn("−1", callback_data=f"char:adj:{field}:-1"),
         _Btn("+1", callback_data=f"char:adj:{field}:1")],
        _nav(lang, "char:set"),
    ])


def _field_label_key(field: str) -> str:
    return "momentum" if field == "momentum" else f"track_{field}"


# --- vows --------------------------------------------------------------------


def vow_menu(lang: str) -> _Kb:
    return _Kb([
        [_Btn(t(lang, "vow_list_btn"), callback_data="vow:list")],
        [_Btn(t(lang, "vow_new_btn"), callback_data="vnew:start")],
        _nav(lang, HOME),
    ])


def vow_list_keyboard(lang: str, vows) -> _Kb:
    """One button per vow; an empty list offers creating one right here."""
    rows = [
        [_Btn(f"#{v.id} {v.title}", callback_data=f"vow:act:{v.id}")]
        for v in vows
    ]
    if not vows:
        rows.append([_Btn(t(lang, "vow_new_btn"), callback_data="vnew:start")])
    rows.append(_nav(lang, "vow:menu"))
    return _Kb(rows)


def vow_actions(lang: str, vow_id: int) -> _Kb:
    return _Kb([
        [_Btn(t(lang, "vow_do_progress"), callback_data=f"vow:do:progress:{vow_id}")],
        [_Btn(t(lang, "vow_do_fulfill"), callback_data=f"vow:do:fulfill:{vow_id}")],
        [_Btn(t(lang, "vow_do_forsake"), callback_data=f"vow:do:forsake:{vow_id}")],
        _nav(lang, "vow:list"),
    ])


# --- tracks ------------------------------------------------------------------


def track_menu(lang: str) -> _Kb:
    return _Kb([
        [_Btn(t(lang, "track_list_btn"), callback_data="track:list")],
        [_Btn(t(lang, "track_new_btn"), callback_data="tnew:start")],
        _nav(lang, HOME),
    ])


def track_list_keyboard(lang: str, tracks) -> _Kb:
    """One button per track; an empty list offers creating one right here."""
    rows = [
        [_Btn(f"#{tr.id} {tr.title}", callback_data=f"track:act:{tr.id}")]
        for tr in tracks
    ]
    if not tracks:
        rows.append([_Btn(t(lang, "track_new_btn"), callback_data="tnew:start")])
    rows.append(_nav(lang, "track:menu"))
    return _Kb(rows)


def track_actions(lang: str, track_id: int) -> _Kb:
    return _Kb([
        [_Btn(t(lang, "track_do_hit"), callback_data=f"track:do:hit:{track_id}")],
        [_Btn(t(lang, "track_do_end"), callback_data=f"track:do:end:{track_id}")],
        [_Btn(t(lang, "track_do_clear"), callback_data=f"track:do:clear:{track_id}")],
        _nav(lang, "track:list"),
    ])


# --- GM submenu --------------------------------------------------------------


def gm_menu(lang: str) -> _Kb:
    return _Kb([
        [_Btn(t(lang, "gm_start_btn"), callback_data="gm:start")],
        [_Btn(t(lang, "gm_scene_btn"), callback_data="gm:scene"),
         _Btn(t(lang, "gm_npcs_btn"), callback_data="gm:npcs")],
        [_Btn(t(lang, "gm_stop_btn"), callback_data="gm:stop")],
        _nav(lang, HOME),
    ])


# --- shared small keyboards --------------------------------------------------


def home_only(lang: str) -> _Kb:
    """A single 🏠 Home button, shown under action results."""
    return _Kb([[_Btn(t(lang, "btn_home"), callback_data=HOME)]])


def back_home(lang: str, back: str) -> _Kb:
    """A single 🔙 Back + 🏠 Home row (for static screens like a sheet)."""
    return _Kb([_nav(lang, back)])


def help_keyboard(lang: str) -> _Kb:
    return _Kb([_nav(lang, HOME)])


def rank_keyboard(lang: str, prefix: str) -> _Kb:
    """Difficulty rank picker; each button is ``{prefix}:{rank}``.

    Every button carries "+N" — the progress boxes one mark fills at that
    rank — so the difficulty trade-off is visible before choosing.
    """
    return _Kb([
        [_Btn(f"{t(lang, f'rank_{r.value}')} · +{progress_per_hit(r):g}",
              callback_data=f"{prefix}:{r.value}")]
        for r in Rank
    ])


def track_type_keyboard(lang: str, prefix: str) -> _Kb:
    return _Kb([
        [_Btn(t(lang, f"type_{tt.value}"), callback_data=f"{prefix}:{tt.value}")]
        for tt in TrackType
    ])


def stat_value_keyboard(prefix: str) -> _Kb:
    """1/2/3 picker used when creating a character; ``{prefix}:{n}``."""
    return _Kb([[
        _Btn("1", callback_data=f"{prefix}:1"),
        _Btn("2", callback_data=f"{prefix}:2"),
        _Btn("3", callback_data=f"{prefix}:3"),
    ]])


# --- guided hero creation (archetype path + stat allocation) -----------------


def archetype_keyboard(lang: str) -> _Kb:
    """The 8 archetype paths, two per row (``cnew:arch:<key>``)."""
    buttons = [
        _Btn(f"{arch.flavor_icon} {t(lang, f'arch_{key}_name')}",
             callback_data=f"cnew:arch:{key}")
        for key, arch in ARCHETYPES.items()
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return _Kb(rows)


def archetype_detail_keyboard(lang: str, key: str) -> _Kb:
    """Confirm the chosen path or go back to the list."""
    return _Kb([[
        _Btn(t(lang, "btn_confirm"), callback_data=f"cnew:archok:{key}"),
        _Btn(t(lang, "btn_other_path"), callback_data="cnew:archback"),
    ]])


def allocation_keyboard(lang: str, pool: list[int]) -> _Kb:
    """Remaining values to place (``cnew:val:<value>``), or ✅ Done when empty."""
    if pool:
        return _Kb([[_Btn(str(value), callback_data=f"cnew:val:{value}")
                     for value in pool]])
    return _Kb([[_Btn(t(lang, "btn_done"), callback_data="cnew:done")]])


def assign_stat_keyboard(lang: str, stats: list[str]) -> _Kb:
    """Pick which unassigned stat receives the tapped value (``cnew:assign:<stat>``)."""
    rows = [
        [_Btn(t(lang, f"stat_{stat}"), callback_data=f"cnew:assign:{stat}")]
        for stat in stats
    ]
    return _Kb(rows)


def new_confirm_keyboard(lang: str) -> _Kb:
    """Final create / start-over choice."""
    return _Kb([[
        _Btn(t(lang, "btn_create_hero"), callback_data="cnew:create"),
        _Btn(t(lang, "btn_restart"), callback_data="cnew:restart"),
    ]])


# --- multiplayer sessions (lobby + turns) -------------------------------------


def session_none_keyboard(lang: str) -> _Kb:
    """No session in this chat yet: offer to open a lobby."""
    return _Kb([
        [_Btn(t(lang, "session_create_btn"), callback_data="screate:start")],
        [_Btn(t(lang, "btn_home"), callback_data=HOME)],
    ])


def lobby_keyboard(lang: str) -> _Kb:
    """The shared lobby message's buttons.

    One message serves every player in the group, so all controls are always
    shown; the handlers enforce who may press what (start is creator-only) and
    reject others with an alert. Deliberately no Home/Back: navigating would
    destroy the shared lobby view for everyone.
    """
    return _Kb([
        [_Btn(t(lang, "session_join_btn"), callback_data="sjoin:start")],
        [_Btn(t(lang, "session_start_btn"), callback_data="sess:begin")],
        [_Btn(t(lang, "session_leave_btn"), callback_data="sess:leave")],
    ])


def session_active_keyboard(lang: str) -> _Kb:
    """The session hub while a game runs (end is enforced creator-only)."""
    return _Kb([
        [_Btn(t(lang, "session_leave_btn"), callback_data="sess:leave"),
         _Btn(t(lang, "session_end_btn"), callback_data="sess:end")],
        [_Btn(t(lang, "btn_home"), callback_data=HOME)],
    ])


def turn_keyboard(lang: str, has_character: bool) -> _Kb:
    """Action choices on the Current-Turn message (active player only).

    Without a hero only passing is possible — moves need a character sheet.
    """
    rows = []
    if has_character:
        rows.append([_Btn(t(lang, "session_act_move_btn"), callback_data="sess:move")])
        rows.append([_Btn(t(lang, "session_act_custom_btn"),
                          callback_data="scust:start")])
    rows.append([_Btn(t(lang, "session_act_pass_btn"), callback_data="sess:pass")])
    return _Kb(rows)


def session_moves_keyboard(lang: str) -> _Kb:
    """Every named move as one flat list (``sess:mv:<key>``), plus back-to-turn."""
    rows = [
        [_Btn(t(lang, f"move_{key}"), callback_data=f"sess:mv:{key}")]
        for key in MOVES
    ]
    rows.append([_Btn(t(lang, "btn_back"), callback_data="sess:turn")])
    return _Kb(rows)


def session_stat_keyboard(
    lang: str, prefix: str, back: str = "sess:turn", character=None
) -> _Kb:
    """Stat picker for a session action (``{prefix}:{stat}``), plus a back button.

    Like :func:`stat_keyboard`, a given ``character`` puts the hero's values
    on the buttons.
    """
    rows = [
        [_Btn(_stat_label(lang, stat, character), callback_data=f"{prefix}:{stat}")]
        for stat in STAT_NAMES
    ]
    rows.append([_Btn(t(lang, "btn_back"), callback_data=back)])
    return _Kb(rows)
