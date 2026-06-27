"""Tests for the shared progress mechanics (ranks, advancement, parsing)."""

import pytest

from bot.i18n import LANGS, RANK_ALIASES, TEXTS, TRACK_TYPE_ALIASES
from engine.progress import Rank, advance, parse_rank, progress_per_hit
from engine.tracks import TrackType

_PER_HIT = [
    (Rank.TROUBLESOME, 3.0),
    (Rank.DANGEROUS, 2.0),
    (Rank.FORMIDABLE, 1.0),
    (Rank.EXTREME, 0.5),
    (Rank.EPIC, 0.25),
]


@pytest.mark.parametrize("rank, expected", _PER_HIT)
def test_progress_per_hit(rank: Rank, expected: float) -> None:
    assert progress_per_hit(rank) == expected


@pytest.mark.parametrize("rank, expected", _PER_HIT)
def test_advance_one_hit_from_zero(rank: Rank, expected: float) -> None:
    assert advance(0.0, rank, 1) == expected


def test_advance_accumulates_hits() -> None:
    assert advance(0.0, Rank.DANGEROUS, 3) == 6.0
    assert advance(1.0, Rank.EPIC, 2) == 1.5


def test_advance_clamps_at_max() -> None:
    # 9 + 3 = 12, clamped to 10
    assert advance(9.0, Rank.TROUBLESOME, 1) == 10.0
    assert advance(10.0, Rank.EPIC, 8) == 10.0


def test_advance_zero_hits_is_noop() -> None:
    assert advance(4.0, Rank.DANGEROUS, 0) == 4.0


def test_advance_negative_hits_raises() -> None:
    with pytest.raises(ValueError):
        advance(0.0, Rank.DANGEROUS, -1)


def test_parse_rank_is_case_insensitive() -> None:
    assert parse_rank("Dangerous") is Rank.DANGEROUS
    assert parse_rank("  epic ") is Rank.EPIC


def test_parse_rank_unknown_raises() -> None:
    with pytest.raises(ValueError):
        parse_rank("legendary")


def test_rank_aliases_cover_every_rank() -> None:
    assert set(RANK_ALIASES.values()) == {r.value for r in Rank}
    # every canonical english rank name maps to itself
    for rank in Rank:
        assert RANK_ALIASES[rank.value] == rank.value


def test_track_type_aliases_cover_every_type() -> None:
    assert set(TRACK_TYPE_ALIASES.values()) == {tt.value for tt in TrackType}
    for track_type in TrackType:
        assert TRACK_TYPE_ALIASES[track_type.value] == track_type.value


def test_rank_and_type_labels_exist_in_every_language() -> None:
    for lang in LANGS:
        for rank in Rank:
            assert f"rank_{rank.value}" in TEXTS[lang]
        for track_type in TrackType:
            assert f"type_{track_type.value}" in TEXTS[lang]
