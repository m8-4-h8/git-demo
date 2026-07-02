"""Tests for the async multiplayer-session store (tmp SQLite database)."""

import asyncio

from engine.session import (
    SessionPhase,
    advance_turn,
    create_session,
    join_session,
    start_session,
)
from storage import SessionRecord, SessionStore


def _store(tmp_path) -> SessionStore:
    return SessionStore(str(tmp_path / "test.db"))


def _run(coro):
    return asyncio.run(coro)


def _record() -> SessionRecord:
    session = join_session(create_session(1, "Anna", "pw"), 2, "Boris", "pw")
    return SessionRecord(session=session, lang="ru")


def test_get_missing_returns_none(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        return await store.get(100)

    assert _run(scenario()) is None


def test_save_then_get_round_trip(tmp_path) -> None:
    store = _store(tmp_path)
    record = _record()

    async def scenario():
        await store.init()
        await store.save(100, record)
        return await store.get(100)

    loaded = _run(scenario())
    assert loaded == record
    assert loaded.session.phase is SessionPhase.LOBBY
    assert [p.name for p in loaded.session.players] == ["Anna", "Boris"]


def test_save_overwrites_existing_row(tmp_path) -> None:
    store = _store(tmp_path)
    record = _record()

    async def scenario():
        await store.init()
        await store.save(100, record)
        started = advance_turn(start_session(record.session, 1))
        updated = SessionRecord(
            session=started,
            lang="ru",
            lobby_message_id=10,
            setting_message_id=11,
            turn_message_id=12,
            setting_text="A windswept coast.",
        )
        await store.save(100, updated)
        return await store.get(100)

    loaded = _run(scenario())
    assert loaded.session.phase is SessionPhase.ACTIVE
    assert loaded.session.turn_index == 1
    assert loaded.turn_message_id == 12
    assert loaded.setting_text == "A windswept coast."


def test_sessions_are_per_chat(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.save(100, _record())
        return await store.get(200)

    assert _run(scenario()) is None


def test_delete_removes_session(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.save(100, _record())
        await store.delete(100)
        return await store.get(100)

    assert _run(scenario()) is None


def test_with_session_swaps_game_state_only(tmp_path) -> None:
    record = SessionRecord(session=_record().session, lang="en", turn_message_id=5)
    started = start_session(record.session, 1)
    swapped = record.with_session(started)
    assert swapped.session.phase is SessionPhase.ACTIVE
    assert swapped.turn_message_id == 5
    assert swapped.lang == "en"
