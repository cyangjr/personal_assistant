from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from assistant.auth import is_allowed
from assistant.config import Settings
from assistant.gemini import GeminiAssistant
from assistant.memory import MemoryStore

logger = logging.getLogger(__name__)

HELP_TEXT = """*Personal Assistant*

Commands:
/start — intro
/help — this help
/clear — clear conversation memory
/profile — show saved notes
/profile set `<key>` `<value>` — save a note \\(e\\.g\\. cards, memberships\\)
/profile del `<key>` — delete a note

Just chat normally for everything else\\. For credit\\-card or membership benefit questions, I look up public web sources when needed\\.
"""


class BotApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.memory = MemoryStore(settings.database_path)
        self.assistant = GeminiAssistant(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    def build(self) -> Application:
        app = (
            Application.builder()
            .token(self.settings.telegram_bot_token)
            .build()
        )
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("clear", self.clear))
        app.add_handler(CommandHandler("profile", self.profile))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text)
        )
        return app

    async def _reject_if_unauthorized(self, update: Update) -> bool:
        chat = update.effective_chat
        if chat is None:
            return True
        if is_allowed(chat.id, self.settings.allowed_chat_ids):
            return False
        logger.warning("Rejected unauthorized chat_id=%s", chat.id)
        if update.effective_message:
            await update.effective_message.reply_text(
                "This bot is private. Your chat is not on the allowlist.\n"
                f"Your chat id: `{chat.id}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        return True

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return
        await update.effective_message.reply_text(
            "Hi — I'm your private personal assistant.\n"
            "Ask me anything. For cards/memberships, tell me what you have "
            "(/profile set cards ...) and ask about benefits.\n\n"
            "Try /help for commands."
        )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return
        await update.effective_message.reply_text(
            HELP_TEXT, parse_mode=ParseMode.MARKDOWN_V2
        )

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return
        chat_id = update.effective_chat.id
        self.memory.clear_messages(chat_id)
        await update.effective_message.reply_text("Conversation memory cleared.")

    async def profile(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return

        chat_id = update.effective_chat.id
        args = context.args or []

        if not args:
            await update.effective_message.reply_text(
                self.memory.format_profile(chat_id)
            )
            return

        action = args[0].lower()
        if action == "set":
            if len(args) < 3:
                await update.effective_message.reply_text(
                    "Usage: /profile set <key> <value>\n"
                    "Example: /profile set cards Chase Sapphire Preferred, Costco Executive"
                )
                return
            key = args[1]
            value = " ".join(args[2:])
            self.memory.set_profile_note(chat_id, key, value)
            await update.effective_message.reply_text(f"Saved `{key}`.", parse_mode=ParseMode.MARKDOWN)
            return

        if action in {"del", "delete", "rm"}:
            if len(args) < 2:
                await update.effective_message.reply_text(
                    "Usage: /profile del <key>"
                )
                return
            key = args[1]
            deleted = self.memory.delete_profile_note(chat_id, key)
            if deleted:
                await update.effective_message.reply_text(f"Deleted `{key}`.", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.effective_message.reply_text(f"No note named `{key}`.", parse_mode=ParseMode.MARKDOWN)
            return

        await update.effective_message.reply_text(
            "Usage:\n"
            "/profile\n"
            "/profile set <key> <value>\n"
            "/profile del <key>"
        )

    async def on_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return

        message = update.effective_message
        chat_id = update.effective_chat.id
        user_text = (message.text or "").strip()
        if not user_text:
            return

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        history = self.memory.get_recent_messages(
            chat_id, self.settings.history_limit
        )
        profile = self.memory.get_profile_notes(chat_id)

        try:
            reply = self.assistant.reply(
                user_text=user_text,
                history=history,
                profile_notes=profile,
            )
        except Exception:
            logger.exception("Gemini request failed for chat_id=%s", chat_id)
            await message.reply_text(
                "Something went wrong talking to Gemini. Try again in a moment."
            )
            return

        self.memory.add_message(chat_id, "user", user_text)
        self.memory.add_message(chat_id, "model", reply.text)

        await self._send_reply(message, reply.text)

    async def _send_reply(self, message, text: str) -> None:
        # Telegram Markdown can fail on model output; fall back to plain text.
        try:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            try:
                safe = escape_markdown(text, version=2)
                await message.reply_text(safe, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception:
                await message.reply_text(text)
