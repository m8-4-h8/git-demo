# Ironsworn Telegram Bot

A Telegram bot for the GM-less tabletop RPG **Ironsworn** — for solo and co-op
play with friends in a group chat. This is **v0**.

## Playing with buttons

The bot is **button-first**: `/start` (or `/menu`, or the 🏠 Menu button) opens
an inline-keyboard main menu, and you navigate everything by tapping — make a
move, roll, ask the Oracle, manage vows/tracks/character, or play with the GM.
Every screen has 🔙 Back and 🏠 Menu. The only things you ever type are a hero's
name and a vow/track title. The slash commands below all still work as a
power-user fallback.

## Commands

- `/start`, `/menu` — friendly intro + the main button menu
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

## Optional: AI Narrator & Game Master (Ollama)

The narrator (short prose after each roll) and the AI Game Master (`/gm`) are
optional and talk to a **local [Ollama](https://ollama.ai) server** — no API
keys, nothing leaves your machine. Both fail soft: if Ollama isn't running the
bot just skips the prose, so this is entirely opt-in.

1. Install Ollama from <https://ollama.ai>.
2. Pull a model: `ollama pull mistral` (or `neural-chat`, `dolphin-mixtral`, …).
3. Run the server: `ollama serve` (listens on `http://localhost:11434`).
4. In `.env`, set `NARRATOR_ENABLED=true` and/or `GM_ENABLED=true`.
5. Optional overrides: `OLLAMA_MODEL=neural-chat` to pick another model, and
   `OLLAMA_BASE_URL=http://localhost:11434` if Ollama runs elsewhere.

These layers only ever **describe** outcomes; the `engine` always decides the
mechanics.

## Tests

```bash
pytest
```
