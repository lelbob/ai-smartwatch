"""Tests for the proactive scheduler and search-result model routing."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from athena.database import Database
from athena.scheduler import ProactiveScheduler, _parse_dt


# ----------------------------------------------------------------------- helpers


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    return database


@pytest.fixture
def user_id(db):
    return db.upsert_user(
        telegram_user_id=999,
        username="schedtest",
        first_name="Sched",
        last_name="Test",
    )


def _run(coro):
    """Run a coroutine in a fresh event loop (avoids needing pytest-asyncio)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ----------------------------------------------------------------- _parse_dt


class TestParseDt:
    def test_parses_iso_with_tz(self):
        dt = _parse_dt("2026-06-19T12:00:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2026

    def test_parses_iso_naive_assumes_utc(self):
        dt = _parse_dt("2026-06-19T12:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_none_returns_none(self):
        assert _parse_dt(None) is None

    def test_garbage_returns_none(self):
        assert _parse_dt("not a date") is None


# ------------------------------------------------------ proactive DB helpers


class TestProactiveDbHelpers:
    def test_was_proactive_sent_false_initially(self, db):
        assert db.was_proactive_sent("tasks-today-2026-06-19-1") is False

    def test_mark_then_was_sent_true(self, db):
        key = "tasks-today-2026-06-19-1"
        db.mark_proactive_sent(key)
        assert db.was_proactive_sent(key) is True

    def test_mark_idempotent(self, db):
        key = "reminder-5"
        db.mark_proactive_sent(key)
        db.mark_proactive_sent(key)  # second insert should not error
        assert db.was_proactive_sent(key) is True

    def test_all_user_ids(self, db, user_id):
        ids = db.all_user_ids()
        assert user_id in ids

    def test_upcoming_reminders_all_empty(self, db):
        now = datetime.now(timezone.utc)
        end = now + timedelta(minutes=15)
        assert db.upcoming_reminders_all(now, end) == []

    def test_upcoming_reminders_all_returns_pending(self, db, user_id):
        soon = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.add_reminder(user_id=user_id, telegram_chat_id=999, text="test", remind_at=soon)
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        end = datetime.now(timezone.utc) + timedelta(minutes=15)
        results = db.upcoming_reminders_all(now, end)
        assert len(results) == 1
        assert results[0]["text"] == "test"

    def test_proactive_sent_table_created(self, db):
        # Verify the table exists by inserting and reading
        db.mark_proactive_sent("test-key")
        assert db.was_proactive_sent("test-key") is True
        assert db.was_proactive_sent("other-key") is False


# ---------------------------------------------------------- scheduler logic


class TestProactiveScheduler:
    def _make_scheduler(self, db, interval=600):
        app = MagicMock()
        app.bot.send_message = AsyncMock()
        return ProactiveScheduler(database=db, application=app, interval_seconds=interval)

    def test_check_sends_reminder_nudge(self, db, user_id):
        sched = self._make_scheduler(db)
        soon = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.add_reminder(user_id=user_id, telegram_chat_id=999, text="Call mom", remind_at=soon)

        _run(sched._check())

        sched.application.bot.send_message.assert_awaited_once()
        call_kwargs = sched.application.bot.send_message.call_args
        assert call_kwargs.kwargs["chat_id"] == 999  # falls back to telegram_user_id
        assert "Call mom" in call_kwargs.kwargs["text"]

    def test_check_does_not_resend_same_reminder(self, db, user_id):
        sched = self._make_scheduler(db)
        soon = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.add_reminder(user_id=user_id, telegram_chat_id=999, text="Once", remind_at=soon)

        _run(sched._check())
        _run(sched._check())  # second check should not resend

        assert sched.application.bot.send_message.await_count == 1

    def test_check_sends_task_nudge_once(self, db, user_id):
        sched = self._make_scheduler(db)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.add_task(user_id=user_id, task="Finish report", due_date=today)

        _run(sched._check())
        _run(sched._check())  # should not duplicate

        assert sched.application.bot.send_message.await_count == 1
        call_kwargs = sched.application.bot.send_message.call_args
        assert "Finish report" in call_kwargs.kwargs["text"]

    def test_check_skips_past_reminders(self, db, user_id):
        sched = self._make_scheduler(db)
        past = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.add_reminder(user_id=user_id, telegram_chat_id=999, text="Old", remind_at=past)

        _run(sched._check())

        # Past reminder should not be picked up by the lookahead window
        sched.application.bot.send_message.assert_not_awaited()

    def test_check_skips_far_future_reminders(self, db, user_id):
        sched = self._make_scheduler(db)
        far = datetime.now(timezone.utc) + timedelta(hours=5)
        db.add_reminder(user_id=user_id, telegram_chat_id=999, text="Later", remind_at=far)

        _run(sched._check())

        sched.application.bot.send_message.assert_not_awaited()

    def test_send_uses_telegram_user_id_as_chat_id(self, db, user_id):
        sched = self._make_scheduler(db)
        # user_id's telegram_user_id is 999 (from fixture)
        _run(sched._send(user_id, 0, "test message"))

        sched.application.bot.send_message.assert_awaited_once_with(
            chat_id=999, text="test message"
        )

    def test_send_skips_unknown_user(self, db):
        sched = self._make_scheduler(db)
        _run(sched._send(99999, 0, "test"))  # non-existent user

        sched.application.bot.send_message.assert_not_awaited()

    def test_loop_runs_and_can_be_cancelled(self, db):
        sched = self._make_scheduler(db, interval=0)  # no sleeping
        sched._check = AsyncMock()

        async def _runner():
            task = asyncio.create_task(sched._loop())
            await asyncio.sleep(0.05)  # let it run a couple iterations
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        _run(_runner())
        assert sched._check.await_count >= 1


# ---------------------------------------------------- search-result routing


class TestSearchResultRouting:
    def test_generate_response_skips_local_when_search_present(self, tmp_path):
        """When search_results are provided, the local model must be skipped."""
        from athena.model_router import ModelRouter
        from athena.search_service import SearchResult

        settings = SimpleNamespace(
            gemini_api_key="fake-key",
            gemini_flash_model="flash",
            gemini_pro_model="pro",
            alt_cloud_base_url="",
            alt_cloud_api_key="",
            alt_cloud_model="",
            ollama_url="http://localhost:11434",
            ollama_model="test-model",
            ollama_timeout=5.0,
            ollama_keep_alive="1m",
            ollama_num_predict=64,
            prompt_log_path="",
        )
        router = ModelRouter(settings)

        # Gemini client is created but API call will fail; we patch to verify
        # the local model is NOT called when search results are present.
        router.local_llm.generate = MagicMock(return_value="local output")
        router._generate_gemini = MagicMock(side_effect=RuntimeError("no cloud"))

        result = router.generate_response(
            user_message="test",
            memories=[],
            history=[],
            search_results=[SearchResult(title="t", url="u", snippet="s")],
            context=None,
        )

        # Local model should NOT have been called (force_cloud)
        router.local_llm.generate.assert_not_called()
        assert "cloud required" in result.text

    def test_generate_response_uses_local_when_no_search(self, tmp_path):
        """Without search results, local model fallback should still work."""
        from athena.model_router import ModelRouter

        settings = SimpleNamespace(
            gemini_api_key="fake-key",
            gemini_flash_model="flash",
            gemini_pro_model="pro",
            alt_cloud_base_url="",
            alt_cloud_api_key="",
            alt_cloud_model="",
            ollama_url="http://localhost:11434",
            ollama_model="test-model",
            ollama_timeout=5.0,
            ollama_keep_alive="1m",
            ollama_num_predict=64,
            prompt_log_path="",
        )
        router = ModelRouter(settings)
        router.local_llm.generate = MagicMock(return_value="local output")
        router._generate_gemini = MagicMock(side_effect=RuntimeError("no cloud"))

        result = router.generate_response(
            user_message="test",
            memories=[],
            history=[],
            search_results=None,
            context=None,
        )

        router.local_llm.generate.assert_called_once()
        assert result.text == "local output"
