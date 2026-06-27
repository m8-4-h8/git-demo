"""Ironsworn action roll.

Pure game logic for resolving an action roll. No I/O, no frontend imports.
The RNG is injectable so tests can be fully deterministic.

Rules implemented:
- action score = action die (1d6) + stat (0-4) + adds, capped at 10.
- two challenge dice (2x 1d10).
- strong hit  : action score beats BOTH challenge dice.
- weak hit    : action score beats EXACTLY ONE challenge die.
- miss        : action score beats NEITHER (<= both).
- match       : both challenge dice show the same number -> dramatic twist
                (a boost on a hit, a complication on a miss). Returned as a flag.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from enum import Enum

MAX_ACTION_SCORE = 10
STAT_MIN = 0
STAT_MAX = 4


class Outcome(Enum):
    """Result of an action roll."""

    STRONG = "strong"
    WEAK = "weak"
    MISS = "miss"


@dataclass(frozen=True)
class ActionRoll:
    """Outcome of a single action roll.

    ``action_score`` is already capped at :data:`MAX_ACTION_SCORE`.
    """

    action_die: int
    challenge_dice: tuple[int, int]
    stat: int
    adds: int
    action_score: int
    outcome: Outcome
    is_match: bool
    burned: bool = False


def _resolve(action_score: int, challenge_dice: tuple[int, int]) -> Outcome:
    """Decide the outcome of an action score against the challenge dice."""
    beaten = sum(1 for die in challenge_dice if action_score > die)
    if beaten == 2:
        return Outcome.STRONG
    if beaten == 1:
        return Outcome.WEAK
    return Outcome.MISS


def roll_action(
    stat: int,
    adds: int = 0,
    *,
    rng: random.Random | None = None,
) -> ActionRoll:
    """Resolve an Ironsworn action roll.

    Args:
        stat: The character stat to add, in the range 0-4.
        adds: Extra modifiers to add (non-negative). Defaults to 0.
        rng: Random source to draw dice from. Inject a seeded
            ``random.Random`` (or any object exposing ``randint``) for
            deterministic results. Defaults to a fresh ``random.Random``.

    Returns:
        An :class:`ActionRoll` describing the dice, the capped action score,
        the outcome, and whether the challenge dice matched.

    Raises:
        ValueError: If ``stat`` is outside 0-4 or ``adds`` is negative.
    """
    if not STAT_MIN <= stat <= STAT_MAX:
        raise ValueError(f"stat must be between {STAT_MIN} and {STAT_MAX}, got {stat}")
    if adds < 0:
        raise ValueError(f"adds must be non-negative, got {adds}")

    if rng is None:
        rng = random.Random()

    action_die = rng.randint(1, 6)
    challenge_dice = (rng.randint(1, 10), rng.randint(1, 10))

    action_score = min(action_die + stat + adds, MAX_ACTION_SCORE)
    is_match = challenge_dice[0] == challenge_dice[1]

    return ActionRoll(
        action_die=action_die,
        challenge_dice=challenge_dice,
        stat=stat,
        adds=adds,
        action_score=action_score,
        outcome=_resolve(action_score, challenge_dice),
        is_match=is_match,
    )


def burn_momentum(roll: ActionRoll, momentum: int) -> ActionRoll:
    """Burn momentum: replace the action score with the momentum value.

    The challenge dice are unchanged; the outcome is recomputed against the new
    score (capped at :data:`MAX_ACTION_SCORE`). Negative momentum naturally
    produces a miss. Resetting the character's momentum afterward is the
    caller's responsibility (see :func:`engine.character.reset_momentum`).
    """
    score = min(momentum, MAX_ACTION_SCORE)
    return replace(
        roll,
        action_score=score,
        outcome=_resolve(score, roll.challenge_dice),
        burned=True,
    )
