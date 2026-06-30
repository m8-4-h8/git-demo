"""Tests for the pure archetype layer (engine/classes.py)."""

import pytest

from engine.character import STAT_NAMES
from engine.classes import (
    ARCHETYPES,
    STARTING_ALLOCATION,
    apply_archetype_bonus,
    archetype_keys,
    create_with_archetype,
    get_archetype,
    validate_allocation,
)

# A valid allocation: each of 1,1,2,2,3 used once across the five stats.
_VALID = {"edge": 1, "heart": 1, "iron": 2, "shadow": 2, "wits": 3}


def test_eight_archetypes_with_valid_primary_stats() -> None:
    assert len(ARCHETYPES) == 8
    for arch in ARCHETYPES.values():
        assert arch.primary_stat in STAT_NAMES
        assert 2 <= len(arch.suggested_items) <= 3
        assert arch.flavor_icon  # an emoji label for the button


def test_archetype_keys_order_matches_registry() -> None:
    assert archetype_keys() == list(ARCHETYPES)


def test_get_archetype_unknown_raises() -> None:
    with pytest.raises(ValueError):
        get_archetype("paladin")


def test_validate_allocation_accepts_permutation() -> None:
    validate_allocation({"edge": 2, "heart": 1, "iron": 3, "shadow": 1, "wits": 2})


def test_validate_allocation_rejects_wrong_multiset() -> None:
    with pytest.raises(ValueError):
        validate_allocation({"edge": 3, "heart": 3, "iron": 3, "shadow": 1, "wits": 2})


def test_validate_allocation_rejects_missing_stat() -> None:
    with pytest.raises(ValueError):
        validate_allocation({"edge": 1, "heart": 1, "iron": 2, "shadow": 2})


def test_archetype_bonus_adds_one_to_primary() -> None:
    ranger = get_archetype("ranger")  # primary: edge
    boosted = apply_archetype_bonus(_VALID, ranger)
    assert boosted["edge"] == _VALID["edge"] + 1
    # other stats untouched
    assert boosted["iron"] == _VALID["iron"]


def test_archetype_bonus_caps_at_four() -> None:
    warrior = get_archetype("warrior")  # primary: iron
    stats = {"edge": 1, "heart": 1, "iron": 3, "shadow": 2, "wits": 2}
    boosted = apply_archetype_bonus(stats, warrior)
    assert boosted["iron"] == 4  # 3 + 1, capped at 4 (not 5)


def test_create_with_archetype_applies_bonus_items_and_key() -> None:
    ranger = get_archetype("ranger")
    hero = create_with_archetype("Robin", _VALID, ranger)
    assert hero.name == "Robin"
    assert hero.archetype == "ranger"
    assert hero.edge == _VALID["edge"] + 1            # primary boosted
    assert hero.items == list(ranger.suggested_items)  # starter gear in inventory


def test_create_with_archetype_localized_items_override() -> None:
    warrior = get_archetype("warrior")
    hero = create_with_archetype("Grim", _VALID, warrior, items=["меч", "щит"])
    assert hero.items == ["меч", "щит"]
    assert hero.iron == _VALID["iron"] + 1


def test_create_with_archetype_rejects_bad_allocation() -> None:
    warrior = get_archetype("warrior")
    with pytest.raises(ValueError):
        create_with_archetype("X", {"edge": 3, "heart": 3, "iron": 3,
                                    "shadow": 3, "wits": 3}, warrior)


def test_create_with_archetype_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        create_with_archetype("  ", _VALID, get_archetype("warrior"))


def test_starting_allocation_is_one_one_two_two_three() -> None:
    assert sorted(STARTING_ALLOCATION) == [1, 1, 2, 2, 3]
