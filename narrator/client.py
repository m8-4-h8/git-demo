"""The narrator client: turn a NarratorContext into a short prose paragraph.

Sends an async HTTP request to a local **Ollama** server (default model
``mistral``, endpoint ``/api/chat``). The whole layer fails soft: if the feature
flag is off, the request times out, or Ollama errors, :func:`narrate` returns
``None`` and the bot simply shows no narration.

Configuration (all optional, read from the environment):
- ``NARRATOR_ENABLED`` — turn the narrator on/off.
- ``OLLAMA_BASE_URL`` — Ollama server URL (default ``http://localhost:11434``).
- ``OLLAMA_MODEL`` — model name, overriding :data:`MODEL`.
"""

from __future__ import annotations

import asyncio
import os

from narrator.context import NarratorContext
from narrator.prompts import build_system_prompt, build_user_prompt

MODEL = "mistral"
MAX_TOKENS = 150
TEMPERATURE = 0.8
DEFAULT_TIMEOUT = 8.0
DEFAULT_BASE_URL = "http://localhost:11434"

# Re-exported so callers can `from narrator import NarratorContext`.
__all__ = ["NarratorContext", "narrate", "is_enabled"]

# Lazily-created, reused across calls so we don't build a client per roll.
_default_client = None


def is_enabled() -> bool:
    """True if NARRATOR_ENABLED is set to a truthy value.

    The bot uses this to skip scheduling narration work entirely when off.
    """
    return os.environ.get("NARRATOR_ENABLED", "false").strip().lower() in {
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


async def narrate(
    context: NarratorContext,
    *,
    client: object | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """Return 2-3 sentences of prose for ``context``, or ``None`` on any problem.

    Args:
        context: The mechanical result to describe.
        client: An ``httpx.AsyncClient`` (or compatible mock exposing an async
            ``post``). If ``None``, a shared one is created lazily — keeping
            ``httpx`` the only new dependency.
        timeout: Seconds to wait before giving up.

    Returns:
        The prose string, or ``None`` if the narrator is disabled, times out, or
        the request fails. Never raises.
    """
    if not is_enabled():
        return None

    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": build_system_prompt(context.language)},
            {"role": "user", "content": build_user_prompt(context)},
        ],
        "stream": False,
        "options": {"temperature": TEMPERATURE, "num_predict": MAX_TOKENS},
    }

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
