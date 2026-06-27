"""Tests for progress-track rules: advancement and encounter resolution."""

import pytest

from engine.progress import Rank
from engine.rolls import Outcome
from engine.tracks import (
    Track,
    TrackType,
    clear_progress,
    complete,
    end_encounter,
    mark_progress,
    parse_track_type,
)


def _track(
    rank: Rank = Rank.FORMIDABLE,
    progress: float = 0.0,
    completed: bool = False,
) -> Track:
    return Track(
        id=1,
        title="Duel",
        track_type=TrackType.COMBAT,
        rank=rank,
        progress=progress,
        completed=completed,
    )


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
    assert mark_progress(_track(rank), 1).progress == expected


def test_mark_progress_clamps_at_10() -> None:
    assert mark_progress(_track(Rank.TROUBLESOME, 9.5), 2).progress == 10.0


def test_end_encounter_strong_at_10() -> None:
    assert end_encounter(_track(progress=10.0)) is Outcome.STRONG


def test_end_encounter_weak_at_threshold() -> None:
    assert end_encounter(_track(progress=7.0)) is Outcome.WEAK


def test_end_encounter_weak_between_7_and_10() -> None:
    assert end_encounter(_track(progress=9.5)) is Outcome.WEAK


def test_end_encounter_miss_just_below_7() -> None:
    assert end_encounter(_track(progress=6.5)) is Outcome.MISS


def test_end_encounter_miss_at_zero() -> None:
    assert end_encounter(_track(progress=0.0)) is Outcome.MISS


def test_complete_marks_completed_immutably() -> None:
    track = _track(progress=5.0)
    done = complete(track)
    assert done.completed is True
    assert track.completed is False


def test_clear_progress_resets_to_zero() -> None:
    assert clear_progress(_track(progress=8.0)).progress == 0.0


def test_parse_track_type_is_case_insensitive() -> None:
    assert parse_track_type("Journey") is TrackType.JOURNEY
    assert parse_track_type("BOND") is TrackType.BOND


def test_parse_track_type_unknown_raises() -> None:
    with pytest.raises(ValueError):
        parse_track_type("raid")
