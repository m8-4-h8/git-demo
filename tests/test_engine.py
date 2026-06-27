"""Engine isolation tests.

These tests import only from ``engine`` — never ``telegram`` — proving the game
core is unit-testable without any frontend.
"""

from engine import greeting


def test_greeting_returns_non_empty_string() -> None:
    result = greeting()
    assert isinstance(result, str)
    assert result.strip()
