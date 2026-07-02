"""Tests for the i18n text catalog and helpers."""

import string

import pytest

from bot.i18n import (
    LANGS,
    ODDS_ALIASES,
    STAT_ALIASES,
    TEXTS,
    TRACK_ALIASES,
    resolve_lang,
    t,
)
from engine.character import STAT_NAMES, TRACK_NAMES
from engine.classes import ARCHETYPES, SUGGESTED_ITEM_KEYS
from engine.oracles import Odds


def test_languages_have_identical_keys() -> None:
    en_keys = set(TEXTS["en"])
    for lang in LANGS:
        assert set(TEXTS[lang]) == en_keys, f"key mismatch in '{lang}'"


def test_every_language_has_required_label_keys() -> None:
    required = (
        [f"stat_{s}" for s in STAT_NAMES]
        + [f"track_{tr}" for tr in TRACK_NAMES if tr != "momentum"]
        + [f"odds_{o.name.lower()}" for o in Odds]
        + ["momentum", "reset"]
    )
    for lang in LANGS:
        for key in required:
            assert key in TEXTS[lang], f"{lang} missing {key}"


def test_every_language_describes_the_command_menu() -> None:
    from bot.main import _MENU_COMMANDS

    for lang in LANGS:
        for name in _MENU_COMMANDS:
            description = TEXTS[lang].get(f"cmd_{name}")
            assert description, f"{lang} missing cmd_{name}"
            # Telegram limits command descriptions to 256 chars.
            assert len(description) <= 256


def test_every_language_names_and_describes_each_move() -> None:
    from engine.moves import MOVES

    for lang in LANGS:
        for key in MOVES:
            assert f"move_{key}" in TEXTS[lang], f"{lang} missing move_{key}"
            assert f"move_{key}_desc" in TEXTS[lang], (
                f"{lang} missing move_{key}_desc"
            )


def test_every_language_explains_settable_fields() -> None:
    for lang in LANGS:
        for field in ("health", "spirit", "supply", "momentum"):
            assert f"field_desc_{field}" in TEXTS[lang], (
                f"{lang} missing field_desc_{field}"
            )


def test_every_language_localizes_archetypes_and_gear() -> None:
    required = [f"stat_{s}_desc" for s in STAT_NAMES]
    for key in ARCHETYPES:
        required += [f"arch_{key}_name", f"arch_{key}_desc"]
    required += [f"item_{key}" for key in SUGGESTED_ITEM_KEYS]
    for lang in LANGS:
        for key in required:
            assert key in TEXTS[lang], f"{lang} missing {key}"


def _placeholders(template: str) -> set[str]:
    return {
        name
        for _, name, _, _ in string.Formatter().parse(template)
        if name
    }


def test_placeholders_match_across_languages() -> None:
    for key, en_template in TEXTS["en"].items():
        en_fields = _placeholders(en_template)
        for lang in LANGS:
            assert _placeholders(TEXTS[lang][key]) == en_fields, (
                f"placeholder mismatch for '{key}' in '{lang}'"
            )


def test_t_formats_and_falls_back() -> None:
    assert t("en", "answer_yes")  # plain lookup
    assert "5" in t("ru", "ask_odds", label="X", chance=5, roll=3)
    # unknown key falls back to the key itself
    assert t("en", "totally_unknown_key") == "totally_unknown_key"
    # unknown language falls back to English text
    assert t("zz", "answer_yes") == TEXTS["en"]["answer_yes"]


@pytest.mark.parametrize(
    "stored, code, expected",
    [
        ("ru", "en-US", "ru"),     # stored wins
        ("en", "ru", "en"),        # stored wins
        (None, "ru", "ru"),        # telegram code
        (None, "ru-RU", "ru"),
        (None, "en-GB", "en"),
        (None, None, "en"),        # default
        ("nonsense", "ru", "ru"),  # invalid stored -> code
    ],
)
def test_resolve_lang(stored, code, expected) -> None:
    assert resolve_lang(stored, code) == expected


def test_plain_sent_strings_have_no_markdown_markers() -> None:
    # Only these keys are sent with ParseMode.MARKDOWN; every other string is
    # sent plain, so it must not contain stray Markdown markers (which would
    # render literally to the player).
    markdown_sent = {"start", "guide", "tut_1", "tut_2", "tut_3", "tut_4"}
    for lang in LANGS:
        for key, value in TEXTS[lang].items():
            if key in markdown_sent:
                continue
            assert "*" not in value, f"{lang}/{key} has a stray '*'"
            assert "`" not in value, f"{lang}/{key} has a stray backtick"


def test_aliases_map_to_canonical_names() -> None:
    assert STAT_ALIASES["сталь"] == "iron"
    assert STAT_ALIASES["iron"] == "iron"
    assert TRACK_ALIASES["припасы"] == "supply"
    assert ODDS_ALIASES["вероятно"] == "likely"
    # every canonical stat/track name is reachable by its english alias
    for name in STAT_NAMES:
        assert STAT_ALIASES[name] == name
