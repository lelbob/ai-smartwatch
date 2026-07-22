"""Piper text-to-speech support.

Generates Telegram-friendly OGG/Opus voice files using Piper for synthesis and
FFmpeg for container conversion. The internal API is synchronous; callers in the
async Telegram layer should dispatch it via ``asyncio.to_thread`` so the Piper
and FFmpeg subprocesses never block the event loop.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Raised when voice generation cannot proceed, with a human-readable reason."""


@dataclass(frozen=True)
class TTSStatus:
    """Startup health snapshot for the Piper pipeline."""

    enabled: bool
    reason: str = ""
    voice: str = ""

    def log(self) -> None:
        if self.enabled:
            logger.info("TTS enabled (piper voice: %s).", self.voice)
        else:
            logger.warning("TTS disabled: %s", self.reason or "no reason given")


class TextToSpeech:
    """Generates Telegram-friendly voice files with Piper and FFmpeg."""

    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.voice_replies_enabled
        self.piper_executable = settings.piper_executable
        self.voices: dict[str, str] = dict(settings.piper_voices)
        self.default_voice = settings.piper_model_path or self.voices.get("default", "")
        self._health: TTSStatus | None = None

    # ------------------------------------------------------------------ health

    def health_check(self) -> TTSStatus:
        """Verify Piper, a model, and ffmpeg are all reachable.

        Returns a cached status. Safe and cheap to call at startup.
        """

        if self._health is not None:
            return self._health

        if not self.enabled:
            self._health = TTSStatus(enabled=False, reason="VOICE_REPLIES_ENABLED is not set")
            return self._health

        if not shutil.which(self.piper_executable):
            self._health = TTSStatus(
                enabled=False,
                reason=f"piper executable '{self.piper_executable}' not found on PATH",
            )
            return self._health

        if not self.default_voice or not Path(self.default_voice).is_file():
            self._health = TTSStatus(
                enabled=False,
                reason=f"Piper model not found at '{self.default_voice}'",
            )
            return self._health

        if not shutil.which("ffmpeg"):
            self._health = TTSStatus(enabled=False, reason="ffmpeg not found on PATH")
            return self._health

        self._health = TTSStatus(enabled=True, voice=self.default_voice)
        return self._health

    # ------------------------------------------------------------- generation

    def generate_voice(self, text: str, voice: str | None = None) -> Path:
        """Synthesize ``text`` to an OGG/Opus file and return its path.

        Raises ``TTSError`` with a specific reason on any failure. The caller owns
        cleanup of the returned file's parent temp directory.
        """

        status = self.health_check()
        if not status.enabled:
            raise TTSError(status.reason)

        cleaned = (text or "").strip()
        if not cleaned:
            raise TTSError("nothing to synthesize (empty text)")

        model_path = self._resolve_voice(voice)
        if not model_path:
            raise TTSError("no Piper voice model available")

        temp_dir = Path(tempfile.mkdtemp(prefix="athena_tts_"))
        wav_path = temp_dir / "reply.wav"
        ogg_path = temp_dir / "reply.ogg"

        try:
            self._run_piper(model_path, cleaned, wav_path)
            self._run_ffmpeg(wav_path, ogg_path)
        except Exception:
            # Generation failed; clean up the partial temp dir immediately.
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        logger.info("TTS voice generated (%d chars, voice=%s).", len(cleaned), model_path)
        return ogg_path

    @staticmethod
    def cleanup(path: Path) -> None:
        """Remove the temp directory that owns a generated voice file."""

        parent = path.parent
        if parent.name.startswith("athena_tts_"):
            shutil.rmtree(parent, ignore_errors=True)

    # ----------------------------------------------------------------- helpers

    def _resolve_voice(self, voice: str | None) -> str:
        if voice and voice in self.voices:
            return self.voices[voice]
        return self.default_voice

    def _run_piper(self, model_path: str, text: str, wav_path: Path) -> None:
        try:
            subprocess.run(
                [
                    self.piper_executable,
                    "--model",
                    model_path,
                    "--output_file",
                    str(wav_path),
                ],
                input=text,
                text=True,
                check=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            raise TTSError(f"piper executable not found: {self.piper_executable}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise TTSError(
                f"piper failed (exit {exc.returncode}): {stderr[:200]}"
            ) from exc

    def _run_ffmpeg(self, wav_path: Path, ogg_path: Path) -> None:
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(wav_path),
                    "-c:a",
                    "libopus",
                    str(ogg_path),
                ],
                check=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            raise TTSError("ffmpeg not found") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise TTSError(
                f"ffmpeg failed (exit {exc.returncode}): {stderr[:200]}"
            ) from exc
