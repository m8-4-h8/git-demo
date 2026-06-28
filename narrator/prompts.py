"""Prompt construction for the narrator.

The system prompt is written in English; for Russian sessions a final line asks
for a Russian response (the model translates). The user prompt passes the
mechanical facts the narrator must respect — it never invents outcomes.
"""

from __future__ import annotations

from narrator.context import NarratorContext

_SYSTEM_PROMPT = """\
You are a dark fantasy narrator for an Ironsworn tabletop RPG session.
Your role: write 2-3 sentences of atmospheric prose describing what
just happened in the story based on the mechanical outcome provided.

Rules:
- NEVER invent new mechanics, items, or characters not implied by context
- NEVER contradict the mechanical outcome (strong hit = success, miss = failure)
- Write in second person ("You strike...", "The blow lands...")
- Dark fantasy tone: gritty, tense, consequential
- For MATCH outcomes: hint at something unexpected or dramatic
- Keep it under 60 words
- Respond with prose only, no formatting, no labels"""

_OUTCOME_TEXT = {
    "strong": "strong hit (clear success)",
    "weak": "weak hit (success with a cost)",
    "miss": "miss (failure)",
}


def build_system_prompt(language: str) -> str:
    """Return the narrator system prompt, localized for the response language."""
    if language == "ru":
        return _SYSTEM_PROMPT + "\n- Write your response in Russian"
    return _SYSTEM_PROMPT


def _format_delta(delta: dict[str, int]) -> str:
    if not delta:
        return "none"
    return ", ".join(f"{field} {change:+d}" for field, change in delta.items())


def build_user_prompt(context: NarratorContext) -> str:
    """Render the mechanical facts the narrator must describe."""
    outcome = _OUTCOME_TEXT.get(context.outcome.value, context.outcome.value)
    lines = [
        f"Move: {context.move_name} (stat used: {context.stat_used})",
        f"Outcome: {outcome}",
        f"Match (doubled challenge dice): {'yes' if context.is_match else 'no'}",
        f"What changed: {_format_delta(context.delta)}",
        f"Character: {context.character_name or 'the hero'}",
        f"Active vow: {context.active_vow or 'none'}",
        f"Active progress track: {context.active_track or 'none'}",
        f"Respond in: {'Russian' if context.language == 'ru' else 'English'}",
    ]
    return "\n".join(lines)
