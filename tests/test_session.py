"""Tests for the pure multiplayer-session rules (lobby, turns, edge cases)."""

import pytest

from engine.session import (
    MAX_PASSWORD_LENGTH,
    MAX_PLAYERS,
    AlreadyJoined,
    AlreadyStarted,
    GameSession,
    NotCreator,
    NotInSession,
    NotStarted,
    SessionError,
    SessionFull,
    SessionPhase,
    WrongPassword,
    active_player,
    advance_turn,
    create_session,
    in_session,
    is_active_player,
    join_session,
    leave_session,
    start_session,
)


def _lobby(*extra: tuple[int, str]) -> GameSession:
    """A lobby created by user 1 ('Anna'), with optional extra members."""
    session = create_session(1, "Anna", "secret")
    for user_id, name in extra:
        session = join_session(session, user_id, name, "secret")
    return session


def _game(*extra: tuple[int, str]) -> GameSession:
    return start_session(_lobby(*extra), 1)


# --- creation -----------------------------------------------------------------


def test_create_session_puts_creator_first() -> None:
    session = create_session(7, "  Anna ", " secret ")
    assert session.phase is SessionPhase.LOBBY
    assert session.creator_id == 7
    assert session.password == "secret"
    assert [p.user_id for p in session.players] == [7]
    assert session.players[0].name == "Anna"


@pytest.mark.parametrize("password", ["", "   ", "x" * (MAX_PASSWORD_LENGTH + 1)])
def test_create_session_rejects_bad_password(password: str) -> None:
    with pytest.raises(SessionError):
        create_session(1, "Anna", password)


def test_create_session_rejects_empty_name() -> None:
    with pytest.raises(SessionError):
        create_session(1, "   ", "secret")


# --- joining ------------------------------------------------------------------


def test_join_appends_in_turn_order() -> None:
    session = _lobby((2, "Boris"), (3, "Clara"))
    assert [p.user_id for p in session.players] == [1, 2, 3]
    assert in_session(session, 2)
    assert not in_session(session, 99)


def test_join_wrong_password_rejected() -> None:
    with pytest.raises(WrongPassword):
        join_session(_lobby(), 2, "Boris", "nope")


def test_join_twice_rejected() -> None:
    with pytest.raises(AlreadyJoined):
        join_session(_lobby((2, "Boris")), 2, "Boris", "secret")


def test_join_after_start_rejected() -> None:
    with pytest.raises(AlreadyStarted):
        join_session(_game(), 2, "Boris", "secret")


def test_join_full_lobby_rejected() -> None:
    session = _lobby(*[(i, f"P{i}") for i in range(2, MAX_PLAYERS + 1)])
    assert len(session.players) == MAX_PLAYERS
    with pytest.raises(SessionFull):
        join_session(session, 99, "Late", "secret")


# --- starting -----------------------------------------------------------------


def test_only_creator_starts() -> None:
    with pytest.raises(NotCreator):
        start_session(_lobby((2, "Boris")), 2)


def test_start_twice_rejected() -> None:
    with pytest.raises(AlreadyStarted):
        start_session(_game(), 1)


def test_start_activates_and_resets_turn() -> None:
    game = _game((2, "Boris"))
    assert game.phase is SessionPhase.ACTIVE
    assert active_player(game).user_id == 1


# --- turn order ---------------------------------------------------------------


def test_turns_rotate_round_robin() -> None:
    game = _game((2, "Boris"), (3, "Clara"))
    order = []
    for _ in range(4):
        order.append(active_player(game).user_id)
        game = advance_turn(game)
    assert order == [1, 2, 3, 1]


def test_is_active_player() -> None:
    game = advance_turn(_game((2, "Boris")))
    assert is_active_player(game, 2)
    assert not is_active_player(game, 1)
    assert not is_active_player(_lobby((2, "Boris")), 1)  # lobby: nobody's turn


def test_turn_queries_require_started_game() -> None:
    with pytest.raises(NotStarted):
        active_player(_lobby())
    with pytest.raises(NotStarted):
        advance_turn(_lobby())


# --- leaving (edge cases) -------------------------------------------------------


def test_leave_unknown_user_rejected() -> None:
    with pytest.raises(NotInSession):
        leave_session(_lobby(), 99)


def test_last_player_leaving_dissolves_session() -> None:
    assert leave_session(_lobby(), 1) is None


def test_creator_leaving_promotes_next_player() -> None:
    session = leave_session(_lobby((2, "Boris"), (3, "Clara")), 1)
    assert session is not None
    assert session.creator_id == 2
    assert [p.user_id for p in session.players] == [2, 3]


def test_active_player_leaving_passes_turn_forward() -> None:
    game = advance_turn(_game((2, "Boris"), (3, "Clara")))  # Boris's turn
    game = leave_session(game, 2)
    assert active_player(game).user_id == 3


def test_last_in_order_leaving_wraps_turn_to_first() -> None:
    game = advance_turn(advance_turn(_game((2, "Boris"), (3, "Clara"))))
    assert active_player(game).user_id == 3
    game = leave_session(game, 3)
    assert active_player(game).user_id == 1


def test_earlier_player_leaving_keeps_current_turn() -> None:
    game = advance_turn(advance_turn(_game((2, "Boris"), (3, "Clara"))))
    assert active_player(game).user_id == 3
    game = leave_session(game, 1)  # creator, before the active player
    assert active_player(game).user_id == 3
    assert game.creator_id == 2
