"""Tests for the inline-keyboard builders (callback-data scheme & navigation).

The Telegram handlers themselves aren't unit-tested (same as the rest of the
bot); their logic lives in the tested ``engine``/``storage`` layers. Here we
pin the keyboard *shape*: that callback-data strings are namespaced as expected
and that every navigable submenu carries 🔙 Back and 🏠 Home.
"""

from bot import menu
from engine import ARCHETYPES, MOVES, MoveCategory, Odds, Rank, TrackType
from engine.character import STAT_NAMES

LANG = "en"


def _all_callbacks(keyboard) -> list[str]:
    return [btn.callback_data for row in keyboard.inline_keyboard for btn in row]


def _has_back_and_home(keyboard, *, back: str) -> bool:
    callbacks = _all_callbacks(keyboard)
    return back in callbacks and menu.HOME in callbacks


def test_main_menu_has_nine_entries() -> None:
    callbacks = _all_callbacks(menu.main_menu(LANG))
    assert callbacks == [
        "move:cat", "roll:menu",
        "vow:menu", "track:menu",
        "char:menu", "oracle:menu",
        "sess:menu",
        "gm:menu", "help:show",
    ]


def test_main_menu_offers_creation_to_newcomers() -> None:
    callbacks = _all_callbacks(menu.main_menu(LANG, has_character=False))
    assert callbacks[0] == "cnew:start"  # the CTA leads the menu
    assert "move:cat" in callbacks       # the full menu is still there


def test_no_character_keyboard_offers_creation_and_home() -> None:
    callbacks = _all_callbacks(menu.no_character_keyboard(LANG))
    assert callbacks == ["cnew:start", menu.HOME]


def test_move_categories_cover_enum_and_navigate() -> None:
    kb = menu.move_categories(LANG)
    callbacks = _all_callbacks(kb)
    for category in MoveCategory:
        assert f"move:cat:{category.value}" in callbacks
    assert _has_back_and_home(kb, back=menu.HOME)


def test_moves_keyboard_lists_category_moves() -> None:
    kb = menu.moves_keyboard(LANG, MoveCategory.COMBAT)
    callbacks = _all_callbacks(kb)
    for key, spec in MOVES.items():
        present = f"move:mv:{key}" in callbacks
        assert present is (spec.category is MoveCategory.COMBAT)
    assert _has_back_and_home(kb, back="move:cat")


def test_stat_keyboard_uses_prefix_and_navigates() -> None:
    kb = menu.stat_keyboard(LANG, "move:st:strike", "move:cat:combat")
    callbacks = _all_callbacks(kb)
    for stat in STAT_NAMES:
        assert f"move:st:strike:{stat}" in callbacks
    assert _has_back_and_home(kb, back="move:cat:combat")


def test_oracle_keyboard_has_each_odds() -> None:
    kb = menu.oracle_keyboard(LANG)
    callbacks = _all_callbacks(kb)
    for odds in Odds:
        assert f"oracle:do:{odds.name.lower()}" in callbacks
    assert _has_back_and_home(kb, back=menu.HOME)


def test_character_menu_depends_on_existence() -> None:
    with_char = _all_callbacks(menu.character_menu(LANG, True))
    assert "char:show" in with_char and "char:set" in with_char
    assert "cnew:start" not in with_char

    without = _all_callbacks(menu.character_menu(LANG, False))
    assert "cnew:start" in without
    assert "char:show" not in without


def test_char_stepper_offers_plus_minus_and_back() -> None:
    callbacks = _all_callbacks(menu.char_stepper(LANG, "momentum"))
    assert "char:adj:momentum:-1" in callbacks
    assert "char:adj:momentum:1" in callbacks
    assert "char:set" in callbacks
    assert menu.HOME in callbacks


def test_vow_menu_and_actions() -> None:
    menu_cbs = _all_callbacks(menu.vow_menu(LANG))
    assert "vow:list" in menu_cbs and "vnew:start" in menu_cbs
    assert _has_back_and_home(menu.vow_menu(LANG), back=menu.HOME)

    actions = _all_callbacks(menu.vow_actions(LANG, 7))
    assert "vow:do:progress:7" in actions
    assert "vow:do:fulfill:7" in actions
    assert "vow:do:forsake:7" in actions
    assert "vow:list" in actions


def test_track_menu_and_actions() -> None:
    menu_cbs = _all_callbacks(menu.track_menu(LANG))
    assert "track:list" in menu_cbs and "tnew:start" in menu_cbs

    actions = _all_callbacks(menu.track_actions(LANG, 3))
    assert "track:do:hit:3" in actions
    assert "track:do:end:3" in actions
    assert "track:do:clear:3" in actions


def test_gm_menu_actions() -> None:
    callbacks = _all_callbacks(menu.gm_menu(LANG))
    for action in ("start", "scene", "npcs", "stop"):
        assert f"gm:{action}" in callbacks
    assert _has_back_and_home(menu.gm_menu(LANG), back=menu.HOME)


def test_rank_and_type_keyboards_use_prefix() -> None:
    rank_cbs = _all_callbacks(menu.rank_keyboard(LANG, "vnew:rank"))
    for rank in Rank:
        assert f"vnew:rank:{rank.value}" in rank_cbs

    type_cbs = _all_callbacks(menu.track_type_keyboard(LANG, "tnew:type"))
    for track_type in TrackType:
        assert f"tnew:type:{track_type.value}" in type_cbs


def test_stat_value_keyboard_is_one_two_three() -> None:
    callbacks = _all_callbacks(menu.stat_value_keyboard("cnew:edge"))
    assert callbacks == ["cnew:edge:1", "cnew:edge:2", "cnew:edge:3"]


# --- guided hero creation (archetypes + allocation) --------------------------


def test_archetype_keyboard_lists_all_paths_two_per_row() -> None:
    kb = menu.archetype_keyboard(LANG)
    callbacks = _all_callbacks(kb)
    for key in ARCHETYPES:
        assert f"cnew:arch:{key}" in callbacks
    assert len(callbacks) == len(ARCHETYPES)
    # laid out two per row
    assert all(len(row) <= 2 for row in kb.inline_keyboard)


def test_archetype_detail_keyboard_confirm_and_back() -> None:
    callbacks = _all_callbacks(menu.archetype_detail_keyboard(LANG, "ranger"))
    assert "cnew:archok:ranger" in callbacks
    assert "cnew:archback" in callbacks


def test_allocation_keyboard_shows_pool_values_then_done() -> None:
    pool = _all_callbacks(menu.allocation_keyboard(LANG, [1, 1, 2]))
    assert pool == ["cnew:val:1", "cnew:val:1", "cnew:val:2"]
    # empty pool → the Done button
    assert _all_callbacks(menu.allocation_keyboard(LANG, [])) == ["cnew:done"]


def test_assign_stat_keyboard_lists_given_stats() -> None:
    callbacks = _all_callbacks(menu.assign_stat_keyboard(LANG, ["edge", "iron"]))
    assert callbacks == ["cnew:assign:edge", "cnew:assign:iron"]


def test_new_confirm_keyboard_create_and_restart() -> None:
    callbacks = _all_callbacks(menu.new_confirm_keyboard(LANG))
    assert "cnew:create" in callbacks
    assert "cnew:restart" in callbacks


def test_lists_render_item_callbacks() -> None:
    class _Item:
        def __init__(self, id, title):
            self.id = id
            self.title = title

    vows = [_Item(1, "Find the troop"), _Item(2, "Slay the beast")]
    vow_cbs = _all_callbacks(menu.vow_list_keyboard(LANG, vows))
    assert "vow:act:1" in vow_cbs and "vow:act:2" in vow_cbs

    track_cbs = _all_callbacks(menu.track_list_keyboard(LANG, vows))
    assert "track:act:1" in track_cbs and "track:act:2" in track_cbs


def test_empty_lists_offer_creation() -> None:
    vow_cbs = _all_callbacks(menu.vow_list_keyboard(LANG, []))
    assert "vnew:start" in vow_cbs  # empty state carries a call to action

    track_cbs = _all_callbacks(menu.track_list_keyboard(LANG, []))
    assert "tnew:start" in track_cbs


# --- multiplayer sessions (lobby + turns) -------------------------------------


def test_session_none_offers_creation() -> None:
    callbacks = _all_callbacks(menu.session_none_keyboard(LANG))
    assert "screate:start" in callbacks
    assert menu.HOME in callbacks


def test_lobby_keyboard_has_join_start_leave_and_no_nav() -> None:
    callbacks = _all_callbacks(menu.lobby_keyboard(LANG))
    assert callbacks == ["sjoin:start", "sess:begin", "sess:leave"]
    # the lobby message is shared by the whole group: no Home/Back that would
    # let one player navigate the shared view away for everyone
    assert menu.HOME not in callbacks


def test_session_active_keyboard_offers_leave_end_home() -> None:
    callbacks = _all_callbacks(menu.session_active_keyboard(LANG))
    assert "sess:leave" in callbacks and "sess:end" in callbacks
    assert menu.HOME in callbacks


def test_turn_keyboard_needs_a_hero_for_actions() -> None:
    with_hero = _all_callbacks(menu.turn_keyboard(LANG, has_character=True))
    assert with_hero == ["sess:move", "scust:start", "sess:pass"]

    without = _all_callbacks(menu.turn_keyboard(LANG, has_character=False))
    assert without == ["sess:pass"]  # no sheet — only passing is possible


def test_session_moves_keyboard_lists_all_moves_and_goes_back() -> None:
    callbacks = _all_callbacks(menu.session_moves_keyboard(LANG))
    for key in MOVES:
        assert f"sess:mv:{key}" in callbacks
    assert "sess:turn" in callbacks


def test_session_stat_keyboard_uses_prefix_and_goes_back() -> None:
    callbacks = _all_callbacks(menu.session_stat_keyboard(LANG, "sess:st:strike"))
    for stat in STAT_NAMES:
        assert f"sess:st:strike:{stat}" in callbacks
    assert "sess:turn" in callbacks
