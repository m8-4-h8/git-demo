"""Deterministic tests for the oracles.

The yes/no oracle draws a single 1d100 via ``randint(1, 100)``; the inspiration
draw indexes a table via ``randint(0, n - 1)``. A fake RNG returns queued values
so every branch is exercised exactly.
"""

import pytest

from engine.oracles import (
    Answer,
    Odds,
    ask_yes_no,
    draw_from,
    list_tables,
    random_table,
    table_title,
)


class FakeRandom:
    """Returns queued values from ``randint``, ignoring the bounds."""

    def __init__(self, values: list[int]) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


# --- yes/no oracle: each odds level at and just past its threshold ---


@pytest.mark.parametrize(
    "odds, chance",
    [
        (Odds.ALMOST_CERTAIN, 90),
        (Odds.LIKELY, 75),
        (Odds.FIFTY_FIFTY, 50),
        (Odds.UNLIKELY, 25),
        (Odds.SMALL_CHANCE, 10),
    ],
)
def test_yes_at_threshold(odds: Odds, chance: int) -> None:
    result = ask_yes_no(odds, rng=FakeRandom([chance]))
    assert result.chance == chance
    assert result.roll == chance
    assert result.answer is Answer.YES


@pytest.mark.parametrize(
    "odds, chance",
    [
        (Odds.ALMOST_CERTAIN, 90),
        (Odds.LIKELY, 75),
        (Odds.FIFTY_FIFTY, 50),
        (Odds.UNLIKELY, 25),
        (Odds.SMALL_CHANCE, 10),
    ],
)
def test_no_just_past_threshold(odds: Odds, chance: int) -> None:
    result = ask_yes_no(odds, rng=FakeRandom([chance + 1]))
    assert result.answer is Answer.NO


def test_accepts_odds_by_name() -> None:
    result = ask_yes_no("likely", rng=FakeRandom([50]))
    assert result.odds is Odds.LIKELY
    assert result.answer is Answer.YES


def test_unknown_odds_name_raises() -> None:
    with pytest.raises(ValueError):
        ask_yes_no("coin_flip")


@pytest.mark.parametrize("roll", [11, 22, 33, 44, 55, 66, 77, 88, 99, 100])
def test_extreme_on_matching_digits(roll: int) -> None:
    result = ask_yes_no(Odds.FIFTY_FIFTY, rng=FakeRandom([roll]))
    assert result.is_extreme is True


@pytest.mark.parametrize("roll", [1, 10, 23, 50, 76, 98])
def test_not_extreme_otherwise(roll: int) -> None:
    result = ask_yes_no(Odds.FIFTY_FIFTY, rng=FakeRandom([roll]))
    assert result.is_extreme is False


def test_extreme_yes_combination() -> None:
    # likely (75): roll 22 -> Yes and extreme
    result = ask_yes_no(Odds.LIKELY, rng=FakeRandom([22]))
    assert result.answer is Answer.YES
    assert result.is_extreme is True


# --- inspiration tables ---


def test_draw_from_is_deterministic_with_rng() -> None:
    first = draw_from("npc", rng=FakeRandom([0]))
    assert isinstance(first, str)
    assert first  # non-empty


def test_draw_from_returns_an_actual_entry() -> None:
    _, entries = _table("place")
    drawn = draw_from("place", rng=FakeRandom([2]))
    assert drawn == entries[2]


def test_draw_from_unknown_table_raises() -> None:
    with pytest.raises(ValueError):
        draw_from("does_not_exist")


def test_sample_tables_are_available() -> None:
    tables = list_tables()
    assert {"action_theme", "place", "npc"}.issubset(set(tables))


def test_table_title_reads_data() -> None:
    assert table_title("npc")  # non-empty title declared in JSON


def test_random_table_picks_from_list() -> None:
    tables = list_tables()
    chosen = random_table(rng=FakeRandom([0]))
    assert chosen == tables[0]


def _table(name: str) -> tuple[str, tuple[str, ...]]:
    from engine.oracles import _load_table

    return _load_table(name)
