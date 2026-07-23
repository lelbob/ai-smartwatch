"""LLM-driven intent classification (P3).

Uses Gemini's native structured-output mode (response_mime_type + response_schema)
to guarantee valid JSON, with a tolerant parser as a belt-and-suspenders fallback.
Falls back to ``None`` (signalling the router to use the regex cascade) when the
model is unavailable, so the bot never goes dark.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from google import genai
from google.genai import types as gtypes

from .context_service import UserContext
from .debug_log import PromptLogger
from .tool_spec import REQUIRED_FIELDS, TOOLS, build_catalogue_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentDecision:
    tool: str
    args: dict[str, str]
    missing_fields: list[str] = field(default_factory=list)
    confidence: float = 1.0
    needs_clarification: bool = False

    @property
    def is_valid(self) -> bool:
        return self.tool in TOOLS and self.confidence >= 0.5


SYSTEM_INSTRUCTION = (
    "You are the intent router for Athena, a personal butler assistant. "
    "Given the user's latest message and the recent conversation, choose exactly "
    "ONE tool and extract its arguments. Be decisive.\n\n"
    "Rules:\n"
    "- If a REQUIRED argument is clearly absent from the message, put it in "
    "missing_fields and set needs_clarification=true. Never invent values.\n"
    "- Pick the most specific tool. Use general_chat only for greetings, "
    "opinions, or anything no other tool covers.\n"
    "- confidence reflects how sure you are of the TOOL choice, not the args.\n"
    "- For memory: 'remember that...' or 'note: I should...' -> store; "
    "'when/what is my...' -> leave content empty to recall.\n"
    "- For task: extract the natural-language task text into 'content' and the "
    "natural-language due date/time into 'due'. The 'content' must NOT include "
    "the due date/time phrase itself. For example, for 'add task study for exam "
    "next Friday', set content='study for exam' and due='next Friday'.\n"
    "- For reminder: extract the reminder topic/text into 'content' and the "
    "natural-language time/date into 'when'. The 'content' must NOT include "
    "the time/date phrase. For example, for 'remind me to call mom tomorrow at "
    "5pm', set content='call mom' and when='tomorrow at 5pm'.\n"
    "- IMPORTANT: use 'search' tool for ANY question about the real world that "
    "requires live/current information you would not know: sports scores, "
    "current events, news, weather, prices, who won a match, what is happening "
    "now, stock prices, flight status, election results, etc. When in doubt "
    "between search and general_chat, prefer search.\n"
    "- Examples that MUST use search:\n"
    "  'what world cup match is happening right now' -> search\n"
    "  'who won the game last night' -> search\n"
    "  'what's the weather like' -> search\n"
    "  'latest news' -> search\n"
    "  'how much is bitcoin right now' -> search\n"
    "- For delete: use this when the user wants to remove, delete, clear, or get rid "
    "of a saved item, task, or reminder. Extract what they want deleted into 'target' "
    "exactly as said. If they want everything deleted, set target='all'. "
    "Examples: 'delete the dog task' -> target='the dog task'; "
    "'remove item 3' -> target='3'; 'clear all my tasks' -> target='all'.\n"
)


# --- Pydantic-free schema dict for Gemini structured output -----------------
# Gemini Developer API does NOT support `additionalProperties`. We define all
# known arg fields explicitly and let the tolerant parser handle extras.
RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": list(TOOLS)},
        "args": {
            "type": "object",
            "description": "Extracted argument values for the chosen tool.",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The main task description or reminder content. This MUST NOT contain the due date/time phrase itself. Remove the date/time phrase from it. Example: for 'add task read book tomorrow', content='read book' (not 'read book tomorrow')."
                },
                "query": {"type": "string"},
                "when": {
                    "type": "string",
                    "description": "The natural-language time for a reminder. Extract ONLY the date/time/duration phrase. Example: 'tomorrow at 5pm'."
                },
                "due": {
                    "type": "string",
                    "description": "The natural-language due date/time for a task. Extract ONLY the date/time phrase. Example: 'next Friday'."
                },
                "target": {
                    "type": "string",
                    "description": "For delete: what the user wants deleted (item name, number, or 'all' to clear everything)."
                },
            },
        },
        "missing_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Required fields the user did not provide.",
        },
        "confidence": {"type": "number"},
        "needs_clarification": {"type": "boolean"},
    },
    "required": ["tool", "args", "missing_fields", "confidence", "needs_clarification"],
}


class IntentClassifier:
    """Classifies a user message into a tool + args via Gemini."""

    def __init__(
        self,
        client: genai.Client | None,
        model: str,
        prompt_logger: PromptLogger | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.prompt_logger = prompt_logger or PromptLogger(None)

    def classify(
        self,
        text: str,
        history: list[dict[str, str]],
        context: UserContext | None = None,
    ) -> IntentDecision | None:
        """Return an IntentDecision, or None if classification is unavailable."""

        if self.client is None:
            logger.info("[INTENT] no Gemini client; using regex fallback")
            return None

        prompt = self._build_prompt(text, history, context)
        raw = self._call_model(prompt)
        if raw is None:
            self.prompt_logger.log(
                label="intent", prompt=prompt, response="(call failed)", model=self.model
            )
            return None

        self.prompt_logger.log(label="intent", prompt=prompt, response=raw, model=self.model)

        decision = self._parse(raw)
        if decision is None:
            logger.warning("[INTENT] could not parse output: %r", raw[:200])
        else:
            logger.info(
                "[INTENT] tool=%s args=%s missing=%s conf=%.2f",
                decision.tool,
                decision.args,
                decision.missing_fields,
                decision.confidence,
            )
        return decision

    # ------------------------------------------------------------- model call

    def _call_model(self, prompt: str) -> str | None:
        """Call Gemini with structured-output mode; fall back to plain text."""

        generate_config = gtypes.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.0,
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=generate_config,
            )
            return getattr(response, "text", "") or ""
        except Exception:
            logger.warning("[INTENT] structured call failed; trying plain text", exc_info=True)

        # Fallback: plain text (older endpoints / some models).
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return getattr(response, "text", "") or ""
        except Exception:
            logger.warning("[INTENT] plain-text call also failed", exc_info=True)
            return None

    # ------------------------------------------------------------------ prompt

    def _build_prompt(
        self,
        text: str,
        history: list[dict[str, str]],
        context: UserContext | None,
    ) -> str:
        history_block = "\n".join(
            f"{h['role']}: {h['content']}" for h in history[-6:]
        ) or "(none)"
        context_block = context.to_prompt_block() if context else ""

        return (
            f"{SYSTEM_INSTRUCTION}\n"
            f"{context_block}\n\n"
            f"TOOLS:\n{build_catalogue_text()}\n\n"
            f"REQUIRED FIELDS PER TOOL:\n{_format_required()}\n\n"
            f"Recent conversation:\n{history_block}\n\n"
            f"User message:\n{text}\n"
        )

    # ------------------------------------------------------------------ parse

    def _parse(self, raw: str) -> IntentDecision | None:
        payload = _extract_json(raw)
        if not isinstance(payload, dict):
            return None

        tool = str(payload.get("tool", "")).strip().lower()
        if tool not in TOOLS:
            return None

        raw_args = payload.get("args", {})
        args = {str(k): str(v) for k, v in raw_args.items()} if isinstance(raw_args, dict) else {}

        raw_missing = payload.get("missing_fields", [])
        if not isinstance(raw_missing, list):
            raw_missing = []
        declared_missing = [str(f) for f in raw_missing]

        # Independently re-check required fields so a forgetful model can't hide them.
        required = REQUIRED_FIELDS.get(tool, ())
        effective_missing = list(declared_missing)
        for field_name in required:
            if field_name not in args and field_name not in effective_missing:
                effective_missing.append(field_name)

        confidence = _to_float(payload.get("confidence"), 0.8)
        needs_clarification = bool(payload.get("needs_clarification")) or bool(effective_missing)

        return IntentDecision(
            tool=tool,
            args=args,
            missing_fields=effective_missing,
            confidence=confidence,
            needs_clarification=needs_clarification,
        )


def _format_required() -> str:
    return "\n".join(f"- {t}: {', '.join(f) or '(none)'}" for t, f in REQUIRED_FIELDS.items())


def _extract_json(raw: str) -> object | None:
    """Pull a JSON object out of a possibly-noisy model response."""

    raw = raw.strip()
    # Strip markdown fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Last resort: first {...} block.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
