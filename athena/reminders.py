"""Reminder parsing, storage, and delivery scheduling.

Times are always interpreted in the user's timezone (from UserContext), stored
as UTC ISO strings, and displayed back to the user in their local timezone.
Scheduling compares an aware "now" against the stored time so a reminder set
for 5pm Singapore fires at 5pm Singapore regardless of server location.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import dateparser
from telegram.ext import Application

from .context_service import UserContext
from .database import Database
from .saved_items import SavedItemsService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReminderRequest:
    text: str
    remind_at_utc: datetime
    user_tz_name: str

    def format_for_user(self) -> str:
        """Human-readable time in the user's timezone."""

        from zoneinfo import ZoneInfo

        try:
            local = self.remind_at_utc.astimezone(ZoneInfo(self.user_tz_name))
        except Exception:
            local = self.remind_at_utc
        return local.strftime("%Y-%m-%d %H:%M %Z").strip()


def normalize_time_text(text: str) -> str:
    cleaned = re.sub(r"\b(olclock|oclock|o clock)\b", "o'clock", text, flags=re.IGNORECASE)
    # "next week Friday" / "next week on Friday" -> "Friday"
    cleaned = re.sub(r"\bnext\s+week\s+(?:on\s+)?(\w+)\b", r"\1", cleaned, flags=re.IGNORECASE)
    # "next Friday" / "this Friday" -> "Friday"
    # dateparser 1.4.x cannot parse "next <weekday>" but handles bare weekday
    # names correctly when PREFER_DATES_FROM=future is set.
    _weekdays = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    cleaned = re.sub(r"\b(?:next|this)\s+" + _weekdays, r"\1", cleaned, flags=re.IGNORECASE)
    return cleaned



class RemindersService:
    """Creates reminders and schedules Telegram delivery jobs."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def parse_when(
        self, when_text: str, context: UserContext
    ) -> datetime | None:
        """Parse a natural-language time string in the user's timezone.

        Returns a timezone-aware UTC datetime, or None if unparseable.
        """
        norm_text = normalize_time_text(when_text.strip())
        settings = {
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
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
            settings["TIMEZONE"] = "UTC"
            settings["TO_TIMEZONE"] = "UTC"
            try:
                settings["RELATIVE_BASE"] = datetime.now(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass

        remind_at = dateparser.parse(
            norm_text,
            settings=settings,
        )
        if remind_at is None:
            return None
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=timezone.utc)
        return remind_at.astimezone(timezone.utc)

    def build_reminder(
        self, text: str, when_text: str, context: UserContext
    ) -> ReminderRequest | None:
        """Build a ReminderRequest from already-separated parts (classifier path)."""

        remind_at_utc = self.parse_when(when_text, context)
        if remind_at_utc is None:
            return None

        cleaned_text = text.strip().rstrip(".")
        if when_text:
            cleaned_text = re.sub(re.escape(when_text), "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r"\b(on|at|by|for|next|this|last|tomorrow|today|tonight)\s*$", "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip().rstrip(".")

        return ReminderRequest(
            text=cleaned_text,
            remind_at_utc=remind_at_utc,
            user_tz_name=context.timezone,
        )

    def create_reminder(
        self,
        user_id: int,
        telegram_chat_id: int,
        reminder: ReminderRequest,
        application: Application | None = None,
        saved_item_id: int | None = None,
    ) -> int:
        reminder_id = self.database.add_reminder(
            user_id=user_id,
            telegram_chat_id=telegram_chat_id,
            text=reminder.text,
            remind_at=reminder.remind_at_utc,
        )
        if application:
            self.schedule_reminder(
                application,
                reminder_id,
                telegram_chat_id,
                reminder,
                user_id=user_id,
                saved_item_id=saved_item_id,
            )
        return reminder_id

    def schedule_existing(self, application: Application) -> None:
        if application.job_queue is None:
            logger.warning("Reminder scheduling requires python-telegram-bot[job-queue].")
            return

        for row in self.database.pending_reminders():
            try:
                remind_at_utc = datetime.fromisoformat(str(row["remind_at"]))
                if remind_at_utc.tzinfo is None:
                    remind_at_utc = remind_at_utc.replace(tzinfo=timezone.utc)
                reminder = ReminderRequest(
                    text=str(row["text"]),
                    remind_at_utc=remind_at_utc,
                    user_tz_name="UTC",
                )
                self.schedule_reminder(
                    application=application,
                    reminder_id=int(row["id"]),
                    telegram_chat_id=int(row["telegram_chat_id"]),
                    reminder=reminder,
                    user_id=int(row["user_id"]),
                )
            except Exception:
                logger.exception("Failed to schedule reminder %s", row["id"])

    def schedule_reminder(
        self,
        application: Application,
        reminder_id: int,
        telegram_chat_id: int,
        reminder: ReminderRequest,
        user_id: int | None = None,
        saved_item_id: int | None = None,
    ) -> None:
        if application.job_queue is None:
            logger.warning("Could not schedule reminder %s; job queue is unavailable.", reminder_id)
            return

        now_utc = datetime.now(timezone.utc)
        delay = max(0.0, (reminder.remind_at_utc - now_utc).total_seconds())
        application.job_queue.run_once(
            self._send_reminder,
            when=delay,
            data={
                "id": reminder_id,
                "chat_id": telegram_chat_id,
                "text": reminder.text,
                "user_id": user_id,
                "saved_item_id": saved_item_id,
            },
            name=f"reminder-{reminder_id}",
        )

    async def _send_reminder(self, context) -> None:
        data = context.job.data
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=f"Reminder: {data['text']}",
        )
        self.database.mark_reminder_delivered(int(data["id"]))
        saved_items = SavedItemsService()
        if data.get("saved_item_id"):
            saved_items.delete_by_id(int(data["saved_item_id"]))
        elif data.get("user_id"):
            saved_items.delete_matching_text(int(data["user_id"]), str(data["text"]))
