"""SQLite persistence for conversations and their ordered messages."""
import sqlite3
import json
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
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                answer_id TEXT NOT NULL REFERENCES messages(id), status TEXT NOT NULL,
                model TEXT, parameters TEXT NOT NULL, queue_seconds REAL,
                first_text_seconds REAL, total_seconds REAL,
                input_tokens INTEGER, output_tokens INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(messages)")}
        if "image_url" not in columns:
            self.connection.execute("ALTER TABLE messages ADD COLUMN image_url TEXT")
            self.connection.commit()

    def close(self):
        self.connection.close()

    def recent_conversation(self) -> str | None:
        row = self.connection.execute(
            "SELECT id FROM conversations ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def create_conversation(self, title: str = "新会话") -> str:
        identifier = uuid4().hex
        with self.connection:
            self.connection.execute("INSERT INTO conversations(id,title) VALUES (?,?)", (identifier, title))
        return identifier

    def add_message(self, conversation_id: str, role: str, content: str, status: str = "complete", image_url: str | None = None) -> str:
        identifier = uuid4().hex
        with self.connection:
            self.connection.execute(
                "INSERT INTO messages(id,conversation_id,role,content,status,image_url) VALUES (?,?,?,?,?,?)",
                (identifier, conversation_id, role, content, status, image_url),
            )
        return identifier

    def update_message(self, message_id: str, content: str, status: str):
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE messages SET content=?, status=? WHERE id=?", (content, status, message_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(message_id)

    def create_run(self, run_id, conversation_id, answer_id, model=None, parameters=None):
        with self.connection:
            self.connection.execute(
                "INSERT INTO runs(id,conversation_id,answer_id,status,model,parameters) VALUES (?,?,?,'queued',?,?)",
                (run_id, conversation_id, answer_id, model, json.dumps(parameters or {}, ensure_ascii=False)),
            )

    def update_run(self, run_id, *, status, queue_seconds=None, first_text_seconds=None,
                   total_seconds=None, input_tokens=None, output_tokens=None):
        with self.connection:
            self.connection.execute(
                "UPDATE runs SET status=?, queue_seconds=?, first_text_seconds=?, total_seconds=?, input_tokens=?, output_tokens=? WHERE id=?",
                (status, queue_seconds, first_text_seconds, total_seconds, input_tokens, output_tokens, run_id),
            )

    def run(self, run_id):
        row = self.connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def finish_run(self, run_id, answer_id, content, status, *, queue_seconds=None,
                   first_text_seconds=None, total_seconds=None, input_tokens=None, output_tokens=None):
        """Commit the answer and its final metrics together."""
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE messages SET content=?, status=? WHERE id=?", (content, status, answer_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(answer_id)
            cursor = self.connection.execute(
                "UPDATE runs SET status=?, queue_seconds=?, first_text_seconds=?, total_seconds=?, "
                "input_tokens=?, output_tokens=? WHERE id=? AND answer_id=?",
                (status, queue_seconds, first_text_seconds, total_seconds, input_tokens,
                 output_tokens, run_id, answer_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(run_id)

    def recover_interrupted(self):
        """Mark unfinished work after the owner has established exclusive startup."""
        with self.connection:
            self.connection.execute(
                "UPDATE messages SET status='interrupted' WHERE status IN ('queued','streaming')"
            )
            self.connection.execute(
                "UPDATE runs SET status='interrupted' WHERE status IN ('queued','streaming')"
            )

    def messages(self, conversation_id: str, limit: int = 50, before: int | None = None) -> list[dict]:
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = self.connection.execute(
            "SELECT * FROM messages WHERE conversation_id=? AND (? IS NULL OR sequence < ?) "
            "ORDER BY sequence DESC LIMIT ?", (conversation_id, before, before, limit)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
