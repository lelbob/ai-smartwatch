"""Model fallback routing for Athena."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from google import genai

from .config import Settings
from .context_service import UserContext
from .debug_log import PromptLogger
from .gemini_client import build_prompt
from .local_llm import LocalLLM
from .search_service import SearchResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model_name: str


class ModelRouter:
    """Attempts models in cost/reliability order."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gemini_client = (
            genai.Client(api_key=settings.gemini_api_key)
            if settings.gemini_api_key
            else None
        )
        self.local_llm = LocalLLM(
            settings.ollama_url,
            settings.ollama_model,
            timeout_seconds=settings.ollama_timeout,
            keep_alive=settings.ollama_keep_alive,
            num_predict=settings.ollama_num_predict,
        )
        self.prompt_logger = PromptLogger(settings.prompt_log_path)

    def generate_response(
        self,
        user_message: str,
        memories: list[str],
        history: list[dict[str, str]],
        search_results: list[SearchResult] | None = None,
        context: UserContext | None = None,
        user_id: int | None = None,
    ) -> ModelResponse:
        prompt = build_prompt(
            user_message=user_message,
            memories=memories,
            history=history,
            search_results=search_results or [],
            context=context,
        )

        # When search results are present, the model must synthesize them into a
        # coherent answer.  Small local models (e.g. gemma3:4b) cannot do this
        # reliably, so we require a cloud model and skip the local fallback.
        force_cloud = bool(search_results)

        attempts = [
            ("gemini-flash", self.settings.gemini_flash_model),
        ]

        if self.gemini_client:
            for label, model in attempts:
                text = self._try(label, lambda m=model: self._generate_gemini(m, prompt))
                if text is not None:
                    logger.info("[MODEL] %s", label)
                    self.prompt_logger.log(
                        label="chat", prompt=prompt, response=text, model=label, user_id=user_id
                    )
                    return ModelResponse(text=text, model_name=label)

        if self._has_alt_cloud():
            text = self._try("optional-cloud", lambda: self._generate_alt_cloud(prompt))
            if text is not None:
                logger.info("[MODEL] optional-cloud")
                self.prompt_logger.log(
                    label="chat", prompt=prompt, response=text, model="optional-cloud", user_id=user_id
                )
                return ModelResponse(text=text, model_name="optional-cloud")

        # Local model fallback — skip when search results are present because
        # small models cannot synthesize search data.
        if not force_cloud:
            text = self._try(
                self.settings.ollama_model, lambda: self.local_llm.generate(prompt)
            )
            if text is not None:
                logger.info("[MODEL] %s", self.settings.ollama_model)
                self.prompt_logger.log(
                    label="chat",
                    prompt=prompt,
                    response=text,
                    model=self.settings.ollama_model,
                    user_id=user_id,
                )
                return ModelResponse(text=text, model_name=self.settings.ollama_model)

        self.prompt_logger.log(
            label="chat", prompt=prompt, response="(no model available)", model="none", user_id=user_id
        )
        return ModelResponse(
            text="I cannot reach any model at the moment."
            + (" (cloud required for search results)" if force_cloud else ""),
            model_name="none",
        )

    def _try(self, label: str, call: object) -> str | None:
        """Run a model call; log+swallow failures, return text or None."""

        try:
            return call()  # type: ignore[operator]
        except Exception:
            logger.exception("Model attempt failed: %s", label)
            return None

    def _generate_gemini(self, model: str, prompt: str) -> str:
        if not self.gemini_client:
            raise RuntimeError("Gemini API key is not configured.")
        response = self.gemini_client.models.generate_content(
            model=model,
            contents=prompt,
        )
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise RuntimeError(f"{model} returned an empty response.")
        return text

    def _has_alt_cloud(self) -> bool:
        return all(
            [
                self.settings.alt_cloud_base_url,
                self.settings.alt_cloud_api_key,
                self.settings.alt_cloud_model,
            ]
        )

    def _generate_alt_cloud(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.settings.alt_cloud_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.alt_cloud_api_key}"},
            json={
                "model": self.settings.alt_cloud_model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45.0,
        )
        response.raise_for_status()
        payload = response.json()
        text = str(payload["choices"][0]["message"]["content"]).strip()
        if not text:
            raise RuntimeError("Optional cloud model returned an empty response.")
        return text

