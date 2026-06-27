# Ironsworn Telegram Bot

A Telegram bot for the GM-less tabletop RPG **Ironsworn** — for solo and co-op
play with friends in a group chat. This is **v0**.

## Commands

- `/start` — friendly intro to what the game is
- `/tutorial` — interactive, paged walkthrough
- `/guide`, `/help` — how to play and the command list
- `/new` — create your character (a short step-by-step dialog)
- `/me` — show your character sheet
- `/set <track> <value>` — change `health`/`spirit`/`supply`/`momentum`
- `/roll <stat> [adds] [burn]` — action roll using your character's stat;
  `burn` spends momentum (replaces the score, then resets momentum to +2)
- `/ask <odds> <question>` — yes/no Oracle
- `/oracle [table]` — draw a spark of inspiration
- `/language` — switch the bot's language (RU/EN)

The interface is **bilingual (Russian/English)**; each player's language is
stored and defaults to their Telegram client language. Command keywords accept
either language (e.g. `/roll iron` or `/roll сталь`, `/ask likely …` or
`/ask вероятно …`).

Characters and language preferences are stored per `(chat, user)`, so several
players can keep their own characters in one group chat.

## Architecture

The game core is frontend-independent:

- **`engine/`** — all game logic and rules (rolls, oracles, character model).
  Never imports `telegram` or `storage`. Pure, fully unit-testable functions.
- **`storage/`** — persistence layer (async SQLite via `aiosqlite`). May import
  `engine`; `engine` never imports it.
- **`bot/`** — thin Telegram layer: parse command → call `engine` / `storage` →
  format reply. User-facing text is localized in `bot/i18n.py`. No game logic in
  handlers.
- **`tests/`** — unit tests; the engine is tested in isolation.

See [`CLAUDE.md`](./CLAUDE.md) for the full project conventions.

## Requirements

- Python 3.11+

## Setup

1. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure your bot token. Get one from
   [@BotFather](https://t.me/BotFather), then:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set `BOT_TOKEN`. The `.env` file is git-ignored — never
   commit it.

## Run

```bash
python -m bot
```

The bot uses long polling (no webhook). Send `/start` or `/help` to it in
Telegram to confirm it responds. Character data is saved to a local SQLite file
(`ironsworn.db` by default; override with `DB_PATH`). The database file is
git-ignored.

## Tests

```bash
pytest
```
