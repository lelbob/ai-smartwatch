"""Tests for the bug-fix round: Ollama retry, prompt logging, history budgeting."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from athena.database import Database
from athena.debug_log import PromptLogger
from athena.local_llm import LocalLLM


# ----------------------------------------------------------------------- helpers


def _settings(**overrides) -> SimpleNamespace:
    defaults = dict(
        telegram_bot_token="tok",
        gemini_api_key="key",
        gemini_flash_model="flash",
        gemini_pro_model="pro",
        alt_cloud_base_url="",
        alt_cloud_api_key="",
        alt_cloud_model="",
        ollama_url="http://localhost:11434",
        ollama_model="gemma3:4b",
        ollama_timeout=120.0,
        ollama_keep_alive="30m",
        ollama_num_predict=256,
        piper_executable="piper",
        piper_model_path="",
        piper_voices={},
        searxng_url="http://localhost:8081",
        athena_location="Singapore",
        athena_timezone="Asia/Singapore",
        voice_replies_enabled=False,
        nominatim_user_agent="test/1.0",
        prompt_log_path="",
        history_window=12,
        history_max_chars=1500,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    return database


@pytest.fixture
def user_id(db):
    return db.upsert_user(
        telegram_user_id=12345,
        username="testuser",
        first_name="Test",
        last_name="User",
    )


# ------------------------------------------------------------------- PromptLogger


class TestPromptLogger:
    def test_log_creates_file_and_appends(self, tmp_path):
        log_path = str(tmp_path / "test.log")
        logger = PromptLogger(log_path)
        logger.log(label="chat", prompt="hello", response="hi", model="test", user_id=1)
        logger.log(label="classify", prompt="what?", response="chitchat", model="test", user_id=1)

        content = Path(log_path).read_text()
        assert "chat" in content
        assert "hello" in content
        assert "classify" in content
        assert "chitchat" in content
        # Two entries, each starts with a separator line
        assert content.count("=" * 78) == 2

    def test_disabled_when_path_empty(self):
        logger = PromptLogger("")
        logger.log(label="chat", prompt="hello", response="hi", model="test", user_id=1)
        # Should not raise

    def test_disabled_when_path_none(self):
        logger = PromptLogger(None)
        logger.log(label="chat", prompt="hello", response="hi", model="test", user_id=1)
        # Should not raise

    def test_never_raises_on_caller(self, tmp_path):
        log_path = str(tmp_path / "test.log")
        logger = PromptLogger(log_path)
        # Even with weird content, no error should propagate
        logger.log(label="", prompt="", response="", model="", user_id=None)
        assert Path(log_path).exists()

    def test_log_contains_user_id(self, tmp_path):
        log_path = str(tmp_path / "test.log")
        logger = PromptLogger(log_path)
        logger.log(label="chat", prompt="p", response="r", model="m", user_id=42)
        content = Path(log_path).read_text()
        assert "42" in content

    def test_log_concurrent_writes(self, tmp_path):
        import threading

        log_path = str(tmp_path / "test.log")
        logger = PromptLogger(log_path)

        def write_n(n):
            for i in range(50):
                logger.log(label=f"t{n}", prompt=f"p{i}", response=f"r{i}", model="m", user_id=n)

        threads = [threading.Thread(target=write_n, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        content = Path(log_path).read_text()
        # Each entry has one separator line; 4 threads × 50 = 200 entries
        assert content.count("=" * 78) == 200


# ------------------------------------------------------------- LocalLLM rewrite


class TestLocalLLM:
    def test_init_stores_settings(self):
        llm = LocalLLM(
            base_url="http://localhost:11434",
            model="gemma3:4b",
            timeout_seconds=90,
            keep_alive="10m",
            num_predict=128,
        )
        assert llm.timeout_seconds == 90
        assert llm.keep_alive == "10m"
        assert llm.num_predict == 128

    def test_is_available_false_when_unreachable(self):
        llm = LocalLLM(
            base_url="http://localhost:19999",
            model="nonexistent",
            timeout_seconds=2,
            keep_alive="1m",
            num_predict=64,
        )
        assert llm.is_available() is False

    def test_warm_up_no_raise_when_unavailable(self):
        llm = LocalLLM(
            base_url="http://localhost:19999",
            model="nonexistent",
            timeout_seconds=2,
            keep_alive="1m",
            num_predict=64,
        )
        llm.warm_up()  # should not raise


# ---------------------------------------------------- History budgeting


class TestHistoryBudgeting:
    def test_basic_recent_history(self, db, user_id):
        for i in range(5):
            db.add_history(user_id, "user", f"msg {i}")
            db.add_history(user_id, "assistant", f"reply {i}")

        rows = db.recent_history(user_id, limit=10, max_chars=9999)
        assert len(rows) == 10

    def test_trims_oldest_when_over_budget(self, db, user_id):
        # Each message is ~50 chars; budget for ~4 messages
        for i in range(10):
            db.add_history(user_id, "user", f"This is message number {i} with some padding text here.")
            db.add_history(user_id, "assistant", f"And here is reply number {i} with extra padding too.")

        rows = db.recent_history(user_id, limit=20, max_chars=250)
        # Should have fewer than 20 rows due to budget
        assert len(rows) < 20
        assert len(rows) > 0

    def test_keeps_newest_when_trimming(self, db, user_id):
        # Insert directly with distinct timestamps to avoid CURRENT_TIMESTAMP collisions.
        import sqlite3
        from datetime import datetime, timedelta

        with db.connect() as conn:
            base = datetime(2026, 1, 1, 12, 0, 0)
            for i in range(10):
                ts = (base + timedelta(seconds=i)).isoformat()
                conn.execute(
                    "INSERT INTO conversation_history (user_id, role, content, created_at) VALUES (?,?,?,?)",
                    (user_id, "user", f"User message {i}", ts),
                )
                conn.execute(
                    "INSERT INTO conversation_history (user_id, role, content, created_at) VALUES (?,?,?,?)",
                    (user_id, "assistant", f"Bot reply {i}", ts),
                )

        # Budget of ~120 chars fits ~8 messages, dropping the oldest few.
        rows = db.recent_history(user_id, limit=20, max_chars=120)
        assert len(rows) < 20
        # Oldest message (i=0) should be trimmed out
        contents = [str(row["content"]) for row in rows]
        assert "User message 0" not in contents
        # Newest messages should be present
        assert any("9" in c for c in contents)

    def test_history_before_cutoff(self, db, user_id):
        for i in range(10):
            db.add_history(user_id, "user", f"msg {i}")
            db.add_history(user_id, "assistant", f"reply {i}")

        kept = db.recent_history(user_id, limit=20, max_chars=200)
        dropped = db.history_before_cutoff(user_id, limit=20, max_chars=200)

        # Dropped should be the ones not in kept
        kept_ids = {row["created_at"] for row in kept}
        dropped_ids = {row["created_at"] for row in dropped}
        assert kept_ids.isdisjoint(dropped_ids)

    def test_no_dropped_when_budget_sufficient(self, db, user_id):
        for i in range(3):
            db.add_history(user_id, "user", f"hi {i}")
            db.add_history(user_id, "assistant", f"hey {i}")

        dropped = db.history_before_cutoff(user_id, limit=10, max_chars=9999)
        assert dropped == []

    def test_empty_history(self, db, user_id):
        rows = db.recent_history(user_id, limit=10, max_chars=1500)
        assert rows == []


# ---------------------------------------------------------- main.py wiring


class TestMainWiring:
    def test_tool_router_accepts_settings(self):
        """Verify ToolRouter.__init__ signature includes settings."""
        from athena.tool_router import ToolRouter
        import inspect

        sig = inspect.signature(ToolRouter.__init__)
        assert "settings" in sig.parameters

    def test_athena_bot_accepts_settings(self):
        """Verify AthenaBot.__init__ signature includes settings."""
        from athena.telegram_bot import AthenaBot
        import inspect

        sig = inspect.signature(AthenaBot.__init__)
        assert "settings" in sig.parameters

    def test_step_classifier_accepts_prompt_logger(self):
        """Verify StepClassifier.__init__ signature includes prompt_logger."""
        from athena.step_classifier import StepClassifier
        import inspect

        sig = inspect.signature(StepClassifier.__init__)
        assert "prompt_logger" in sig.parameters
