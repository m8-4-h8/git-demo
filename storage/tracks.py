"""SQLite-backed progress-track persistence (async, via aiosqlite).

Unlike characters and vows, progress tracks are keyed by ``chat_id`` *only*:
they are shared by the whole co-op group (a combat or journey the party faces
together), not owned per player. Each track has a ``track_id`` that is sequential
per chat so commands can refer to it (``/track hit 1``). Rows map to and from the
pure :class:`engine.tracks.Track` model; this layer holds no game rules.
"""

from __future__ import annotations

import aiosqlite

from engine.progress import Rank
from engine.tracks import Track, TrackType
from storage._db import connect

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tracks (
    chat_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    track_type TEXT NOT NULL,
    rank TEXT NOT NULL,
    progress REAL NOT NULL,
    completed INTEGER NOT NULL,
    PRIMARY KEY (chat_id, track_id)
)
"""


def _row_to_track(row: tuple) -> Track:
    track_id, title, track_type, rank, progress, completed = row
    return Track(
        id=track_id,
        title=title,
        track_type=TrackType(track_type),
        rank=Rank(rank),
        progress=progress,
        completed=bool(completed),
    )


class TrackStore:
    """Async SQLite store for progress tracks, shared per chat_id."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the tracks table if it does not exist."""
        async with connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def create(
        self, chat_id: int, title: str, track_type: TrackType, rank: Rank
    ) -> Track:
        """Create a new track with the next per-chat id and return it.

        If two creates race and collide on the primary key, retry once with a
        freshly computed id.
        """
        for attempt in range(2):
            try:
                return await self._insert(chat_id, title, track_type, rank)
            except aiosqlite.IntegrityError:
                if attempt == 1:
                    raise

    async def _insert(
        self, chat_id: int, title: str, track_type: TrackType, rank: Rank
    ) -> Track:
        async with connect(self._db_path) as db:
            async with db.execute(
                "SELECT COALESCE(MAX(track_id), 0) + 1 FROM tracks "
                "WHERE chat_id = ?",
                (chat_id,),
            ) as cursor:
                (track_id,) = await cursor.fetchone()
            track = Track(id=track_id, title=title, track_type=track_type, rank=rank)
            await db.execute(
                "INSERT INTO tracks "
                "(chat_id, track_id, title, track_type, rank, progress, completed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, track.id, track.title, track.track_type.value,
                 track.rank.value, track.progress, int(track.completed)),
            )
            await db.commit()
        return track

    async def get(self, chat_id: int, track_id: int) -> Track | None:
        """Return one track by its per-chat id, or None."""
        async with connect(self._db_path) as db:
            async with db.execute(
                "SELECT track_id, title, track_type, rank, progress, completed "
                "FROM tracks WHERE chat_id = ? AND track_id = ?",
                (chat_id, track_id),
            ) as cursor:
                row = await cursor.fetchone()
        return _row_to_track(row) if row is not None else None

    async def list(self, chat_id: int, *, active_only: bool = True) -> list[Track]:
        """Return the chat's tracks ordered by id (active i.e. not completed by default)."""
        query = (
            "SELECT track_id, title, track_type, rank, progress, completed "
            "FROM tracks WHERE chat_id = ?"
        )
        if active_only:
            query += " AND completed = 0"
        query += " ORDER BY track_id"
        async with connect(self._db_path) as db:
            async with db.execute(query, (chat_id,)) as cursor:
                rows = await cursor.fetchall()
        return [_row_to_track(row) for row in rows]

    async def update(self, chat_id: int, track: Track) -> None:
        """Overwrite a stored track (matched by its per-chat id)."""
        async with connect(self._db_path) as db:
            await db.execute(
                "UPDATE tracks SET title = ?, track_type = ?, rank = ?, "
                "progress = ?, completed = ? "
                "WHERE chat_id = ? AND track_id = ?",
                (track.title, track.track_type.value, track.rank.value,
                 track.progress, int(track.completed), chat_id, track.id),
            )
            await db.commit()
