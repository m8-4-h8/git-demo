"""Ironsworn character model and rules.

Pure, frontend-independent, and persistence-independent: this module holds the
character data model plus the rules that bound its values. It imports only the
standard library — never ``telegram`` and never ``storage``. Persistence lives
in the separate ``storage`` package.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

STAT_NAMES = ("edge", "heart", "iron", "shadow", "wits")
TRACK_NAMES = ("health", "spirit", "supply")
# Fields a player may change with /set.
SETTABLE_FIELDS = (*TRACK_NAMES, "momentum")

STAT_MIN = 1
STAT_MAX = 3
TRACK_MIN = 0
TRACK_MAX = 5
MOMENTUM_MIN = -6
MOMENTUM_MAX = 10
MOMENTUM_START = 2
MOMENTUM_RESET = 2


@dataclass(frozen=True)
class Character:
    """An Ironsworn character sheet.

    Stats are 1-3, tracks 0-5, momentum -6..+10. Instances are immutable;
    rule helpers return new copies via :func:`dataclasses.replace`.
    """

    name: str
    edge: int
    heart: int
    iron: int
    shadow: int
    wits: int
    health: int = TRACK_MAX
    spirit: int = TRACK_MAX
    supply: int = TRACK_MAX
    momentum: int = MOMENTUM_START


def bounds_for(field: str) -> tuple[int, int]:
    """Return the inclusive (min, max) bounds for a settable field."""
    if field in TRACK_NAMES:
        return TRACK_MIN, TRACK_MAX
    if field == "momentum":
        return MOMENTUM_MIN, MOMENTUM_MAX
    raise ValueError(
        f"unknown field '{field}'. Settable: {', '.join(SETTABLE_FIELDS)}"
    )


def new_character(
    name: str,
    edge: int,
    heart: int,
    iron: int,
    shadow: int,
    wits: int,
) -> Character:
    """Create a character with full tracks and starting momentum.

    Raises:
        ValueError: If the name is empty or any stat is outside 1-3.
    """
    if not name.strip():
        raise ValueError("name must not be empty")
    stats = {
        "edge": edge,
        "heart": heart,
        "iron": iron,
        "shadow": shadow,
        "wits": wits,
    }
    for stat_name, value in stats.items():
        if not STAT_MIN <= value <= STAT_MAX:
            raise ValueError(
                f"{stat_name} must be between {STAT_MIN} and {STAT_MAX}, got {value}"
            )
    return Character(name=name.strip(), edge=edge, heart=heart, iron=iron,
                     shadow=shadow, wits=wits)


def stat_value(character: Character, name: str) -> int:
    """Return the value of a named stat (edge/heart/iron/shadow/wits)."""
    key = name.strip().lower()
    if key not in STAT_NAMES:
        raise ValueError(
            f"unknown stat '{name}'. Choose one of: {', '.join(STAT_NAMES)}"
        )
    return getattr(character, key)


def set_field(character: Character, field: str, value: int) -> Character:
    """Return a copy of ``character`` with ``field`` set to ``value``.

    Raises:
        ValueError: If the field is not settable or the value is out of bounds.
    """
    key = field.strip().lower()
    low, high = bounds_for(key)  # also validates that the field is settable
    if not low <= value <= high:
        raise ValueError(f"{key} must be between {low} and {high}, got {value}")
    return replace(character, **{key: value})


def reset_momentum(character: Character) -> Character:
    """Return a copy of ``character`` with momentum reset to its starting value."""
    return replace(character, momentum=MOMENTUM_RESET)
