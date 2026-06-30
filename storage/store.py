"""SQLite-backed character persistence (async, via aiosqlite).

A character is keyed by ``(chat_id, user_id)`` so several players can keep their
own characters in a single group chat (co-op). The store maps rows to and from
the pure :class:`engine.character.Character` model; it holds no game rules.
"""

from __future__ import annotations

import json
from dataclasses import fields

import aiosqlite

from engine.character import Character
from storage._db import connect

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
    items TEXT NOT NULL DEFAULT '[]',
    background TEXT,
    archetype TEXT,
    PRIMARY KEY ({", ".join(_KEY_COLUMNS)})
)
"""

# Columns added after the first release; (name, DDL) for additive migrations.
_MIGRATIONS = (
    ("items", "TEXT NOT NULL DEFAULT '[]'"),
    ("background", "TEXT"),
    ("archetype", "TEXT"),
)


def _to_row(character: Character) -> tuple:
    """Map a Character to a value tuple in ``_FIELDS`` order (items as JSON)."""
    values = []
    for name in _FIELDS:
        value = getattr(character, name)
        if name == "items":
            value = json.dumps(value)
        values.append(value)
    return tuple(values)


def _from_row(row) -> Character:
    """Build a Character from a row, decoding ``items`` and defaulting old NULLs."""
    data = dict(zip(_FIELDS, row))
    raw_items = data.get("items")
    data["items"] = json.loads(raw_items) if raw_items else []
    return Character(**data)


class CharacterExists(Exception):
    """Raised when creating a character that already exists for (chat, user)."""


class CharacterStore:
    """Async SQLite store for characters, keyed by (chat_id, user_id)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the characters table, migrating older schemas additively."""
        async with connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await self._migrate(db)
            await db.commit()

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        """Add any columns missing from an older ``characters`` table."""
        async with db.execute("PRAGMA table_info(characters)") as cursor:
            existing = {row[1] for row in await cursor.fetchall()}
        for column, ddl in _MIGRATIONS:
            if column not in existing:
                await db.execute(
                    f"ALTER TABLE characters ADD COLUMN {column} {ddl}"
                )

    async def get(self, chat_id: int, user_id: int) -> Character | None:
        """Return the character for (chat, user), or None if there is none."""
        columns = ", ".join(_FIELDS)
        async with connect(self._db_path) as db:
            async with db.execute(
                f"SELECT {columns} FROM characters WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
        return _from_row(row) if row is not None else None

    async def create(
        self, chat_id: int, user_id: int, character: Character
    ) -> None:
        """Insert a new character.

        Raises:
            CharacterExists: If one already exists for (chat, user).
        """
        all_columns = (*_KEY_COLUMNS, *_FIELDS)
        placeholders = ", ".join("?" for _ in all_columns)
        values = (chat_id, user_id, *_to_row(character))
        async with connect(self._db_path) as db:
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

    async def list(self, chat_id: int) -> list[Character]:
        """Return all characters in a chat (the co-op party), ordered by user."""
        columns = ", ".join(_FIELDS)
        async with connect(self._db_path) as db:
            async with db.execute(
                f"SELECT {columns} FROM characters WHERE chat_id = ? ORDER BY user_id",
                (chat_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [_from_row(row) for row in rows]

    async def update(
        self, chat_id: int, user_id: int, character: Character
    ) -> None:
        """Overwrite the stored character for (chat, user)."""
        assignments = ", ".join(f"{name} = ?" for name in _FIELDS)
        values = (*_to_row(character), chat_id, user_id)
        async with connect(self._db_path) as db:
            await db.execute(
                f"UPDATE characters SET {assignments} "
                "WHERE chat_id = ? AND user_id = ?",
                values,
            )
            await db.commit()
