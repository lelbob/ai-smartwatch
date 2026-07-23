"""Athena AI entry point."""

from __future__ import annotations

import logging

from google import genai

from .config import load_settings, validate_settings
from .context_service import ContextService
from .database import Database
from .debug_log import PromptLogger
from .geolocation import GeoService
from .step_classifier import StepClassifier
from .model_router import ModelRouter
from .search_service import SearchService
from .telegram_bot import AthenaBot
from .tts import TextToSpeech
from .whisper_service import WhisperService


def main() -> None:
    settings = load_settings()
    validate_settings(settings)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger(__name__)

    database = Database(settings.database_path)
    database.initialize()

    if settings.gemini_model:
        log.warning(
            "GEMINI_MODEL is deprecated; use GEMINI_FLASH_MODEL and GEMINI_PRO_MODEL."
        )
    if not settings.gemini_api_key:
        log.warning(
            "GEMINI_API_KEY is not configured; Athena will rely on configured fallbacks."
        )

    tts = TextToSpeech(settings)
    tts.health_check().log()

    gemini_client = (
        genai.Client(api_key=settings.gemini_api_key)
        if settings.gemini_api_key
        else None
    )

    prompt_logger = PromptLogger(settings.prompt_log_path)

    context_service = ContextService(database, settings)
    geo_service = GeoService(settings.nominatim_user_agent)

    model_router = ModelRouter(settings)
    if model_router.local_llm.is_available():
        log.info("Warming up Ollama model %s ...", settings.ollama_model)
        model_router.local_llm.warm_up()

    classifier = StepClassifier(
        gemini_client,
        settings.gemini_flash_model,
        local_llm=model_router.local_llm,
        prompt_logger=prompt_logger,
    )

    bot = AthenaBot(
        token=settings.telegram_bot_token,
        database=database,
        model_router=model_router,
        whisper_service=WhisperService(settings.whisper_model),
        search_service=SearchService(settings.searxng_url),
        tts=tts,
        location=settings.athena_location,
        context_service=context_service,
        classifier=classifier,
        geo_service=geo_service,
        settings=settings,
    )

    application = bot.build_application()
    log.info("Athena is running through Telegram.")
    application.run_polling(allowed_updates=["message", "edited_message", "location"])


if __name__ == "__main__":
    main()
