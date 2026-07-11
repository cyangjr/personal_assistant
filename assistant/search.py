from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TavilySearch:
    """Thin client for Tavily web search."""

    def __init__(self, api_key: str, max_results: int = 5) -> None:
        self.api_key = api_key
        self.max_results = max_results

    def search(self, query: str) -> list[dict[str, str]]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": self.max_results,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()

        results: list[dict[str, str]] = []
        for item in data.get("results", []):
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()
            if not url and not content:
                continue
            results.append({"url": url, "title": title, "content": content})
        return results

    def format_context(self, results: list[dict[str, str]]) -> str:
        if not results:
            return "No web search results found."
        blocks = []
        for i, item in enumerate(results, start=1):
            blocks.append(
                f"[{i}] {item.get('title') or 'Untitled'}\n"
                f"URL: {item.get('url') or 'n/a'}\n"
                f"{item.get('content') or ''}"
            )
        return "\n\n".join(blocks)
