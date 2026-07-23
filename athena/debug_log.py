"""Prompt observability.

Writes every model prompt and response to an append-only log file so you can
see exactly what is being sent to the model and what came back. This is the
"file somewhere that lets me see how you prompt the ai."

Enable by setting PROMPT_LOG_PATH (defaults to athena/data/prompts.log). Set it
to empty to disable. Entries are delimited for easy reading in a text editor.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptLogger:
    """Thread-safe appender for prompt/response pairs."""

    def __init__(self, path: str | Path | None) -> None:
        self.enabled = bool(path)
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        if self.enabled and self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.warning("Could not create prompt log dir: %s", self.path.parent)
                self.enabled = False

    def log(
        self,
        *,
        label: str,
        prompt: str,
        response: str,
        model: str = "",
        user_id: int | None = None,
    ) -> None:
        """Append one prompt/response pair. Never raises on the caller."""

        if not self.enabled or self.path is None:
            return
        stamp = datetime.now().isoformat(timespec="seconds")
        user_line = f" | user_id={user_id}" if user_id is not None else ""
        model_line = f" | model={model}" if model else ""
        block = (
            f"\n{'=' * 78}\n"
            f"[{stamp}] {label}{user_line}{model_line}\n"
            f"{'-' * 78}\n"
            f"PROMPT:\n{prompt}\n"
            f"{'-' * 78}\n"
            f"RESPONSE:\n{response}\n"
        )
        try:
            with self._lock, self.path.open("a", encoding="utf-8") as handle:
                handle.write(block)
        except Exception:
            logger.warning("Failed to write prompt log", exc_info=True)
