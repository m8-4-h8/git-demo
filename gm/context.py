"""GM state and context — the data the AI Game Master reasons over.

Pure and frontend-/persistence-independent: imports nothing from ``bot``,
``telegram``, or ``storage``. Holds the campaign snapshot the GM needs, plus the
serialization helpers the storage layer uses to persist it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Sliding window: keep at most this many recent scenes for continuity.
SCENE_HISTORY_LIMIT = 5


@dataclass(frozen=True)
class ScenarioOption:
    """One scenario the GM offers at the start of a campaign."""

    title: str
    goal: str
    opening_scene: str


@dataclass(frozen=True)
class GMContext:
    """Everything the GM needs to describe the next beat (never to decide it)."""

    scenario_title: str
    scenario_goal: str
    current_scene: str
    scene_history: list[str] = field(default_factory=list)
    active_characters: list[str] = field(default_factory=list)
    active_vows: list[str] = field(default_factory=list)
    npc_memory: dict[str, str] = field(default_factory=dict)
    language: str = "en"
    # Optional colour for richer narrative — the acting hero's story & gear.
    # Both default to empty, so the GM works exactly as before without them.
    background: str | None = None
    items: list[str] = field(default_factory=list)


def push_scene(
    history: list[str], scene: str, limit: int = SCENE_HISTORY_LIMIT
) -> list[str]:
    """Return ``history`` with ``scene`` appended, keeping only the last ``limit``."""
    return [*history, scene][-limit:]


def to_state_dict(
    *,
    scenario_title: str,
    scenario_goal: str,
    current_scene: str,
    scene_history: list[str],
    npc_memory: dict[str, str],
) -> dict:
    """Build the persisted GM-state subset (campaign-level, per chat)."""
    return {
        "scenario_title": scenario_title,
        "scenario_goal": scenario_goal,
        "current_scene": current_scene,
        "scene_history": list(scene_history)[-SCENE_HISTORY_LIMIT:],
        "npc_memory": dict(npc_memory),
    }


def from_state_dict(state: dict) -> dict:
    """Normalize a loaded GM-state dict (defaults + history cap)."""
    return {
        "scenario_title": state.get("scenario_title", ""),
        "scenario_goal": state.get("scenario_goal", ""),
        "current_scene": state.get("current_scene", ""),
        "scene_history": list(state.get("scene_history", []))[-SCENE_HISTORY_LIMIT:],
        "npc_memory": dict(state.get("npc_memory", {})),
    }
