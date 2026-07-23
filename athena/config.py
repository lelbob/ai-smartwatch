"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


@dataclass(frozen=True)
class Settings:
    """Runtime settings for Athena."""

    telegram_bot_token: str
    gemini_api_key: str
    gemini_model: str
    gemini_flash_model: str
    gemini_pro_model: str
    alt_cloud_base_url: str
    alt_cloud_api_key: str
    alt_cloud_model: str
    searxng_url: str
    athena_location: str
    athena_timezone: str
    ollama_url: str
    ollama_model: str
    ollama_timeout: float
    ollama_keep_alive: str
    ollama_num_predict: int
    voice_replies_enabled: bool
    piper_executable: str
    piper_model_path: str
    piper_voices: dict[str, str]
    nominatim_user_agent: str
    database_path: Path
    whisper_model: str
    log_level: str
    prompt_log_path: str
    history_window: int
    history_max_chars: int
    reminder_check_interval: int  # seconds between proactive checks


def load_settings() -> Settings:
    """Load settings from .env and the current shell environment."""

    load_dotenv()

    database_path = Path(
        os.getenv("ATHENA_DATABASE_PATH", str(DATA_DIR / "athena.db"))
    ).expanduser()

    legacy_gemini_model = os.getenv("GEMINI_MODEL", "")
    gemini_flash_model = os.getenv(
        "GEMINI_FLASH_MODEL", legacy_gemini_model or "gemini-2.5-flash"
    )
    gemini_pro_model = os.getenv(
        "GEMINI_PRO_MODEL", legacy_gemini_model or "gemini-2.5-pro"
    )

    piper_model_path = os.getenv("PIPER_MODEL_PATH", "")

    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=legacy_gemini_model,
        gemini_flash_model=gemini_flash_model,
        gemini_pro_model=gemini_pro_model,
        alt_cloud_base_url=os.getenv("ALT_CLOUD_BASE_URL", ""),
        alt_cloud_api_key=os.getenv("ALT_CLOUD_API_KEY", ""),
        alt_cloud_model=os.getenv("ALT_CLOUD_MODEL", ""),
        searxng_url=os.getenv("SEARXNG_URL", "http://localhost:8081"),
        athena_location=os.getenv("ATHENA_LOCATION", ""),
        athena_timezone=os.getenv("ATHENA_TIMEZONE", "UTC"),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "gemma3:4b"),
        ollama_timeout=_env_float("OLLAMA_TIMEOUT", default=120.0),
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
        ollama_num_predict=_env_int("OLLAMA_NUM_PREDICT", default=256),
        voice_replies_enabled=_env_bool("VOICE_REPLIES_ENABLED", default=False),
        piper_executable=os.getenv("PIPER_EXECUTABLE", "piper"),
        piper_model_path=piper_model_path,
        piper_voices=_load_voice_map(piper_model_path),
        nominatim_user_agent=os.getenv(
            "NOMINATIM_USER_AGENT", "athena-ai/1.0 (personal-assistant)"
        ),
        database_path=database_path,
        whisper_model=os.getenv("WHISPER_MODEL", "base"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        prompt_log_path=os.getenv("PROMPT_LOG_PATH", "athena/data/prompts.log"),
        history_window=_env_int("HISTORY_WINDOW", default=12),
        history_max_chars=_env_int("HISTORY_MAX_CHARS", default=1500),
        reminder_check_interval=_env_int("REMINDER_CHECK_INTERVAL", default=600),
    )


def validate_settings(settings: Settings) -> None:
    """Raise a clear error if required settings are missing."""

    missing: list[str] = []
    if not settings.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variable(s): {names}")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _load_voice_map(default_model_path: str) -> dict[str, str]:
    """Parse PIPER_VOICES="voice1=/path,voice2=/path" into a dict.

    Falls back to a single "default" entry pointing at PIPER_MODEL_PATH.
    """

    raw = os.getenv("PIPER_VOICES", "").strip()
    voices: dict[str, str] = {}
    if raw:
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if "=" in entry:
                name, path = entry.split("=", 1)
                voices[name.strip()] = path.strip()
            else:
                voices.setdefault("default", entry.strip())
    if default_model_path and "default" not in voices:
        voices["default"] = default_model_path
    return voices
