# Personal Assistant

Private Telegram bot powered by **Groq** (chat) and **Tavily** (web search). Focused on credit-card / membership benefits: structured wallet, cached benefit graph, opportunity alerts, claim checklists, evals, and usage stats.

## Features

1. **Structured wallet** — typed cards/memberships (`/wallet`)
2. **Benefit graph** — cached official lookups with source URL + fetch time (`/benefits`)
3. **Opportunity engine** — weekly (or `/opportunities scan`) unused-value alerts
4. **Action helpers** — claim checklists + deep links (`/claim`)
5. **Eval harness** — 50 benefit QA cases (`python -m assistant.eval_runner`)
6. **Cost/latency dashboard** — `/stats`

Also: allowlisted chats, SQLite memory, Tavily only for benefit-style questions.

## Setup

```bash
cd personal-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill TELEGRAM_BOT_TOKEN, GROQ_API_KEY, TAVILY_API_KEY, ALLOWED_CHAT_IDS
python -m assistant.main
```

## Key commands

| Command | Purpose |
| --- | --- |
| `/wallet add card Chase \| Sapphire Preferred fee=95` | Add card |
| `/wallet add membership Costco \| Executive fee=120 renew=2026-12-01` | Add membership |
| `/opportunities` / `/opportunities scan` | View / refresh opportunities |
| `/claim chase_sapphire_travel_credit` | Claim checklist |
| `/benefits` | Cached benefit docs |
| `/stats` | Usage / cost / cache hit rate |

## Evals

```bash
python -m assistant.eval_runner          # offline structure check (50 cases)
python -m assistant.eval_runner --live --limit 5   # live Groq+Tavily (uses quota)
```

## Environment

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | BotFather token |
| `GROQ_API_KEY` | yes | Groq API key |
| `TAVILY_API_KEY` | yes | Tavily API key |
| `ALLOWED_CHAT_IDS` | yes | Comma-separated chat ids |
| `GROQ_MODEL` | no | Default `llama-3.3-70b-versatile` |
| `OPPORTUNITY_INTERVAL_SECONDS` | no | Default weekly (`604800`) |
