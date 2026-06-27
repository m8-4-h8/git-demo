"""Ironsworn oracles.

GM-less play answers yes/no questions with the Oracle, and draws inspiration
from content tables. All logic here is pure and frontend-independent; the RNG
is injectable for deterministic tests.

Yes/No oracle:
- Each odds level maps to a "yes" chance: almost_certain 90, likely 75,
  fifty_fifty 50, unlikely 25, small_chance 10.
- Roll 1d100; a roll <= the chance means Yes, otherwise No.
- A roll with matching digits (11, 22, ... 99, and 100 read as "00") is an
  "extreme" result: an unexpected, dramatic twist. Returned as a flag.

Inspiration tables live as JSON in ``data/oracles/`` so content can grow by
editing data, not code.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

ORACLE_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "oracles"


class Odds(Enum):
    """Likelihood of a "yes" answer; the value is the percent chance."""

    ALMOST_CERTAIN = 90
    LIKELY = 75
    FIFTY_FIFTY = 50
    UNLIKELY = 25
    SMALL_CHANCE = 10

    @classmethod
    def from_name(cls, name: str) -> "Odds":
        """Resolve a user-facing name like ``"likely"`` to an :class:`Odds`."""
        try:
            return cls[name.strip().upper()]
        except KeyError:
            valid = ", ".join(o.name.lower() for o in cls)
            raise ValueError(f"unknown odds '{name}'. Choose one of: {valid}")


class Answer(Enum):
    """Yes/No oracle answer."""

    YES = "yes"
    NO = "no"


@dataclass(frozen=True)
class YesNoResult:
    """Outcome of a yes/no oracle question."""

    odds: Odds
    chance: int
    roll: int
    answer: Answer
    is_extreme: bool


def _is_double(roll: int) -> bool:
    """True if the d100 roll has matching digits (11, 22, ... 99, or 100/"00")."""
    return roll == 100 or roll % 11 == 0


def ask_yes_no(odds: Odds | str, *, rng: random.Random | None = None) -> YesNoResult:
    """Answer a yes/no question with the given odds.

    Args:
        odds: An :class:`Odds` member or its name (e.g. ``"likely"``).
        rng: Random source exposing ``randint``. Inject a seeded
            ``random.Random`` for deterministic results.

    Returns:
        A :class:`YesNoResult` with the roll, answer, and extreme flag.

    Raises:
        ValueError: If ``odds`` is an unknown name.
    """
    if isinstance(odds, str):
        odds = Odds.from_name(odds)
    if rng is None:
        rng = random.Random()

    chance = odds.value
    roll = rng.randint(1, 100)
    answer = Answer.YES if roll <= chance else Answer.NO
    return YesNoResult(
        odds=odds,
        chance=chance,
        roll=roll,
        answer=answer,
        is_extreme=_is_double(roll),
    )


@lru_cache(maxsize=None)
def _load_table(table_name: str) -> tuple[str, tuple[str, ...]]:
    """Load a table's title and entries from ``data/oracles/<name>.json``."""
    path = ORACLE_DATA_DIR / f"{table_name}.json"
    if not path.exists():
        available = ", ".join(list_tables()) or "(none)"
        raise ValueError(
            f"unknown oracle table '{table_name}'. Available: {available}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = tuple(data.get("entries", ()))
    if not entries:
        raise ValueError(f"oracle table '{table_name}' has no entries")
    return data.get("name", table_name), entries


def list_tables() -> list[str]:
    """Return the available oracle table names, sorted."""
    if not ORACLE_DATA_DIR.is_dir():
        return []
    return sorted(p.stem for p in ORACLE_DATA_DIR.glob("*.json"))


def table_title(table_name: str) -> str:
    """Return the human-readable title declared inside a table file."""
    title, _ = _load_table(table_name)
    return title


def draw_from(table_name: str, *, rng: random.Random | None = None) -> str:
    """Return a random entry from the named inspiration table.

    Raises:
        ValueError: If the table is unknown or empty.
    """
    _, entries = _load_table(table_name)
    if rng is None:
        rng = random.Random()
    return entries[rng.randint(0, len(entries) - 1)]


def random_table(*, rng: random.Random | None = None) -> str:
    """Return a random available table name.

    Raises:
        ValueError: If no oracle tables are available.
    """
    tables = list_tables()
    if not tables:
        raise ValueError("no oracle tables available")
    if rng is None:
        rng = random.Random()
    return tables[rng.randint(0, len(tables) - 1)]
