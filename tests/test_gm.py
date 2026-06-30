"""Tests for the AI Game Master layer — the Ollama HTTP call is always mocked.

We test control flow (flag, timeout, error handling, exactly-3 parsing) and the
pure helpers, never the quality of generated prose.
"""

import asyncio
import json

from gm import (
    GMContext,
    ScenarioOption,
    generate_complication,
    generate_scenario_options,
    generate_scene,
    push_scene,
)
from gm.context import SCENE_HISTORY_LIMIT, from_state_dict, to_state_dict


class _Response:
    """Mimics the slice of ``httpx.Response`` the GM client touches."""

    def __init__(self, text: str) -> None:
        self._text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        # Shape of Ollama's POST /api/chat reply.
        return {"message": {"role": "assistant", "content": self._text}}


class FakeClient:
    """Mimics the surface the GM client uses: ``await client.post(url, json=...)``."""

    def __init__(self, *, text="scene", delay=0.0, error=None) -> None:
        self._text, self._delay, self._error = text, delay, error

    async def post(self, url, *, json=None, **kwargs):
        if self._error is not None:
            raise self._error
        if self._delay:
            await asyncio.sleep(self._delay)
        return _Response(self._text)


def _scenarios_json(n: int) -> str:
    return json.dumps({
        "scenarios": [
            {"title": f"T{i}", "goal": f"goal {i}", "opening_scene": f"scene {i}"}
            for i in range(n)
        ]
    })


def _ctx() -> GMContext:
    return GMContext(
        scenario_title="Slay the dragon",
        scenario_goal="slay Kor'tan",
        current_scene="A cave yawns ahead.",
        scene_history=["s1"],
        active_characters=["Aila"],
        active_vows=["slay Kor'tan"],
        npc_memory={"Bren": "a scarred smuggler"},
        language="en",
    )


def _run(coro):
    return asyncio.run(coro)


# --- scenario options ---


def test_scenario_options_returns_exactly_three(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "true")
    options = _run(generate_scenario_options("en", client=FakeClient(text=_scenarios_json(3))))
    assert options is not None
    assert len(options) == 3
    assert all(isinstance(o, ScenarioOption) for o in options)
    assert options[0].title == "T0"


def test_scenario_options_non_three_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "true")
    assert _run(generate_scenario_options("en", client=FakeClient(text=_scenarios_json(2)))) is None


def test_scenario_options_disabled_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "false")
    assert _run(generate_scenario_options("en", client=FakeClient(text=_scenarios_json(3)))) is None


def test_scenario_options_bad_json_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "true")
    assert _run(generate_scenario_options("en", client=FakeClient(text="not json"))) is None


# --- scene / complication ---


def test_generate_scene_returns_text(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "true")
    out = _run(generate_scene(_ctx(), "Aila acted with iron — weak hit",
                              client=FakeClient(text="A shadow stirs.")))
    assert out == "A shadow stirs."


def test_generate_scene_timeout_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "true")
    out = _run(generate_scene(_ctx(), "x",
                              client=FakeClient(text="slow", delay=0.5), timeout=0.01))
    assert out is None


def test_generate_complication_error_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "true")
    out = _run(generate_complication(_ctx(), client=FakeClient(error=RuntimeError("boom"))))
    assert out is None


def test_generate_scene_disabled_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("GM_ENABLED", "false")
    out = _run(generate_scene(_ctx(), "x", client=FakeClient(text="nope")))
    assert out is None


# --- pure helpers ---


def test_push_scene_caps_at_limit() -> None:
    history: list[str] = []
    for i in range(SCENE_HISTORY_LIMIT + 4):
        history = push_scene(history, f"scene {i}")
    assert len(history) == SCENE_HISTORY_LIMIT
    # keeps the most recent
    assert history[-1] == f"scene {SCENE_HISTORY_LIMIT + 3}"
    assert history[0] == "scene 4"


def test_state_dict_round_trips() -> None:
    state = to_state_dict(
        scenario_title="T", scenario_goal="G", current_scene="C",
        scene_history=["a", "b"], npc_memory={"n": "d"},
    )
    restored = from_state_dict(json.loads(json.dumps(state)))
    assert restored == state


def test_state_dict_caps_history() -> None:
    long_history = [f"s{i}" for i in range(20)]
    state = to_state_dict(
        scenario_title="T", scenario_goal="G", current_scene="C",
        scene_history=long_history, npc_memory={},
    )
    assert len(state["scene_history"]) == SCENE_HISTORY_LIMIT
    assert state["scene_history"][-1] == "s19"
