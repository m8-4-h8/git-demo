"""Ironsworn vows.

A vow is a character's sworn quest — the main engine of play. It carries a
difficulty :class:`~engine.progress.Rank`, a progress track (0.0-10.0), and is
eventually fulfilled (or forsaken). Marking progress and the fulfillment roll
are pure, deterministic functions here; persistence and presentation live
elsewhere.

Pure and frontend-independent: never imports ``telegram`` or ``storage``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

from engine.progress import Rank, advance, progress_per_hit
from engine.rolls import ActionRoll, Outcome, progress_roll

__all__ = [
    "Vow",
    "FulfillmentResult",
    "progress_per_hit",
    "mark_progress",
    "fulfillment_roll",
    "forsake",
]


@dataclass(frozen=True)
class Vow:
    """A sworn quest. Immutable; helpers return new copies."""

    id: int
    title: str
    rank: Rank
    progress: float = 0.0
    fulfilled: bool = False
    forsaken: bool = False


@dataclass(frozen=True)
class FulfillmentResult:
    """Outcome of a fulfillment roll plus the (possibly updated) vow.

    ``vow`` has ``fulfilled`` set on a strong or weak hit; on a miss it is the
    original vow unchanged (progress is never reset).
    """

    roll: ActionRoll
    vow: Vow


def mark_progress(vow: Vow, hits: int = 1) -> Vow:
    """Return a copy of ``vow`` with progress advanced by ``hits`` (clamped).

    Raises:
        ValueError: If ``hits`` is negative.
    """
    return replace(vow, progress=advance(vow.progress, vow.rank, hits))


def fulfillment_roll(
    vow: Vow, *, rng: random.Random | None = None
) -> FulfillmentResult:
    """Make the fulfillment roll for ``vow``.

    The progress score is ``floor(progress)`` (rounded down to whole boxes) and
    is compared against two challenge dice via :func:`engine.rolls.progress_roll`
    (stat 0, no action die). A strong or weak hit fulfills the vow; a miss leaves
    it untouched — progress is *not* reset.
    """
    roll = progress_roll(math.floor(vow.progress), rng=rng)
    if roll.outcome in (Outcome.STRONG, Outcome.WEAK):
        return FulfillmentResult(roll=roll, vow=replace(vow, fulfilled=True))
    return FulfillmentResult(roll=roll, vow=vow)


def forsake(vow: Vow) -> Vow:
    """Return a copy of ``vow`` marked as forsaken (abandoned)."""
    return replace(vow, forsaken=True)
