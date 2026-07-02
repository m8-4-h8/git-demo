"""Multiplayer game-session rules: lobby, membership, and turn order.

Pure and frontend-independent, like the rest of the engine: no ``telegram``,
no ``storage`` — just an immutable session model and the rules that govern it.
A session lives in one chat: players gather in a password-protected lobby, the
creator starts the game, and turns then rotate round-robin. Every rule error is
a distinct :class:`SessionError` subclass so a frontend can localize each case.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

MAX_PLAYERS = 8
MAX_PASSWORD_LENGTH = 32
MAX_PLAYER_NAME_LENGTH = 64


class SessionPhase(Enum):
    """Lifecycle of a session: gathering in the lobby, then playing."""

    LOBBY = "lobby"
    ACTIVE = "active"


class SessionError(ValueError):
    """Base class for every session rule violation."""


class WrongPassword(SessionError):
    """The join password does not match the session's password."""


class AlreadyJoined(SessionError):
    """The user is already a member of the session."""


class NotInSession(SessionError):
    """The user is not a member of the session."""


class NotCreator(SessionError):
    """Only the session's creator may perform this action."""


class AlreadyStarted(SessionError):
    """The action is only valid while the session is in the lobby."""


class NotStarted(SessionError):
    """The action is only valid once the game has started."""


class SessionFull(SessionError):
    """The session already has :data:`MAX_PLAYERS` members."""


@dataclass(frozen=True)
class SessionPlayer:
    """A session member: the frontend user id plus a display name."""

    user_id: int
    name: str


@dataclass(frozen=True)
class GameSession:
    """A multiplayer session in one chat.

    ``players`` doubles as the turn order (join order); ``turn_index`` points at
    the player whose turn it is once the phase is ACTIVE. Instances are
    immutable; the rule functions below return new copies.
    """

    creator_id: int
    password: str
    phase: SessionPhase = SessionPhase.LOBBY
    players: tuple[SessionPlayer, ...] = ()
    turn_index: int = 0


def _clean_password(password: str) -> str:
    cleaned = password.strip()
    if not cleaned:
        raise SessionError("password must not be empty")
    if len(cleaned) > MAX_PASSWORD_LENGTH:
        raise SessionError(
            f"password must be at most {MAX_PASSWORD_LENGTH} characters"
        )
    return cleaned


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise SessionError("player name must not be empty")
    return cleaned[:MAX_PLAYER_NAME_LENGTH]


def create_session(creator_id: int, creator_name: str, password: str) -> GameSession:
    """Open a new lobby with the creator as its first player.

    Raises:
        SessionError: If the password is empty/too long or the name is empty.
    """
    return GameSession(
        creator_id=creator_id,
        password=_clean_password(password),
        players=(SessionPlayer(creator_id, _clean_name(creator_name)),),
    )


def in_session(session: GameSession, user_id: int) -> bool:
    """True if ``user_id`` is a member of the session."""
    return any(player.user_id == user_id for player in session.players)


def join_session(
    session: GameSession, user_id: int, name: str, password: str
) -> GameSession:
    """Add a player to the lobby after checking the password.

    Raises:
        AlreadyStarted: If the game is no longer in the lobby.
        AlreadyJoined: If the user is already a member.
        SessionFull: If the lobby already has :data:`MAX_PLAYERS` players.
        WrongPassword: If the password does not match.
    """
    if session.phase is not SessionPhase.LOBBY:
        raise AlreadyStarted("the game has already started")
    if in_session(session, user_id):
        raise AlreadyJoined(f"user {user_id} is already in the session")
    if len(session.players) >= MAX_PLAYERS:
        raise SessionFull(f"the session is full (max {MAX_PLAYERS} players)")
    if password.strip() != session.password:
        raise WrongPassword("wrong session password")
    player = SessionPlayer(user_id, _clean_name(name))
    return replace(session, players=(*session.players, player))


def leave_session(session: GameSession, user_id: int) -> GameSession | None:
    """Remove a player; return the new session, or None if it dissolves.

    Works in both phases. If the leaver held the current turn, the turn passes
    to the next player in order; if the leaver was the creator, the earliest
    remaining player inherits the session.

    Raises:
        NotInSession: If the user is not a member.
    """
    index = next(
        (i for i, p in enumerate(session.players) if p.user_id == user_id), None
    )
    if index is None:
        raise NotInSession(f"user {user_id} is not in the session")
    remaining = tuple(p for p in session.players if p.user_id != user_id)
    if not remaining:
        return None
    turn_index = session.turn_index
    if index < turn_index:
        turn_index -= 1
    turn_index %= len(remaining)
    creator_id = session.creator_id
    if user_id == creator_id:
        creator_id = remaining[0].user_id
    return replace(
        session, players=remaining, turn_index=turn_index, creator_id=creator_id
    )


def start_session(session: GameSession, user_id: int) -> GameSession:
    """Begin the game: only the creator may start, and only from the lobby.

    Raises:
        NotCreator: If ``user_id`` is not the session creator.
        AlreadyStarted: If the game is already running.
    """
    if session.phase is not SessionPhase.LOBBY:
        raise AlreadyStarted("the game has already started")
    if user_id != session.creator_id:
        raise NotCreator("only the creator can start the game")
    return replace(session, phase=SessionPhase.ACTIVE, turn_index=0)


def active_player(session: GameSession) -> SessionPlayer:
    """Return the player whose turn it is.

    Raises:
        NotStarted: If the game has not started yet.
    """
    if session.phase is not SessionPhase.ACTIVE:
        raise NotStarted("the game has not started")
    return session.players[session.turn_index]


def is_active_player(session: GameSession, user_id: int) -> bool:
    """True if the game is running and it is ``user_id``'s turn."""
    return (
        session.phase is SessionPhase.ACTIVE
        and session.players[session.turn_index].user_id == user_id
    )


def advance_turn(session: GameSession) -> GameSession:
    """Pass the turn to the next player, round-robin.

    Raises:
        NotStarted: If the game has not started yet.
    """
    if session.phase is not SessionPhase.ACTIVE:
        raise NotStarted("the game has not started")
    return replace(
        session, turn_index=(session.turn_index + 1) % len(session.players)
    )
