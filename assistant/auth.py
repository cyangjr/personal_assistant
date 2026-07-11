from __future__ import annotations

from collections.abc import Iterable


def is_allowed(chat_id: int, allowed_chat_ids: Iterable[int]) -> bool:
    return chat_id in set(allowed_chat_ids)
