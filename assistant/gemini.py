from __future__ import annotations

from dataclasses import dataclass

from google import genai
from google.genai import types

SYSTEM_PROMPT = """You are a private personal assistant on Telegram.

Style:
- Keep answers concise and mobile-friendly.
- Prefer short paragraphs and simple Markdown (bold, bullets, links).
- Avoid huge tables or desktop-only formatting.

Benefits & memberships:
- The user may have credit cards, warehouse clubs (e.g. Costco), streaming, or other memberships.
- They usually do NOT have PDFs. Look up public official terms on the web when needed.
- For card/membership benefit questions, use Google Search grounding.
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


class GeminiAssistant:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model

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

        contents = self._build_contents(history, user_text)
        config_kwargs: dict = {
            "system_instruction": self._system_instruction(profile_notes),
            "temperature": 0.4,
        }
        if use_search:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text = (response.text or "").strip()
        if not text:
            text = "I couldn't generate a reply. Try rephrasing your question."

        sources = self._extract_sources(response)
        if sources and "http" not in text.lower():
            source_lines = "\n".join(f"- {url}" for url in sources[:5])
            text = f"{text}\n\nSources:\n{source_lines}"

        return AssistantReply(text=text, sources=sources)

    def _system_instruction(self, profile_notes: dict[str, str]) -> str:
        if not profile_notes:
            profile_block = "No saved profile notes yet."
        else:
            lines = [f"- {key}: {value}" for key, value in profile_notes.items()]
            profile_block = "Saved profile notes:\n" + "\n".join(lines)
        return f"{SYSTEM_PROMPT}\n\n{profile_block}"

    def _build_contents(
        self, history: list[dict[str, str]], user_text: str
    ) -> list[types.Content]:
        contents: list[types.Content] = []
        for message in history:
            role = "user" if message["role"] == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=message["content"])],
                )
            )
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_text)],
            )
        )
        return contents

    def _extract_sources(self, response) -> list[str]:
        sources: list[str] = []
        seen: set[str] = set()

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            metadata = getattr(candidate, "grounding_metadata", None)
            if not metadata:
                continue

            chunks = getattr(metadata, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri and uri not in seen:
                    seen.add(uri)
                    sources.append(uri)

            supports = getattr(metadata, "grounding_supports", None) or []
            for support in supports:
                # Some SDK versions expose segment metadata only; chunks cover URIs.
                _ = support

        return sources
