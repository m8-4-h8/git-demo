"""Deterministic tests for the Ironsworn action roll.

Uses a fake RNG that returns predetermined dice so every outcome can be
exercised exactly. The engine draws dice in this order: action die (1d6),
then the two challenge dice (1d10 each).
"""

import random

import pytest

from engine.rolls import ActionRoll, Outcome, burn_momentum, roll_action


class FakeRandom:
    """Returns queued values from ``randint``, ignoring the bounds."""

    def __init__(self, values: list[int]) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


def _rng(action_die: int, challenge_a: int, challenge_b: int) -> FakeRandom:
    return FakeRandom([action_die, challenge_a, challenge_b])


def test_strong_hit_beats_both() -> None:
    # score = 6 + 2 = 8, beats 3 and 4
    result = roll_action(2, rng=_rng(6, 3, 4))
    assert result.action_score == 8
    assert result.outcome is Outcome.STRONG
    assert result.is_match is False


def test_weak_hit_beats_exactly_one() -> None:
    # score = 6 + 2 = 8, beats 3 but not 10
    result = roll_action(2, rng=_rng(6, 3, 10))
    assert result.action_score == 8
    assert result.outcome is Outcome.WEAK
    assert result.is_match is False


def test_miss_beats_neither() -> None:
    # score = 1 + 0 = 1, beats neither 5 nor 9
    result = roll_action(0, rng=_rng(1, 5, 9))
    assert result.action_score == 1
    assert result.outcome is Outcome.MISS
    assert result.is_match is False


def test_miss_when_equal_to_challenge_die() -> None:
    # score = 5, equals both challenge dice -> "greater than" fails -> miss
    result = roll_action(4, adds=0, rng=_rng(1, 5, 5))
    assert result.action_score == 5
    assert result.outcome is Outcome.MISS


def test_match_on_hit_is_flagged() -> None:
    # score = 8, both challenge dice are 4 -> strong hit + match
    result = roll_action(2, rng=_rng(6, 4, 4))
    assert result.outcome is Outcome.STRONG
    assert result.is_match is True


def test_match_on_miss_is_flagged() -> None:
    # score = 2, both challenge dice are 8 -> miss + match
    result = roll_action(0, rng=_rng(2, 8, 8))
    assert result.outcome is Outcome.MISS
    assert result.is_match is True


def test_action_score_is_capped_at_10() -> None:
    # 6 + 4 + 5 = 15, capped to 10
    result = roll_action(4, adds=5, rng=_rng(6, 9, 9))
    assert result.action_score == 10
    assert result.outcome is Outcome.STRONG


def test_adds_are_included() -> None:
    # 3 + 1 + 2 = 6
    result = roll_action(1, adds=2, rng=_rng(3, 4, 9))
    assert result.action_score == 6
    assert result.outcome is Outcome.WEAK


def test_returns_dataclass_with_raw_dice() -> None:
    result = roll_action(2, adds=1, rng=_rng(5, 2, 7))
    assert isinstance(result, ActionRoll)
    assert result.action_die == 5
    assert result.challenge_dice == (2, 7)
    assert result.stat == 2
    assert result.adds == 1


@pytest.mark.parametrize("stat", [-1, 5])
def test_invalid_stat_raises(stat: int) -> None:
    with pytest.raises(ValueError):
        roll_action(stat)


def test_negative_adds_raises() -> None:
    with pytest.raises(ValueError):
        roll_action(2, adds=-1)


def test_default_rng_produces_in_range_dice() -> None:
    result = roll_action(2, rng=random.Random(12345))
    assert 1 <= result.action_die <= 6
    assert all(1 <= die <= 10 for die in result.challenge_dice)
    assert result.outcome in Outcome


def test_default_roll_is_not_burned() -> None:
    result = roll_action(2, rng=_rng(6, 3, 4))
    assert result.burned is False


def test_burn_turns_a_miss_into_a_strong_hit() -> None:
    # natural: 1 + 0 = 1 vs (3, 4) -> miss
    natural = roll_action(0, rng=_rng(1, 3, 4))
    assert natural.outcome is Outcome.MISS

    burned = burn_momentum(natural, momentum=8)
    assert burned.burned is True
    assert burned.action_score == 8
    assert burned.outcome is Outcome.STRONG
    # the challenge dice are untouched by the burn
    assert burned.challenge_dice == natural.challenge_dice


def test_burn_recomputes_to_weak_hit() -> None:
    natural = roll_action(0, rng=_rng(1, 3, 9))  # miss vs (3, 9)
    burned = burn_momentum(natural, momentum=5)  # 5 beats 3, not 9
    assert burned.action_score == 5
    assert burned.outcome is Outcome.WEAK


def test_burn_negative_momentum_is_a_miss() -> None:
    natural = roll_action(2, rng=_rng(6, 1, 1))  # strong hit
    burned = burn_momentum(natural, momentum=-3)
    assert burned.action_score == -3
    assert burned.outcome is Outcome.MISS


def test_burn_caps_score_at_10() -> None:
    natural = roll_action(0, rng=_rng(1, 9, 9))
    burned = burn_momentum(natural, momentum=10)
    assert burned.action_score == 10
    assert burned.outcome is Outcome.STRONG


def test_burn_preserves_is_match() -> None:
    natural = roll_action(0, rng=_rng(1, 7, 7))  # match
    burned = burn_momentum(natural, momentum=9)
    assert burned.is_match is True
