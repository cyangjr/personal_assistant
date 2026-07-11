from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UsageStats:
    events: int
    avg_latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    tavily_calls: int
    cache_hits: int
    cache_hit_rate: float
    estimated_groq_cost_usd: float


class MetricsStore:
    # Rough Groq llama-3.3-70b-versatile pricing for dashboard estimates.
    INPUT_PER_MTOK = 0.59
    OUTPUT_PER_MTOK = 0.79

    def __init__(self, db) -> None:
        self.db = db

    def record(
        self,
        *,
        chat_id: int | None,
        kind: str,
        latency_ms: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        tavily_calls: int = 0,
        cache_hit: bool = False,
        model: str | None = None,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events
                    (chat_id, kind, latency_ms, prompt_tokens, completion_tokens,
                     tavily_calls, cache_hit, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    kind,
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    tavily_calls,
                    1 if cache_hit else 0,
                    model,
                ),
            )

    def summary(self, days: int = 7) -> UsageStats:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS events,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(tavily_calls), 0) AS tavily_calls,
                    COALESCE(SUM(cache_hit), 0) AS cache_hits
                FROM usage_events
                WHERE created_at >= datetime('now', ?)
                """,
                (f"-{days} days",),
            ).fetchone()
        events = int(row["events"] or 0)
        cache_hits = int(row["cache_hits"] or 0)
        tavily_calls = int(row["tavily_calls"] or 0)
        denom = cache_hits + tavily_calls
        hit_rate = (cache_hits / denom) if denom else 0.0
        prompt = int(row["prompt_tokens"] or 0)
        completion = int(row["completion_tokens"] or 0)
        cost = (
            prompt / 1_000_000 * self.INPUT_PER_MTOK
            + completion / 1_000_000 * self.OUTPUT_PER_MTOK
        )
        return UsageStats(
            events=events,
            avg_latency_ms=float(row["avg_latency_ms"] or 0),
            prompt_tokens=prompt,
            completion_tokens=completion,
            tavily_calls=tavily_calls,
            cache_hits=cache_hits,
            cache_hit_rate=hit_rate,
            estimated_groq_cost_usd=cost,
        )

    def format_summary(self, days: int = 7) -> str:
        stats = self.summary(days)
        return (
            f"Usage last {days} days\n"
            f"- events: {stats.events}\n"
            f"- avg latency: {stats.avg_latency_ms:.0f} ms\n"
            f"- tokens in/out: {stats.prompt_tokens}/{stats.completion_tokens}\n"
            f"- est. Groq cost: ${stats.estimated_groq_cost_usd:.4f}\n"
            f"- Tavily calls: {stats.tavily_calls}\n"
            f"- benefit cache hits: {stats.cache_hits} "
            f"({stats.cache_hit_rate:.0%} of fetch attempts)"
        )
