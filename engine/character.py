"""Ironsworn character model and rules.

Pure, frontend-independent, and persistence-independent: this module holds the
character data model plus the rules that bound its values. It imports only the
standard library — never ``telegram`` and never ``storage``. Persistence lives
in the separate ``storage`` package.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

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

# Inventory / background limits (validated by the helpers below).
MAX_ITEMS = 20
MAX_ITEM_LENGTH = 50
MAX_BACKGROUND_LENGTH = 500


@dataclass(frozen=True)
class Character:
    """An Ironsworn character sheet.

    Stats are 1-3, tracks 0-5, momentum -6..+10. ``items`` is a simple
    inventory of short strings and ``background`` is optional free prose.
    Instances are immutable; rule helpers return new copies via
    :func:`dataclasses.replace`.
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
    items: list[str] = field(default_factory=list)
    background: str | None = None
    archetype: str | None = None


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


def add_item(character: Character, item: str) -> Character:
    """Return a copy of ``character`` with ``item`` appended to the inventory.

    Raises:
        ValueError: If the item is empty, too long, or the inventory is full.
    """
    text = item.strip()
    if not text:
        raise ValueError("item must not be empty")
    if len(text) > MAX_ITEM_LENGTH:
        raise ValueError(
            f"item must be at most {MAX_ITEM_LENGTH} characters, got {len(text)}"
        )
    if len(character.items) >= MAX_ITEMS:
        raise ValueError(f"inventory is full (max {MAX_ITEMS} items)")
    return replace(character, items=[*character.items, text])


def remove_item(character: Character, index: int) -> Character:
    """Return a copy of ``character`` with the item at ``index`` removed.

    Raises:
        ValueError: If ``index`` is out of range.
    """
    if not 0 <= index < len(character.items):
        raise ValueError(f"no item at index {index}")
    remaining = [it for i, it in enumerate(character.items) if i != index]
    return replace(character, items=remaining)


def set_background(character: Character, text: str) -> Character:
    """Return a copy of ``character`` with ``background`` replaced wholesale.

    A blank string clears the background (stored as ``None``).

    Raises:
        ValueError: If the text exceeds the length limit.
    """
    cleaned = text.strip()
    if len(cleaned) > MAX_BACKGROUND_LENGTH:
        raise ValueError(
            f"background must be at most {MAX_BACKGROUND_LENGTH} characters, "
            f"got {len(cleaned)}"
        )
    return replace(character, background=cleaned or None)
