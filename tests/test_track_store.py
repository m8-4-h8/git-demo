"""Tests for the async SQLite track store (shared per chat, not per user)."""

import asyncio

from engine.progress import Rank
from engine.tracks import TrackType, clear_progress, complete, mark_progress
from storage import TrackStore


def _store(tmp_path) -> TrackStore:
    return TrackStore(str(tmp_path / "test.db"))


def _run(coro):
    return asyncio.run(coro)


def test_create_assigns_sequential_ids_per_chat(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        a = await store.create(100, "Duel", TrackType.COMBAT, Rank.FORMIDABLE)
        b = await store.create(100, "Journey", TrackType.JOURNEY, Rank.DANGEROUS)
        return a.id, b.id

    assert _run(scenario()) == (1, 2)


def test_tracks_are_shared_across_the_chat(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.create(100, "Group fight", TrackType.COMBAT, Rank.DANGEROUS)
        # Different chat keeps its own independent numbering.
        other = await store.create(200, "Other chat", TrackType.BOND, Rank.EPIC)
        return [t.id for t in await store.list(100)], other.id

    chat_100_ids, other_id = _run(scenario())
    assert chat_100_ids == [1]
    assert other_id == 1


def test_progress_round_trips(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        track = await store.create(100, "Duel", TrackType.COMBAT, Rank.FORMIDABLE)
        await store.update(100, mark_progress(track, 5))
        return await store.get(100, track.id)

    fetched = _run(scenario())
    assert fetched.progress == 5.0
    assert fetched.track_type is TrackType.COMBAT


def test_completed_tracks_excluded_from_active(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        keep = await store.create(100, "Open", TrackType.JOURNEY, Rank.DANGEROUS)
        done = await store.create(100, "Resolved", TrackType.COMBAT, Rank.EPIC)
        await store.update(100, complete(done))
        return [t.id for t in await store.list(100)], keep.id

    active_ids, keep_id = _run(scenario())
    assert active_ids == [keep_id]


def test_clear_resets_progress(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        track = await store.create(100, "Duel", TrackType.COMBAT, Rank.FORMIDABLE)
        await store.update(100, mark_progress(track, 4))
        track = await store.get(100, track.id)
        await store.update(100, clear_progress(track))
        return await store.get(100, track.id)

    assert _run(scenario()).progress == 0.0
