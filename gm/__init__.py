"""Optional AI Game Master layer (local LLM via Ollama).

The GM proposes scenarios and describes the evolving world after each action —
introducing NPCs, threats, and twists, and keeping continuity across turns. It
generates **narrative only**: rolls, outcomes, HP, and tracks stay with
``engine``. It may import ``engine`` types but never ``bot``/``telegram``, and is
gated by the ``GM_ENABLED`` env flag (fails soft, returning ``None``).
"""

from gm.client import (
    generate_complication,
    generate_scenario_options,
    generate_scene,
    is_enabled,
)
from gm.context import GMContext, ScenarioOption, push_scene

__all__ = [
    "GMContext",
    "ScenarioOption",
    "push_scene",
    "generate_scenario_options",
    "generate_scene",
    "generate_complication",
    "is_enabled",
]
