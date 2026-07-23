"""Phase 2.1 tests: TTS, preferences, context, classifier, tz-aware parsing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from athena.context_service import ContextService, UserContext
from athena.database import Database
from athena.geolocation import GeoService, ResolvedLocation
from athena.step_classifier import StepClassifier, StepDecision, _extract_json
from athena.model_router import ModelRouter
from athena.reminders import RemindersService
from athena.search_service import SearchService
from athena.tasks import TasksService
from athena.tts import TTSError, TextToSpeech, TTSStatus
from athena.user_preferences import PreferenceService


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
        piper_executable="piper",
        piper_model_path="",
        piper_voices={},
        searxng_url="http://localhost:8081",
        athena_location="Singapore",
        athena_timezone="Asia/Singapore",
        voice_replies_enabled=False,
        nominatim_user_agent="test/1.0",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _db(tmp_path: Path, user_telegram_id: int = 123) -> tuple[Database, int]:
    db = Database(tmp_path / "test.db")
    db.initialize()
    user_id = db.upsert_user(user_telegram_id, None, "Test", None)
    return db, user_id


# ----------------------------------------------------------------------- TTS (P1)


class TestTextToSpeech:
    def test_health_check_disabled_when_env_false(self):
        settings = _settings(voice_replies_enabled=False, piper_model_path="/fake/model.onnx")
        tts = TextToSpeech(settings)
        status = tts.health_check()
        assert not status.enabled
        assert "VOICE_REPLIES_ENABLED" in status.reason

    def test_health_check_disabled_when_no_model(self):
        settings = _settings(voice_replies_enabled=True, piper_model_path="")
        tts = TextToSpeech(settings)
        status = tts.health_check()
        assert not status.enabled
        assert "model not found" in status.reason

    def test_health_check_disabled_when_no_piper(self):
        settings = _settings(voice_replies_enabled=True, piper_executable="nonexistent_piper_bin", piper_model_path="/fake/model.onnx")
        tts = TextToSpeech(settings)
        status = tts.health_check()
        assert not status.enabled
        assert "not found" in status.reason

    def test_health_check_enabled_when_all_present(self):
        """Use a fake ffmpeg + piper that exist as scripts on PATH."""
        settings = _settings(
            voice_replies_enabled=True,
            piper_executable="python",  # always exists
            piper_model_path=__file__,  # any existing file
        )
        with patch("shutil.which", side_effect=lambda name: True):
            tts = TextToSpeech(settings)
            status = tts.health_check()
        assert status.enabled

    def test_generate_voice_raises_when_disabled(self):
        settings = _settings(voice_replies_enabled=False)
        tts = TextToSpeech(settings)
        with pytest.raises(TTSError):
            tts.generate_voice("hello")

    def test_generate_voice_raises_when_empty(self):
        settings = _settings(voice_replies_enabled=True)
        tts = TextToSpeech(settings)
        # Bypass health check to test empty-text path.
        tts._health = TTSStatus(enabled=True, voice="test")
        with pytest.raises(TTSError, match="empty"):
            tts.generate_voice("")

    def test_cleanup_removes_temp_dir(self, tmp_path: Path):
        temp_dir = tmp_path / "athena_tts_test"
        temp_dir.mkdir()
        ogg = temp_dir / "reply.ogg"
        ogg.write_text("fake")
        assert temp_dir.exists()
        TextToSpeech.cleanup(ogg)
        assert not temp_dir.exists()

    def test_cleanup_does_not_remove_wrong_dirs(self, tmp_path: Path):
        other = tmp_path / "other_dir"
        other.mkdir()
        ogg = other / "reply.ogg"
        ogg.write_text("fake")
        TextToSpeech.cleanup(ogg)
        assert other.exists()


# ----------------------------------------------------------------------- context (P5)


class TestContextService:
    def test_returns_fallback_when_no_user(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        settings = _settings(athena_timezone="UTC", athena_location="")
        svc = ContextService(db, settings)
        ctx = svc.get_context(user_id)
        assert ctx.timezone == "UTC"
        assert ctx.location == ""

    def test_uses_user_timezone_and_location(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        db.update_user_location(user_id, 1.35, 103.82, "Singapore", "Singapore", "Asia/Singapore")
        settings = _settings(athena_timezone="UTC", athena_location="Nowhere")
        svc = ContextService(db, settings)
        ctx = svc.get_context(user_id)
        assert ctx.timezone == "Asia/Singapore"
        assert ctx.location == "Singapore, Singapore"

    def test_prompt_block_format(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        db.update_user_location(user_id, 1.35, 103.82, "Singapore", "Singapore", "Asia/Singapore")
        settings = _settings(athena_timezone="UTC")
        svc = ContextService(db, settings)
        ctx = svc.get_context(user_id)
        block = ctx.to_prompt_block()
        assert "SYSTEM CONTEXT" in block
        assert "Singapore" in block
        assert "Asia/Singapore" in block

    def test_falls_back_to_utc_for_invalid_tz(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        db.update_user_location(user_id, 0, 0, None, None, "Not/Real/Tz")
        settings = _settings(athena_timezone="Invalid")
        svc = ContextService(db, settings)
        ctx = svc.get_context(user_id)
        assert ctx.timezone == "UTC"


# ----------------------------------------------------------------------- preferences (P2)


class TestPreferenceService:
    def test_get_returns_none_when_unknown(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        svc = PreferenceService(db)
        assert svc.get(user_id) is None

    def test_set_and_get_roundtrip(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        svc = PreferenceService(db, default_voice="default_voice")
        svc.set(user_id, True)
        assert svc.get(user_id) is True
        assert svc.preferred_voice(user_id) == "default_voice"

    def test_interpret_answer_affirmative(self):
        svc = PreferenceService(MagicMock())
        assert svc.interpret_answer("yes") is True
        assert svc.interpret_answer("sure") is True
        assert svc.interpret_answer("ok") is True

    def test_interpret_answer_negative(self):
        svc = PreferenceService(MagicMock())
        assert svc.interpret_answer("no") is False
        assert svc.interpret_answer("nah") is False

    def test_interpret_answer_ambiguous(self):
        svc = PreferenceService(MagicMock())
        assert svc.interpret_answer("maybe") is None

    def test_onboarding_stores_pending_action(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        svc = PreferenceService(db)
        reply = svc.begin_onboarding(user_id)
        assert "voice" in reply.lower()
        pending = db.get_pending_action(user_id)
        assert pending is not None
        assert pending["pending_tool"] == "set_voice_preference"


# ----------------------------------------------------------------------- geolocation (P6)


class TestGeoService:
    def test_resolve_uses_cache(self):
        svc = GeoService("test/1.0")
        cached = ResolvedLocation(city="Tokyo", country="Japan", timezone="Asia/Tokyo")
        svc._cache[(35.68, 139.69)] = cached
        result = svc.resolve(35.68, 139.69)
        assert result.city == "Tokyo"

    def test_resolve_offline_timezone(self):
        """timezonefinder is offline; verify it resolves a known coordinate."""

        try:
            from timezonefinder import TimezoneFinder

            svc = GeoService("test/1.0")
            result = svc.resolve(1.35, 103.82)  # Singapore
            assert result.timezone == "Asia/Singapore"
        except ImportError:
            pytest.skip("timezonefinder not installed")


# ----------------------------------------------------------------------- classifier (P3)


class TestStepClassifier:
    def test_returns_none_when_no_client(self):
        svc = StepClassifier(gemini_client=None, model="flash")
        assert svc.classify("hello") is None

    def test_parse_valid_json(self):
        raw = '{"action": "add", "content": "exam is Friday"}'
        assert _extract_json(raw) == {"action": "add", "content": "exam is Friday"}

    def test_parse_json_in_markdown_fences(self):
        raw = '```json\n{"action": "add", "content": "buy milk"}\n```'
        assert _extract_json(raw) == {"action": "add", "content": "buy milk"}

    def test_parse_garbage_returns_none(self):
        assert _extract_json("not json at all") is None

    def test_decision_is_valid_with_known_tool(self):
        d = StepDecision(tool="task", action="add", args={"content": "test"})
        assert d.is_valid

    def test_decision_invalid_with_unknown_tool(self):
        d = StepDecision(tool="nonexistent")
        assert not d.is_valid


# ----------------------------------------------------------------------- tz-aware reminders (P7)


class TestTimezoneAwareReminders:
    def test_parse_when_returns_aware_datetime(self):
        db, user_id = _db(tmp_path := Path("."))
        db.initialize()
        ctx_svc = ContextService(db, _settings(athena_timezone="Asia/Singapore"))
        ctx = ctx_svc.get_context(user_id)
        svc = RemindersService(db)
        result = svc.parse_when("tomorrow at 9am", ctx)
        assert result is not None
        assert result.tzinfo is not None

    def test_reminder_format_displays_user_tz(self):
        from datetime import datetime, timezone
        from athena.reminders import ReminderRequest

        r = ReminderRequest(
            text="call mom",
            remind_at_utc=datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc),
            user_tz_name="Asia/Singapore",
        )
        formatted = r.format_for_user()
        assert "2026" in formatted


# ----------------------------------------------------------------------- tz-aware tasks (P7)


class TestTimezoneAwareTasks:
    def test_build_task_with_context(self):
        db, user_id = _db(tmp_path := Path("."))
        db.initialize()
        ctx_svc = ContextService(db, _settings(athena_timezone="Asia/Singapore"))
        ctx = ctx_svc.get_context(user_id)
        svc = TasksService(db)
        title, due = svc.build_task("submit the report", "tomorrow", ctx)
        assert "submit the report" in title
        assert due is not None


# ----------------------------------------------------------------------- DB migrations (P2/P6)


class TestDatabaseMigrations:
    def test_new_tables_created(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        # user_preferences table exists (get_preference doesn't crash).
        # A brand-new user has no preference row yet.
        assert db.get_preference(user_id) is None
        # conversation_state table exists (get_pending_action doesn't crash).
        assert db.get_pending_action(user_id) is None

    def test_user_location_columns_migrated(self, tmp_path: Path):
        db, user_id = _db(tmp_path)
        db.update_user_location(user_id, 1.35, 103.82, "SG", "SG", "Asia/Singapore")
        user = db.get_user(user_id)
        assert user["latitude"] == 1.35
        assert user["timezone"] == "Asia/Singapore"
