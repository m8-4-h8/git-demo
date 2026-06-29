"""Tests for the moves engine (pure, deterministic via injected RNG)."""

import pytest

from engine import (
    MOVES,
    MoveCategory,
    apply_effects,
    moves_in,
    new_character,
    resolve_move,
)
from engine.moves import CharacterDelta
from engine.rolls import Outcome


class FakeRandom:
    """Returns queued values from randint, ignoring bounds."""

    def __init__(self, values: list[int]) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


def _hero(**over):
    base = dict(name="Aila", edge=1, heart=2, iron=3, shadow=1, wits=2)
    base.update(over)
    return new_character(**base)


def _rng(action_die, c1, c2) -> FakeRandom:
    return FakeRandom([action_die, c1, c2])


def test_categories_partition_moves() -> None:
    keyed = {k for cat in MoveCategory for k in moves_in(cat)}
    assert keyed == set(MOVES)
    assert "strike" in moves_in(MoveCategory.COMBAT)
    assert "face_danger" in moves_in(MoveCategory.ADVENTURE)


def test_strike_strong_hit_gains_momentum() -> None:
    # iron=3, action die 6 -> score 9 vs (3,4) -> strong
    result = resolve_move("strike", _hero(), "iron", rng=_rng(6, 3, 4))
    assert result.roll.outcome is Outcome.STRONG
    assert result.delta.changes == {"momentum": 2}
    assert result.stat_name == "iron"


def test_strike_miss_costs_health() -> None:
    # iron=3, action die 1 -> score 4 vs (8,9) -> miss
    result = resolve_move("strike", _hero(), "iron", rng=_rng(1, 8, 9))
    assert result.roll.outcome is Outcome.MISS
    assert result.delta.changes == {"health": -1}


def test_apply_effects_changes_and_clamps() -> None:
    hero = _hero()  # momentum 2, health 5
    updated, applied = apply_effects(hero, CharacterDelta({"momentum": +2}))
    assert updated.momentum == 4
    assert applied.changes == {"momentum": 2}

    # clamp: health can't exceed its max (5); a +3 is a no-op
    updated2, applied2 = apply_effects(hero, CharacterDelta({"health": +3}))
    assert updated2.health == 5
    assert applied2.changes == {}  # nothing actually changed


def test_apply_effects_clamps_floor() -> None:
    hero = _hero()  # health 5
    # -9 clamps to 0; applied delta reflects the real change (-5)
    updated, applied = apply_effects(hero, CharacterDelta({"health": -9}))
    assert updated.health == 0
    assert applied.changes == {"health": -5}


def test_empty_delta_is_falsy() -> None:
    assert not CharacterDelta({})
    assert CharacterDelta({"momentum": 1})


def test_unknown_move_raises() -> None:
    with pytest.raises(ValueError):
        resolve_move("teleport", _hero(), "iron", rng=_rng(6, 3, 4))


def test_unknown_stat_raises() -> None:
    with pytest.raises(ValueError):
        resolve_move("strike", _hero(), "luck", rng=_rng(6, 3, 4))
