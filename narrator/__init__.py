"""Optional narrative layer for the Ironsworn bot.

An LLM writes 2-3 sentences of atmospheric prose after a mechanical outcome.
The narrator **describes, never decides**: the ``engine`` is the source of truth
and this layer only visualizes the result. It must never import ``bot`` or
``telegram``; it may import ``engine`` types. The whole layer is gated by the
``NARRATOR_ENABLED`` environment flag and fails soft (returns ``None``) so the
bot keeps working without it.
"""

from narrator.client import NarratorContext, is_enabled, narrate

__all__ = ["NarratorContext", "narrate", "is_enabled"]
