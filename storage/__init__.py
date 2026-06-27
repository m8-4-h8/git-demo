"""Persistence layer for the Ironsworn bot.

Keeps storage concerns out of the pure game ``engine``. This package may import
``engine`` (e.g. the :class:`~engine.character.Character` model), but ``engine``
must never import ``storage``.
"""

from storage.store import CharacterExists, CharacterStore

__all__ = ["CharacterStore", "CharacterExists"]
