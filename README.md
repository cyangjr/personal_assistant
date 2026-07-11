# Personal Assistant

Private Telegram bot powered by Google AI Studio (Gemini). Helps with everyday questions and looks up public credit-card / membership benefits on the web when needed — no PDF uploads required.

## Features

- Long-polling Telegram bot (no public URL needed for local use)
- Allowlisted `chat_id`s only
- Gemini `gemini-2.5-flash` via AI Studio API key
- SQLite conversation memory + profile notes (cards, memberships)
- Google Search grounding for benefit/membership questions, with source URLs when available

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create an API key in [Google AI Studio](https://aistudio.google.com/apikey).
3. Find your Telegram chat id (message the bot once after start, or use a helper like `@userinfobot`).
4. Install and configure:

```bash
cd personal-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ALLOWED_CHAT_IDS
```

5. Run:

```bash
python -m assistant.main
```

Then open Telegram and message your bot.

## Commands

| Command | What it does |
| --- | --- |
| `/start` | Intro |
| `/help` | Help |
| `/clear` | Clear conversation memory |
| `/profile` | Show saved notes |
| `/profile set cards Chase Sapphire Preferred, Costco Executive` | Save a note |
| `/profile del cards` | Delete a note |

## Environment

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | BotFather token |
| `GEMINI_API_KEY` | yes | AI Studio API key |
| `ALLOWED_CHAT_IDS` | yes | Comma-separated chat ids |
| `GEMINI_MODEL` | no | Default `gemini-2.5-flash` |
| `HISTORY_LIMIT` | no | Recent messages kept (default `20`) |
| `DATABASE_PATH` | no | SQLite path (default `data/assistant.db`) |

## Notes

- Search grounding is enabled automatically for benefit/membership-style questions to conserve free-tier search quota.
- Unauthorized chats are rejected and shown their `chat_id` so you can add them to the allowlist.
- Deploy later with a webhook host if you want the bot always online; local long polling is enough to start.
