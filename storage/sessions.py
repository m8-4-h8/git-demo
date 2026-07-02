"""SQLite-backed multiplayer-session persistence (async, via aiosqlite).

One session per chat, so rows are keyed by ``chat_id`` only. The store maps
rows to and from the pure :class:`engine.session.GameSession` model, wrapped in
a :class:`SessionRecord` that adds the frontend bookkeeping the bot needs (the
shared language plus the ids of the edit-in-place lobby/setting/turn messages
and the generated setting text). No game rules live here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from engine.session import GameSession, SessionPhase, SessionPlayer
from storage._db import connect

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    chat_id INTEGER NOT NULL,
    creator_id INTEGER NOT NULL,
    password TEXT NOT NULL,
    phase TEXT NOT NULL,
    players TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    lang TEXT NOT NULL DEFAULT 'en',
    lobby_message_id INTEGER,
    setting_message_id INTEGER,
    turn_message_id INTEGER,
    setting_text TEXT,
    PRIMARY KEY (chat_id)
)
"""

_COLUMNS = (
    "creator_id", "password", "phase", "players", "turn_index", "lang",
    "lobby_message_id", "setting_message_id", "turn_message_id", "setting_text",
)


@dataclass(frozen=True)
class SessionRecord:
    """A persisted session: the pure game state plus frontend bookkeeping."""

    session: GameSession
    lang: str = "en"
    lobby_message_id: int | None = None
    setting_message_id: int | None = None
    turn_message_id: int | None = None
    setting_text: str | None = None

    def with_session(self, session: GameSession) -> SessionRecord:
        """Return a copy of the record carrying an updated game state."""
        return replace(self, session=session)


def _to_row(record: SessionRecord) -> tuple:
    session = record.session
    players = json.dumps([[p.user_id, p.name] for p in session.players])
    return (
        session.creator_id, session.password, session.phase.value, players,
        session.turn_index, record.lang, record.lobby_message_id,
        record.setting_message_id, record.turn_message_id, record.setting_text,
    )


def _from_row(row) -> SessionRecord:
    (creator_id, password, phase, players_json, turn_index, lang,
     lobby_message_id, setting_message_id, turn_message_id, setting_text) = row
    players = tuple(
        SessionPlayer(int(user_id), name) for user_id, name in json.loads(players_json)
    )
    session = GameSession(
        creator_id=creator_id,
        password=password,
        phase=SessionPhase(phase),
        players=players,
        turn_index=turn_index,
    )
    return SessionRecord(
        session=session,
        lang=lang,
        lobby_message_id=lobby_message_id,
        setting_message_id=setting_message_id,
        turn_message_id=turn_message_id,
        setting_text=setting_text,
    )


class SessionStore:
    """Async SQLite store for multiplayer sessions, keyed by chat_id."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the sessions table if it does not exist."""
        async with connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def get(self, chat_id: int) -> SessionRecord | None:
        """Return the chat's session record, or None if there is no session."""
        columns = ", ".join(_COLUMNS)
        async with connect(self._db_path) as db:
            async with db.execute(
                f"SELECT {columns} FROM sessions WHERE chat_id = ?", (chat_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return _from_row(row) if row is not None else None

    async def save(self, chat_id: int, record: SessionRecord) -> None:
        """Insert or replace the chat's session record."""
        assignments = ", ".join(f"{name} = excluded.{name}" for name in _COLUMNS)
        placeholders = ", ".join("?" for _ in (*_COLUMNS, "chat_id"))
        async with connect(self._db_path) as db:
            await db.execute(
                f"INSERT INTO sessions (chat_id, {', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(chat_id) DO UPDATE SET {assignments}",
                (chat_id, *_to_row(record)),
            )
            await db.commit()

    async def delete(self, chat_id: int) -> None:
        """Remove the chat's session (the party dissolved or the game ended)."""
        async with connect(self._db_path) as db:
            await db.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
            await db.commit()
