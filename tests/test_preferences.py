"""Tests for the async preference store."""

import asyncio

from storage import PreferenceStore


def _store(tmp_path) -> PreferenceStore:
    return PreferenceStore(str(tmp_path / "test.db"))


def _run(coro):
    return asyncio.run(coro)


def test_get_missing_returns_none(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        return await store.get_language(1, 2)

    assert _run(scenario()) is None


def test_set_then_get(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.set_language(10, 20, "ru")
        return await store.get_language(10, 20)

    assert _run(scenario()) == "ru"


def test_set_overwrites(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.set_language(10, 20, "ru")
        await store.set_language(10, 20, "en")
        return await store.get_language(10, 20)

    assert _run(scenario()) == "en"


def test_per_user_isolation(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.set_language(100, 1, "ru")
        await store.set_language(100, 2, "en")
        return (
            await store.get_language(100, 1),
            await store.get_language(100, 2),
        )

    assert _run(scenario()) == ("ru", "en")
