"""Persistence layer for the Ironsworn bot.

Keeps storage concerns out of the pure game ``engine``. This package may import
``engine`` (e.g. the :class:`~engine.character.Character` model), but ``engine``
must never import ``storage``.
"""

from storage.preferences import PreferenceStore
from storage.store import CharacterExists, CharacterStore
from storage.tracks import TrackStore
from storage.vows import VowStore

__all__ = [
    "CharacterStore",
    "CharacterExists",
    "PreferenceStore",
    "VowStore",
    "TrackStore",
]
