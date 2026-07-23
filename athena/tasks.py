"""Natural-language task capture."""

from __future__ import annotations
 
import re
from datetime import datetime, timezone
 
import dateparser
 
from .context_service import UserContext
from .database import Database
from .reminders import normalize_time_text
 
TIME_WORDS = [
    "today",
    "tomorrow",
    "tonight",
    "morning",
    "afternoon",
    "evening",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
 
 
class TasksService:
    """Stores, lists, and completes tasks."""
 
    def __init__(self, database: Database, saved_items: object | None = None) -> None:
        self.database = database
        if saved_items is not None:
            self.saved_items = saved_items
        else:
            from .saved_items import SavedItemsService
            self.saved_items = SavedItemsService()
 
    def save_task(self, user_id: int, task: str, due_date: datetime | None) -> int:
        due_str = due_date.date().isoformat() if due_date else None
        db_id = self.database.add_task(user_id, task, due_str)
        self.saved_items.add(user_id, task, remind_at=due_date)
        return db_id
 
    def build_task(
        self, content: str, due_text: str | None, context: UserContext | None
    ) -> tuple[str, datetime | None]:
        """Assemble a (title, due_date) pair from classifier-extracted parts."""
 
        title = content.strip().rstrip(".")
        if not due_text:
            due_date, cleaned_title = _extract_due_date_and_clean_title(title, context)
            return cleaned_title, due_date
        else:
            # Clean the title by removing the due_text phrase
            cleaned_title = re.sub(re.escape(due_text), "", title, flags=re.IGNORECASE)
            cleaned_title = re.sub(r"\b(on|at|by|for|next|this|last|tomorrow|today|tonight)\s*$", "", cleaned_title, flags=re.IGNORECASE)
            cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip().rstrip(".")
            due_date = _parse_due(due_text, context)
            return cleaned_title, due_date
 
    def format_tasks(self, user_id: int) -> str:
        items = self.saved_items.list_active(user_id)
        if not items:
            return "You have no open tasks."
 
        user_row = self.database.get_user(user_id)
        user_tz = user_row["timezone"] if user_row else None
 
        lines = ["Open tasks:"]
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
 
    def complete_task(self, user_id: int, task_id: int) -> str:
        db_id = self._resolve_db_task_id(user_id, task_id)
        if db_id is not None:
            self.database.complete_task(user_id, db_id)

        if self.saved_items.delete_visible(user_id, task_id):
            return f"Task {task_id} completed."
        return f"I could not find task {task_id}."
 
    def delete_task(self, user_id: int, task_id: int) -> str:
        db_id = self._resolve_db_task_id(user_id, task_id)
        if db_id is not None:
            self.database.delete_task(user_id, db_id)

        if self.saved_items.delete_visible(user_id, task_id):
            return f"Task {task_id} deleted."
        return f"I could not find task {task_id}."

    def _resolve_db_task_id(self, user_id: int, task_id: int) -> int | None:
        active_tasks = self.database.active_tasks(user_id)
        if any(int(row["id"]) == task_id for row in active_tasks):
            return task_id

        visible_index = task_id - 1
        if 0 <= visible_index < len(active_tasks):
            return int(active_tasks[visible_index]["id"])

        return None
 
 
def _extract_due_date_and_clean_title(title: str, context: UserContext | None = None) -> tuple[datetime | None, str]:
    lowered = title.lower()
    for word in TIME_WORDS:
        if word in lowered:
            # Check if there is a more complete time expression starting before this word
            # e.g., "on Thursday", "next Friday", "tomorrow afternoon", "tomorrow at 5pm"
            pattern = rf"\b(on|at|by|for|next|this|last|tomorrow|today|tonight)\s+{re.escape(word)}\b"
            match = re.search(pattern, lowered)
            if match:
                expression = match.group(0)
                # Check if there is a time following, like "tomorrow at 10am" or "Friday at 5pm" or "Thursday ten o'clock"
                after_pattern = rf"{re.escape(expression)}\s+(at\s+)?(\d+(?::\d+)?\s*(?:am|pm)?|ten\s+olclock|ten\s+o'clock|noon|night|morning|afternoon|evening)\b"
                after_match = re.search(after_pattern, lowered)
                if after_match:
                    expression = after_match.group(0)
            else:
                # Just the word itself
                # Check if it has a time after it, e.g., "Friday 10am"
                pattern_just = rf"\b{re.escape(word)}\b"
                match_just = re.search(pattern_just, lowered)
                if match_just:
                    expression = match_just.group(0)
                    after_pattern = rf"{re.escape(expression)}\s+(at\s+)?(\d+(?::\d+)?\s*(?:am|pm)?|ten\s+olclock|ten\s+o'clock|noon|night|morning|afternoon|evening)\b"
                    after_match = re.search(after_pattern, lowered)
                    if after_match:
                        expression = after_match.group(0)
                else:
                    continue

            norm_expr = normalize_time_text(expression)
            parsed = _parse_due(norm_expr, context)
            if parsed:
                # Remove the expression from the original title
                cleaned = re.sub(re.escape(expression), "", title, flags=re.IGNORECASE)
                # Clean up prepositions that might be left over, e.g. "read a book on" -> "read a book"
                cleaned = re.sub(r"\b(on|at|by|for|next|this|last|tomorrow|today|tonight)\s*$", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
                return parsed, cleaned

    return None, title


def _parse_due(when_text: str, context: UserContext | None) -> datetime | None:
    norm_text = normalize_time_text(when_text)
    settings = {"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": True}
    if context is not None and context.timezone:
        settings["TIMEZONE"] = context.timezone
        settings["TO_TIMEZONE"] = "UTC"
        try:
            import zoneinfo
            user_now = datetime.now(zoneinfo.ZoneInfo(context.timezone))
            settings["RELATIVE_BASE"] = user_now.replace(tzinfo=None)
        except Exception:
            pass
    else:
        try:
            settings["RELATIVE_BASE"] = datetime.now().replace(tzinfo=None)
        except Exception:
            pass

    parsed = dateparser.parse(norm_text, settings=settings)
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
