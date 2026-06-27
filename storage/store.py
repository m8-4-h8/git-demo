"""SQLite-backed character persistence (async, via aiosqlite).

A character is keyed by ``(chat_id, user_id)`` so several players can keep their
own characters in a single group chat (co-op). The store maps rows to and from
the pure :class:`engine.character.Character` model; it holds no game rules.
"""

from __future__ import annotations

from dataclasses import astuple, fields

import aiosqlite

from engine.character import Character

# Character field names, in declaration order, used to build SQL and map rows.
_FIELDS = tuple(f.name for f in fields(Character))
_KEY_COLUMNS = ("chat_id", "user_id")

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS characters (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    edge INTEGER NOT NULL,
    heart INTEGER NOT NULL,
    iron INTEGER NOT NULL,
    shadow INTEGER NOT NULL,
    wits INTEGER NOT NULL,
    health INTEGER NOT NULL,
    spirit INTEGER NOT NULL,
    supply INTEGER NOT NULL,
    momentum INTEGER NOT NULL,
    PRIMARY KEY ({", ".join(_KEY_COLUMNS)})
)
"""


class CharacterExists(Exception):
    """Raised when creating a character that already exists for (chat, user)."""


class CharacterStore:
    """Async SQLite store for characters, keyed by (chat_id, user_id)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the characters table if it does not exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def get(self, chat_id: int, user_id: int) -> Character | None:
        """Return the character for (chat, user), or None if there is none."""
        columns = ", ".join(_FIELDS)
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                f"SELECT {columns} FROM characters WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
        return Character(*row) if row is not None else None

    async def create(
        self, chat_id: int, user_id: int, character: Character
    ) -> None:
        """Insert a new character.

        Raises:
            CharacterExists: If one already exists for (chat, user).
        """
        all_columns = (*_KEY_COLUMNS, *_FIELDS)
        placeholders = ", ".join("?" for _ in all_columns)
        values = (chat_id, user_id, *astuple(character))
        async with aiosqlite.connect(self._db_path) as db:
            try:
                await db.execute(
                    f"INSERT INTO characters ({', '.join(all_columns)}) "
                    f"VALUES ({placeholders})",
                    values,
                )
            except aiosqlite.IntegrityError as error:
                raise CharacterExists(
                    f"a character already exists for chat {chat_id}, user {user_id}"
                ) from error
            await db.commit()

    async def update(
        self, chat_id: int, user_id: int, character: Character
    ) -> None:
        """Overwrite the stored character for (chat, user)."""
        assignments = ", ".join(f"{name} = ?" for name in _FIELDS)
        values = (*astuple(character), chat_id, user_id)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                f"UPDATE characters SET {assignments} "
                "WHERE chat_id = ? AND user_id = ?",
                values,
            )
            await db.commit()
