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
