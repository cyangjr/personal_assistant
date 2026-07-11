from __future__ import annotations

import logging

from assistant.bot import BotApp
from assistant.config import load_settings


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    settings = load_settings()
    bot = BotApp(settings)
    app = bot.build()
    logging.getLogger(__name__).info(
        "Starting personal assistant (model=%s, allowlist=%s)",
        settings.gemini_model,
        sorted(settings.allowed_chat_ids),
    )
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
