"""SQLite persistence for conversations and their ordered messages."""
import sqlite3
from pathlib import Path
from uuid import uuid4


class Store:
    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE,
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS messages_conversation_order
                ON messages(conversation_id, sequence);
        """)

    def close(self):
        self.connection.close()

    def create_conversation(self, title: str = "新会话") -> str:
        identifier = uuid4().hex
        with self.connection:
            self.connection.execute("INSERT INTO conversations(id,title) VALUES (?,?)", (identifier, title))
        return identifier

    def add_message(self, conversation_id: str, role: str, content: str, status: str = "complete") -> str:
        identifier = uuid4().hex
        with self.connection:
            self.connection.execute(
                "INSERT INTO messages(id,conversation_id,role,content,status) VALUES (?,?,?,?,?)",
                (identifier, conversation_id, role, content, status),
            )
        return identifier

    def update_message(self, message_id: str, content: str, status: str):
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE messages SET content=?, status=? WHERE id=?", (content, status, message_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(message_id)

    def messages(self, conversation_id: str, limit: int = 50, before: int | None = None) -> list[dict]:
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = self.connection.execute(
            "SELECT * FROM messages WHERE conversation_id=? AND (? IS NULL OR sequence < ?) "
            "ORDER BY sequence DESC LIMIT ?", (conversation_id, before, before, limit)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
