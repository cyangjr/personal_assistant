from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


def product_key(issuer: str, product_name: str) -> str:
    return f"{issuer.strip().lower()}|{product_name.strip().lower()}"


@dataclass
class WalletItem:
    id: int
    chat_id: int
    item_type: str
    issuer: str
    product_name: str
    annual_fee: float | None
    renewal_date: str | None
    notes: str

    @property
    def key(self) -> str:
        return product_key(self.issuer, self.product_name)

    def label(self) -> str:
        return f"{self.issuer} {self.product_name}".strip()


class WalletStore:
    def __init__(self, db) -> None:
        self.db = db

    def add(
        self,
        *,
        chat_id: int,
        item_type: str,
        issuer: str,
        product_name: str,
        annual_fee: float | None = None,
        renewal_date: str | None = None,
        notes: str = "",
    ) -> WalletItem:
        if item_type not in {"card", "membership"}:
            raise ValueError("item_type must be 'card' or 'membership'")
        if renewal_date:
            date.fromisoformat(renewal_date)  # validate
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO wallet_items
                    (chat_id, item_type, issuer, product_name, annual_fee, renewal_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    item_type,
                    issuer.strip(),
                    product_name.strip(),
                    annual_fee,
                    renewal_date,
                    notes.strip(),
                ),
            )
            item_id = int(cur.lastrowid)
        return self.get(item_id)

    def get(self, item_id: int) -> WalletItem:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM wallet_items WHERE id = ?", (item_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"wallet item {item_id} not found")
        return self._row(row)

    def list(self, chat_id: int) -> list[WalletItem]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM wallet_items
                WHERE chat_id = ?
                ORDER BY item_type, issuer, product_name
                """,
                (chat_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def delete(self, chat_id: int, item_id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute(
                "DELETE FROM wallet_items WHERE chat_id = ? AND id = ?",
                (chat_id, item_id),
            )
            return cur.rowcount > 0

    def format(self, chat_id: int) -> str:
        items = self.list(chat_id)
        if not items:
            return (
                "Wallet is empty.\n"
                "Add with:\n"
                "/wallet add card Chase | Sapphire Preferred\n"
                "/wallet add membership Costco | Executive fee=120 renew=2026-12-01"
            )
        lines = ["Your wallet:"]
        for item in items:
            fee = f", fee=${item.annual_fee:.0f}" if item.annual_fee is not None else ""
            renew = f", renew={item.renewal_date}" if item.renewal_date else ""
            lines.append(
                f"#{item.id} [{item.item_type}] {item.label()}{fee}{renew}"
            )
        return "\n".join(lines)

    def as_profile_context(self, chat_id: int) -> dict[str, str]:
        items = self.list(chat_id)
        if not items:
            return {}
        cards = [i.label() for i in items if i.item_type == "card"]
        memberships = [i.label() for i in items if i.item_type == "membership"]
        ctx: dict[str, str] = {}
        if cards:
            ctx["cards"] = ", ".join(cards)
        if memberships:
            ctx["memberships"] = ", ".join(memberships)
        return ctx

    @staticmethod
    def _row(row) -> WalletItem:
        return WalletItem(
            id=row["id"],
            chat_id=row["chat_id"],
            item_type=row["item_type"],
            issuer=row["issuer"],
            product_name=row["product_name"],
            annual_fee=row["annual_fee"],
            renewal_date=row["renewal_date"],
            notes=row["notes"] or "",
        )


def parse_wallet_add_args(args: list[str]) -> dict:
    """Parse: card Chase | Sapphire Preferred fee=95 renew=2026-11-01 notes=..."""
    if len(args) < 2:
        raise ValueError("need type and details")
    item_type = args[0].lower()
    if item_type not in {"card", "membership"}:
        raise ValueError("type must be card or membership")

    rest = " ".join(args[1:])
    fee = None
    renew = None
    notes = ""
    tokens = rest.split()
    kept: list[str] = []
    for token in tokens:
        lower = token.lower()
        if lower.startswith("fee="):
            fee = float(lower.split("=", 1)[1].replace("$", ""))
        elif lower.startswith("renew="):
            renew = lower.split("=", 1)[1]
            date.fromisoformat(renew)
        elif lower.startswith("notes="):
            notes = token.split("=", 1)[1]
        else:
            kept.append(token)
    body = " ".join(kept)
    if "|" not in body:
        raise ValueError("use Issuer | Product Name")
    issuer, product = [part.strip() for part in body.split("|", 1)]
    if not issuer or not product:
        raise ValueError("issuer and product required")
    return {
        "item_type": item_type,
        "issuer": issuer,
        "product_name": product,
        "annual_fee": fee,
        "renewal_date": renew,
        "notes": notes,
    }


def days_until(iso_date: str | None) -> int | None:
    if not iso_date:
        return None
    target = date.fromisoformat(iso_date)
    return (target - date.today()).days
