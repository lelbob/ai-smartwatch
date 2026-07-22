"""Voice transcription with Whisper."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import whisper

logger = logging.getLogger(__name__)


class WhisperService:
    """Loads Whisper once and transcribes Telegram voice files."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            logger.info("Loading Whisper model: %s", self.model_name)
            self._model = whisper.load_model(self.model_name)
        return self._model

    def transcribe(self, audio_path: Path) -> str:
        result = self.model.transcribe(str(audio_path))
        text = str(result.get("text", "")).strip()
        if not text:
            raise RuntimeError("Whisper did not return any transcription text.")
        return text

