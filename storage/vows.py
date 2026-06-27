"""SQLite-backed vow persistence (async, via aiosqlite).

Vows are keyed by ``(chat_id, user_id)`` — each player owns their own vows, even
within a shared co-op chat. Each vow also has a small ``vow_id`` that is
sequential *per player* (1, 2, 3, …) so commands can refer to it (``/vow
progress 1``). Rows map to and from the pure :class:`engine.vows.Vow` model; this
layer holds no game rules.
"""

from __future__ import annotations

import aiosqlite

from engine.progress import Rank
from engine.vows import Vow

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS vows (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    vow_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    rank TEXT NOT NULL,
    progress REAL NOT NULL,
    fulfilled INTEGER NOT NULL,
    forsaken INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id, vow_id)
)
"""


def _row_to_vow(row: tuple) -> Vow:
    vow_id, title, rank, progress, fulfilled, forsaken = row
    return Vow(
        id=vow_id,
        title=title,
        rank=Rank(rank),
        progress=progress,
        fulfilled=bool(fulfilled),
        forsaken=bool(forsaken),
    )


class VowStore:
    """Async SQLite store for vows, keyed by (chat_id, user_id)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the vows table if it does not exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def create(
        self, chat_id: int, user_id: int, title: str, rank: Rank
    ) -> Vow:
        """Create a new vow with the next per-player id and return it."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT COALESCE(MAX(vow_id), 0) + 1 FROM vows "
                "WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            ) as cursor:
                (vow_id,) = await cursor.fetchone()
            vow = Vow(id=vow_id, title=title, rank=rank)
            await db.execute(
                "INSERT INTO vows "
                "(chat_id, user_id, vow_id, title, rank, progress, fulfilled, forsaken) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, vow.id, vow.title, vow.rank.value,
                 vow.progress, int(vow.fulfilled), int(vow.forsaken)),
            )
            await db.commit()
        return vow

    async def get(self, chat_id: int, user_id: int, vow_id: int) -> Vow | None:
        """Return one vow by its per-player id, or None."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT vow_id, title, rank, progress, fulfilled, forsaken "
                "FROM vows WHERE chat_id = ? AND user_id = ? AND vow_id = ?",
                (chat_id, user_id, vow_id),
            ) as cursor:
                row = await cursor.fetchone()
        return _row_to_vow(row) if row is not None else None

    async def list(
        self, chat_id: int, user_id: int, *, active_only: bool = True
    ) -> list[Vow]:
        """Return a player's vows ordered by id.

        By default only active vows (neither fulfilled nor forsaken) are returned.
        """
        query = (
            "SELECT vow_id, title, rank, progress, fulfilled, forsaken "
            "FROM vows WHERE chat_id = ? AND user_id = ?"
        )
        if active_only:
            query += " AND fulfilled = 0 AND forsaken = 0"
        query += " ORDER BY vow_id"
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(query, (chat_id, user_id)) as cursor:
                rows = await cursor.fetchall()
        return [_row_to_vow(row) for row in rows]

    async def update(self, chat_id: int, user_id: int, vow: Vow) -> None:
        """Overwrite a stored vow (matched by its per-player id)."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE vows SET title = ?, rank = ?, progress = ?, "
                "fulfilled = ?, forsaken = ? "
                "WHERE chat_id = ? AND user_id = ? AND vow_id = ?",
                (vow.title, vow.rank.value, vow.progress, int(vow.fulfilled),
                 int(vow.forsaken), chat_id, user_id, vow.id),
            )
            await db.commit()
