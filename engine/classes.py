"""Character archetypes ("paths") and archetype-aware creation.

A light, original adaptation of the classic RPG class fantasy — not a copy of
any specific system. Each :class:`CharacterArchetype` is language-agnostic data:
a stable ``key``, the stat it favours, its suggested starting gear (item *keys*,
localized by the bot), and an emoji. The human-readable name and description
live in the bot's i18n catalog, keyed by the archetype key.

This module is pure: it imports only :mod:`engine.character` and never touches a
frontend or storage.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.character import STAT_NAMES, Character

# A new hero distributes exactly these five values across the five stats — each
# value used once — then the chosen path adds +1 to its favoured stat.
STARTING_ALLOCATION = (1, 1, 2, 2, 3)
# The archetype bonus may push one stat to 4 (above the normal 1-3 spread).
ARCHETYPE_STAT_CAP = 4


@dataclass(frozen=True)
class CharacterArchetype:
    """A hero's path: favoured stat, starting gear, and an emoji.

    ``key`` is the canonical identifier; the localized name/description live in
    i18n. ``suggested_items`` are item keys (the bot localizes them into the
    inventory at creation). ``primary_stat`` gets +1 when the path is chosen.
    """

    key: str
    primary_stat: str
    suggested_items: tuple[str, ...]
    flavor_icon: str


# Eight archetypes — a free adaptation, written in the spirit of the Ironsworn
# world rather than any licensed class list.
ARCHETYPES: dict[str, CharacterArchetype] = {
    "warrior": CharacterArchetype("warrior", "iron", ("sword", "shield"), "⚔️"),
    "rogue": CharacterArchetype("rogue", "shadow", ("daggers", "lockpicks"), "🗡️"),
    "ranger": CharacterArchetype("ranger", "edge", ("bow", "arrows"), "🏹"),
    "sage": CharacterArchetype("sage", "wits", ("spellbook", "staff"), "📖"),
    "priest": CharacterArchetype("priest", "heart", ("holy_symbol", "healing_herbs"), "🙏"),
    "bard": CharacterArchetype("bard", "heart", ("lute", "wine_flask"), "🎭"),
    "savage": CharacterArchetype("savage", "iron", ("axe", "beast_pelt"), "🐺"),
    "wanderer": CharacterArchetype("wanderer", "wits", ("herbs", "wanderers_staff"), "🌿"),
}

# Every item key referenced by the archetypes (handy for i18n coverage tests).
SUGGESTED_ITEM_KEYS = tuple(
    key for arch in ARCHETYPES.values() for key in arch.suggested_items
)


def archetype_keys() -> list[str]:
    """Return the archetype keys in registry order (for laying out buttons)."""
    return list(ARCHETYPES)


def get_archetype(key: str) -> CharacterArchetype:
    """Look up an archetype by key.

    Raises:
        ValueError: If ``key`` is unknown.
    """
    try:
        return ARCHETYPES[key]
    except KeyError:
        raise ValueError(
            f"unknown archetype '{key}'. Known: {', '.join(ARCHETYPES)}"
        ) from None


def validate_allocation(stats: dict[str, int]) -> None:
    """Check ``stats`` assigns each stat exactly one of 1, 1, 2, 2, 3.

    Raises:
        ValueError: If a stat is missing/extra or the multiset is wrong.
    """
    if set(stats) != set(STAT_NAMES):
        raise ValueError(
            f"must assign exactly these stats: {', '.join(STAT_NAMES)}"
        )
    if sorted(stats.values()) != sorted(STARTING_ALLOCATION):
        raise ValueError(
            "stats must use each of "
            f"{', '.join(map(str, STARTING_ALLOCATION))} exactly once"
        )


def apply_archetype_bonus(
    stats: dict[str, int], archetype: CharacterArchetype
) -> dict[str, int]:
    """Return ``stats`` with the archetype's primary stat +1 (capped at 4)."""
    boosted = dict(stats)
    primary = archetype.primary_stat
    boosted[primary] = min(ARCHETYPE_STAT_CAP, boosted.get(primary, 0) + 1)
    return boosted


def create_with_archetype(
    name: str,
    stats: dict[str, int],
    archetype: CharacterArchetype,
    items: list[str] | None = None,
) -> Character:
    """Build a Character from a validated allocation, applying the path bonus.

    ``items`` are the (already-localized) starting items to seed the inventory;
    when omitted, the archetype's ``suggested_items`` keys are used as-is.

    Raises:
        ValueError: If the name is empty or the allocation is invalid.
    """
    if not name.strip():
        raise ValueError("name must not be empty")
    validate_allocation(stats)
    boosted = apply_archetype_bonus(stats, archetype)
    starting_items = list(items) if items is not None else list(archetype.suggested_items)
    return Character(
        name=name.strip(),
        edge=boosted["edge"],
        heart=boosted["heart"],
        iron=boosted["iron"],
        shadow=boosted["shadow"],
        wits=boosted["wits"],
        items=starting_items,
        archetype=archetype.key,
    )
