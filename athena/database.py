"""SQLite database access for Athena."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


class Database:
    """Small SQLite wrapper used by the service modules."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection with rows available by column name."""

        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("Database transaction failed")
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create and migrate the Athena database schema."""

        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    latitude REAL,
                    longitude REAL,
                    city TEXT,
                    country TEXT,
                    timezone TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    voice_replies_enabled INTEGER NOT NULL DEFAULT 0,
                    preferred_voice TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversation_state (
                    user_id INTEGER PRIMARY KEY,
                    pending_tool TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    missing_fields_json TEXT NOT NULL DEFAULT '[]',
                    question TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    due_text TEXT,
                    is_done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    telegram_chat_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    delivered INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_memories_user_created
                    ON memories (user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_notes_user_created
                    ON notes (user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tasks_user_created
                    ON tasks (user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_reminders_pending
                    ON reminders (delivered, remind_at);
                CREATE INDEX IF NOT EXISTS idx_history_user_created
                    ON conversation_history (user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS proactive_sent (
                    key TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._add_column_if_missing(db, "tasks", "task", "TEXT")
            self._add_column_if_missing(db, "tasks", "due_date", "TEXT")
            self._add_column_if_missing(
                db, "tasks", "completed", "INTEGER NOT NULL DEFAULT 0"
            )
            db.execute(
                """
                UPDATE tasks
                SET
                    task = COALESCE(task, title),
                    due_date = COALESCE(due_date, due_text),
                    completed = CASE
                        WHEN COALESCE(is_done, 0) = 1 THEN 1
                        ELSE COALESCE(completed, 0)
                    END
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_user_completed_due
                    ON tasks (user_id, completed, due_date)
                """
            )

            # Phase 2.1: per-user location for timezone-aware features.
            self._add_column_if_missing(db, "users", "latitude", "REAL")
            self._add_column_if_missing(db, "users", "longitude", "REAL")
            self._add_column_if_missing(db, "users", "city", "TEXT")
            self._add_column_if_missing(db, "users", "country", "TEXT")
            self._add_column_if_missing(db, "users", "timezone", "TEXT")

    def _add_column_if_missing(
        self, db: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {str(row["name"]) for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def upsert_user(
        self,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> int:
        """Create or update a Telegram user and return the local user id."""

        with self.connect() as db:
            db.execute(
                """
                INSERT INTO users (
                    telegram_user_id, username, first_name, last_name
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (telegram_user_id, username, first_name, last_name),
            )
            row = db.execute(
                "SELECT id FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            return int(row["id"])

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        """Return the full user row, including location fields."""

        with self.connect() as db:
            return db.execute(
                """
                SELECT id, telegram_user_id, username, first_name, last_name,
                       latitude, longitude, city, country, timezone
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

    def update_user_location(
        self,
        user_id: int,
        latitude: float,
        longitude: float,
        city: str | None,
        country: str | None,
        timezone: str | None,
    ) -> None:
        """Store the user's geolocation and derived timezone."""

        with self.connect() as db:
            db.execute(
                """
                UPDATE users
                SET latitude = ?,
                    longitude = ?,
                    city = ?,
                    country = ?,
                    timezone = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (latitude, longitude, city, country, timezone, user_id),
            )

    # -------------------------------------------------------- preferences (P2)

    def get_preference(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                """
                SELECT user_id, voice_replies_enabled, preferred_voice
                FROM user_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

    def upsert_preference(
        self,
        user_id: int,
        voice_replies_enabled: bool,
        preferred_voice: str | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO user_preferences (user_id, voice_replies_enabled, preferred_voice)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    voice_replies_enabled = excluded.voice_replies_enabled,
                    preferred_voice = COALESCE(excluded.preferred_voice, user_preferences.preferred_voice),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    1 if voice_replies_enabled else 0,
                    preferred_voice,
                ),
            )

    # -------------------------------------------------- conversation state (P4)

    def get_pending_action(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                """
                SELECT user_id, pending_tool, args_json, missing_fields_json, question
                FROM conversation_state
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

    def set_pending_action(
        self,
        user_id: int,
        pending_tool: str,
        args_json: str,
        missing_fields_json: str = "[]",
        question: str | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO conversation_state
                    (user_id, pending_tool, args_json, missing_fields_json, question)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    pending_tool = excluded.pending_tool,
                    args_json = excluded.args_json,
                    missing_fields_json = excluded.missing_fields_json,
                    question = excluded.question,
                    created_at = CURRENT_TIMESTAMP
                """,
                (user_id, pending_tool, args_json, missing_fields_json, question),
            )

    def clear_pending_action(self, user_id: int) -> None:
        with self.connect() as db:
            db.execute(
                "DELETE FROM conversation_state WHERE user_id = ?",
                (user_id,),
            )

    def add_memory(self, user_id: int, content: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO memories (user_id, content) VALUES (?, ?)",
                (user_id, content),
            )

    def add_note(self, user_id: int, content: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO notes (user_id, content) VALUES (?, ?)",
                (user_id, content),
            )

    def add_task(self, user_id: int, task: str, due_date: str | None) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO tasks (
                    user_id, title, due_text, is_done, task, due_date, completed
                )
                VALUES (?, ?, ?, 0, ?, ?, 0)
                """,
                (user_id, task, due_date, task, due_date),
            )
            return int(cursor.lastrowid)

    def active_tasks(self, user_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT id, COALESCE(task, title) AS task, due_date, created_at
                    FROM tasks
                    WHERE user_id = ?
                      AND COALESCE(completed, is_done, 0) = 0
                    ORDER BY
                        CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END,
                        due_date ASC,
                        created_at ASC
                    """,
                    (user_id,),
                ).fetchall()
            )

    def due_tasks_for_date(self, user_id: int, date_prefix: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT id, COALESCE(task, title) AS task, due_date
                    FROM tasks
                    WHERE user_id = ?
                      AND COALESCE(completed, is_done, 0) = 0
                      AND due_date LIKE ?
                    ORDER BY due_date ASC, created_at ASC
                    """,
                    (user_id, f"{date_prefix}%"),
                ).fetchall()
            )

    def complete_task(self, user_id: int, task_id: int) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                """
                UPDATE tasks
                SET completed = 1,
                    is_done = 1,
                    completed_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND id = ?
                """,
                (user_id, task_id),
            )
            return cursor.rowcount > 0

    def delete_task(self, user_id: int, task_id: int) -> bool:
        """Delete an open or completed task owned by the user."""

        with self.connect() as db:
            cursor = db.execute(
                "DELETE FROM tasks WHERE user_id = ? AND id = ?",
                (user_id, task_id),
            )
            return cursor.rowcount > 0

    def add_history(self, user_id: int, role: str, content: str) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO conversation_history (user_id, role, content)
                VALUES (?, ?, ?)
                """,
                (user_id, role, content),
            )

    def recent_history(
        self,
        user_id: int,
        limit: int = 12,
        max_chars: int = 1500,
    ) -> list[sqlite3.Row]:
        """Return recent conversation history, oldest-first.

        Fetches up to *limit* rows, then trims the oldest turns whose
        cumulative content exceeds *max_chars*.  This gives a token-budgeted
        sliding window that keeps the freshest context.
        """
        with self.connect() as db:
            rows = list(
                db.execute(
                    """
                    SELECT role, content, created_at
                    FROM conversation_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            )[::-1]  # oldest first

        # Trim oldest turns that push the budget over max_chars.
        budget = max_chars
        keep = []
        for row in reversed(rows):  # newest first
            content_len = len(str(row["content"]))
            if content_len > budget and keep:
                break  # can't fit this turn; stop keeping older ones
            keep.append(row)
            budget -= content_len
        return keep[::-1]  # back to oldest-first

    def history_before_cutoff(
        self,
        user_id: int,
        limit: int = 12,
        max_chars: int = 1500,
    ) -> list[sqlite3.Row]:
        """Return the oldest turns that were trimmed by recent_history.

        Used for session summarization — fetches up to *limit* rows, returns
        only the oldest ones that exceed the char budget (i.e. the dropped
        context).
        """
        with self.connect() as db:
            rows = list(
                db.execute(
                    """
                    SELECT role, content, created_at
                    FROM conversation_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            )[::-1]

        budget = max_chars
        drop_start = 0
        total = 0
        for i, row in enumerate(rows):
            content_len = len(str(row["content"]))
            total += content_len
            if total > budget:
                drop_start = i + 1
                break

        if drop_start == 0:
            return []  # nothing dropped
        return rows[:drop_start]

    def recent_memories(self, user_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT content, created_at
                    FROM memories
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            )

    def recent_notes(self, user_id: int, limit: int = 5) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT content, created_at
                    FROM notes
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            )

    def add_reminder(
        self, user_id: int, telegram_chat_id: int, text: str, remind_at: datetime
    ) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO reminders (user_id, telegram_chat_id, text, remind_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, telegram_chat_id, text, remind_at.isoformat(timespec="seconds")),
            )
            return int(cursor.lastrowid)

    def pending_reminders(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT id, user_id, telegram_chat_id, text, remind_at
                    FROM reminders
                    WHERE delivered = 0
                    ORDER BY remind_at ASC
                    """
                ).fetchall()
            )

    def upcoming_reminders(
        self, user_id: int, now: datetime, hours: int = 24, limit: int = 5
    ) -> list[sqlite3.Row]:
        end = now + timedelta(hours=hours)
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT id, text, remind_at
                    FROM reminders
                    WHERE user_id = ?
                      AND delivered = 0
                      AND remind_at >= ?
                      AND remind_at <= ?
                    ORDER BY remind_at ASC
                    LIMIT ?
                    """,
                    (
                        user_id,
                        now.isoformat(timespec="seconds"),
                        end.isoformat(timespec="seconds"),
                        limit,
                    ),
                ).fetchall()
            )

    def mark_reminder_delivered(self, reminder_id: int) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE reminders SET delivered = 1 WHERE id = ?",
                (reminder_id,),
            )

    # ---------------------------------------------- proactive scheduler helpers

    def all_user_ids(self) -> list[int]:
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT id FROM users").fetchall()]

    def upcoming_reminders_all(
        self, now: datetime, end: datetime, limit: int = 50
    ) -> list[sqlite3.Row]:
        """Fetch undelivered reminders for ALL users in the [now, end] window."""
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT id, user_id, text, remind_at
                    FROM reminders
                    WHERE delivered = 0
                      AND remind_at >= ?
                      AND remind_at <= ?
                    ORDER BY remind_at ASC
                    LIMIT ?
                    """,
                    (now.isoformat(), end.isoformat(), limit),
                ).fetchall()
            )

    def was_proactive_sent(self, key: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM proactive_sent WHERE key = ?", (key,)
            ).fetchone()
            return row is not None

    def mark_proactive_sent(self, key: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO proactive_sent (key) VALUES (?)",
                (key,),
            )
