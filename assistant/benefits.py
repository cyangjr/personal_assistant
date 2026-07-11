from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from assistant.wallet import product_key


@dataclass
class BenefitDoc:
    id: int
    product_key: str
    title: str
    summary: str
    source_url: str
    snippet: str
    fetched_at: str

    def is_fresh(self, max_age_days: int = 7) -> bool:
        fetched = datetime.fromisoformat(self.fetched_at)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - fetched <= timedelta(days=max_age_days)


class BenefitGraph:
    def __init__(self, db, search, max_age_days: int = 7) -> None:
        self.db = db
        self.search = search
        self.max_age_days = max_age_days

    def get(self, key: str) -> BenefitDoc | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM benefit_docs WHERE product_key = ?", (key,)
            ).fetchone()
        return self._row(row) if row else None

    def upsert(
        self,
        *,
        key: str,
        title: str,
        summary: str,
        source_url: str,
        snippet: str,
    ) -> BenefitDoc:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO benefit_docs
                    (product_key, title, summary, source_url, snippet, fetched_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(product_key) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    source_url = excluded.source_url,
                    snippet = excluded.snippet,
                    fetched_at = datetime('now')
                """,
                (key, title, summary, source_url, snippet),
            )
        doc = self.get(key)
        assert doc is not None
        return doc

    def ensure_product(
        self, issuer: str, product_name: str
    ) -> tuple[BenefitDoc | None, bool, int]:
        """Return (doc, cache_hit, tavily_calls)."""
        key = product_key(issuer, product_name)
        cached = self.get(key)
        if cached and cached.is_fresh(self.max_age_days):
            return cached, True, 0

        query = f"{issuer} {product_name} official benefits guide"
        results = self.search.search(query)
        if not results:
            return cached, False, 1

        top = results[0]
        summary_bits = [r.get("content", "")[:280] for r in results[:3]]
        doc = self.upsert(
            key=key,
            title=top.get("title") or f"{issuer} {product_name} benefits",
            summary="\n".join(bit for bit in summary_bits if bit),
            source_url=top.get("url") or "",
            snippet=top.get("content") or "",
        )
        return doc, False, 1

    def context_for_products(
        self, products: list[tuple[str, str]]
    ) -> tuple[str, list[str], int, int]:
        """Fetch/cache docs for products. Returns context, sources, tavily_calls, cache_hits."""
        blocks: list[str] = []
        sources: list[str] = []
        tavily_calls = 0
        cache_hits = 0
        for issuer, product_name in products:
            doc, hit, calls = self.ensure_product(issuer, product_name)
            tavily_calls += calls
            if hit:
                cache_hits += 1
            if not doc:
                continue
            blocks.append(
                f"Product: {issuer} {product_name}\n"
                f"Title: {doc.title}\n"
                f"Fetched: {doc.fetched_at}\n"
                f"URL: {doc.source_url}\n"
                f"Summary: {doc.summary or doc.snippet}"
            )
            if doc.source_url:
                sources.append(doc.source_url)
        return "\n\n".join(blocks), sources, tavily_calls, cache_hits

    def list_recent(self, limit: int = 20) -> list[BenefitDoc]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM benefit_docs
                ORDER BY fetched_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> BenefitDoc:
        return BenefitDoc(
            id=row["id"],
            product_key=row["product_key"],
            title=row["title"],
            summary=row["summary"] or "",
            source_url=row["source_url"] or "",
            snippet=row["snippet"] or "",
            fetched_at=row["fetched_at"],
        )
