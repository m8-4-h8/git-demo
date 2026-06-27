# CLAUDE.md

Guidance for future sessions working in this repo.

## Goal
A Telegram bot for the GM-less (no game master) tabletop RPG **Ironsworn**,
supporting solo play and co-op play with friends in a group chat. This is **v0**.
The frontend is Telegram, but the game core is frontend-independent.

## Stack
- Python 3.11+
- python-telegram-bot 22.x (async)
- SQLite — for persistence (added later, not yet wired)
- pytest
- Dependencies via `requirements.txt` + a virtualenv (`venv/`)
- `BOT_TOKEN` read from the environment via `python-dotenv` (`.env`, git-ignored)

## Architecture rule (applies to the whole project)
- **`engine/`** holds ALL game logic. It must **never import anything from
  `telegram`** (or any other frontend). Pure, deterministic, fully
  unit-testable functions.
- **`bot/`** is the thin Telegram layer: parse the command → call `engine` →
  format the reply. **No game logic in handlers.**

This separation keeps the game core reusable across frontends (Telegram now,
possibly CLI/others later) and trivially testable in isolation.

## Conventions
- English for all code, names, comments, and commit messages.
- Type hints everywhere.
- Bot user-facing text is in English.
- Keep v0 simple: no game mechanics, no LLM, no premature complexity.

## Run
See `README.md` for venv setup. Run the bot with `python -m bot`
(long polling, not webhook). Run tests with `pytest`.

## Layout
```
engine/   # pure game core, no telegram imports
bot/      # thin Telegram frontend (handlers, entrypoint)
tests/    # unit tests (engine tested in isolation)
```
