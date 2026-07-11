from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryStore:
    """SQLite-backed chat history and profile notes per Telegram chat_id."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'model')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_messages_chat_id
                    ON messages (chat_id, id);

                CREATE TABLE IF NOT EXISTS profile_notes (
                    chat_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (chat_id, key)
                );
                """
            )

    def add_message(self, chat_id: int, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content),
            )

    def get_recent_messages(
        self, chat_id: int, limit: int
    ) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content
                    FROM messages
                    WHERE chat_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) recent
                ORDER BY id ASC
                """,
                (chat_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def clear_messages(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))

    def set_profile_note(self, chat_id: int, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO profile_notes (chat_id, key, value, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(chat_id, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = datetime('now')
                """,
                (chat_id, key.strip().lower(), value.strip()),
            )

    def delete_profile_note(self, chat_id: int, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM profile_notes WHERE chat_id = ? AND key = ?",
                (chat_id, key.strip().lower()),
            )
            return cur.rowcount > 0

    def get_profile_notes(self, chat_id: int) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value
                FROM profile_notes
                WHERE chat_id = ?
                ORDER BY key ASC
                """,
                (chat_id,),
            ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def format_profile(self, chat_id: int) -> str:
        notes = self.get_profile_notes(chat_id)
        if not notes:
            return "No profile notes saved yet."
        lines = [f"- {key}: {value}" for key, value in notes.items()]
        return "Saved profile notes:\n" + "\n".join(lines)
