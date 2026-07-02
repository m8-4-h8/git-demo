# CLAUDE.md

Guidance for future sessions working in this repo.

## Goal
A Telegram bot for the GM-less (no game master) tabletop RPG **Ironsworn**,
supporting solo play and co-op play with friends in a group chat. This is **v0**.
The frontend is Telegram, but the game core is frontend-independent.

## Stack
- Python 3.11+
- python-telegram-bot 22.x (async), with the `[job-queue]` extra (APScheduler)
  for conversation timeouts
- SQLite for persistence, async via `aiosqlite` (lives in `storage/`)
- pytest
- Dependencies via `requirements.txt` + a virtualenv (`venv/`)
- `BOT_TOKEN` read from the environment via `python-dotenv` (`.env`, git-ignored)

## Architecture rule (applies to the whole project)
- **`engine/`** holds ALL game logic and rules (rolls, oracles, character
  model). It must **never import anything from `telegram`** (or any other
  frontend) **nor from `storage`**. Pure, deterministic, fully unit-testable
  functions. The `Character` sheet carries the name, five stats, three tracks
  and momentum, plus an `items: list[str]` inventory and an optional
  `background: str | None` story; `add_item`/`remove_item`/`set_background`
  are pure helpers with limits (≤20 items, ≤50 chars each, ≤500-char story).
- **`storage/`** is the persistence layer (async SQLite via `aiosqlite`). It may
  import `engine` (e.g. the `Character` model); `engine` never imports it.
  Characters are keyed by `(chat_id, user_id)` for co-op in one chat. The
  `characters` table is migrated additively (e.g. `items` JSON + `background` +
  `archetype` columns added via `ALTER TABLE`), so older databases keep working
  with defaulted values.
- **`engine/moves.py`** holds the named-moves layer: a small v1 set of moves
  (Strike, Face Danger, …) grouped by category (Adventure/Combat/Quest), each
  with per-outcome effects on the character's tracks/momentum. `resolve_move`
  rolls a player-chosen stat and `apply_effects` clamps & applies the delta —
  still pure, deterministic, no telegram/storage.
- **`engine/session.py`** holds the multiplayer **session rules**: an immutable
  `GameSession` (creator, password, phase LOBBY/ACTIVE, a `players` tuple that
  doubles as the turn order, `turn_index`) plus pure functions —
  `create/join/leave/start_session`, `advance_turn`, `active_player`,
  `is_active_player`. Every rule violation is a distinct `SessionError`
  subclass (`WrongPassword`, `AlreadyJoined`, `SessionFull`, `NotCreator`, …)
  so the bot can localize each case. Leaving handles the edge cases: the turn
  passes on, the earliest remaining player inherits the creator role, and an
  empty session dissolves to `None`.
- **`engine/classes.py`** holds the character **archetypes** ("paths") — eight
  light, original adaptations (Warrior, Rogue, Ranger, Sage, Priest, Bard,
  Savage, Wanderer). Each `CharacterArchetype` is language-agnostic data (a
  `key`, favoured `primary_stat`, `suggested_items` keys, and an emoji); the
  localized name/description live in i18n. Creation distributes the fixed spread
  1,1,2,2,3 across the five stats (`validate_allocation`), then the path adds +1
  to its primary stat (capped at 4); `create_with_archetype` builds the
  `Character` with that bonus, the path key, and the starting gear in inventory.
- **`bot/`** is the thin Telegram layer: parse the command → call `engine` /
  `storage` → format the reply. **No game logic in handlers.** The store is
  built in `bot/main.py` and shared via `application.bot_data["store"]`.
  The UX is **button-first**: `/start` (and a 🏠 Menu button) opens an
  InlineKeyboard main menu; players navigate everything via buttons (with 🔙 Back
  and 🏠 Home on every screen), typing only a hero's name and a vow/track title.
  Slash commands stay as a hidden power-user fallback. Keyboard builders and the
  namespaced `callback_data` scheme (`area:action[:arg…]`) live in `bot/menu.py`;
  a single `menu_callback` routes `menu|move|roll|oracle|char|vow|track|help:`,
  while the guided creation flows own the `cnew|vnew|tnew:` prefixes. `/new` is a
  guided, teaching flow: name → pick a **path/archetype** (with a blurb and which
  stat it strengthens) → distribute 1,1,2,2,3 across the stats (each shown with a
  one-line explanation) → confirm a summary (boosted stat marked, starting gear
  listed) → create. If the narrator is on, one optional GM-style opening line
  follows (fail-soft). UX conventions: Telegram's native "/" menu advertises a
  short, curated command list (`set_my_commands`, RU/EN); newcomers without a
  hero get a ✨ Create-hero CTA in the main menu and in every "no hero yet"
  reply; empty vow/track lists offer a create button; a typing indicator shows
  while the narrator/GM generate; every guided dialog expires after 10 minutes
  (`conversation_timeout`) so an abandoned flow never swallows later messages.
  **Co-op sessions** live in `bot/session_handlers.py` (own module; imports the
  shared helpers from `bot/handlers.py`): `session_callback` routes the `sess:`
  prefix, and three conversations own `screate:` (create lobby → typed
  password), `sjoin:` (join → typed password; the password message is deleted
  after reading) and `scust:` (custom action → typed description → stat
  buttons). One session per chat (`storage/sessions.py`, `sessions` table keyed
  by `chat_id`; `SessionRecord` wraps the engine `GameSession` plus the shared
  language and the ids of the edit-in-place messages). The UX runs on three
  edit-in-place messages: the **lobby** (participant list, refreshed on
  join/leave — shared by the group, so deliberately no Home/Back buttons), the
  **🗺 Setting** (posted once at game start; LLM-written when
  `SESSION_LLM_SETTING` — defaulting to `GM_ENABLED` — is on, else a static
  i18n text, always fail-soft) and the **🎯 Current Turn** (the active player's
  hero card — name, path, stats, tracks — plus move/custom/pass buttons, edited
  on every turn change). **Access control:** every game-turn button verifies
  the clicker is the active player and answers everyone else with a popup
  alert, executing nothing; start/end are enforced creator-only the same way.
  Turns rotate round-robin; an idle active player is auto-skipped after 10
  minutes via the job queue.
- **`narrator/`** is an OPTIONAL LLM prose layer (local LLM via Ollama, over
  async HTTP with `httpx`). After a mechanical outcome (a roll, a vow
  fulfillment, an encounter) it writes 2-3 sentences of flavor — it
  **describes, never decides** (the `engine` is the source of truth). It may
  import `engine` types but never `bot`/`telegram`. Gated by the
  `NARRATOR_ENABLED` env flag and fails soft (returns `None`) so the bot works
  without it. Model/host via `OLLAMA_MODEL`/`OLLAMA_BASE_URL`.
- **`gm/`** is an OPTIONAL AI Game Master (local LLM via Ollama). It proposes scenarios,
  describes the evolving world after each action, introduces NPCs/threats, and
  keeps continuity across turns — but **generates narrative only, never
  mechanics** (the `engine` decides rolls/outcomes). It may import `engine`
  types but never `bot`/`telegram`; campaign state is persisted in `storage/`
  (`gm_state`, per chat). Gated by the `GM_ENABLED` env flag and fails soft.

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
engine/   # pure game core (rules incl. moves + archetypes), no telegram/storage imports
storage/  # async SQLite persistence (aiosqlite); may import engine
bot/      # thin Telegram frontend (handlers, entrypoint, i18n)
narrator/ # optional LLM prose layer (Ollama via httpx); describes, never decides
gm/       # optional AI Game Master (Ollama via httpx); narrative & scenes, never mechanics
data/     # oracle tables (JSON), editable content
tests/    # unit tests (engine tested in isolation; storage via tmp db)
```
