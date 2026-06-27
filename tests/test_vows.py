"""Tests for vow rules: progress marking and the fulfillment roll.

The fulfillment roll reuses ``roll_action`` for the challenge dice, so the
fake RNG must supply, in order: the (ignored) action die, then the two
challenge dice.
"""

import pytest

from engine.progress import Rank
from engine.rolls import Outcome
from engine.vows import Vow, forsake, fulfillment_roll, mark_progress


class FakeRandom:
    """Returns queued values from ``randint``, ignoring the bounds."""

    def __init__(self, values: list[int]) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


def _vow(rank: Rank = Rank.DANGEROUS, progress: float = 0.0) -> Vow:
    return Vow(id=1, title="Quest", rank=rank, progress=progress)


@pytest.mark.parametrize(
    "rank, expected",
    [
        (Rank.TROUBLESOME, 3.0),
        (Rank.DANGEROUS, 2.0),
        (Rank.FORMIDABLE, 1.0),
        (Rank.EXTREME, 0.5),
        (Rank.EPIC, 0.25),
    ],
)
def test_mark_progress_per_rank(rank: Rank, expected: float) -> None:
    assert mark_progress(_vow(rank), 1).progress == expected


def test_mark_progress_is_immutable() -> None:
    original = _vow()
    advanced = mark_progress(original, 1)
    assert original.progress == 0.0
    assert advanced.progress == 2.0
    assert advanced is not original


def test_mark_progress_clamps_at_10() -> None:
    assert mark_progress(_vow(Rank.TROUBLESOME, 9.0), 1).progress == 10.0


def test_fulfillment_strong_hit_fulfills() -> None:
    # progress 8 -> score 8, beats both 3 and 4
    result = fulfillment_roll(_vow(progress=8.0), rng=FakeRandom([1, 3, 4]))
    assert result.roll.action_score == 8
    assert result.roll.outcome is Outcome.STRONG
    assert result.vow.fulfilled is True


def test_fulfillment_weak_hit_fulfills() -> None:
    # score 8 beats 3 but not 10
    result = fulfillment_roll(_vow(progress=8.0), rng=FakeRandom([1, 3, 10]))
    assert result.roll.outcome is Outcome.WEAK
    assert result.vow.fulfilled is True


def test_fulfillment_miss_does_not_fulfill_or_reset() -> None:
    # score 2 beats neither 5 nor 9
    vow = _vow(progress=2.0)
    result = fulfillment_roll(vow, rng=FakeRandom([1, 5, 9]))
    assert result.roll.outcome is Outcome.MISS
    assert result.vow.fulfilled is False
    assert result.vow.progress == 2.0  # progress is never reset on a miss
    assert result.vow is vow  # unchanged object returned


def test_fulfillment_uses_floor_of_progress() -> None:
    # progress 4.5 -> score floor(4.5) = 4, beats 1 and 2
    result = fulfillment_roll(_vow(progress=4.5), rng=FakeRandom([1, 1, 2]))
    assert result.roll.action_score == 4
    assert result.roll.outcome is Outcome.STRONG


def test_forsake_marks_forsaken_immutably() -> None:
    original = _vow()
    forsaken = forsake(original)
    assert forsaken.forsaken is True
    assert original.forsaken is False
