"""Core engine entry points.

v0 placeholder: no game mechanics yet. This module exists to establish the
engine -> frontend boundary and to give the test suite a real, pure function to
exercise. Game logic added in later steps must stay pure and telegram-free.
"""


def greeting() -> str:
    """Return the engine-owned welcome line the frontend renders.

    Pure: no I/O, no side effects, deterministic output.
    """
    return "Forge your own legend. (Ironsworn engine v0)"
