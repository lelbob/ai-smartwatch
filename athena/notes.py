"""Natural-language note capture."""

from __future__ import annotations

import re

from .database import Database


NOTE_PATTERNS = [
    re.compile(r"^\s*save\s+a\s+note\s+that\s+(?P<content>.+)$", re.IGNORECASE),
    re.compile(r"^\s*note\s+that\s+(?P<content>.+)$", re.IGNORECASE),
    re.compile(r"^\s*make\s+a\s+note\s+that\s+(?P<content>.+)$", re.IGNORECASE),
]


class NotesService:
    """Stores notes when the user's intent is clear."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def extract_note(self, text: str) -> str | None:
        for pattern in NOTE_PATTERNS:
            match = pattern.match(text)
            if match:
                return match.group("content").strip().rstrip(".")
        return None

    def save_note(self, user_id: int, content: str) -> None:
        self.database.add_note(user_id, content)

