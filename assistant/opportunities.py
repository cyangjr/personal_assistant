from __future__ import annotations

from dataclasses import dataclass

from assistant.actions import find_actions_for_product
from assistant.wallet import WalletItem, days_until


@dataclass
class Opportunity:
    id: int
    chat_id: int
    wallet_item_id: int | None
    title: str
    detail: str
    estimated_value: float | None
    action_key: str | None
    status: str


class OpportunityEngine:
    def __init__(self, db, wallet_store, benefit_graph) -> None:
        self.db = db
        self.wallet = wallet_store
        self.benefits = benefit_graph

    def scan_chat(self, chat_id: int, *, warm_cache: bool = False) -> list[Opportunity]:
        items = self.wallet.list(chat_id)
        created: list[Opportunity] = []
        for item in items:
            for draft in self._drafts_for_item(item):
                if self._exists_open(chat_id, draft["title"]):
                    continue
                created.append(self._insert(chat_id, item.id, draft))
            if warm_cache:
                try:
                    self.benefits.ensure_product(item.issuer, item.product_name)
                except Exception:
                    pass
        return created

    def list_open(self, chat_id: int) -> list[Opportunity]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM opportunities
                WHERE chat_id = ? AND status = 'open'
                ORDER BY id DESC
                """,
                (chat_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def format_open(self, chat_id: int, *, hint: str | None = None) -> str:
        opps = self.list_open(chat_id)
        if not opps:
            wallet_count = len(self.wallet.list(chat_id))
            if wallet_count == 0:
                return (
                    "No open opportunities.\n"
                    "Add cards/memberships first, e.g.\n"
                    "/wallet add Chase Sapphire Preferred\n"
                    "Then run /opportunities again."
                )
            return hint or (
                "No open opportunities for your wallet yet.\n"
                "Try /opportunities scan, or add fee=/renew= on wallet items."
            )
        lines = ["Open opportunities:"]
        for opp in opps:
            value = (
                f" (~${opp.estimated_value:.0f})"
                if opp.estimated_value is not None
                else ""
            )
            action = f" [/claim {opp.action_key}]" if opp.action_key else ""
            lines.append(f"#{opp.id} {opp.title}{value}{action}")
            lines.append(f"   {opp.detail}")
        return "\n".join(lines)

    def _drafts_for_item(self, item: WalletItem) -> list[dict]:
        drafts: list[dict] = []
        label = item.label()
        days = days_until(item.renewal_date)
        if days is not None and 0 <= days <= 45:
            drafts.append(
                {
                    "title": f"Renewal window: {label}",
                    "detail": (
                        f"Renewal date {item.renewal_date} is in {days} days. "
                        "Review whether benefits used this year cover the fee."
                    ),
                    "estimated_value": item.annual_fee,
                    "action_key": None,
                }
            )
        if item.annual_fee and item.annual_fee >= 95:
            drafts.append(
                {
                    "title": f"Fee vs benefits check: {label}",
                    "detail": (
                        f"Annual fee about ${item.annual_fee:.0f}. "
                        "Confirm credits/perks used this anniversary year."
                    ),
                    "estimated_value": item.annual_fee,
                    "action_key": None,
                }
            )
        for action in find_actions_for_product(label):
            drafts.append(
                {
                    "title": action.title,
                    "detail": (
                        f"Matched wallet item '{label}'. "
                        f"{action.estimated_value_hint or 'Review claim steps.'} "
                        f"Use /claim {action.key}"
                    ),
                    "estimated_value": None,
                    "action_key": action.key,
                }
            )
        return drafts

    def _exists_open(self, chat_id: int, title: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM opportunities
                WHERE chat_id = ? AND status = 'open' AND title = ?
                LIMIT 1
                """,
                (chat_id, title),
            ).fetchone()
        return row is not None

    def _insert(self, chat_id: int, wallet_item_id: int, draft: dict) -> Opportunity:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO opportunities
                    (chat_id, wallet_item_id, title, detail, estimated_value, action_key)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    wallet_item_id,
                    draft["title"],
                    draft["detail"],
                    draft["estimated_value"],
                    draft["action_key"],
                ),
            )
            opp_id = int(cur.lastrowid)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM opportunities WHERE id = ?", (opp_id,)
            ).fetchone()
        return self._row(row)

    @staticmethod
    def _row(row) -> Opportunity:
        return Opportunity(
            id=row["id"],
            chat_id=row["chat_id"],
            wallet_item_id=row["wallet_item_id"],
            title=row["title"],
            detail=row["detail"],
            estimated_value=row["estimated_value"],
            action_key=row["action_key"],
            status=row["status"],
        )
