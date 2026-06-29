"""The data the narrator describes — a frozen snapshot of one mechanical result.

Kept in its own module so both ``prompts`` and ``client`` can import it without
a cycle. Imports only ``engine`` types (allowed); never ``bot``/``telegram``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine import Outcome


@dataclass(frozen=True)
class NarratorContext:
    """Everything the narrator needs to describe (not decide) an outcome."""

    move_name: str
    outcome: Outcome
    is_match: bool
    stat_used: str
    character_name: str = ""
    delta: dict[str, int] = field(default_factory=dict)
    active_vow: str | None = None
    active_track: str | None = None
    language: str = "en"
