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

from assistant.actions import format_action, format_actions_for_label, get_action
from assistant.auth import is_allowed
from assistant.benefits import BenefitGraph
from assistant.config import Settings
from assistant.db import Database
from assistant.llm import GroqAssistant
from assistant.memory import MemoryStore
from assistant.metrics import MetricsStore
from assistant.opportunities import OpportunityEngine
from assistant.search import TavilySearch
from assistant.wallet import WalletStore, parse_wallet_add_args

logger = logging.getLogger(__name__)

HELP_TEXT = """*Personal Assistant*

Wallet & benefits:
/wallet — show structured cards/memberships
/wallet add card Issuer \\| Product
/wallet add membership Issuer \\| Product fee\\=120 renew\\=2026\\-12\\-01
/wallet del `<id>`
/opportunities — unused\\-value opportunities
/opportunities scan — refresh opportunities now
/claim `<action_key or product>` — claim checklist
/benefits — cached benefit docs
/stats — cost \\& latency dashboard

Memory:
/clear — clear chat memory
/profile — freeform notes \\(legacy\\)

Chat normally for everything else\\. Benefit questions use Tavily \\+ the benefit graph\\.
"""


class BotApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_path)
        self.memory = MemoryStore(self.db)
        self.wallet = WalletStore(self.db)
        self.search = TavilySearch(
            settings.tavily_api_key, max_results=settings.tavily_max_results
        )
        self.benefits = BenefitGraph(self.db, self.search)
        self.opportunities = OpportunityEngine(self.db, self.wallet, self.benefits)
        self.metrics = MetricsStore(self.db)
        self.assistant = GroqAssistant(
            groq_api_key=settings.groq_api_key,
            model=settings.groq_model,
            benefit_graph=self.benefits,
            search=self.search,
        )

    def build(self) -> Application:
        builder = Application.builder().token(self.settings.telegram_bot_token)
        app = builder.build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("clear", self.clear))
        app.add_handler(CommandHandler("profile", self.profile))
        app.add_handler(CommandHandler("wallet", self.wallet_command))
        app.add_handler(CommandHandler("opportunities", self.opportunities_command))
        app.add_handler(CommandHandler("claim", self.claim_command))
        app.add_handler(CommandHandler("benefits", self.benefits_command))
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text)
        )
        if app.job_queue is not None:
            app.job_queue.run_repeating(
                self.weekly_opportunity_job,
                interval=self.settings.opportunity_interval_seconds,
                first=60,
                name="weekly_opportunities",
            )
        else:
            logger.warning(
                "JobQueue unavailable; install python-telegram-bot[job-queue] "
                "for weekly opportunity scans. Use /opportunities scan meanwhile."
            )
        return app

    async def weekly_opportunity_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        for chat_id in self.settings.allowed_chat_ids:
            created = self.opportunities.scan_chat(chat_id)
            self.metrics.record(
                chat_id=chat_id,
                kind="opportunity_scan",
                tavily_calls=0,
            )
            if not created:
                continue
            preview = "\n".join(f"- {opp.title}" for opp in created[:5])
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"Found {len(created)} new opportunity(ies):\n{preview}\n\n"
                        "See /opportunities or /claim <action_key>."
                    ),
                )
            except Exception:
                logger.exception("Failed to send opportunity alert to %s", chat_id)

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
            "Hi — I'm your private benefits assistant.\n"
            "1) Add cards/memberships with /wallet\n"
            "2) Ask about benefits\n"
            "3) Check /opportunities for unused value\n\n"
            "Try /help."
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
                + "\n\nPrefer /wallet for structured cards/memberships."
            )
            return

        action = args[0].lower()
        if action == "set":
            if len(args) < 3:
                await update.effective_message.reply_text(
                    "Usage: /profile set <key> <value>"
                )
                return
            key = args[1]
            value = " ".join(args[2:])
            self.memory.set_profile_note(chat_id, key, value)
            await update.effective_message.reply_text(
                f"Saved `{key}`.", parse_mode=ParseMode.MARKDOWN
            )
            return

        if action in {"del", "delete", "rm"}:
            if len(args) < 2:
                await update.effective_message.reply_text("Usage: /profile del <key>")
                return
            key = args[1]
            deleted = self.memory.delete_profile_note(chat_id, key)
            msg = f"Deleted `{key}`." if deleted else f"No note named `{key}`."
            await update.effective_message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        await update.effective_message.reply_text(
            "Usage:\n/profile\n/profile set <key> <value>\n/profile del <key>"
        )

    async def wallet_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return
        chat_id = update.effective_chat.id
        args = context.args or []
        if not args:
            await update.effective_message.reply_text(self.wallet.format(chat_id))
            return

        action = args[0].lower()
        if action == "add":
            try:
                parsed = parse_wallet_add_args(args[1:])
                item = self.wallet.add(chat_id=chat_id, **parsed)
            except Exception as exc:
                await update.effective_message.reply_text(
                    "Could not add wallet item.\n"
                    "Example: /wallet add card Chase | Sapphire Preferred fee=95\n"
                    f"Error: {exc}"
                )
                return
            await update.effective_message.reply_text(
                f"Added #{item.id} [{item.item_type}] {item.label()}"
            )
            return

        if action in {"del", "delete", "rm"}:
            if len(args) < 2 or not args[1].isdigit():
                await update.effective_message.reply_text("Usage: /wallet del <id>")
                return
            deleted = self.wallet.delete(chat_id, int(args[1]))
            await update.effective_message.reply_text(
                "Deleted." if deleted else "No wallet item with that id."
            )
            return

        await update.effective_message.reply_text(self.wallet.format(chat_id))

    async def opportunities_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return
        chat_id = update.effective_chat.id
        args = context.args or []
        if args and args[0].lower() == "scan":
            created = self.opportunities.scan_chat(chat_id)
            self.metrics.record(chat_id=chat_id, kind="opportunity_scan")
            await update.effective_message.reply_text(
                f"Scan complete. New opportunities: {len(created)}\n\n"
                + self.opportunities.format_open(chat_id)
            )
            return
        await update.effective_message.reply_text(
            self.opportunities.format_open(chat_id)
        )

    async def claim_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return
        args = context.args or []
        if not args:
            await update.effective_message.reply_text(
                "Usage: /claim <action_key or product text>\n"
                "Example: /claim chase_sapphire_travel_credit\n"
                "Or: /claim sapphire preferred"
            )
            return
        key_or_label = " ".join(args)
        action = get_action(key_or_label)
        if action:
            await update.effective_message.reply_text(format_action(action))
            return
        await update.effective_message.reply_text(
            format_actions_for_label(key_or_label)
        )

    async def benefits_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return
        docs = self.benefits.list_recent(15)
        if not docs:
            await update.effective_message.reply_text(
                "Benefit graph is empty. Ask a benefits question or /opportunities scan."
            )
            return
        lines = ["Cached benefit docs:"]
        for doc in docs:
            lines.append(f"- {doc.product_key} ({doc.fetched_at})")
            if doc.source_url:
                lines.append(f"  {doc.source_url}")
        await update.effective_message.reply_text("\n".join(lines))

    async def stats_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return
        await update.effective_message.reply_text(self.metrics.format_summary(7))

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
        wallet_ctx = self.wallet.as_profile_context(chat_id)
        merged_profile = {**profile, **wallet_ctx}
        wallet_products = [
            (item.issuer, item.product_name) for item in self.wallet.list(chat_id)
        ]

        try:
            reply = self.assistant.reply(
                user_text=user_text,
                history=history,
                profile_notes=merged_profile,
                wallet_products=wallet_products,
            )
        except Exception as exc:
            logger.exception("Assistant request failed for chat_id=%s", chat_id)
            detail = str(exc)
            if "429" in detail or "rate_limit" in detail.lower():
                await message.reply_text(
                    "API rate limit hit right now. Wait a minute and try again."
                )
                return
            short = detail.split("\n", 1)[0][:240]
            await message.reply_text(
                "Something went wrong generating a reply.\n"
                f"`{short}`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        self.metrics.record(
            chat_id=chat_id,
            kind="chat",
            latency_ms=reply.latency_ms,
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
            tavily_calls=reply.tavily_calls,
            cache_hit=reply.cache_hit,
            model=self.settings.groq_model,
        )
        self.memory.add_message(chat_id, "user", user_text)
        self.memory.add_message(chat_id, "model", reply.text)
        await self._send_reply(message, reply.text)

    async def _send_reply(self, message, text: str) -> None:
        try:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            try:
                safe = escape_markdown(text, version=2)
                await message.reply_text(safe, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception:
                await message.reply_text(text)
