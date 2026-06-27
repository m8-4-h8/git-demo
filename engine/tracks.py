"""Ironsworn progress tracks.

A progress track models any multi-step challenge — a combat, a journey, a bond,
or anything custom. It advances exactly like a vow (same rank-based progress),
but instead of a fulfillment roll it is resolved by reading its progress against
fixed thresholds (:func:`end_encounter`).

Pure and frontend-independent: never imports ``telegram`` or ``storage``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from engine.progress import Rank, advance, progress_per_hit
from engine.rolls import Outcome

__all__ = [
    "TrackType",
    "Track",
    "progress_per_hit",
    "mark_progress",
    "end_encounter",
    "complete",
    "clear_progress",
    "parse_track_type",
]

# Progress thresholds for resolving a track (in boxes).
STRONG_AT = 10.0
WEAK_AT = 7.0


class TrackType(Enum):
    """What kind of challenge a progress track represents."""

    COMBAT = "combat"
    JOURNEY = "journey"
    BOND = "bond"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Track:
    """A multi-step challenge with a progress track. Immutable."""

    id: int
    title: str
    track_type: TrackType
    rank: Rank
    progress: float = 0.0
    completed: bool = False


def mark_progress(track: Track, hits: int = 1) -> Track:
    """Return a copy of ``track`` with progress advanced by ``hits`` (clamped).

    Raises:
        ValueError: If ``hits`` is negative.
    """
    return replace(track, progress=advance(track.progress, track.rank, hits))


def end_encounter(track: Track) -> Outcome:
    """Resolve a track by its progress: >=10 strong, >=7 weak, otherwise miss."""
    if track.progress >= STRONG_AT:
        return Outcome.STRONG
    if track.progress >= WEAK_AT:
        return Outcome.WEAK
    return Outcome.MISS


def complete(track: Track) -> Track:
    """Return a copy of ``track`` marked as completed."""
    return replace(track, completed=True)


def clear_progress(track: Track) -> Track:
    """Return a copy of ``track`` with progress reset to zero (still active)."""
    return replace(track, progress=0.0)


def parse_track_type(text: str) -> TrackType:
    """Resolve a canonical type name (e.g. ``"combat"``) to a :class:`TrackType`.

    Case-insensitive. The frontend translates localized aliases to a canonical
    English name before calling this.

    Raises:
        ValueError: If ``text`` is not a known track type.
    """
    try:
        return TrackType(text.strip().lower())
    except ValueError:
        valid = ", ".join(tt.value for tt in TrackType)
        raise ValueError(f"unknown track type '{text}'. Choose one of: {valid}")
