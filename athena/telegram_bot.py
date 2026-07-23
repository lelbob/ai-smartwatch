"""Telegram bot handlers for Athena."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import Message, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .briefing import BriefingService
from .config import Settings
from .context_service import ContextService
from .database import Database
from .geolocation import GeoService
from .intent_classifier import IntentClassifier
from .memory import MemoryService
from .model_router import ModelRouter
from .notes import NotesService
from .reminders import RemindersService
from .scheduler import ProactiveScheduler
from .search_service import SearchService
from .tasks import TasksService
from .tool_router import ToolRouter
from .tts import TTSError, TextToSpeech
from .user_preferences import PreferenceService
from .whisper_service import WhisperService

logger = logging.getLogger(__name__)


class AthenaBot:
    """Coordinates Telegram messages, tools, models, and voice replies."""

    def __init__(
        self,
        token: str,
        database: Database,
        model_router: ModelRouter,
        whisper_service: WhisperService,
        search_service: SearchService,
        tts: TextToSpeech,
        location: str,
        context_service: ContextService,
        classifier: IntentClassifier,
        geo_service: GeoService,
        settings: Settings,
    ) -> None:
        self.token = token
        self.database = database
        self.model_router = model_router
        self.settings = settings
        self.whisper_service = whisper_service
        self.search_service = search_service
        self.tts = tts
        self.context_service = context_service
        self.geo_service = geo_service

        memory = MemoryService(database)
        notes = NotesService(database)
        tasks = TasksService(database)
        reminders = RemindersService(database)
        briefing = BriefingService(database, search_service, location, model_router=model_router)

        self.reminders = reminders
        self.preferences = PreferenceService(database, tts.default_voice)
        self.router = ToolRouter(
            database=database,
            memory=memory,
            notes=notes,
            tasks=tasks,
            reminders=reminders,
            search_service=search_service,
            briefing=briefing,
            model_router=model_router,
            context_service=context_service,
            classifier=classifier,
            settings=settings,
        )

    def build_application(self) -> Application:
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("briefing", self.handle_command))
        app.add_handler(CommandHandler("tasks", self.handle_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        app.add_handler(MessageHandler(filters.LOCATION, self.handle_location))
        app.add_error_handler(self.handle_error)
        self.reminders.schedule_existing(app)

        # Start the proactive scheduler (periodic task/reminder nudges).
        self.scheduler = ProactiveScheduler(
            database=self.database,
            application=app,
            interval_seconds=self.settings.reminder_check_interval,
        )
        app.post_init = self._post_init
        app.post_shutdown = self._post_shutdown
        return app

    async def _post_init(self, application: Application) -> None:
        self.scheduler.start()

    async def _post_shutdown(self, application: Application) -> None:
        self.scheduler.stop()

    # ----------------------------------------------------------- command handlers

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = self._ensure_user(update)
        self.database.add_history(user_id, "assistant", "Athena started.")
        await update.effective_message.reply_text("Athena is online.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            "Ask for tasks, reminders, notes, search, or a briefing."
        )

    async def handle_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message or not update.message.text:
            return

        user_id = self._ensure_user(update)
        await self._handle_user_message(
            update=update,
            context=context,
            user_id=user_id,
            text=update.message.text,
        )

    async def handle_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message or not update.message.text:
            return

        user_id = self._ensure_user(update)
        await self._handle_user_message(
            update=update,
            context=context,
            user_id=user_id,
            text=update.message.text,
        )

    async def handle_voice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message or not update.message.voice:
            return

        user_id = self._ensure_user(update)
        await update.message.chat.send_action("typing")

        with tempfile.TemporaryDirectory(prefix="athena_voice_") as temp_dir:
            audio_path = Path(temp_dir) / "voice.ogg"
            telegram_file = await update.message.voice.get_file()
            await telegram_file.download_to_drive(custom_path=str(audio_path))

            try:
                # Whisper inference is CPU-bound; keep it off the event loop.
                text = await asyncio.to_thread(self.whisper_service.transcribe, audio_path)
            except Exception:
                logger.exception("Voice transcription failed")
                await update.message.reply_text("I could not transcribe that voice note.")
                return

        await self._handle_user_message(
            update=update,
            context=context,
            user_id=user_id,
            text=text,
            wants_voice=True,
        )

    async def handle_location(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Store a shared Telegram location and derive timezone/place."""

        if not update.message or not update.message.location:
            return

        user_id = self._ensure_user(update)
        loc = update.message.location
        latitude, longitude = loc.latitude, loc.longitude

        try:
            resolved = await asyncio.to_thread(self.geo_service.resolve, latitude, longitude)
        except Exception:
            logger.exception("Geolocation resolution failed")
            resolved = None

        self.database.update_user_location(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            city=resolved.city if resolved else None,
            country=resolved.country if resolved else None,
            timezone=resolved.timezone if resolved else None,
        )

        if resolved and (resolved.city or resolved.timezone):
            where = resolved.city or "your area"
            tz = resolved.timezone or "your timezone"
            await update.message.reply_text(f"Location saved: {where} ({tz}).")
        else:
            await update.message.reply_text("Location saved.")

    # ----------------------------------------------------------- core pipeline

    async def _handle_user_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        text: str,
        wants_voice: bool = False,
    ) -> None:
        message = update.effective_message
        if message is None:
            return

        self.database.add_history(user_id, "user", text)

        # P2: ask once whether the user wants voice replies. Only trigger when
        # there's no preference and no other pending action in flight.
        if (
            self.preferences.get(user_id) is None
            and self.database.get_pending_action(user_id) is None
        ):
            reply = self.preferences.begin_onboarding(user_id)
            self.database.add_history(user_id, "assistant", reply)
            await self._send_reply(message, reply, user_id=user_id, wants_voice=False)
            return

        try:
            result = self.router.route(
                text=text,
                user_id=user_id,
                telegram_chat_id=message.chat_id,
                application=context.application,
            )
            reply = result.reply
        except Exception:
            logger.exception("Tool routing failed")
            reply = "I encountered a problem while handling that."

        self.database.add_history(user_id, "assistant", reply)
        await self._send_reply(message, reply, user_id=user_id, wants_voice=wants_voice)

    async def _send_reply(
        self,
        message: Message,
        reply: str,
        user_id: int,
        wants_voice: bool,
    ) -> None:
        # Voice is gated by the user's saved preference, not just the input modality.
        if wants_voice:
            wants_voice = bool(self.preferences.get(user_id))

        if not wants_voice:
            await message.reply_text(reply)
            return

        voice = self.preferences.preferred_voice(user_id)
        try:
            voice_path = await asyncio.to_thread(self.tts.generate_voice, reply, voice)
        except TTSError as exc:
            logger.warning("Voice generation disabled/failed (%s); replying by text.", exc)
            await message.reply_text(reply)
            return
        except Exception:
            logger.exception("Unexpected TTS failure; replying by text.")
            await message.reply_text(reply)
            return

        try:
            with voice_path.open("rb") as audio:
                await message.reply_voice(voice=audio)
        finally:
            # Always clean up the temp directory that owns the generated file.
            self.tts.cleanup(voice_path)

    async def handle_error(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.exception("Unhandled Telegram error", exc_info=context.error)

    def _ensure_user(self, update: Update) -> int:
        user = update.effective_user
        if user is None:
            raise RuntimeError("Telegram update did not include an effective user.")

        return self.database.upsert_user(
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
