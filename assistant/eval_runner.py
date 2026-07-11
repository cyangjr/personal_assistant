from __future__ import annotations

"""Offline eval harness for benefit Q&A quality.

Runs without live APIs by default (structure checks).
Optional --live mode calls Groq+Tavily (costs quota).
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SET = ROOT / "evals" / "benefit_qa.json"


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise SystemExit("eval set must be a JSON list")
    return data


def score_text(case: dict, text: str, sources: list[str] | None = None) -> dict:
    lowered = text.lower()
    needles = [n.lower() for n in case.get("must_include_any", [])]
    hit = any(n in lowered for n in needles) if needles else bool(text.strip())
    domain_hit = False
    preferred = case.get("preferred_domains") or []
    joined_sources = " ".join(sources or [])
    if preferred:
        domain_hit = any(domain in joined_sources or domain in lowered for domain in preferred)
    else:
        domain_hit = True
    return {
        "id": case["id"],
        "content_hit": hit,
        "domain_hit": domain_hit,
        "passed": hit and domain_hit,
    }


def run_offline(cases: list[dict]) -> int:
    """Validate eval set integrity and print coverage stats."""
    print(f"Loaded {len(cases)} eval cases from benefit QA set")
    missing = [c["id"] for c in cases if not c.get("must_include_any")]
    if missing:
        print("Cases missing must_include_any:", ", ".join(missing))
        return 1
    products = sorted({c.get("product", "?") for c in cases})
    print(f"Products covered: {len(products)}")
    for product in products:
        count = sum(1 for c in cases if c.get("product") == product)
        print(f"  - {product}: {count}")
    print("Offline structure check: PASS")
    return 0


def run_live(cases: list[dict], limit: int | None) -> int:
    from assistant.benefits import BenefitGraph
    from assistant.config import load_settings
    from assistant.db import Database
    from assistant.llm import GroqAssistant
    from assistant.search import TavilySearch

    settings = load_settings()
    db = Database(Path("data/eval.db"))
    search = TavilySearch(settings.tavily_api_key, max_results=3)
    graph = BenefitGraph(db, search)
    assistant = GroqAssistant(
        groq_api_key=settings.groq_api_key,
        model=settings.groq_model,
        benefit_graph=graph,
        search=search,
    )

    selected = cases[: limit or len(cases)]
    results = []
    for case in selected:
        product = case.get("product", "")
        wallet_products = []
        if product:
            parts = product.split(" ", 1)
            if len(parts) == 2:
                wallet_products = [(parts[0], parts[1])]
        reply = assistant.reply(
            user_text=case["question"],
            history=[],
            profile_notes={"cards": product} if product else {},
            wallet_products=wallet_products,
            use_search=True,
        )
        scored = score_text(case, reply.text, reply.sources)
        results.append(scored)
        status = "PASS" if scored["passed"] else "FAIL"
        print(f"[{status}] {case['id']}: {case['question'][:70]}")

    passed = sum(1 for r in results if r["passed"])
    print(f"\nLive score: {passed}/{len(results)} ({passed / max(len(results), 1):.0%})")
    return 0 if passed == len(results) else 2


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Benefit QA eval harness")
    parser.add_argument("--set", type=Path, default=DEFAULT_SET)
    parser.add_argument("--live", action="store_true", help="Call Groq+Tavily")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    cases = load_cases(args.set)
    code = run_live(cases, args.limit) if args.live else run_offline(cases)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
