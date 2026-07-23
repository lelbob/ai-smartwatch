"""Per-user context resolution.

Resolves the current date, time, timezone, and location for a user and exposes
it in two forms: a timezone-aware ``now`` for scheduling, and a text block for
injection into LLM prompts. Every model request and every time-relative parse
(reminders, tasks) should flow through ``ContextService.get_context`` so the
server's wall clock never silently overrides the user's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from sqlite3 import Row
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .database import Database


@dataclass(frozen=True)
class UserContext:
    """Resolved user-local context."""

    date: str
    time: str
    timezone: str
    location: str
    latitude: float | None
    longitude: float | None
    now: datetime  # timezone-aware, in the user's timezone

    def to_prompt_block(self) -> str:
        lines = [
            "SYSTEM CONTEXT",
            f"Date: {self.date}",
            f"Time: {self.time}",
            f"Timezone: {self.timezone}",
        ]
        if self.location:
            lines.append(f"Location: {self.location}")
        return "\n".join(lines)


class ContextService:
    """Builds UserContext from stored user data with config fallbacks."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.fallback_timezone = settings.athena_timezone
        self.fallback_location = settings.athena_location

    def get_context(self, user_id: int) -> UserContext:
        user = self.database.get_user(user_id)

        timezone_name = self._timezone_name(user)
        location = self._location(user)
        latitude = float(user["latitude"]) if user and user["latitude"] is not None else None
        longitude = (
            float(user["longitude"]) if user and user["longitude"] is not None else None
        )

        tz = self._resolve_zone(timezone_name)
        now = datetime.now(tz)

        return UserContext(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            timezone=timezone_name,
            location=location,
            latitude=latitude,
            longitude=longitude,
            now=now,
        )

    # ------------------------------------------------------------------ helpers

    def _timezone_name(self, user: Row | None) -> str:
        raw = str(user["timezone"]) if user and user["timezone"] else ""
        if raw:
            try:
                ZoneInfo(raw)
                return raw
            except (ZoneInfoNotFoundError, ValueError):
                pass
        # Validate fallback too.
        try:
            ZoneInfo(self.fallback_timezone)
            return self.fallback_timezone
        except (ZoneInfoNotFoundError, ValueError):
            return "UTC"

    def _location(self, user: Row | None) -> str:
        if not user:
            return self.fallback_location
        parts = [p for p in (user["city"], user["country"]) if p]
        if parts:
            return ", ".join(str(p) for p in parts)
        return self.fallback_location

    @staticmethod
    def _resolve_zone(name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")
