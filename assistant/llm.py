from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from groq import Groq
from groq import RateLimitError

from assistant.search import TavilySearch

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a private personal assistant on Telegram.

Style:
- Keep answers concise and mobile-friendly.
- Prefer short paragraphs and simple Markdown (bold, bullets, links).
- Avoid huge tables or desktop-only formatting.

Benefits & memberships:
- The user may have credit cards, warehouse clubs (e.g. Costco), streaming, or other memberships.
- They usually do NOT have PDFs. Look up public official terms using the provided web search results.
- Prefer official issuer/merchant sources over random blogs.
- Never invent benefits from training memory alone. If search results are thin, say what is uncertain.
- When you use web sources, mention them briefly and include URLs when available.

Profile:
- Use any saved profile notes (cards, memberships, preferences) when answering.
- If the user tells you about a new card or membership, acknowledge it; they can also save notes with /profile set.
"""

BENEFIT_KEYWORDS = (
    "benefit",
    "benefits",
    "credit card",
    "card",
    "membership",
    "costco",
    "amex",
    "american express",
    "chase",
    "capital one",
    "citi",
    "visa",
    "mastercard",
    "sapphire",
    "freedom",
    "platinum",
    "gold card",
    "annual fee",
    "travel credit",
    "lounge",
    "insurance",
    "warranty",
    "points",
    "miles",
    "rewards",
    "subscription",
    "perk",
    "perks",
)


@dataclass
class AssistantReply:
    text: str
    sources: list[str]


class GroqAssistant:
    def __init__(
        self,
        *,
        groq_api_key: str,
        tavily_api_key: str,
        model: str,
        search_max_results: int = 5,
    ) -> None:
        self.client = Groq(api_key=groq_api_key)
        self.model = model
        self.search = TavilySearch(tavily_api_key, max_results=search_max_results)

    def should_use_search(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(keyword in lowered for keyword in BENEFIT_KEYWORDS)

    def reply(
        self,
        *,
        user_text: str,
        history: list[dict[str, str]],
        profile_notes: dict[str, str],
        use_search: bool | None = None,
    ) -> AssistantReply:
        if use_search is None:
            use_search = self.should_use_search(user_text)

        sources: list[str] = []
        search_context = ""
        if use_search:
            query = self._search_query(user_text, profile_notes)
            try:
                results = self.search.search(query)
            except Exception:
                logger.exception("Tavily search failed")
                results = []
            search_context = self.search.format_context(results)
            sources = [item["url"] for item in results if item.get("url")]

        messages = self._build_messages(
            history=history,
            user_text=user_text,
            profile_notes=profile_notes,
            search_context=search_context if use_search else None,
        )

        text = self._generate_with_retry(messages)
        if not text:
            text = "I couldn't generate a reply. Try rephrasing your question."

        if sources and "http" not in text.lower():
            source_lines = "\n".join(f"- {url}" for url in sources[:5])
            text = f"{text}\n\nSources:\n{source_lines}"

        return AssistantReply(text=text, sources=sources)

    def _search_query(self, user_text: str, profile_notes: dict[str, str]) -> str:
        extras = []
        for key in ("cards", "memberships", "membership"):
            if key in profile_notes:
                extras.append(profile_notes[key])
        if extras:
            return f"{user_text} {' '.join(extras)} official benefits"
        return f"{user_text} official benefits guide"

    def _build_messages(
        self,
        *,
        history: list[dict[str, str]],
        user_text: str,
        profile_notes: dict[str, str],
        search_context: str | None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_instruction(profile_notes)}
        ]
        for message in history:
            role = "assistant" if message["role"] == "model" else "user"
            messages.append({"role": role, "content": message["content"]})

        if search_context is not None:
            content = (
                "Use these web search results to answer. Prefer official sources.\n\n"
                f"{search_context}\n\n"
                f"User question: {user_text}"
            )
        else:
            content = user_text
        messages.append({"role": "user", "content": content})
        return messages

    def _system_instruction(self, profile_notes: dict[str, str]) -> str:
        if not profile_notes:
            profile_block = "No saved profile notes yet."
        else:
            lines = [f"- {key}: {value}" for key, value in profile_notes.items()]
            profile_block = "Saved profile notes:\n" + "\n".join(lines)
        return f"{SYSTEM_PROMPT}\n\n{profile_block}"

    def _generate_with_retry(self, messages: list[dict[str, str]], attempts: int = 4) -> str:
        delay = 5.0
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.4,
                )
                return (completion.choices[0].message.content or "").strip()
            except RateLimitError as exc:
                last_error = exc
                if attempt == attempts:
                    raise
                logger.warning(
                    "Groq quota hit (attempt %s/%s); waiting %.0fs",
                    attempt,
                    attempts,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
        assert last_error is not None
        raise last_error
