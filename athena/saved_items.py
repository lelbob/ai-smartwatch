"""Plain-text saved item storage.

Athena keeps the user's remembered items in ``athena/data/tasks``. The file is
JSON-lines text so it is easy to inspect, while still being safe to parse.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR


TASKS_FILE = DATA_DIR / "tasks"


@dataclass(frozen=True)
class SavedItem:
    id: int
    user_id: int
    text: str
    remind_at: str | None = None


class SavedItemsService:
    """Stores every task/note/reminder-like thing in one text file."""

    def __init__(self, path: Path = TASKS_FILE) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def add(
        self,
        user_id: int,
        text: str,
        remind_at: datetime | None = None,
    ) -> SavedItem:
        items = self._read_all()
        item = SavedItem(
            id=self._next_id(items),
            user_id=user_id,
            text=_clean_text(text),
            remind_at=(
                remind_at.astimezone(timezone.utc).isoformat(timespec="seconds")
                if remind_at
                else None
            ),
        )
        items.append(item)
        self._write_all(items)
        return item

    def list_active(self, user_id: int) -> list[SavedItem]:
        self.delete_expired()
        return [item for item in self._read_all() if item.user_id == user_id]

    def format_items(self, user_id: int, database: object = None) -> str:
        items = self.list_active(user_id)
        if not items:
            return "Nothing saved."
 
        user_tz = None
        if database is not None:
            try:
                user_row = database.get_user(user_id)  # type: ignore[attr-defined]
                if user_row:
                    user_tz = user_row["timezone"]
            except Exception:
                pass
 
        lines = ["Saved items:"]
        for index, item in enumerate(items[:10], start=1):
            time_str = ""
            if item.remind_at:
                try:
                    import zoneinfo
                    dt = datetime.fromisoformat(item.remind_at)
                    if user_tz:
                        try:
                            tz = zoneinfo.ZoneInfo(user_tz)
                            dt = dt.astimezone(tz)
                        except Exception:
                            pass
                    time_str = f" - {dt.hour:02d}:{dt.minute:02d} {dt.month}/{dt.day}/{dt.year}"
                except Exception:
                    pass
            lines.append(f"{index}. {item.text}{time_str}")
        return "\n".join(lines)

    def delete_visible(self, user_id: int, visible_number: int) -> bool:
        items = self._read_all()
        user_items = [item for item in items if item.user_id == user_id]
        index = visible_number - 1
        if not 0 <= index < len(user_items):
            return False

        delete_id = user_items[index].id
        self._write_all([item for item in items if item.id != delete_id])
        return True

    def delete_by_id(self, item_id: int) -> bool:
        items = self._read_all()
        kept = [item for item in items if item.id != item_id]
        if len(kept) == len(items):
            return False
        self._write_all(kept)
        return True

    def delete_matching_text(self, user_id: int, text: str) -> bool:
        items = self._read_all()
        target_words = _keywords(text)
        if not target_words:
            return False

        delete_id: int | None = None
        for item in items:
            if item.user_id != user_id:
                continue
            if target_words.issubset(_keywords(item.text)):
                delete_id = item.id
                break

        if delete_id is None:
            return False
        self._write_all([item for item in items if item.id != delete_id])
        return True

    def delete_expired(self, now: datetime | None = None) -> int:
        now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        items = self._read_all()
        kept: list[SavedItem] = []
        removed = 0

        for item in items:
            if not item.remind_at:
                kept.append(item)
                continue
            try:
                remind_at = datetime.fromisoformat(item.remind_at)
                if remind_at.tzinfo is None:
                    remind_at = remind_at.replace(tzinfo=timezone.utc)
            except ValueError:
                kept.append(item)
                continue

            if remind_at <= now_utc:
                removed += 1
            else:
                kept.append(item)

        if removed:
            self._write_all(kept)
        return removed

    def save_memory(self, user_id: int, content: str) -> None:
        """Persist a long-term memory fact."""
        self.add(user_id, content)

    def retrieve_relevant(self, user_id: int, query: str, top_k: int = 5) -> list[str]:
        """Return saved items whose text overlaps with query keywords."""
        query_words = set(re.findall(r"[a-zA-Z0-9']+", query.lower()))
        query_words -= {"i", "me", "my", "the", "a", "an", "is", "am", "are",
                        "do", "does", "did", "to", "of", "in", "on", "at", "for",
                        "and", "or", "but", "not", "it", "this", "that", "what",
                        "when", "where", "how", "who", "which", "have", "has"}
        if not query_words:
            return []
        items = self.list_active(user_id)
        scored = []
        for item in items:
            item_words = set(re.findall(r"[a-zA-Z0-9']+", item.text.lower()))
            overlap = len(query_words & item_words)
            if overlap > 0:
                scored.append((overlap, item.text))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for _, text in scored[:top_k]]

    def _read_all(self) -> list[SavedItem]:
        items: list[SavedItem] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                items.append(
                    SavedItem(
                        id=int(raw["id"]),
                        user_id=int(raw["user_id"]),
                        text=str(raw["text"]),
                        remind_at=raw.get("remind_at"),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return items

    def _write_all(self, items: list[SavedItem]) -> None:
        lines = [
            json.dumps(
                {
                    "id": item.id,
                    "user_id": item.user_id,
                    "text": item.text,
                    "remind_at": item.remind_at,
                },
                ensure_ascii=True,
            )
            for item in items
        ]
        self.path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _next_id(self, items: list[SavedItem]) -> int:
        return max((item.id for item in items), default=0) + 1


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def _keywords(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-zA-Z0-9']+", text.lower())
        if len(word) > 2
    }
