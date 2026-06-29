"""The AI Game Master client.

Calls Anthropic (``claude-sonnet-4-6``) to propose scenarios and describe the
evolving world. It generates narrative only — it never resolves mechanics. The
whole layer is gated by ``GM_ENABLED`` and fails soft: on a disabled flag,
timeout, or API error every function returns ``None`` and never raises.
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

MODEL = "claude-sonnet-4-6"
SCENE_MAX_TOKENS = 300
SCENARIO_MAX_TOKENS = 800
DEFAULT_TIMEOUT = 10.0

__all__ = [
    "generate_scenario_options",
    "generate_scene",
    "generate_complication",
    "is_enabled",
]

# JSON schema constraining the scenario response (3 requested in the prompt).
_SCENARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "goal": {"type": "string"},
                    "opening_scene": {"type": "string"},
                },
                "required": ["title", "goal", "opening_scene"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenarios"],
    "additionalProperties": False,
}

_default_client = None


def is_enabled() -> bool:
    """True if GM_ENABLED is set to a truthy value."""
    return os.environ.get("GM_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _get_client():
    global _default_client
    if _default_client is None:
        from anthropic import AsyncAnthropic  # lazy: optional dependency

        _default_client = AsyncAnthropic()
    return _default_client


def _extract_text(response: object) -> str:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return (getattr(block, "text", "") or "").strip()
    return ""


async def _complete(
    system: str,
    user: str,
    *,
    client,
    timeout: float,
    max_tokens: int,
    output_config: dict | None = None,
):
    """Run one Messages request, or return None on disabled/timeout/error."""
    if not is_enabled():
        return None
    try:
        if client is None:
            client = _get_client()
        kwargs = {
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "disabled"},
        }
        if output_config is not None:
            kwargs["output_config"] = output_config
        return await asyncio.wait_for(client.messages.create(**kwargs), timeout=timeout)
    except Exception:
        return None


async def generate_scenario_options(
    language: str, *, client=None, timeout: float = DEFAULT_TIMEOUT
) -> list[ScenarioOption] | None:
    """Return exactly three scenario options, or None on any problem."""
    response = await _complete(
        build_system_prompt(language),
        build_scenario_prompt(language),
        client=client,
        timeout=timeout,
        max_tokens=SCENARIO_MAX_TOKENS,
        output_config={"format": {"type": "json_schema", "schema": _SCENARIO_SCHEMA}},
    )
    if response is None:
        return None
    try:
        data = json.loads(_extract_text(response))
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
    response = await _complete(
        build_system_prompt(context.language),
        build_scene_prompt(context, last_move_result),
        client=client,
        timeout=timeout,
        max_tokens=SCENE_MAX_TOKENS,
    )
    if response is None:
        return None
    return _extract_text(response) or None


async def generate_complication(
    context: GMContext, *, client=None, timeout: float = DEFAULT_TIMEOUT
) -> str | None:
    """Introduce a complication/turn (used on a miss), or None."""
    response = await _complete(
        build_system_prompt(context.language),
        build_complication_prompt(context),
        client=client,
        timeout=timeout,
        max_tokens=SCENE_MAX_TOKENS,
    )
    if response is None:
        return None
    return _extract_text(response) or None
