"""Ollama local model fallback.

Built for reliability: keeps the model warm in memory (no cold-start timeouts),
retries once on transient errors, caps the response length so small models don't
ramble, and exposes a lightweight warm-up probe used at startup.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class LocalLLM:
    """Small Ollama client used after cloud models fail."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
        keep_alive: str = "30m",
        num_predict: int = 256,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.keep_alive = keep_alive
        self.num_predict = num_predict

    def is_available(self) -> bool:
        """Cheap reachability check; also pins the model in memory if up."""

        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            return True
        except Exception:
            return False

    def warm_up(self) -> bool:
        """Preload the model so the first real request isn't a cold start.

        Returns True if the model is reachable and loaded.
        """

        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "ok",
                    "stream": False,
                    "keep_alive": self.keep_alive,
                    "options": {"num_predict": 1, "temperature": 0},
                },
                timeout=max(self.timeout_seconds, 30.0),
            )
            response.raise_for_status()
            logger.info("[OLLAMA] warmed up %s", self.model)
            return True
        except Exception:
            logger.warning("[OLLAMA] warm-up failed; will retry on first request", exc_info=True)
            return False

    def generate(self, prompt: str) -> str:
        """Generate a reply, retrying once on transient errors."""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": self.num_predict},
        }

        # First attempt (and one retry on transient failure).
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                response = httpx.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code >= 500:
                    raise RuntimeError(f"Ollama server error {response.status_code}")
                response.raise_for_status()
                text = str(response.json().get("message", {}).get("content", "")).strip()
                if not text:
                    raise RuntimeError("Ollama returned an empty response.")
                return text
            except Exception as exc:
                last_error = exc
                if attempt == 1:
                    logger.warning("[OLLAMA] attempt 1 failed (%s); retrying...", exc)
                continue

        raise RuntimeError(f"Ollama failed after retry: {last_error}")
