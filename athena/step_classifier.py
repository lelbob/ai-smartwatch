"""Two-step LLM classifier for Athena.

Step 1: Pick the tool category (task / search / chat / briefing).
Step 2: Extract structured arguments for that category.

Each step is a tiny, focused prompt so even small local models (gemma3:4b)
can handle them reliably.  Falls back gracefully when models are offline.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from google import genai

from .context_service import UserContext
from .debug_log import PromptLogger

logger = logging.getLogger(__name__)

# The four tool categories.
TOOLS = ("task", "search", "chat", "briefing")

# Valid task sub-actions.
TASK_ACTIONS = ("add", "delete", "complete", "list", "recall")


@dataclass(frozen=True)
class StepDecision:
    """Result of the two-step classification pipeline."""

    tool: str  # task | search | chat | briefing
    action: str = ""  # For task: add | delete | complete | list | recall
    args: dict[str, object] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.tool in TOOLS


# ── Step 1 prompt ──────────────────────────────────────────────────────────

_STEP1_SYSTEM = """\
You are a message router for a personal assistant.
Classify the user's message into exactly ONE category.

Categories:
- task: Adding, deleting, completing, or listing tasks, reminders, notes, or memories. Also recalling stored facts.
- search: Any question needing live/current information (weather, news, sports scores, prices, events, etc.)
- chat: Greetings, opinions, general conversation, or anything not covered above.
- briefing: The user wants their daily summary/briefing.

Reply with ONLY the category name (one word). Nothing else."""

# ── Step 2 prompts (per tool) ──────────────────────────────────────────────

_STEP2_TASK = """\
The user sent a task/reminder/note command. Extract the action and details.

Actions:
- add: Save a new task, reminder, note, or memory.
- delete: Remove one or more items. If the user says a range like "1 to 5", expand it to individual numbers [1,2,3,4,5]. If they name an item, put the name in targets.
- complete: Mark items as done. Same target rules as delete.
- list: Show current tasks/items.
- recall: Look up a previously saved fact or memory.

Reply as JSON (no markdown, no explanation):
{"action": "add|delete|complete|list|recall", "content": "task text without the time part", "when": "time/date phrase if any", "targets": ["list of item numbers or names to delete/complete"], "query": "what to recall"}

Only include fields that are relevant. Examples:
- "remind me to read a book next Friday at 5pm" -> {"action": "add", "content": "read a book", "when": "next Friday at 5pm"}
- "delete 1 to 5" -> {"action": "delete", "targets": ["1","2","3","4","5"]}
- "remove the dog task" -> {"action": "delete", "targets": ["dog task"]}
- "delete everything" -> {"action": "delete", "targets": ["all"]}
- "done with item 3" -> {"action": "complete", "targets": ["3"]}
- "what tasks do I have?" -> {"action": "list"}
- "when is my exam?" -> {"action": "recall", "query": "exam"}
- "remember that my physics exam is Friday" -> {"action": "add", "content": "my physics exam is Friday"}
- "note: buy milk" -> {"action": "add", "content": "buy milk"}

User message: {message}"""

_STEP2_SEARCH = """\
The user wants to search for information. Extract the search query.
Strip any leading phrases like "search for", "look up", "what is".

Reply as JSON (no markdown): {{"query": "the search query"}}

User message: {message}"""


class StepClassifier:
    """Two-step intent classifier using small, focused LLM prompts."""

    def __init__(
        self,
        gemini_client: genai.Client | None,
        model: str,
        local_llm: object | None = None,
        prompt_logger: PromptLogger | None = None,
    ) -> None:
        self.gemini_client = gemini_client
        self.model = model
        self.local_llm = local_llm
        self.prompt_logger = prompt_logger or PromptLogger(None)

    # ── public API ─────────────────────────────────────────────────────────

    def classify(
        self,
        text: str,
        context: UserContext | None = None,
    ) -> StepDecision | None:
        """Run the two-step classification pipeline.

        Returns a StepDecision or None if no model is reachable.
        """
        # Step 1: pick the tool category.
        tool = self._step1_tool(text, context)
        if tool is None:
            return None

        # Step 2: extract args for that tool.
        if tool == "chat":
            return StepDecision(tool="chat")

        if tool == "briefing":
            return StepDecision(tool="briefing")

        if tool == "search":
            args = self._step2_search(text)
            return StepDecision(tool="search", args=args)

        if tool == "task":
            action, args = self._step2_task(text)
            return StepDecision(tool="task", action=action, args=args)

        return StepDecision(tool="chat")

    # ── Step 1: tool selection ─────────────────────────────────────────────

    def _step1_tool(self, text: str, context: UserContext | None) -> str | None:
        """Ask the LLM to pick one of four categories."""
        context_block = context.to_prompt_block() if context else ""
        prompt = f"{_STEP1_SYSTEM}\n\n{context_block}\n\nUser message:\n{text}"

        raw = self._call_llm(prompt, label="step1")
        if raw is None:
            return None

        # Parse: the model should return a single word.
        cleaned = raw.strip().lower().strip("\"'. ")
        # Handle models that return "Category: task" or "The category is task"
        for tool in TOOLS:
            if tool in cleaned:
                return tool

        logger.warning("[STEP1] could not parse tool from: %r", raw[:100])
        return "chat"  # safe fallback

    # ── Step 2: argument extraction ────────────────────────────────────────

    def _step2_task(self, text: str) -> tuple[str, dict]:
        """Extract task action and arguments."""
        prompt = _STEP2_TASK.replace("{message}", text)
        raw = self._call_llm(prompt, label="step2_task")
        if raw is None:
            # Can't extract args — treat as add with the full text.
            return "add", {"content": text}

        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            return "add", {"content": text}

        action = str(parsed.get("action", "add")).lower().strip()
        if action not in TASK_ACTIONS:
            action = "add"

        args: dict[str, object] = {}
        for key in ("content", "when", "query"):
            val = parsed.get(key)
            if val and str(val).strip():
                args[key] = str(val).strip()

        targets = parsed.get("targets")
        if isinstance(targets, list):
            args["targets"] = [str(t).strip() for t in targets if str(t).strip()]

        return action, args

    def _step2_search(self, text: str) -> dict:
        """Extract search query."""
        prompt = _STEP2_SEARCH.replace("{message}", text)
        raw = self._call_llm(prompt, label="step2_search")
        if raw is None:
            # Fallback: use the raw text as the query.
            return {"query": text}

        parsed = _extract_json(raw)
        if isinstance(parsed, dict) and parsed.get("query"):
            return {"query": str(parsed["query"]).strip()}

        return {"query": text}

    # ── LLM call (Gemini → local fallback) ─────────────────────────────────

    def _call_llm(self, prompt: str, label: str) -> str | None:
        """Try Gemini first, then local LLM. Return raw text or None."""
        # Try Gemini.
        if self.gemini_client is not None:
            try:
                response = self.gemini_client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                )
                text = getattr(response, "text", "") or ""
                if text.strip():
                    self.prompt_logger.log(
                        label=label, prompt=prompt, response=text, model=self.model,
                    )
                    return text
            except Exception:
                logger.warning("[%s] Gemini call failed", label, exc_info=True)

        # Try local LLM.
        if self.local_llm is not None:
            try:
                text = self.local_llm.generate(prompt)
                if text and text.strip():
                    self.prompt_logger.log(
                        label=label, prompt=prompt, response=text, model="local",
                    )
                    return text
            except Exception:
                logger.warning("[%s] local LLM call failed", label, exc_info=True)

        return None


# ── JSON extraction helper ─────────────────────────────────────────────────

def _extract_json(raw: str) -> object | None:
    """Pull a JSON object out of a possibly-noisy model response."""
    raw = raw.strip()
    # Strip markdown fences.
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
