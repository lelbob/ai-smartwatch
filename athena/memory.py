"""Memory capture and retrieval."""

from __future__ import annotations

import re

from .database import Database


MEMORY_PATTERNS = [
    re.compile(r"^\s*remember(?:\s+that)?\s+(?P<content>.+)$", re.IGNORECASE),
    re.compile(r"^\s*please\s+remember(?:\s+that)?\s+(?P<content>.+)$", re.IGNORECASE),
]


class MemoryService:
    """Stores important facts and retrieves simple relevant context."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def extract_memory(self, text: str) -> str | None:
        """Return memory content when a message clearly asks to remember it."""

        for pattern in MEMORY_PATTERNS:
            match = pattern.match(text)
            if match:
                return match.group("content").strip().rstrip(".")
        return None

    def save_memory(self, user_id: int, content: str) -> None:
        self.database.add_memory(user_id, content)

    def retrieve_relevant(self, user_id: int, message: str, limit: int = 6) -> list[str]:
        """Retrieve memories with lightweight keyword scoring."""

        memories = self.database.recent_memories(user_id, limit=30)
        keywords = _keywords(message)

        scored: list[tuple[int, str]] = []
        for row in memories:
            content = str(row["content"])
            memory_words = _keywords(content)
            score = len(keywords.intersection(memory_words))
            scored.append((score, content))

        scored.sort(key=lambda item: item[0], reverse=True)
        relevant = [content for score, content in scored if score > 0][:limit]

        if relevant:
            return relevant

        return [str(row["content"]) for row in memories[: min(3, limit)]]


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "i",
        "is",
        "it",
        "me",
        "my",
        "of",
        "that",
        "the",
        "to",
        "you",
    }
    return {word for word in words if len(word) > 2 and word not in stop_words}

