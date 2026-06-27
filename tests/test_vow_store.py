"""Tests for the async SQLite vow store (keyed per chat + user)."""

import asyncio

from engine.progress import Rank
from engine.vows import forsake, mark_progress
from storage import VowStore


def _store(tmp_path) -> VowStore:
    return VowStore(str(tmp_path / "test.db"))


def _run(coro):
    return asyncio.run(coro)


def test_create_assigns_sequential_ids_per_user(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        a = await store.create(100, 1, "Find the troop", Rank.DANGEROUS)
        b = await store.create(100, 1, "Avenge", Rank.FORMIDABLE)
        return a.id, b.id

    assert _run(scenario()) == (1, 2)


def test_ids_are_independent_across_users(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.create(100, 1, "User1 vow", Rank.EPIC)
        other = await store.create(100, 2, "User2 vow", Rank.EPIC)
        return other.id

    assert _run(scenario()) == 1  # each player's ids start at 1


def test_progress_round_trips(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        vow = await store.create(100, 1, "Quest", Rank.DANGEROUS)
        await store.update(100, 1, mark_progress(vow, 2))
        return await store.get(100, 1, vow.id)

    fetched = _run(scenario())
    assert fetched.progress == 4.0
    assert fetched.rank is Rank.DANGEROUS


def test_list_active_excludes_fulfilled_and_forsaken(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        keep = await store.create(100, 1, "Active", Rank.DANGEROUS)
        drop = await store.create(100, 1, "Abandoned", Rank.EPIC)
        await store.update(100, 1, forsake(drop))
        active = await store.list(100, 1)
        every = await store.list(100, 1, active_only=False)
        return [v.id for v in active], [v.id for v in every], keep.id

    active_ids, all_ids, keep_id = _run(scenario())
    assert active_ids == [keep_id]
    assert all_ids == [1, 2]


def test_get_missing_returns_none(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        return await store.get(1, 2, 99)

    assert _run(scenario()) is None
