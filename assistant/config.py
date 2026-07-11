from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    groq_api_key: str
    tavily_api_key: str
    allowed_chat_ids: frozenset[int]
    groq_model: str = "llama-3.3-70b-versatile"
    history_limit: int = 20
    database_path: Path = Path("data/assistant.db")
    tavily_max_results: int = 5


def _parse_chat_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.add(int(part))
    return frozenset(ids)


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    allowed_raw = os.getenv("ALLOWED_CHAT_IDS", "").strip()

    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not groq_key:
        missing.append("GROQ_API_KEY")
    if not tavily_key:
        missing.append("TAVILY_API_KEY")
    if not allowed_raw:
        missing.append("ALLOWED_CHAT_IDS")
    if missing:
        raise SystemExit(
            "Missing required env vars: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill them in."
        )

    return Settings(
        telegram_bot_token=token,
        groq_api_key=groq_key,
        tavily_api_key=tavily_key,
        allowed_chat_ids=_parse_chat_ids(allowed_raw),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        history_limit=int(os.getenv("HISTORY_LIMIT", "20")),
        database_path=Path(os.getenv("DATABASE_PATH", "data/assistant.db")),
        tavily_max_results=int(os.getenv("TAVILY_MAX_RESULTS", "5")),
    )
