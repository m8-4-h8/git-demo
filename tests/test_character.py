"""Tests for the pure character model and its rules."""

from dataclasses import replace

import pytest

from engine.character import (
    MAX_BACKGROUND_LENGTH,
    MAX_ITEM_LENGTH,
    MAX_ITEMS,
    MOMENTUM_RESET,
    Character,
    add_item,
    new_character,
    remove_item,
    reset_momentum,
    set_background,
    set_field,
    stat_value,
)


def _char(**overrides) -> Character:
    # items/background aren't constructor args of new_character; apply after.
    extras = {k: overrides.pop(k) for k in ("items", "background") if k in overrides}
    base = dict(name="Hero", edge=1, heart=2, iron=3, shadow=1, wits=2)
    base.update(overrides)
    hero = new_character(**base)
    return replace(hero, **extras) if extras else hero


# --- inventory & background --------------------------------------------------


def test_new_character_has_empty_inventory_and_no_background() -> None:
    hero = _char()
    assert hero.items == []
    assert hero.background is None


def test_add_item_appends_and_is_immutable() -> None:
    hero = _char()
    updated = add_item(hero, "  Old dagger  ")  # trimmed
    assert updated.items == ["Old dagger"]
    assert hero.items == []  # original unchanged (frozen, new copy)


def test_add_item_rejects_empty() -> None:
    with pytest.raises(ValueError):
        add_item(_char(), "   ")


def test_add_item_rejects_too_long() -> None:
    with pytest.raises(ValueError):
        add_item(_char(), "x" * (MAX_ITEM_LENGTH + 1))
    # exactly at the limit is fine
    assert add_item(_char(), "x" * MAX_ITEM_LENGTH).items == ["x" * MAX_ITEM_LENGTH]


def test_add_item_enforces_inventory_cap() -> None:
    hero = _char(items=[f"item{i}" for i in range(MAX_ITEMS)])
    with pytest.raises(ValueError):
        add_item(hero, "one too many")


def test_remove_item_by_index() -> None:
    hero = _char(items=["a", "b", "c"])
    assert remove_item(hero, 1).items == ["a", "c"]
    assert remove_item(hero, 0).items == ["b", "c"]
    assert remove_item(hero, 2).items == ["a", "b"]


def test_remove_item_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        remove_item(_char(items=["a"]), 5)
    with pytest.raises(ValueError):
        remove_item(_char(items=[]), 0)


def test_set_background_replaces_and_trims() -> None:
    hero = _char()
    told = set_background(hero, "  Born in the ashen wastes.  ")
    assert told.background == "Born in the ashen wastes."
    # overwrites wholesale, does not append
    assert set_background(told, "A new tale.").background == "A new tale."


def test_set_background_blank_clears_to_none() -> None:
    hero = _char(background="something")
    assert set_background(hero, "   ").background is None


def test_set_background_rejects_too_long() -> None:
    with pytest.raises(ValueError):
        set_background(_char(), "x" * (MAX_BACKGROUND_LENGTH + 1))


def test_new_character_defaults_full_tracks_and_start_momentum() -> None:
    c = _char()
    assert (c.health, c.spirit, c.supply) == (5, 5, 5)
    assert c.momentum == 2


def test_new_character_strips_name() -> None:
    assert new_character("  Aila  ", 1, 1, 1, 1, 1).name == "Aila"


def test_new_character_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        new_character("   ", 1, 1, 1, 1, 1)


@pytest.mark.parametrize("value", [0, 4, -1])
def test_new_character_rejects_out_of_range_stat(value: int) -> None:
    with pytest.raises(ValueError):
        new_character("Hero", value, 2, 2, 1, 1)


def test_stat_value_lookup() -> None:
    c = _char(iron=3)
    assert stat_value(c, "iron") == 3
    assert stat_value(c, "EDGE") == c.edge  # case-insensitive


def test_stat_value_unknown_raises() -> None:
    with pytest.raises(ValueError):
        stat_value(_char(), "luck")


@pytest.mark.parametrize("track", ["health", "spirit", "supply"])
def test_set_track_within_bounds(track: str) -> None:
    updated = set_field(_char(), track, 0)
    assert getattr(updated, track) == 0
    updated = set_field(_char(), track, 5)
    assert getattr(updated, track) == 5


@pytest.mark.parametrize("track", ["health", "spirit", "supply"])
@pytest.mark.parametrize("value", [-1, 6])
def test_set_track_out_of_bounds_raises(track: str, value: int) -> None:
    with pytest.raises(ValueError):
        set_field(_char(), track, value)


@pytest.mark.parametrize("value", [-6, 0, 10])
def test_set_momentum_within_bounds(value: int) -> None:
    assert set_field(_char(), "momentum", value).momentum == value


@pytest.mark.parametrize("value", [-7, 11])
def test_set_momentum_out_of_bounds_raises(value: int) -> None:
    with pytest.raises(ValueError):
        set_field(_char(), "momentum", value)


def test_set_unknown_field_raises() -> None:
    with pytest.raises(ValueError):
        set_field(_char(), "edge", 2)  # stats are not settable via /set


def test_set_field_returns_new_instance() -> None:
    original = _char()
    updated = set_field(original, "supply", 1)
    assert original.supply == 5  # frozen, unchanged
    assert updated.supply == 1


def test_reset_momentum() -> None:
    c = set_field(_char(), "momentum", -4)
    assert reset_momentum(c).momentum == MOMENTUM_RESET
