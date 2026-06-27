"""Frontend-independent game core for the Ironsworn bot.

This package holds ALL game logic. It must never import anything from
``telegram`` (or any other frontend). Everything here is composed of pure,
fully unit-testable functions so the engine can be driven from a Telegram bot,
a CLI, tests, or any future frontend without modification.
"""

from engine.core import greeting
from engine.rolls import ActionRoll, Outcome, roll_action

__all__ = ["greeting", "roll_action", "ActionRoll", "Outcome"]
