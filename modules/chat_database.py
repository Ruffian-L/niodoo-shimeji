"""SQLite database for chat history management.

Supports multiple chat sessions, import/export, and graceful session management.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)


class ChatDatabase:
    """Manages chat sessions and messages in SQLite."""

    def __init__(self, db_path: str = "var/chat_history.db") -> None:
        """Initialize the chat database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._current_session_id: Optional[int] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    title TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    author TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session 
                ON chat_messages(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_created 
                ON chat_messages(created_at)
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper error handling."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except sqlite3.Error as exc:
            LOGGER.error("Database error: %s", exc)
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_new_session(self, title: Optional[str] = None, metadata: Optional[Dict] = None) -> int:
        """Create a new chat session.

        Args:
            title: Optional title for the session.
            metadata: Optional metadata dictionary.

        Returns:
            The session ID.
        """
        metadata_json = json.dumps(metadata) if metadata else None
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO chat_sessions (title, metadata) VALUES (?, ?)",
                (title, metadata_json)
            )
            session_id = cursor.lastrowid
            conn.commit()
            self._current_session_id = session_id
            LOGGER.info("Created new chat session %d", session_id)
            return session_id

    def get_current_session_id(self) -> Optional[int]:
        """Get the current active session ID."""
        return self._current_session_id

    def load_or_create_session(self) -> int:
        """Load the most recent session or create a new one.

        Returns:
            The session ID.
        """
        if self._current_session_id:
            return self._current_session_id

        # Get the most recent session
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM chat_sessions ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                self._current_session_id = row["id"]
                LOGGER.info("Loaded existing session %d", self._current_session_id)
                return self._current_session_id

        # Create new session if none exists
        return self.create_new_session()

    def add_message(self, author: str, text: str, session_id: Optional[int] = None) -> None:
        """Add a message to a session.

        Args:
            author: Message author.
            text: Message text.
            session_id: Session ID (uses current if None).
        """
        if session_id is None:
            session_id = self.load_or_create_session()

        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO chat_messages (session_id, author, text) VALUES (?, ?, ?)",
                (session_id, author, text)
            )
            # Update session updated_at
            conn.execute(
                "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,)
            )
            conn.commit()

    def get_messages(self, session_id: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Get messages from a session.

        Args:
            session_id: Session ID (uses current if None).
            limit: Optional limit on number of messages.

        Returns:
            List of message dictionaries with 'author' and 'text' keys.
        """
        if session_id is None:
            session_id = self.load_or_create_session()

        query = "SELECT author, text FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC"
        params = [session_id]
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [{"author": row["author"], "text": row["text"]} for row in cursor.fetchall()]

    def list_sessions(self, limit: int = 50) -> List[Dict]:
        """List all chat sessions.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of session dictionaries with id, created_at, updated_at, title, message_count.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    s.id,
                    s.created_at,
                    s.updated_at,
                    s.title,
                    COUNT(m.id) as message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON s.id = m.session_id
                GROUP BY s.id
                ORDER BY s.created_at DESC
                LIMIT ?
            """, (limit,))
            return [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "title": row["title"],
                    "message_count": row["message_count"],
                }
                for row in cursor.fetchall()
            ]

    def get_session(self, session_id: int) -> Optional[Dict]:
        """Get a session by ID.

        Args:
            session_id: Session ID.

        Returns:
            Session dictionary or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, created_at, updated_at, title, metadata FROM chat_sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                metadata = json.loads(row["metadata"]) if row["metadata"] else None
                return {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "title": row["title"],
                    "metadata": metadata,
                }
            return None

    def export_session(self, session_id: Optional[int] = None, format: str = "json") -> str:
        """Export a session to JSON or Markdown.

        Args:
            session_id: Session ID (uses current if None).
            format: Export format ('json' or 'markdown').

        Returns:
            Exported content as string.
        """
        if session_id is None:
            session_id = self.load_or_create_session()

        session = self.get_session(session_id)
        messages = self.get_messages(session_id)

        if format == "json":
            return json.dumps(
                {
                    "session": session,
                    "messages": messages,
                },
                indent=2,
                ensure_ascii=False,
            )
        elif format == "markdown":
            lines = ["# Chat History\n"]
            if session:
                if session.get("title"):
                    lines.append(f"**Title:** {session['title']}\n")
                lines.append(f"**Created:** {session['created_at']}\n")
                lines.append(f"**Updated:** {session['updated_at']}\n")
                lines.append(f"**Messages:** {len(messages)}\n\n")
                lines.append("---\n\n")

            for msg in messages:
                author = msg.get("author", "Unknown")
                text = msg.get("text", "")
                lines.append(f"## {author}\n\n{text}\n\n")

            return "".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def export_session_to_file(
        self, session_id: Optional[int] = None, file_path: Optional[str] = None, format: str = "markdown"
    ) -> str:
        """Export a session to a file.

        Args:
            session_id: Session ID (uses current if None).
            file_path: Output file path (auto-generated if None).
            format: Export format ('json' or 'markdown').

        Returns:
            Path to the exported file.
        """
        if file_path is None:
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            ext = "md" if format == "markdown" else "json"
            file_path = f"chat_export_{timestamp}.{ext}"

        content = self.export_session(session_id, format)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        LOGGER.info("Exported session %s to %s", session_id, file_path)
        return file_path

    def import_session(self, file_path: str, create_new: bool = True) -> int:
        """Import a session from a JSON file.

        Args:
            file_path: Path to JSON export file.
            create_new: If True, create a new session. If False, append to current.

        Returns:
            The session ID.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if create_new:
            session_id = self.create_new_session(
                title=data.get("session", {}).get("title"),
                metadata=data.get("session", {}).get("metadata"),
            )
        else:
            session_id = self.load_or_create_session()

        messages = data.get("messages", [])
        for msg in messages:
            self.add_message(
                author=msg.get("author", "Unknown"),
                text=msg.get("text", ""),
                session_id=session_id,
            )

        LOGGER.info("Imported %d messages into session %d", len(messages), session_id)
        return session_id

    def delete_session(self, session_id: int) -> None:
        """Delete a session and all its messages.

        Args:
            session_id: Session ID to delete.
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            conn.commit()
            LOGGER.info("Deleted session %d", session_id)

    def close(self) -> None:
        """Close the database connection."""
        # SQLite connections are closed automatically, but we can reset session
        self._current_session_id = None

