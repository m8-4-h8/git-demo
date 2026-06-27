"""Tests for the pure character model and its rules."""

import pytest

from engine.character import (
    MOMENTUM_RESET,
    Character,
    new_character,
    reset_momentum,
    set_field,
    stat_value,
)


def _char(**overrides) -> Character:
    base = dict(name="Hero", edge=1, heart=2, iron=3, shadow=1, wits=2)
    base.update(overrides)
    return new_character(**base)


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
