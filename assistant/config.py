from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    allowed_chat_ids: frozenset[int]
    gemini_model: str = "gemini-2.5-flash"
    history_limit: int = 20
    database_path: Path = Path("data/assistant.db")


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
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    allowed_raw = os.getenv("ALLOWED_CHAT_IDS", "").strip()

    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not api_key:
        missing.append("GEMINI_API_KEY")
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
        gemini_api_key=api_key,
        allowed_chat_ids=_parse_chat_ids(allowed_raw),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        history_limit=int(os.getenv("HISTORY_LIMIT", "20")),
        database_path=Path(os.getenv("DATABASE_PATH", "data/assistant.db")),
    )
