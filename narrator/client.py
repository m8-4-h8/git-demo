"""The narrator client: turn a NarratorContext into a short prose paragraph.

Calls the Anthropic API (``claude-sonnet-4-6``) asynchronously. The whole layer
fails soft: if the feature flag is off, the request times out, or the API errors,
:func:`narrate` returns ``None`` and the bot simply shows no narration.
"""

from __future__ import annotations

import asyncio
import os

from narrator.context import NarratorContext
from narrator.prompts import build_system_prompt, build_user_prompt

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 150
DEFAULT_TIMEOUT = 8.0

# Re-exported so callers can `from narrator import NarratorContext`.
__all__ = ["NarratorContext", "narrate"]


def _enabled() -> bool:
    """True if NARRATOR_ENABLED is set to a truthy value."""
    return os.environ.get("NARRATOR_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _extract_text(response: object) -> str:
    """Pull the first text block out of a Messages API response."""
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return (getattr(block, "text", "") or "").strip()
    return ""


async def narrate(
    context: NarratorContext,
    *,
    client: object | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """Return 2-3 sentences of prose for ``context``, or ``None`` on any problem.

    Args:
        context: The mechanical result to describe.
        client: An Anthropic async client (or compatible mock). If ``None``, one
            is created lazily — keeping ``anthropic`` an optional dependency.
        timeout: Seconds to wait before giving up.

    Returns:
        The prose string, or ``None`` if the narrator is disabled, times out, or
        the API call fails. Never raises.
    """
    if not _enabled():
        return None

    try:
        if client is None:
            from anthropic import AsyncAnthropic  # lazy: optional dependency

            client = AsyncAnthropic()

        response = await asyncio.wait_for(
            client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=build_system_prompt(context.language),
                messages=[
                    {"role": "user", "content": build_user_prompt(context)}
                ],
                thinking={"type": "disabled"},
            ),
            timeout=timeout,
        )
    except Exception:
        return None

    text = _extract_text(response)
    return text or None
