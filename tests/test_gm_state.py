"""Tests for the async GM-state store."""

import asyncio

from storage import GMStateStore


def _store(tmp_path) -> GMStateStore:
    return GMStateStore(str(tmp_path / "test.db"))


def _run(coro):
    return asyncio.run(coro)


def test_get_missing_returns_none(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        return await store.get(100)

    assert _run(scenario()) is None


def test_save_then_get_round_trip(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.save(
            100,
            scenario_title="Slay the dragon",
            scenario_goal="slay Kor'tan",
            current_scene="A cave yawns ahead.",
            scene_history=["s1", "s2"],
            npc_memory={"Bren": "a scarred smuggler"},
        )
        return await store.get(100)

    state = _run(scenario())
    assert state["scenario_title"] == "Slay the dragon"
    assert state["scene_history"] == ["s1", "s2"]
    assert state["npc_memory"] == {"Bren": "a scarred smuggler"}


def test_save_overwrites(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.save(100, scenario_title="A", scenario_goal="a",
                         current_scene="one", scene_history=[], npc_memory={})
        await store.save(100, scenario_title="A", scenario_goal="a",
                         current_scene="two", scene_history=["one"], npc_memory={})
        return await store.get(100)

    state = _run(scenario())
    assert state["current_scene"] == "two"
    assert state["scene_history"] == ["one"]


def test_delete_clears_campaign(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.save(100, scenario_title="A", scenario_goal="a",
                         current_scene="one", scene_history=[], npc_memory={})
        await store.delete(100)
        return await store.get(100)

    assert _run(scenario()) is None


def test_per_chat_isolation(tmp_path) -> None:
    store = _store(tmp_path)

    async def scenario():
        await store.init()
        await store.save(1, scenario_title="One", scenario_goal="g1",
                         current_scene="c1", scene_history=[], npc_memory={})
        await store.save(2, scenario_title="Two", scenario_goal="g2",
                         current_scene="c2", scene_history=[], npc_memory={})
        return await store.get(1), await store.get(2)

    a, b = _run(scenario())
    assert a["scenario_title"] == "One"
    assert b["scenario_title"] == "Two"
