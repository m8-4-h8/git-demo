"""The AI Game Master client.

Sends async HTTP requests to a local **Ollama** server (default model
``mistral``, endpoint ``/api/chat``) to propose scenarios and describe the
evolving world. It generates narrative only — it never resolves mechanics. The
whole layer is gated by ``GM_ENABLED`` and fails soft: on a disabled flag,
timeout, or HTTP error every function returns ``None`` and never raises.

Configuration (all optional, read from the environment):
- ``GM_ENABLED`` — turn the Game Master on/off.
- ``OLLAMA_BASE_URL`` — Ollama server URL (default ``http://localhost:11434``).
- ``OLLAMA_MODEL`` — model name, overriding :data:`MODEL`.
"""

from __future__ import annotations

import asyncio
import json
import os

from gm.context import GMContext, ScenarioOption
from gm.prompts import (
    build_complication_prompt,
    build_scenario_prompt,
    build_scene_prompt,
    build_system_prompt,
)

MODEL = "mistral"
TEMPERATURE = 0.8
SCENE_MAX_TOKENS = 300
SCENARIO_MAX_TOKENS = 800
DEFAULT_TIMEOUT = 10.0
DEFAULT_BASE_URL = "http://localhost:11434"

__all__ = [
    "generate_scenario_options",
    "generate_scene",
    "generate_complication",
    "is_enabled",
]

_default_client = None


def is_enabled() -> bool:
    """True if GM_ENABLED is set to a truthy value."""
    return os.environ.get("GM_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _base_url() -> str:
    """The Ollama base URL, configurable via ``OLLAMA_BASE_URL``."""
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _model() -> str:
    """The Ollama model name, configurable via ``OLLAMA_MODEL``."""
    return os.environ.get("OLLAMA_MODEL", MODEL)


def _get_client():
    """Return a shared ``httpx.AsyncClient``, building it on first use."""
    global _default_client
    if _default_client is None:
        import httpx  # lazy: optional dependency

        _default_client = httpx.AsyncClient()
    return _default_client


def _extract_text(data: object) -> str:
    """Pull the assistant text out of an Ollama ``/api/chat`` response body."""
    if not isinstance(data, dict):
        return ""
    message = data.get("message") or {}
    return (message.get("content") or "").strip()


async def _complete(
    system: str,
    user: str,
    *,
    client,
    timeout: float,
    max_tokens: int,
    json_mode: bool = False,
) -> str | None:
    """Run one Ollama chat request, returning the text or None on any problem.

    With ``json_mode`` the request asks Ollama to constrain its output to valid
    JSON (Ollama's ``format: "json"``); callers then parse the text.
    """
    if not is_enabled():
        return None
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": TEMPERATURE, "num_predict": max_tokens},
    }
    if json_mode:
        payload["format"] = "json"
    try:
        if client is None:
            client = _get_client()
        response = await asyncio.wait_for(
            client.post(f"{_base_url()}/api/chat", json=payload), timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None
    return _extract_text(data) or None


async def generate_scenario_options(
    language: str, *, client=None, timeout: float = DEFAULT_TIMEOUT
) -> list[ScenarioOption] | None:
    """Return exactly three scenario options, or None on any problem."""
    text = await _complete(
        build_system_prompt(language),
        build_scenario_prompt(language),
        client=client,
        timeout=timeout,
        max_tokens=SCENARIO_MAX_TOKENS,
        json_mode=True,
    )
    if text is None:
        return None
    try:
        data = json.loads(text)
        items = data["scenarios"]
        options = [
            ScenarioOption(
                title=item["title"],
                goal=item["goal"],
                opening_scene=item["opening_scene"],
            )
            for item in items
        ]
    except (ValueError, KeyError, TypeError):
        return None
    return options if len(options) == 3 else None


async def generate_scene(
    context: GMContext, last_move_result: str, *, client=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """Narrate what the world does next after a player's action, or None."""
    return await _complete(
        build_system_prompt(context.language),
        build_scene_prompt(context, last_move_result),
        client=client,
        timeout=timeout,
        max_tokens=SCENE_MAX_TOKENS,
    )


async def generate_complication(
    context: GMContext, *, client=None, timeout: float = DEFAULT_TIMEOUT
) -> str | None:
    """Introduce a complication/turn (used on a miss), or None."""
    return await _complete(
        build_system_prompt(context.language),
        build_complication_prompt(context),
        client=client,
        timeout=timeout,
        max_tokens=SCENE_MAX_TOKENS,
    )
