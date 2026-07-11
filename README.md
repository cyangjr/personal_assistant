# Personal Assistant

Private Telegram bot powered by **Groq** (chat) and **Tavily** (web search for benefits). Helps with everyday questions and looks up public credit-card / membership benefits — no PDF uploads required.

## Features

- Long-polling Telegram bot (no public URL needed for local use)
- Allowlisted `chat_id`s only
- Groq `llama-3.3-70b-versatile` for replies
- SQLite conversation memory + profile notes (cards, memberships)
- Tavily web search for benefit/membership questions, with source URLs

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create a Groq key at [console.groq.com/keys](https://console.groq.com/keys).
3. Create a Tavily key at [app.tavily.com](https://app.tavily.com/home).
4. Find your Telegram chat id (message the bot once after start, or use `@userinfobot`).
5. Install and configure:

```bash
cd personal-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with TELEGRAM_BOT_TOKEN, GROQ_API_KEY, TAVILY_API_KEY, ALLOWED_CHAT_IDS
```

6. Run:

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
| `GROQ_API_KEY` | yes | Groq API key |
| `TAVILY_API_KEY` | yes | Tavily API key |
| `ALLOWED_CHAT_IDS` | yes | Comma-separated chat ids |
| `GROQ_MODEL` | no | Default `llama-3.3-70b-versatile` |
| `TAVILY_MAX_RESULTS` | no | Default `5` |
| `HISTORY_LIMIT` | no | Recent messages kept (default `20`) |
| `DATABASE_PATH` | no | SQLite path (default `data/assistant.db`) |

## Notes

- Tavily search runs only for benefit/membership-style questions to conserve free-tier search credits.
- Unauthorized chats are rejected and shown their `chat_id` so you can add them to the allowlist.
- Deploy later with a webhook host if you want the bot always online; local long polling is enough to start.
