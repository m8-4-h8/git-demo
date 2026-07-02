"""Tests for the pure text helpers that explain choices and outcomes.

These helpers power the "always know what to do and why" UX: move blurbs shown
before committing to a move, per-category move overviews, and the 💡 what-next
hints appended to roll results. They build strings only — no Telegram objects —
so they are unit-tested directly.
"""

from bot.handlers import _move_blurb, _moves_overview, _outcome_hint
from bot.i18n import LANGS, t
from engine.moves import MOVES
from engine.rolls import Outcome


def test_outcome_hint_is_distinct_per_outcome_and_language() -> None:
    for lang in LANGS:
        hints = {_outcome_hint(outcome, lang) for outcome in Outcome}
        assert len(hints) == len(Outcome)
    for outcome in Outcome:
        assert _outcome_hint(outcome, "en") != _outcome_hint(outcome, "ru")


def test_moves_overview_names_and_explains_every_move() -> None:
    for lang in LANGS:
        text = _moves_overview(lang, MOVES)
        for key in MOVES:
            assert t(lang, f"move_{key}") in text
            assert t(lang, f"move_{key}_desc") in text


def test_move_blurb_shows_purpose_all_outcomes_and_a_prompt() -> None:
    for lang in LANGS:
        blurb = _move_blurb(MOVES["strike"], lang)
        assert t(lang, "move_strike_desc") in blurb
        for outcome_key in ("outcome_strong", "outcome_weak", "outcome_miss"):
            assert t(lang, outcome_key) in blurb
        assert t(lang, "move_stat_title") in blurb


def test_move_blurb_renders_signed_effects() -> None:
    blurb = _move_blurb(MOVES["strike"], "en")
    assert "+2" in blurb  # strong hit: momentum +2
    assert "-1" in blurb  # miss: health -1
