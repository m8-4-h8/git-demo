# Ironsworn Telegram Bot

A Telegram bot for the GM-less tabletop RPG **Ironsworn** — for solo and co-op
play with friends in a group chat. This is **v0**: it stands up the project
structure and a working bot that responds to `/start` and `/help`.

## Architecture

The game core is frontend-independent:

- **`engine/`** — all game logic. Never imports `telegram`. Pure, fully
  unit-testable functions.
- **`bot/`** — thin Telegram layer: parse command → call `engine` → format
  reply. No game logic in handlers.
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
Telegram to confirm it responds.

## Tests

```bash
pytest
```
