from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from groq import Groq
from groq import RateLimitError

from assistant.benefits import BenefitGraph
from assistant.search import TavilySearch

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a private personal assistant on Telegram focused on cards, memberships, and everyday help.

Style:
- Keep answers concise and mobile-friendly.
- Prefer short paragraphs and simple Markdown (bold, bullets, links).
- Avoid huge tables or desktop-only formatting.

Benefits & memberships:
- Prefer the provided benefit graph / web search context over training memory.
- Prefer official issuer/merchant sources over random blogs.
- Never invent benefits. If evidence is thin, say what is uncertain.
- Always cite source URLs when available.
- When relevant, mention /claim <action_key> checklists for how to redeem.

Wallet:
- Use the user's structured wallet items when answering.
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
    "claim",
    "credit",
)


@dataclass
class AssistantReply:
    text: str
    sources: list[str] = field(default_factory=list)
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tavily_calls: int = 0
    cache_hit: bool = False


class GroqAssistant:
    def __init__(
        self,
        *,
        groq_api_key: str,
        model: str,
        benefit_graph: BenefitGraph,
        search: TavilySearch | None = None,
    ) -> None:
        self.client = Groq(api_key=groq_api_key)
        self.model = model
        self.benefit_graph = benefit_graph
        self.search = search or benefit_graph.search

    def should_use_search(self, user_text: str) -> bool:
        lowered = user_text.lower()
        return any(keyword in lowered for keyword in BENEFIT_KEYWORDS)

    def reply(
        self,
        *,
        user_text: str,
        history: list[dict[str, str]],
        profile_notes: dict[str, str],
        wallet_products: list[tuple[str, str]] | None = None,
        use_search: bool | None = None,
    ) -> AssistantReply:
        started = time.perf_counter()
        if use_search is None:
            use_search = self.should_use_search(user_text)

        sources: list[str] = []
        search_context = ""
        tavily_calls = 0
        cache_hit = False

        if use_search and wallet_products:
            graph_ctx, graph_sources, calls, hits = self.benefit_graph.context_for_products(
                wallet_products
            )
            tavily_calls += calls
            cache_hit = hits > 0 and calls == 0
            if graph_ctx:
                search_context = "Benefit graph (cached/official lookups):\n" + graph_ctx
            sources.extend(graph_sources)

        if use_search:
            query = self._search_query(user_text, profile_notes)
            try:
                results = self.search.search(query)
                tavily_calls += 1
            except Exception:
                logger.exception("Tavily search failed")
                results = []
            live_ctx = self.search.format_context(results)
            if search_context:
                search_context = f"{search_context}\n\nLive search:\n{live_ctx}"
            else:
                search_context = live_ctx
            sources.extend(item["url"] for item in results if item.get("url"))

        messages = self._build_messages(
            history=history,
            user_text=user_text,
            profile_notes=profile_notes,
            search_context=search_context if use_search else None,
        )

        text, prompt_tokens, completion_tokens = self._generate_with_retry(messages)
        if not text:
            text = "I couldn't generate a reply. Try rephrasing your question."

        # Dedupe sources preserving order
        deduped: list[str] = []
        seen: set[str] = set()
        for url in sources:
            if url and url not in seen:
                seen.add(url)
                deduped.append(url)
        sources = deduped

        if sources and "http" not in text.lower():
            source_lines = "\n".join(f"- {url}" for url in sources[:5])
            text = f"{text}\n\nSources:\n{source_lines}"

        latency_ms = int((time.perf_counter() - started) * 1000)
        return AssistantReply(
            text=text,
            sources=sources,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tavily_calls=tavily_calls,
            cache_hit=cache_hit,
        )

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
                "Use these retrieved sources to answer. Prefer official sources.\n\n"
                f"{search_context}\n\n"
                f"User question: {user_text}"
            )
        else:
            content = user_text
        messages.append({"role": "user", "content": content})
        return messages

    def _system_instruction(self, profile_notes: dict[str, str]) -> str:
        if not profile_notes:
            profile_block = "No saved wallet/profile notes yet."
        else:
            lines = [f"- {key}: {value}" for key, value in profile_notes.items()]
            profile_block = "Saved wallet/profile notes:\n" + "\n".join(lines)
        return f"{SYSTEM_PROMPT}\n\n{profile_block}"

    def _generate_with_retry(
        self, messages: list[dict[str, str]], attempts: int = 4
    ) -> tuple[str, int, int]:
        delay = 5.0
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.4,
                )
                text = (completion.choices[0].message.content or "").strip()
                usage = getattr(completion, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                return text, prompt_tokens, completion_tokens
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
