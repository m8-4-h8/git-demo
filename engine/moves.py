"""Ironsworn moves — named actions grouped by category, with simple effects.

A *move* is a thematic action (Strike, Face Danger, …) in a category
(Adventure / Combat / Quest). The player picks a move and then a stat to roll;
the engine resolves the roll and applies the move's per-outcome effect to the
character's tracks/momentum. Pure and frontend-/persistence-independent.

The effect set here is a deliberately small v1 — not the full Ironsworn move
list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from engine.character import Character, bounds_for, set_field, stat_value
from engine.rolls import ActionRoll, Outcome, roll_action


class MoveCategory(Enum):
    """Which part of play a move belongs to."""

    ADVENTURE = "adventure"
    COMBAT = "combat"
    QUEST = "quest"


@dataclass(frozen=True)
class CharacterDelta:
    """Signed changes to a character's tracks/momentum (empty = no effect)."""

    changes: dict[str, int] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.changes)


@dataclass(frozen=True)
class MoveSpec:
    """A move: its category and its per-outcome effects."""

    key: str
    category: MoveCategory
    effects: dict[Outcome, dict[str, int]]


@dataclass(frozen=True)
class MoveResult:
    """The roll for a move plus the effect to apply."""

    move_key: str
    stat_name: str
    roll: ActionRoll
    delta: CharacterDelta


# v1 move set. The stat is chosen by the player at roll time, not fixed here.
MOVES: dict[str, MoveSpec] = {
    "strike": MoveSpec(
        "strike", MoveCategory.COMBAT,
        {Outcome.STRONG: {"momentum": +2},
         Outcome.WEAK: {"momentum": +1},
         Outcome.MISS: {"health": -1}},
    ),
    "clash": MoveSpec(
        "clash", MoveCategory.COMBAT,
        {Outcome.STRONG: {"momentum": +2},
         Outcome.WEAK: {"supply": -1},
         Outcome.MISS: {"health": -1}},
    ),
    "face_danger": MoveSpec(
        "face_danger", MoveCategory.ADVENTURE,
        {Outcome.STRONG: {"momentum": +1},
         Outcome.WEAK: {"supply": -1},
         Outcome.MISS: {"spirit": -1}},
    ),
    "secure_advantage": MoveSpec(
        "secure_advantage", MoveCategory.ADVENTURE,
        {Outcome.STRONG: {"momentum": +2},
         Outcome.WEAK: {"momentum": +1},
         Outcome.MISS: {"momentum": -1}},
    ),
    "gather_information": MoveSpec(
        "gather_information", MoveCategory.ADVENTURE,
        {Outcome.STRONG: {"momentum": +1},
         Outcome.WEAK: {"momentum": +1},
         Outcome.MISS: {"spirit": -1}},
    ),
    "gather_your_resolve": MoveSpec(
        "gather_your_resolve", MoveCategory.QUEST,
        {Outcome.STRONG: {"spirit": +2},
         Outcome.WEAK: {"spirit": +1},
         Outcome.MISS: {"momentum": -1}},
    ),
    "reach_a_milestone": MoveSpec(
        "reach_a_milestone", MoveCategory.QUEST,
        {Outcome.STRONG: {"momentum": +1},
         Outcome.WEAK: {"momentum": +1},
         Outcome.MISS: {"spirit": -1}},
    ),
}


def moves_in(category: MoveCategory) -> list[str]:
    """Return the move keys in a category, in registry order."""
    return [key for key, spec in MOVES.items() if spec.category is category]


def resolve_move(
    move_key: str,
    character: Character,
    stat_name: str,
    adds: int = 0,
    *,
    rng=None,
) -> MoveResult:
    """Roll the chosen stat for a move and compute its pending effect.

    Raises:
        ValueError: If ``move_key`` or ``stat_name`` is unknown.
    """
    spec = MOVES.get(move_key)
    if spec is None:
        raise ValueError(f"unknown move '{move_key}'. Known: {', '.join(MOVES)}")
    roll = roll_action(stat_value(character, stat_name), adds, rng=rng)
    delta = CharacterDelta(dict(spec.effects.get(roll.outcome, {})))
    return MoveResult(move_key=move_key, stat_name=stat_name, roll=roll, delta=delta)


def apply_effects(
    character: Character, delta: CharacterDelta
) -> tuple[Character, CharacterDelta]:
    """Apply a delta to a character, clamped to bounds; return the applied delta."""
    updated = character
    applied: dict[str, int] = {}
    for field_name, change in delta.changes.items():
        low, high = bounds_for(field_name)
        current = getattr(updated, field_name)
        new_value = max(low, min(high, current + change))
        if new_value != current:
            updated = set_field(updated, field_name, new_value)
            applied[field_name] = new_value - current
    return updated, CharacterDelta(applied)
