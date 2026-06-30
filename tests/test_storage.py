"""Tests for the async SQLite character store.

Async store methods are driven from synchronous tests with ``asyncio.run`` so
no extra pytest plugin is required. Each test uses an isolated db file under
``tmp_path``.
"""

import asyncio
import sqlite3

import pytest

from engine.character import add_item, new_character, set_background, set_field
from storage import CharacterExists, CharacterStore


def _store(tmp_path) -> CharacterStore:
    return CharacterStore(str(tmp_path / "test.db"))


def _run(coro):
    return asyncio.run(coro)


def _hero(name: str = "Hero") -> object:
    return new_character(name, edge=1, heart=2, iron=3, shadow=1, wits=2)


def test_create_and_get_round_trip(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.create(10, 20, _hero("Aila"))
        return await store.get(10, 20)

    fetched = _run(scenario())
    assert fetched is not None
    assert fetched.name == "Aila"
    assert fetched.iron == 3
    assert fetched.momentum == 2


def test_get_missing_returns_none(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        return await store.get(1, 2)

    assert _run(scenario()) is None


def test_update_persists_changes(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.create(10, 20, _hero())
        character = await store.get(10, 20)
        character = set_field(character, "supply", 2)
        character = set_field(character, "momentum", -3)
        await store.update(10, 20, character)
        return await store.get(10, 20)

    updated = _run(scenario())
    assert updated.supply == 2
    assert updated.momentum == -3


def test_duplicate_create_raises(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.create(10, 20, _hero())
        await store.create(10, 20, _hero("Other"))

    with pytest.raises(CharacterExists):
        _run(scenario())


def test_coop_two_users_same_chat_are_independent(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.create(100, 1, _hero("Alice"))
        await store.create(100, 2, _hero("Bob"))
        # change only Bob
        bob = await store.get(100, 2)
        await store.update(100, 2, set_field(bob, "health", 1))
        return await store.get(100, 1), await store.get(100, 2)

    alice, bob = _run(scenario())
    assert alice.name == "Alice"
    assert alice.health == 5
    assert bob.name == "Bob"
    assert bob.health == 1


# --- inventory & background persistence --------------------------------------


def test_items_and_background_round_trip(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        hero = add_item(_hero("Aila"), "Old dagger")
        hero = add_item(hero, "Lockpicks")
        hero = set_background(hero, "Born in the ashen wastes.")
        await store.create(10, 20, hero)
        return await store.get(10, 20)

    fetched = _run(scenario())
    assert fetched.items == ["Old dagger", "Lockpicks"]
    assert fetched.background == "Born in the ashen wastes."


def test_update_persists_inventory(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.create(10, 20, _hero())
        hero = await store.get(10, 20)
        await store.update(10, 20, add_item(hero, "Torch"))
        return await store.get(10, 20)

    assert _run(scenario()).items == ["Torch"]


def test_old_schema_migrates_with_defaults(tmp_path) -> None:
    """A pre-existing DB without items/background must load with safe defaults."""
    db_path = str(tmp_path / "legacy.db")
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        """CREATE TABLE characters (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL,
            edge INTEGER, heart INTEGER, iron INTEGER, shadow INTEGER, wits INTEGER,
            health INTEGER, spirit INTEGER, supply INTEGER, momentum INTEGER,
            PRIMARY KEY (chat_id, user_id))"""
    )
    legacy.execute(
        "INSERT INTO characters VALUES (1, 1, 'Veteran', 1, 2, 3, 1, 2, 5, 5, 5, 2)"
    )
    legacy.commit()
    legacy.close()

    store = CharacterStore(db_path)

    async def scenario():
        await store.init()  # migrates additively, must not break the old row
        return await store.get(1, 1)

    fetched = _run(scenario())
    assert fetched.name == "Veteran"
    assert fetched.items == []
    assert fetched.background is None
