"""Central tool selection for Athena — two-step AI pipeline.

Routing flow:
1. Check pending multi-step actions (P4 resume).
2. StepClassifier.classify() → picks tool + extracts args in two LLM calls.
3. Execute the action via a clean handler.

No regex fallback cascade. Requires at least one model (Gemini or Ollama).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from telegram.ext import Application

from .briefing import BriefingService
from .config import Settings
from .context_service import ContextService, UserContext
from .database import Database
from .model_router import ModelRouter
from .reminders import RemindersService
from .saved_items import SavedItemsService
from .search_service import SearchResult, SearchService
from .step_classifier import StepClassifier, StepDecision
from .tasks import TasksService

logger = logging.getLogger(__name__)

# Pending-tool identifiers.
PENDING_VOICE_PREFERENCE = "set_voice_preference"


@dataclass(frozen=True)
class ToolResult:
    reply: str
    used_search: bool = False
    search_results: list[SearchResult] | None = None
    model_name: str | None = None
    tool: str | None = None


class ToolRouter:
    """Routes user messages through the two-step AI pipeline."""

    def __init__(
        self,
        database: Database,
        tasks: TasksService,
        reminders: RemindersService,
        search_service: SearchService,
        briefing: BriefingService,
        model_router: ModelRouter,
        context_service: ContextService,
        classifier: StepClassifier,
        settings: Settings,
    ) -> None:
        self.database = database
        self.tasks = tasks
        self.reminders = reminders
        self.search_service = search_service
        self.briefing = briefing
        self.model_router = model_router
        self.context_service = context_service
        self.classifier = classifier
        self.settings = settings
        self.saved_items = SavedItemsService()

    # ------------------------------------------------------------------- entry

    def route(
        self,
        text: str,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None = None,
    ) -> ToolResult:
        context = self.context_service.get_context(user_id)
        self.saved_items.delete_expired()

        # P4: resume a pending multi-step action before classifying anew.
        pending = self.database.get_pending_action(user_id)
        if pending is not None:
            resumed = self._resume_pending(
                text, user_id, telegram_chat_id, application, context, pending
            )
            if resumed is not None:
                return resumed

        # Two-step AI classification.
        decision = self.classifier.classify(text, context)
        if decision is not None and decision.is_valid:
            result = self._execute_decision(
                text, decision, user_id, telegram_chat_id, application, context
            )
            if result is not None:
                return result

        # No model could classify — answer with whatever model is available.
        return self._answer_with_model(user_id, text, [], tool="chat")

    # ---------------------------------------------------- pending-action flow

    def _resume_pending(
        self,
        text: str,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
        pending: object,
    ) -> ToolResult | None:
        tool = str(pending["pending_tool"])
        args = json.loads(str(pending["args_json"]) or "{}")

        if tool == PENDING_VOICE_PREFERENCE:
            return self._resume_voice_preference(text, user_id)

        if tool == "reminder":
            return self._resume_reminder(
                text, user_id, telegram_chat_id, application, context, args
            )

        # Unknown pending tool: clear and let normal routing take over.
        self.database.clear_pending_action(user_id)
        return None

    def _resume_voice_preference(
        self, text: str, user_id: int
    ) -> ToolResult | None:
        from .user_preferences import PreferenceService

        pref = PreferenceService(self.database)
        enabled = pref.interpret_answer(text)
        if enabled is None:
            return ToolResult(
                reply="Please reply yes or no: would you like voice replies?"
            )
        pref.set(user_id, enabled)
        self.database.clear_pending_action(user_id)
        return ToolResult(
            reply="Voice replies are on." if enabled else "I'll reply by text.",
            tool="set_voice_preference",
        )

    def _resume_reminder(
        self,
        text: str,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
        args: dict[str, str],
    ) -> ToolResult | None:
        reminder = self.reminders.build_reminder(
            args.get("content", ""), text, context
        )
        if reminder is None:
            content = args.get("content", "").strip() or text.strip()
            self.saved_items.add(user_id, content)
            self.database.clear_pending_action(user_id)
            return ToolResult(reply=f"Saved: {content}.", tool="task")
        item = self.saved_items.add(
            user_id, reminder.text, remind_at=reminder.remind_at_utc
        )
        self.reminders.create_reminder(
            user_id=user_id,
            telegram_chat_id=telegram_chat_id,
            reminder=reminder,
            application=application,
            saved_item_id=item.id,
        )
        self.database.clear_pending_action(user_id)
        return ToolResult(
            reply=f"I'll remind you: {reminder.text}.", tool="reminder"
        )

    # ----------------------------------------------- decision execution

    def _execute_decision(
        self,
        text: str,
        decision: StepDecision,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult | None:
        handler = {
            "task": self._do_task,
            "briefing": self._do_briefing,
            "search": self._do_search,
            "chat": self._do_chat,
        }.get(decision.tool)
        if handler is None:
            return None
        return handler(
            decision, user_id, text, telegram_chat_id, application, context
        )

    # --- task handler (add / delete / complete / list / recall) ---

    def _do_task(
        self,
        decision: StepDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        action = decision.action or "add"
        args = decision.args

        if action == "list":
            return ToolResult(
                reply=self.saved_items.format_items(user_id), tool="task"
            )

        if action == "recall":
            query = str(args.get("query", "")).strip() or text
            memories = self.saved_items.retrieve_relevant(user_id, query)
            if not memories:
                return ToolResult(reply="Nothing saved about that.", tool="task")
            return ToolResult(
                reply="I recall: " + "; ".join(memories[:3]), tool="task"
            )

        if action == "delete":
            return self._do_delete(args, user_id)

        if action == "complete":
            return self._do_complete(args, user_id)

        # action == "add" (default)
        return self._do_add(args, user_id, telegram_chat_id, application, context, text)

    def _do_add(
        self,
        args: dict,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
        text: str,
    ) -> ToolResult:
        content = str(args.get("content", "")).strip() or text.strip()
        when = str(args.get("when", "")).strip()

        if when:
            # Try to create a timed reminder.
            reminder = self.reminders.build_reminder(content, when, context)
            if reminder is not None:
                item = self.saved_items.add(
                    user_id, reminder.text, remind_at=reminder.remind_at_utc
                )
                self.reminders.create_reminder(
                    user_id=user_id,
                    telegram_chat_id=telegram_chat_id,
                    reminder=reminder,
                    application=application,
                    saved_item_id=item.id,
                )
                return ToolResult(
                    reply=f"I'll remind you: {reminder.text}.", tool="reminder"
                )

        # No time or unparseable — save as an untimed item.
        self.saved_items.add(user_id, content)
        return ToolResult(reply=f"Saved: {content}.", tool="task")

    def _do_delete(self, args: dict, user_id: int) -> ToolResult:
        """Handle delete action — supports numbers, ranges, names, and 'all'."""
        targets = args.get("targets", [])
        if not targets:
            return ToolResult(
                reply="What should I delete? Give me an item number or name.",
                tool="task",
            )

        # Handle "all" / "everything".
        if any(t.lower() in ("all", "everything") for t in targets):
            items = self.saved_items.list_active(user_id)
            count = len(items)
            for item in items:
                self.saved_items.delete_matching_text(user_id, item.text)
            return ToolResult(
                reply=f"Cleared all {count} item(s).", tool="task"
            )

        deleted = []
        failed = []

        for target in targets:
            # Try as a number.
            if re.fullmatch(r"\d+", target):
                n = int(target)
                if self.saved_items.delete_visible(user_id, n):
                    deleted.append(str(n))
                else:
                    failed.append(str(n))
            else:
                # Try as text match.
                if self.saved_items.delete_matching_text(user_id, target):
                    deleted.append(target)
                else:
                    # Fuzzy: try individual words.
                    matched = False
                    for word in target.split():
                        if len(word) > 3 and self.saved_items.delete_matching_text(
                            user_id, word
                        ):
                            deleted.append(target)
                            matched = True
                            break
                    if not matched:
                        failed.append(target)

        parts = []
        if deleted:
            parts.append(f"Deleted: {', '.join(deleted)}")
        if failed:
            parts.append(f"Couldn't find: {', '.join(failed)}")
        return ToolResult(
            reply=". ".join(parts) + "." if parts else "Nothing to delete.",
            tool="task",
        )

    def _do_complete(self, args: dict, user_id: int) -> ToolResult:
        """Handle complete action — supports numbers and names."""
        targets = args.get("targets", [])
        if not targets:
            return ToolResult(
                reply="Which item should I mark as done?", tool="task"
            )

        completed = []
        failed = []

        for target in targets:
            if re.fullmatch(r"\d+", target):
                n = int(target)
                if self.saved_items.delete_visible(user_id, n):
                    completed.append(str(n))
                else:
                    failed.append(str(n))
            else:
                if self.saved_items.delete_matching_text(user_id, target):
                    completed.append(target)
                else:
                    failed.append(target)

        parts = []
        if completed:
            parts.append(f"Done: {', '.join(completed)}")
        if failed:
            parts.append(f"Couldn't find: {', '.join(failed)}")
        return ToolResult(
            reply=". ".join(parts) + "." if parts else "Nothing to complete.",
            tool="task",
        )

    # --- briefing handler ---

    def _do_briefing(
        self,
        decision: StepDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        return ToolResult(
            reply=self.briefing.build_briefing(user_id), tool="briefing"
        )

    # --- search handler ---

    def _do_search(
        self,
        decision: StepDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        query = str(decision.args.get("query", "")).strip() or text
        results = self.search_service.search(query)
        if not results:
            return ToolResult(
                reply="I couldn't find anything on that.", tool="search"
            )
        return self._answer_with_model(
            user_id, query, results, tool="search"
        )

    # --- chat handler ---

    def _do_chat(
        self,
        decision: StepDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        return self._answer_with_model(user_id, text, [], tool="chat")

    # ----------------------------------------------------------------- helpers

    def _history(self, user_id: int) -> list[dict[str, str]]:
        rows = self.database.recent_history(
            user_id,
            limit=self.settings.history_window,
            max_chars=self.settings.history_max_chars,
        )
        return [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in rows
        ]

    def _answer_with_model(
        self,
        user_id: int,
        user_message: str,
        search_results: list[SearchResult],
        tool: str,
    ) -> ToolResult:
        context = self.context_service.get_context(user_id)
        saved_item_memories = [
            item.text for item in self.saved_items.list_active(user_id)
        ]
        memories = saved_item_memories + self.saved_items.retrieve_relevant(
            user_id, user_message
        )
        history = self._history(user_id)
        response = self.model_router.generate_response(
            user_message=user_message,
            memories=memories,
            history=history,
            search_results=search_results,
            context=context,
            user_id=user_id,
        )
        return ToolResult(
            reply=response.text,
            used_search=bool(search_results),
            search_results=search_results,
            model_name=response.model_name,
            tool=tool,
        )
