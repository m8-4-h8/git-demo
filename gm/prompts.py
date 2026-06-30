"""Prompts for the AI Game Master.

The system prompt is English; for Russian sessions a final line requests a
Russian response. User prompts pass the campaign state the GM must stay
consistent with — and remind it never to resolve mechanics.
"""

from __future__ import annotations

from gm.context import GMContext

_SYSTEM_PROMPT = """\
You are a dark fantasy Game Master for a cooperative RPG session in Telegram.
Your role: describe the world, introduce NPCs and threats, create atmosphere.

Rules:
- NEVER resolve dice rolls or mechanical outcomes — the game engine does that
- NEVER say "you succeed" or "you fail" — say what the world does next
- Introduce complications on miss results, opportunities on strong hits
- Remember NPCs you introduce — keep them consistent
- Dark fantasy tone: morally grey, dangerous world, meaningful choices
- Each scene response: 2-4 sentences maximum
- End each scene with an implicit question or tension (what do you do?)"""


def build_system_prompt(language: str) -> str:
    """Return the GM system prompt, asking for the right response language."""
    lang_name = "Russian" if language == "ru" else "English"
    return f"{_SYSTEM_PROMPT}\n- Language: respond in {lang_name}"


def build_scenario_prompt(language: str) -> str:
    """Ask for three dark-fantasy scenario options as a plain JSON object.

    Ollama is also told to constrain output to JSON (``format: "json"``), but we
    spell out the exact shape here too so the text we parse is predictable.
    """
    lang_name = "Russian" if language == "ru" else "English"
    return (
        "Propose exactly THREE distinct dark-fantasy campaign scenarios for a "
        "co-op Ironsworn-style game. For each, give a short evocative title, a "
        "concrete goal (one sworn quest, e.g. 'slay the dragon Kor'tan'), and a "
        "2-3 sentence opening scene that sets the hook. "
        f"Write all text in {lang_name}.\n\n"
        "Return ONLY a JSON object (no prose, no markdown, no code fences) of "
        "exactly this shape:\n"
        '{"scenarios": [{"title": "...", "goal": "...", "opening_scene": "..."}, '
        '{"title": "...", "goal": "...", "opening_scene": "..."}, '
        '{"title": "...", "goal": "...", "opening_scene": "..."}]}'
    )


def _campaign_block(context: GMContext) -> str:
    npcs = (
        "; ".join(f"{name}: {desc}" for name, desc in context.npc_memory.items())
        or "none yet"
    )
    recent = " || ".join(context.scene_history[-3:]) or "none"
    return (
        f"Scenario: {context.scenario_title} — goal: {context.scenario_goal}\n"
        f"Party: {', '.join(context.active_characters) or 'unknown'}\n"
        f"Active vows: {', '.join(context.active_vows) or 'none'}\n"
        f"Known NPCs: {npcs}\n"
        f"Recent scenes: {recent}\n"
        f"Current scene: {context.current_scene or 'none'}"
    )


def build_scene_prompt(context: GMContext, last_move_result: str) -> str:
    """Ask the GM to narrate what the world does next after a player's action."""
    return (
        f"{_campaign_block(context)}\n\n"
        f"A player just acted. Mechanical result (already decided by the engine — "
        f"do not re-judge it): {last_move_result}\n\n"
        "Describe what happens next in the world (2-4 sentences). Do not state "
        "success or failure; react to the situation and end with tension."
    )


def build_complication_prompt(context: GMContext) -> str:
    """Ask the GM to introduce a complication or dramatic turn (used on a miss)."""
    return (
        f"{_campaign_block(context)}\n\n"
        "The player's action went badly (the engine ruled a miss). Introduce a "
        "complication, threat, or dramatic turn (2-4 sentences). Do not say they "
        "failed; show the world turning against them and end with tension."
    )
