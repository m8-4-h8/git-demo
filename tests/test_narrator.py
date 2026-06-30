"""Tests for the narrator layer — the Ollama HTTP call is always mocked.

We test the control flow (feature flag, timeout, error handling) and the prompt
contents, never the quality of the generated prose.
"""

import asyncio

from engine import Outcome
from narrator import NarratorContext, narrate, narrate_intro
from narrator.prompts import build_intro_prompt, build_user_prompt


class _Response:
    """Mimics the slice of ``httpx.Response`` that narrate() touches."""

    def __init__(self, text: str) -> None:
        self._text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        # Shape of Ollama's POST /api/chat reply.
        return {"message": {"role": "assistant", "content": self._text}}


class FakeClient:
    """Mimics the surface narrate() uses: ``await client.post(url, json=...)``."""

    def __init__(self, *, text="prose", delay=0.0, error=None) -> None:
        self._text = text
        self._delay = delay
        self._error = error

    async def post(self, url, *, json=None, **kwargs):
        if self._error is not None:
            raise self._error
        if self._delay:
            await asyncio.sleep(self._delay)
        return _Response(self._text)


def _ctx(language: str = "en") -> NarratorContext:
    return NarratorContext(
        move_name="action roll (iron)",
        outcome=Outcome.MISS,
        is_match=True,
        stat_used="iron",
        character_name="Aila",
        delta={"health": -1},
        active_vow="Avenge the village",
        active_track="Combat with the bandits",
        language=language,
    )


def _run(coro):
    return asyncio.run(coro)


def test_disabled_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_ENABLED", "false")
    # Even with a working client, the flag short-circuits to None.
    assert _run(narrate(_ctx(), client=FakeClient(text="x"))) is None


def test_enabled_returns_prose(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_ENABLED", "true")
    result = _run(narrate(_ctx(), client=FakeClient(text="The blow misses.")))
    assert result == "The blow misses."


def test_timeout_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_ENABLED", "true")
    slow = FakeClient(text="too slow", delay=0.5)
    assert _run(narrate(_ctx(), client=slow, timeout=0.01)) is None


def test_api_error_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_ENABLED", "true")
    boom = FakeClient(error=RuntimeError("api down"))
    assert _run(narrate(_ctx(), client=boom)) is None


def test_empty_text_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_ENABLED", "true")
    assert _run(narrate(_ctx(), client=FakeClient(text="   "))) is None


def test_user_prompt_handles_missing_character_and_optionals() -> None:
    # tracks are group-level: no character, no vow.
    ctx = NarratorContext(
        move_name="resolve the encounter",
        outcome=Outcome.STRONG,
        is_match=False,
        stat_used="",
        active_track="Combat with the bandits",
    )
    prompt = build_user_prompt(ctx)
    assert "the hero" in prompt          # character fallback
    assert "Active vow: none" in prompt
    assert "Combat with the bandits" in prompt


def test_intro_disabled_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_ENABLED", "false")
    assert _run(narrate_intro("Grim", "Warrior", "en",
                              client=FakeClient(text="x"))) is None


def test_intro_returns_line_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_ENABLED", "true")
    result = _run(narrate_intro("Grim", "Warrior", "en",
                                client=FakeClient(text="So begins the saga.")))
    assert result == "So begins the saga."


def test_intro_prompt_names_hero_and_path() -> None:
    prompt = build_intro_prompt("Grim", "Warrior", "ru")
    assert "Grim" in prompt
    assert "Warrior" in prompt
    assert "Russian" in prompt


def test_user_prompt_contains_all_context_fields() -> None:
    prompt = build_user_prompt(_ctx(language="ru"))
    assert "action roll (iron)" in prompt
    assert "iron" in prompt
    assert "miss" in prompt            # outcome
    assert "yes" in prompt             # match flag
    assert "health -1" in prompt       # delta
    assert "Aila" in prompt            # character
    assert "Avenge the village" in prompt
    assert "Combat with the bandits" in prompt
    assert "Russian" in prompt         # response language
