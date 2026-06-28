# CLAUDE.md

Guidance for future sessions working in this repo.

## Goal
A Telegram bot for the GM-less (no game master) tabletop RPG **Ironsworn**,
supporting solo play and co-op play with friends in a group chat. This is **v0**.
The frontend is Telegram, but the game core is frontend-independent.

## Stack
- Python 3.11+
- python-telegram-bot 22.x (async)
- SQLite for persistence, async via `aiosqlite` (lives in `storage/`)
- pytest
- Dependencies via `requirements.txt` + a virtualenv (`venv/`)
- `BOT_TOKEN` read from the environment via `python-dotenv` (`.env`, git-ignored)

## Architecture rule (applies to the whole project)
- **`engine/`** holds ALL game logic and rules (rolls, oracles, character
  model). It must **never import anything from `telegram`** (or any other
  frontend) **nor from `storage`**. Pure, deterministic, fully unit-testable
  functions.
- **`storage/`** is the persistence layer (async SQLite via `aiosqlite`). It may
  import `engine` (e.g. the `Character` model); `engine` never imports it.
  Characters are keyed by `(chat_id, user_id)` for co-op in one chat.
- **`bot/`** is the thin Telegram layer: parse the command → call `engine` /
  `storage` → format the reply. **No game logic in handlers.** The store is
  built in `bot/main.py` and shared via `application.bot_data["store"]`.
- **`narrator/`** is an OPTIONAL LLM prose layer (Anthropic). After a mechanical
  outcome it writes 2-3 sentences of flavor — it **describes, never decides**
  (the `engine` is the source of truth). It may import `engine` types but never
  `bot`/`telegram`. Gated by the `NARRATOR_ENABLED` env flag and fails soft
  (returns `None`) so the bot works without it.

This separation keeps the game core reusable across frontends (Telegram now,
possibly CLI/others later) and trivially testable in isolation.

## Conventions
- English for all code, names, comments, and commit messages.
- Type hints everywhere.
- Bot user-facing text is bilingual (RU/EN). All strings live in `bot/i18n.py`
  (`TEXTS[lang][key]`, rendered via `t(lang, key, ...)`); never hardcode
  user-facing literals in handlers. The `engine` stays language-agnostic
  (returns enums/data; the bot localizes them).
- Keep it simple; avoid premature complexity. The only LLM use is the optional
  `narrator/` (gated by `NARRATOR_ENABLED`), which describes outcomes but never
  drives mechanics.

## Run
See `README.md` for venv setup. Run the bot with `python -m bot`
(long polling, not webhook). Run tests with `pytest`.

## Layout
```
engine/   # pure game core (rules), no telegram/storage imports
storage/  # async SQLite persistence (aiosqlite); may import engine
bot/      # thin Telegram frontend (handlers, entrypoint, i18n)
narrator/ # optional LLM prose layer (Anthropic); describes, never decides
data/     # oracle tables (JSON), editable content
tests/    # unit tests (engine tested in isolation; storage via tmp db)
```
