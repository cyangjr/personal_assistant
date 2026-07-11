from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownProduct:
    item_type: str  # card | membership
    issuer: str
    product_name: str
    aliases: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.issuer} {self.product_name}".strip()

    def all_aliases(self) -> tuple[str, ...]:
        base = (
            self.label.lower(),
            self.product_name.lower(),
            f"{self.issuer.lower()} {self.product_name.lower()}",
        )
        return tuple(dict.fromkeys((*base, *(a.lower() for a in self.aliases))))


KNOWN_PRODUCTS: tuple[KnownProduct, ...] = (
    KnownProduct("card", "Chase", "Sapphire Preferred", ("csp", "chase sapphire preferred", "sapphire preferred")),
    KnownProduct("card", "Chase", "Sapphire Reserve", ("csr", "chase sapphire reserve", "sapphire reserve")),
    KnownProduct("card", "Chase", "Freedom Unlimited", ("cfu", "freedom unlimited", "chase freedom unlimited")),
    KnownProduct("card", "Chase", "Freedom Flex", ("cff", "freedom flex", "chase freedom flex")),
    KnownProduct("card", "Chase", "Ink Business Cash", ("ink cash", "chase ink business cash")),
    KnownProduct("card", "American Express", "Gold Card", ("amex gold", "american express gold", "amex gold card")),
    KnownProduct("card", "American Express", "Platinum Card", ("amex platinum", "american express platinum", "amex plat")),
    KnownProduct("card", "American Express", "Blue Business Plus", ("amex bbp", "blue business plus")),
    KnownProduct("card", "Capital One", "Venture", ("capital one venture", "venture card")),
    KnownProduct("card", "Capital One", "Venture X", ("capital one venture x", "venture x", "venturex")),
    KnownProduct("card", "Capital One", "Walmart Rewards", ("walmart rewards", "capital one walmart")),
    KnownProduct("card", "Citi", "Custom Cash", ("citi custom cash", "custom cash")),
    KnownProduct("card", "Discover", "it Cash Back", ("discover it", "discover cash back")),
    KnownProduct("card", "Wells Fargo", "Active Cash", ("active cash", "wells fargo active cash")),
    KnownProduct("card", "Bank of America", "Customized Cash Rewards", ("bofa customized cash", "customized cash rewards")),
    KnownProduct("card", "U.S. Bank", "Cash+", ("us bank cash+", "cash+")),
    KnownProduct("card", "Apple", "Card", ("apple card",)),
    KnownProduct("card", "Amazon", "Prime Visa", ("amazon prime visa", "prime visa")),
    KnownProduct("card", "Target", "RedCard", ("target redcard", "redcard")),
    KnownProduct("card", "Costco", "Anywhere Visa", ("costco visa", "costco anywhere visa")),
    KnownProduct("card", "Delta", "SkyMiles Gold", ("delta gold", "delta skymiles gold")),
    KnownProduct("card", "United", "Explorer", ("united explorer",)),
    KnownProduct("card", "Southwest", "Rapid Rewards Plus", ("southwest plus", "rapid rewards plus")),
    KnownProduct("card", "IHG", "One Rewards Premier", ("ihg premier",)),
    KnownProduct("card", "Marriott", "Bonvoy Boundless", ("marriott boundless", "bonvoy boundless")),
    KnownProduct("card", "Hilton", "Honors Surpass", ("hilton surpass", "honors surpass")),
    KnownProduct("membership", "Costco", "Executive", ("costco executive", "executive membership")),
    KnownProduct("membership", "Costco", "Gold Star", ("costco gold star", "gold star membership")),
    KnownProduct("membership", "Sam's Club", "Plus", ("sams club plus", "sam's club plus")),
    KnownProduct("membership", "Amazon", "Prime", ("amazon prime", "prime membership")),
    KnownProduct("membership", "Walmart", "+", ("walmart+", "walmart plus")),
    KnownProduct("membership", "AAA", "Membership", ("aaa", "aaa membership")),
)


# Short queries that intentionally map to multiple products.
AMBIGUOUS_QUERIES: dict[str, tuple[str, ...]] = {
    "sapphire": ("Chase Sapphire Preferred", "Chase Sapphire Reserve"),
    "chase sapphire": ("Chase Sapphire Preferred", "Chase Sapphire Reserve"),
    "venture": ("Capital One Venture", "Capital One Venture X"),
    "capital one venture": ("Capital One Venture", "Capital One Venture X"),
    "costco": ("Costco Executive", "Costco Gold Star", "Costco Anywhere Visa"),
}


@dataclass
class ResolveResult:
    status: str  # matched | ambiguous | unknown
    product: KnownProduct | None = None
    candidates: list[KnownProduct] | None = None
    query: str = ""


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("|", " ").split())


def _by_label(label: str) -> KnownProduct | None:
    lowered = label.lower()
    for product in KNOWN_PRODUCTS:
        if product.label.lower() == lowered:
            return product
    return None


def resolve_product_query(query: str) -> ResolveResult:
    """Resolve a natural product phrase to a known card/membership."""
    normalized = _normalize(query)
    if not normalized:
        return ResolveResult(status="unknown", query=query)

    if normalized in AMBIGUOUS_QUERIES:
        candidates = []
        for label in AMBIGUOUS_QUERIES[normalized]:
            product = _by_label(label)
            if product:
                candidates.append(product)
        if len(candidates) > 1:
            return ResolveResult(status="ambiguous", candidates=candidates, query=query)

    scored: list[tuple[int, KnownProduct]] = []
    for product in KNOWN_PRODUCTS:
        best = 0
        for alias in product.all_aliases():
            if normalized == alias:
                best = max(best, 1000 + len(alias))
            elif alias in normalized:
                best = max(best, 100 + len(alias))
            elif normalized in alias:
                best = max(best, 50 + len(normalized))
        if best > 0:
            scored.append((best, product))

    if not scored:
        return ResolveResult(status="unknown", query=query)

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score = scored[0][0]
    top = [product for score, product in scored if score == top_score]
    if len(top) > 1:
        return ResolveResult(status="ambiguous", candidates=top, query=query)
    return ResolveResult(status="matched", product=top[0], query=query)


def format_candidate_prompt(candidates: list[KnownProduct], query: str) -> str:
    lines = [f'Which one did you mean by "{query}"?']
    for i, product in enumerate(candidates, start=1):
        lines.append(f"{i}. {product.label} ({product.item_type})")
    lines.append("Reply with the number (e.g. 1), or /wallet add with the full name.")
    return "\n".join(lines)
