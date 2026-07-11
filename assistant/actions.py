from __future__ import annotations

"""Known claim/action helpers for common cards and memberships.

Matching is product-specific: longer/more precise tokens win, and `exclude`
prevents base products (e.g. Venture) from matching premium variants (Venture X).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionHelper:
    key: str
    title: str
    include: tuple[str, ...]  # lowercase substrings; any match qualifies
    steps: tuple[str, ...]
    links: tuple[tuple[str, str], ...]  # (label, url)
    exclude: tuple[str, ...] = ()  # if present in label, this action does not apply
    estimated_value_hint: str = ""


ACTION_CATALOG: list[ActionHelper] = [
    ActionHelper(
        key="chase_sapphire_preferred_travel_credit",
        title="Claim Chase Sapphire Preferred travel credit",
        include=("sapphire preferred", "csp"),
        exclude=("sapphire reserve", "csr"),
        estimated_value_hint="Typically $50 hotel credit via Ultimate Rewards (confirm current terms)",
        steps=(
            "Confirm the card is Sapphire Preferred (not Reserve).",
            "Book eligible hotel travel through Chase Ultimate Rewards when required by current terms.",
            "Check Ultimate Rewards / statements for the credit posting.",
            "If missing after statement close, secure-message Chase with charge date/amount.",
        ),
        links=(
            ("Chase Ultimate Rewards", "https://ultimaterewards.chase.com/"),
            ("Chase login", "https://secure.chase.com/"),
        ),
    ),
    ActionHelper(
        key="chase_sapphire_reserve_travel_credit",
        title="Claim Chase Sapphire Reserve travel credit",
        include=("sapphire reserve", "csr"),
        exclude=("sapphire preferred",),
        estimated_value_hint="Higher annual travel credit than Preferred (confirm current CSR terms)",
        steps=(
            "Confirm the card is Sapphire Reserve (not Preferred).",
            "Pay for eligible travel categories on the Reserve card per current Chase terms.",
            "Watch for statement credits; CSR credits often auto-post on eligible spend.",
            "If a credit is missing, secure-message Chase with the merchant, date, and amount.",
        ),
        links=(
            ("Chase Ultimate Rewards", "https://ultimaterewards.chase.com/"),
            ("Chase login", "https://secure.chase.com/"),
        ),
    ),
    ActionHelper(
        key="amex_gold_dining_credit",
        title="Use Amex Gold dining credits",
        include=("amex gold", "american express gold", "gold card"),
        exclude=("platinum", "green card", "blue cash"),
        estimated_value_hint="Monthly dining credits when enrolled",
        steps=(
            "Open Amex app → Benefits / Offer hub.",
            "Enroll in the current dining credit (Uber Cash / dining partners as applicable).",
            "Pay with the Gold Card at an eligible merchant in the statement period.",
            "Verify credit posts; re-enroll each period if required.",
        ),
        links=(
            ("Amex offers", "https://www.americanexpress.com/en-us/account/login"),
        ),
    ),
    ActionHelper(
        key="costco_executive_reward",
        title="Maximize Costco Executive 2% reward",
        include=("costco executive", "executive membership"),
        exclude=("gold star",),
        estimated_value_hint="2% reward on qualifying Costco purchases",
        steps=(
            "Confirm membership is Executive (not Gold Star).",
            "Track YTD qualifying spend in Costco account online/app.",
            "Use membership for Costco.com / warehouse / services that earn the reward.",
            "Redeem annual reward certificate when issued (usually anniversary window).",
        ),
        links=(
            ("Costco account", "https://www.costco.com/LogonForm"),
            ("Membership info", "https://www.costco.com/join-costco.html"),
        ),
    ),
    ActionHelper(
        key="capital_one_venture_x_miles",
        title="Use Capital One Venture X benefits",
        include=("venture x", "venturex"),
        estimated_value_hint="Lounge access + travel credits + miles (confirm current Venture X terms)",
        steps=(
            "Confirm the card is Venture X (not standard Venture / VentureOne).",
            "Check Capital One Travel / benefits hub for anniversary credits and lounge access.",
            "Redeem miles via purchase eraser or Capital One Travel portal.",
            "Track annual credits before card anniversary.",
        ),
        links=(
            ("Capital One", "https://www.capitalone.com/"),
        ),
    ),
    ActionHelper(
        key="capital_one_venture_miles",
        title="Redeem Capital One Venture miles",
        include=("venture", "capital one venture"),
        exclude=("venture x", "venturex", "ventureone", "venture one"),
        estimated_value_hint="Travel purchase eraser / portal redemptions",
        steps=(
            "Confirm the card is standard Venture (not Venture X).",
            "Open Capital One app → Miles / Rewards.",
            "For purchase eraser: select a recent travel charge and apply miles.",
            "Or book via Capital One Travel portal if that rates better for your trip.",
        ),
        links=(
            ("Capital One", "https://www.capitalone.com/"),
        ),
    ),
    ActionHelper(
        key="citi_custom_cash",
        title="Set Citi Custom Cash category",
        include=("custom cash", "citi custom cash"),
        estimated_value_hint="5% on top eligible category each billing cycle",
        steps=(
            "Open Citi app → Custom Cash benefits.",
            "Choose/confirm the 5% category for the current billing cycle.",
            "Put spend in that category on this card first.",
        ),
        links=(
            ("Citi login", "https://online.citi.com/"),
        ),
    ),
]


def _match_score(action: ActionHelper, lowered: str) -> int:
    """Return specificity score, or 0 if no match."""
    if any(token in lowered for token in action.exclude):
        return 0
    best = 0
    for token in action.include:
        if token in lowered:
            best = max(best, len(token))
    return best


def find_actions_for_product(label: str) -> list[ActionHelper]:
    lowered = label.lower()
    scored: list[tuple[int, ActionHelper]] = []
    for action in ACTION_CATALOG:
        score = _match_score(action, lowered)
        if score > 0:
            scored.append((score, action))
    if not scored:
        return []
    # Keep only the most specific matches (handles CSP vs CSR, Venture vs Venture X).
    top = max(score for score, _ in scored)
    return [action for score, action in scored if score == top]


def get_action(key: str) -> ActionHelper | None:
    for action in ACTION_CATALOG:
        if action.key == key:
            return action
    return None


def format_action(action: ActionHelper) -> str:
    lines = [f"*{action.title}*"]
    if action.estimated_value_hint:
        lines.append(f"Value hint: {action.estimated_value_hint}")
    lines.append("Steps:")
    for i, step in enumerate(action.steps, start=1):
        lines.append(f"{i}. {step}")
    if action.links:
        lines.append("Links:")
        for label, url in action.links:
            lines.append(f"- {label}: {url}")
    return "\n".join(lines)


def format_actions_for_label(label: str) -> str:
    actions = find_actions_for_product(label)
    if not actions:
        return (
            f"No saved claim checklist for '{label}' yet.\n"
            "Ask me about benefits and I'll search official sources."
        )
    return "\n\n".join(format_action(action) for action in actions)
