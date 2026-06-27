"""Per-player UI preferences (currently: language), persisted in SQLite.

Like :class:`~storage.store.CharacterStore`, preferences are keyed by
``(chat_id, user_id)``. This is a frontend/persistence concern and holds no game
logic, so it lives in ``storage`` rather than ``engine``.
"""

from __future__ import annotations

import aiosqlite

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS preferences (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    PRIMARY KEY (chat_id, user_id)
)
"""


class PreferenceStore:
    """Async SQLite store for per-player preferences."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the preferences table if it does not exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def get_language(self, chat_id: int, user_id: int) -> str | None:
        """Return the stored language for (chat, user), or None if unset."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT language FROM preferences "
                "WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row is not None else None

    async def set_language(
        self, chat_id: int, user_id: int, language: str
    ) -> None:
        """Store the language for (chat, user), inserting or updating."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO preferences (chat_id, user_id, language) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET language = excluded.language",
                (chat_id, user_id, language),
            )
            await db.commit()
