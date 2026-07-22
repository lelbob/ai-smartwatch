"""Proactive background checker for upcoming tasks and reminders.

Runs in an asyncio loop (inside the Telegram bot's event loop).  Every
*interval* seconds it scans the database for:

- Tasks due today that the user hasn't been told about yet.
- Reminders whose ``remind_at`` is within the next *lookahead* window.

A SQLite table (``proactive_sent``) prevents duplicate notifications.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram.ext import Application

from .database import Database

logger = logging.getLogger(__name__)

# How far ahead to look for reminders that are about to fire (minutes).
LOOKAHEAD_MINUTES = 15


class ProactiveScheduler:
    """Background loop that sends upcoming-task and reminder nudge messages."""

    def __init__(
        self,
        database: Database,
        application: Application,
        interval_seconds: int = 600,
    ) -> None:
        self.database = database
        self.application = application
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ public

    def start(self) -> None:
        """Register the background loop on the running event loop."""
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._loop(), name="proactive-scheduler")
        logger.info(
            "Proactive scheduler started (interval=%ds, lookahead=%dmin)",
            self.interval_seconds,
            LOOKAHEAD_MINUTES,
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Proactive scheduler stopped.")

    # ----------------------------------------------------------------- loop

    async def _loop(self) -> None:
        try:
            while True:
                await self._check()
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            pass

    async def _check(self) -> None:
        now = datetime.now(timezone.utc)

        # --- upcoming reminders (lookahead window) -----------------------
        lookahead_end = now + timedelta(minutes=LOOKAHEAD_MINUTES)
        try:
            upcoming = self.database.upcoming_reminders_all(
                now=now, end=lookahead_end
            )
            for row in upcoming:
                user_id = int(row["user_id"])
                key = f"reminder-{row['id']}"
                if self.database.was_proactive_sent(key):
                    continue
                await self._send(user_id, 0, f"Reminder coming up: {row['text']}")
                self.database.mark_proactive_sent(key)
        except Exception:
            logger.exception("Proactive reminder check failed")

        # --- tasks due today ----------------------------------------------
        today = now.strftime("%Y-%m-%d")
        try:
            all_users = self.database.all_user_ids()
            for uid in all_users:
                tasks = self.database.due_tasks_for_date(uid, today)
                if not tasks:
                    continue
                key = f"tasks-today-{today}-{uid}"
                if self.database.was_proactive_sent(key):
                    continue
                task_list = ", ".join(t["task"] for t in tasks[:5])
                await self._send(uid, 0, f"Tasks due today: {task_list}")
                self.database.mark_proactive_sent(key)
        except Exception:
            logger.exception("Proactive task check failed")

    # ----------------------------------------------------------------- send

    async def _send(self, user_id: int, chat_id: int, text: str) -> None:
        """Send a proactive message. Uses telegram_user_id as chat_id for 1-on-1 chats."""
        if chat_id == 0:
            row = self.database.get_user(user_id)
            if row and row["telegram_user_id"]:
                chat_id = int(row["telegram_user_id"])
            else:
                logger.warning("No telegram_user_id for user %d; skipping proactive message.", user_id)
                return

        try:
            bot = self.application.bot
            await bot.send_message(chat_id=chat_id, text=text)
            logger.info("Proactive message sent to user %d (chat %d): %s", user_id, chat_id, text[:60])
        except Exception:
            logger.exception("Failed to send proactive message to user %d", user_id)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
