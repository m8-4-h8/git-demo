"""Shared aiosqlite connection helper.

Opens a connection with a sane ``busy_timeout`` so concurrent writes from
several co-op players wait briefly for the lock instead of failing immediately
with "database is locked".
"""

from __future__ import annotations

import aiosqlite

# How long a blocked write waits for the lock before erroring (milliseconds).
BUSY_TIMEOUT_MS = 5000


def connect(db_path: str) -> aiosqlite.Connection:
    """Return an aiosqlite connection context manager with busy_timeout set.

    Usage mirrors ``aiosqlite.connect`` — ``async with connect(path) as db:`` —
    but the connection has ``PRAGMA busy_timeout`` applied on entry.
    """
    return _Connect(db_path)


class _Connect:
    """Async context manager that opens a connection and sets busy_timeout."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._ctx = aiosqlite.connect(db_path)

    async def __aenter__(self) -> aiosqlite.Connection:
        db = await self._ctx.__aenter__()
        await db.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        return db

    async def __aexit__(self, *exc) -> None:
        await self._ctx.__aexit__(*exc)
