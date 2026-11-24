"""SQLite database: users, conversations (chats), messages and actions.

The tables, primary keys and foreign keys are defined in `schema.sql`
(same folder). This module runs that file and offers simple Python
functions so the rest of the app never writes SQL by hand.

Why a database?
  * Every chat is saved, so you can reopen an old chat and continue it,
    like ChatGPT or Claude (commands: chats, open <id>, new).
  * Every action the AI performed is recorded (audit trail).
  * The data can be analysed with the SQL in `queries.sql` and drawn as
    charts (scripts/draw_charts.py) or as a diagram (scripts/draw_erd.py).

Security: every query uses "?" placeholders, never string concatenation,
so text typed by a user can never change the SQL (no SQL injection).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
TITLE_LENGTH = 50


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Conversation:
    conversation_id: int
    user_id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


@dataclass
class Message:
    message_id: int
    conversation_id: int
    role: str
    content: str
    created_at: str


class ChatDatabase:
    """All database access goes through this class."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # timeout: wait instead of failing when the terminal and the Telegram bot
        # write at the same moment (each has its own connection).
        self.connection = sqlite3.connect(str(db_path), timeout=15)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        if str(db_path) != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")   # readers and a writer together
        self.connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    # -- users -------------------------------------------------------------
    def get_or_create_user(self, display_name: str, source: str,
                           telegram_user_id: int | None = None) -> int:
        """Return the user_id, creating the user the first time."""
        if telegram_user_id is not None:
            row = self.connection.execute(
                "SELECT user_id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT user_id FROM users WHERE source = ? AND telegram_user_id IS NULL "
                "AND display_name = ?", (source, display_name)
            ).fetchone()
        if row:
            return int(row["user_id"])
        cursor = self.connection.execute(
            "INSERT INTO users (display_name, source, telegram_user_id, created_at) VALUES (?, ?, ?, ?)",
            (display_name, source, telegram_user_id, _now()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    # -- conversations -------------------------------------------------------
    def create_conversation(self, user_id: int, title: str = "New chat") -> int:
        now = _now()
        cursor = self.connection.execute(
            "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, title, now, now),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def get_conversation(self, conversation_id: int, user_id: int | None = None) -> Conversation | None:
        """Return the chat, or None if it does not exist (or belongs to someone else)."""
        sql = """SELECT c.*, COUNT(m.message_id) AS message_count
                 FROM conversations c
                 LEFT JOIN messages m ON m.conversation_id = c.conversation_id
                 WHERE c.conversation_id = ?"""
        params: list = [conversation_id]
        if user_id is not None:
            sql += " AND c.user_id = ?"
            params.append(user_id)
        sql += " GROUP BY c.conversation_id"
        row = self.connection.execute(sql, params).fetchone()
        return self._to_conversation(row) if row else None

    def list_conversations(self, user_id: int, limit: int = 20) -> list[Conversation]:
        """The user's chats, most recently used first (uses a JOIN + GROUP BY)."""
        rows = self.connection.execute(
            """SELECT c.*, COUNT(m.message_id) AS message_count
               FROM conversations c
               LEFT JOIN messages m ON m.conversation_id = c.conversation_id
               WHERE c.user_id = ?
               GROUP BY c.conversation_id
               ORDER BY c.updated_at DESC, MAX(m.message_id) DESC, c.conversation_id DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [self._to_conversation(r) for r in rows]

    def latest_conversation(self, user_id: int) -> Conversation | None:
        chats = self.list_conversations(user_id, limit=1)
        return chats[0] if chats else None

    def delete_conversation(self, conversation_id: int, user_id: int) -> bool:
        """Delete a chat; its messages and actions are removed by ON DELETE CASCADE."""
        cursor = self.connection.execute(
            "DELETE FROM conversations WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    # -- messages --------------------------------------------------------------
    def add_message(self, conversation_id: int, role: str, content: str) -> int:
        now = _now()
        cursor = self.connection.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        # The first user message becomes the chat title (like ChatGPT).
        if role == "user":
            title = content.strip().replace("\n", " ")
            if len(title) > TITLE_LENGTH:
                title = title[:TITLE_LENGTH - 3] + "..."
            self.connection.execute(
                "UPDATE conversations SET title = ? WHERE conversation_id = ? AND title = 'New chat'",
                (title or "New chat", conversation_id),
            )
        self.connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?", (now, conversation_id)
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def get_messages(self, conversation_id: int, limit: int | None = None) -> list[Message]:
        """Messages of one chat in chronological order (the last `limit` ones)."""
        if limit is None:
            rows = self.connection.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY message_id", (conversation_id,)
            ).fetchall()
        else:
            rows = self.connection.execute(
                """SELECT * FROM (SELECT * FROM messages WHERE conversation_id = ?
                                  ORDER BY message_id DESC LIMIT ?) ORDER BY message_id""",
                (conversation_id, limit),
            ).fetchall()
        return [Message(r["message_id"], r["conversation_id"], r["role"], r["content"], r["created_at"])
                for r in rows]

    # -- actions -----------------------------------------------------------------
    def add_action(self, message_id: int, action_type: str, success: bool, result: str,
                   path: str | None = None, model_json: str | None = None,
                   duration_ms: int | None = None, model: str | None = None) -> int:
        """Record the action produced by the user message `message_id`."""
        cursor = self.connection.execute(
            """INSERT INTO actions (message_id, action_type, path, model_json, success, result,
                                    duration_ms, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (message_id, action_type, path, model_json, 1 if success else 0, result,
             duration_ms, model, _now()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    # -- context for the AI model -------------------------------------------------
    def get_context(self, conversation_id: int, max_turns: int = 6) -> list[dict[str, str]]:
        """Previous exchanges of a chat, in the format the model understands.

        For every earlier user message we give the model what the user said
        and the JSON action it answered, so that follow-ups such as
        "now delete it" or a clarification answer make sense.
        """
        rows = self.connection.execute(
            """SELECT m.content, a.model_json
               FROM messages m
               LEFT JOIN actions a ON a.message_id = m.message_id
               WHERE m.conversation_id = ? AND m.role = 'user'
                 AND (a.action_type IS NULL OR a.action_type <> 'web_search')
               ORDER BY m.message_id DESC
               LIMIT ?""",
            (conversation_id, max_turns),
        ).fetchall()
        context: list[dict[str, str]] = []
        for row in reversed(rows):
            context.append({"role": "user", "content": row["content"]})
            if row["model_json"]:
                context.append({"role": "assistant", "content": row["model_json"]})
        return context

    # -- statistics ------------------------------------------------------------------
    def count(self, table: str) -> int:
        if table not in ("users", "conversations", "messages", "actions"):
            raise ValueError(f"Unknown table {table!r}")
        return int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    @staticmethod
    def _to_conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(row["conversation_id"], row["user_id"], row["title"],
                            row["created_at"], row["updated_at"], int(row["message_count"]))
