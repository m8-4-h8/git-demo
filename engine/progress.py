"""Shared Ironsworn progress mechanics.

Both vows and progress tracks advance the same way: a challenge has a
difficulty :class:`Rank`, and each marked progress fills a number of boxes that
depends on that rank (a harder challenge advances more slowly). Progress is
measured in boxes on a 0.0-10.0 track.

Pure and frontend-independent: standard library only, never ``telegram`` and
never ``storage``.
"""

from __future__ import annotations

from enum import Enum

PROGRESS_MIN = 0.0
PROGRESS_MAX = 10.0


class Rank(Enum):
    """Difficulty rank of a vow or progress track."""

    TROUBLESOME = "troublesome"
    DANGEROUS = "dangerous"
    FORMIDABLE = "formidable"
    EXTREME = "extreme"
    EPIC = "epic"


# Boxes filled per marked progress, by rank: harder challenges advance slower.
_PROGRESS_PER_HIT = {
    Rank.TROUBLESOME: 3.0,
    Rank.DANGEROUS: 2.0,
    Rank.FORMIDABLE: 1.0,
    Rank.EXTREME: 0.5,
    Rank.EPIC: 0.25,
}


def progress_per_hit(rank: Rank) -> float:
    """Return how many progress boxes one hit fills for the given rank."""
    return _PROGRESS_PER_HIT[rank]


def advance(progress: float, rank: Rank, hits: int = 1) -> float:
    """Return ``progress`` advanced by ``hits`` marks, clamped to 0.0-10.0.

    Raises:
        ValueError: If ``hits`` is negative.
    """
    if hits < 0:
        raise ValueError(f"hits must be non-negative, got {hits}")
    gained = progress_per_hit(rank) * hits
    return min(PROGRESS_MAX, max(PROGRESS_MIN, progress + gained))


def parse_rank(text: str) -> Rank:
    """Resolve a canonical rank name (e.g. ``"dangerous"``) to a :class:`Rank`.

    Case-insensitive. The frontend is responsible for translating localized
    aliases to a canonical English name before calling this.

    Raises:
        ValueError: If ``text`` is not a known rank name.
    """
    try:
        return Rank(text.strip().lower())
    except ValueError:
        valid = ", ".join(r.value for r in Rank)
        raise ValueError(f"unknown rank '{text}'. Choose one of: {valid}")
