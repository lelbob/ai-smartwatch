"""Central tool selection for Athena.

Two-layer routing:

1. **LLM layer (P3):** an IntentClassifier picks a tool and extracts args as
   JSON. If a required field is missing, we ask a clarifying question and store
   a pending action (P4) to resume on the next message.
2. **Regex fallback:** the original keyword cascade, preserved so the bot still
   works when Gemini is unavailable or returns an unparseable decision.

A pending action (set during onboarding or a clarification) is always checked
first and resolved before any new classification.
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
from .intent_classifier import IntentClassifier, IntentDecision
from .memory import MemoryService
from .model_router import ModelRouter
from .notes import NotesService
from .reminders import RemindersService
from .saved_items import SavedItemsService
from .search_service import SearchResult, SearchService
from .tasks import TasksService


logger = logging.getLogger(__name__)


# Pending-tool identifiers. Kept here to avoid a circular import with
# user_preferences.py (which the router only needs at call time).
PENDING_VOICE_PREFERENCE = "set_voice_preference"


@dataclass(frozen=True)
class ToolResult:
    reply: str
    used_search: bool = False
    search_results: list[SearchResult] | None = None
    model_name: str | None = None
    tool: str | None = None


class ToolRouter:
    """Chooses the right Athena tool for a user message."""

    def __init__(
        self,
        database: Database,
        memory: MemoryService,
        notes: NotesService,
        tasks: TasksService,
        reminders: RemindersService,
        search_service: SearchService,
        briefing: BriefingService,
        model_router: ModelRouter,
        context_service: ContextService,
        classifier: IntentClassifier,
        settings: Settings,
    ) -> None:
        self.database = database
        self.memory = memory
        self.notes = notes
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
        normalized = text.strip().lower()
        self.saved_items.delete_expired()

        # P4: resume a pending multi-step action before classifying anew.
        pending = self.database.get_pending_action(user_id)
        if pending is not None:
            resumed = self._resume_pending(text, user_id, telegram_chat_id, application, context, pending)
            if resumed is not None:
                return resumed
            # If the message looked like a brand-new command, fall through and
            # clear the pending action so it doesn't linger.

        direct_saved_result = self._direct_saved_action(
            text, normalized, user_id, telegram_chat_id, application, context
        )
        if direct_saved_result is not None:
            return direct_saved_result

        history = self._history(user_id)

        # P3: LLM-driven classification.
        decision = self.classifier.classify(text, history, context)
        if decision is not None and decision.is_valid:
            result = self._execute_decision(text, decision, user_id, telegram_chat_id, application, context)
            if result is not None:
                return result
            logger.info("LLM decision for '%s' could not execute; falling back to regex.", decision.tool)

        # Regex fallback cascade (the original working MVP path).
        return self._regex_fallback(text, user_id, telegram_chat_id, application, context)

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
            return self._resume_reminder(text, user_id, telegram_chat_id, application, context, args)

        # Unknown pending tool: clear it and let normal routing take over.
        self.database.clear_pending_action(user_id)
        return None

    def _resume_voice_preference(self, text: str, user_id: int) -> ToolResult | None:
        from .user_preferences import PreferenceService

        pref = PreferenceService(self.database)
        enabled = pref.interpret_answer(text)
        if enabled is None:
            # Ambiguous answer: keep the pending action, re-ask.
            return ToolResult(reply="Please reply yes or no: would you like voice replies?")
        pref.set(user_id, enabled)
        self.database.clear_pending_action(user_id)
        return ToolResult(
            reply=("Voice replies are on." if enabled else "I'll reply by text."),
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
        reminder = self.reminders.build_reminder(args.get("content", ""), text, context)
        if reminder is None:
            content = args.get("content", "").strip() or text.strip()
            self.saved_items.add(user_id, content)
            self.database.clear_pending_action(user_id)
            return ToolResult(reply=f"Saved: {content}.", tool="saved_item")
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
            reply=f"I'll remind you: {reminder.text}.",
            tool="reminder",
        )

    # ----------------------------------------------- LLM decision execution

    def _direct_saved_action(
        self,
        text: str,
        normalized: str,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult | None:
        """Handle saved item commands before the LLM classifier."""

        if self._is_show_items_request(normalized):
            return ToolResult(
                reply=self.saved_items.format_items(user_id), tool="saved_item"
            )

        deleted = self.saved_items.extract_delete_number(text)
        if deleted is not None:
            if self.saved_items.delete_visible(user_id, deleted):
                return ToolResult(reply=f"Deleted item {deleted}.", tool="saved_item")
            return ToolResult(reply=f"I could not find item {deleted}.", tool="saved_item")

        completed = self.saved_items.extract_complete_number(text)
        if completed is not None:
            if self.saved_items.delete_visible(user_id, completed):
                return ToolResult(reply=f"Done. Removed item {completed}.", tool="saved_item")
            return ToolResult(reply=f"I could not find item {completed}.", tool="saved_item")

        done_text = self.saved_items.extract_done_text(text)
        if done_text is not None:
            if self.saved_items.delete_matching_text(user_id, done_text):
                return ToolResult(reply="Done. Removed it.", tool="saved_item")
            return ToolResult(reply="I could not find that saved item.", tool="saved_item")

        reminder = self.reminders.extract_reminder(text, context)
        if reminder:
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
            return ToolResult(reply=f"I'll remind you: {reminder.text}.", tool="reminder")

        memory = self.memory.extract_memory(text)
        if memory:
            self.memory.save_memory(user_id, memory)
            self.saved_items.add(user_id, memory)
            return ToolResult(reply=f"Saved: {memory}.", tool="saved_item")

        note = self.notes.extract_note(text)
        if note:
            self.notes.save_note(user_id, note)
            self.saved_items.add(user_id, note)
            return ToolResult(reply=f"Saved: {note}.", tool="saved_item")

        task = self.tasks.extract_task(text, context)
        if task:
            task_text, due_date = task
            self.tasks.save_task(user_id, task_text, due_date)
            return ToolResult(reply=f"Saved: {task_text}.", tool="saved_item")

        return None

    def _execute_decision(
        self,
        text: str,
        decision: IntentDecision,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult | None:
        missing_fields = list(decision.missing_fields)
        if decision.tool == "reminder":
            missing_fields = [field for field in missing_fields if field != "when"]

        # Ask for missing required information (P4).
        if decision.needs_clarification and missing_fields:
            args_json = json.dumps(decision.args)
            self.database.set_pending_action(
                user_id=user_id,
                pending_tool=decision.tool,
                args_json=args_json,
                missing_fields_json=json.dumps(missing_fields),
                question=self._clarification_question(decision),
            )
            return ToolResult(
                reply=self._clarification_question(decision), tool=decision.tool
            )

        handler = {
            "memory": self._do_memory,
            "note": self._do_note,
            "task": self._do_task,
            "reminder": self._do_reminder,
            "delete": self._do_delete,
            "briefing": self._do_briefing,
            "search": self._do_search,
            "general_chat": self._do_general,
        }.get(decision.tool)
        if handler is None:
            return None
        return handler(decision, user_id, text, telegram_chat_id, application, context)

    def _clarification_question(self, decision: IntentDecision) -> str:
        if decision.tool == "reminder":
            return "When would you like to be reminded?"
        if decision.tool == "note":
            return "What would you like the note to say?"
        if decision.tool == "search":
            return "What should I look up?"
        return "Could you give me a bit more detail?"

    # --- per-tool executors (LLM path) ---

    def _do_memory(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        content = decision.args.get("content", "").strip()
        if not content:
            query = decision.args.get("query", "").strip() or text
            memories = self.memory.retrieve_relevant(user_id, query)
            reply = "Nothing saved yet." if not memories else "I recall: " + "; ".join(memories[:3])
            return ToolResult(reply=reply, tool="memory")
        self.memory.save_memory(user_id, content)
        self.saved_items.add(user_id, content)
        return ToolResult(reply=f"Saved: {content}.", tool="saved_item")

    def _do_note(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult | None:
        content = decision.args.get("content", "").strip()
        if not content:
            return None  # let fallback handle
        self.notes.save_note(user_id, content)
        self.saved_items.add(user_id, content)
        return ToolResult(reply=f"Saved: {content}.", tool="saved_item")

    def _do_task(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        content = decision.args.get("content", "").strip()
        due = decision.args.get("due", "").strip() or None
        if not content:
            return ToolResult(reply=self.tasks.format_tasks(user_id), tool="task")
        task_title, due_datetime = self.tasks.build_task(content, due, context)
        self.tasks.save_task(user_id, task_title, due_datetime)
        return ToolResult(reply=f"Saved: {task_title}.", tool="saved_item")

    def _do_reminder(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        when_text = decision.args.get("when", "").strip()
        content = decision.args.get("content", "").strip()
        if not when_text:
            self.saved_items.add(user_id, content)
            return ToolResult(reply=f"Saved: {content}.", tool="saved_item")
        reminder = self.reminders.build_reminder(content, when_text, context)
        if reminder is None:
            self.saved_items.add(user_id, content)
            return ToolResult(reply=f"Saved: {content}.", tool="saved_item")
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
            reply=f"I'll remind you: {reminder.text}.",
            tool="reminder",
        )

    def _do_delete(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        """Handle natural-language delete/remove/clear requests."""
        target = decision.args.get("target", "").strip()

        # --- clear everything ---
        if target.lower() in ("all", "everything", "all tasks", "all items", "all reminders"):
            items = self.saved_items.list_active(user_id)
            count = len(items)
            for item in items:
                self.saved_items.delete_matching_text(user_id, item.text)
            return ToolResult(reply=f"Cleared all {count} item(s).", tool="saved_item")

        # --- delete by visible number (e.g. target="3" or "item 3" or "the first") ---
        ordinals = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
        num_match = re.search(r"\b(\d+)\b", target)
        ordinal_match = re.search(r"\b(" + "|".join(ordinals) + r")\b", target.lower())
        if num_match:
            n = int(num_match.group(1))
            if self.saved_items.delete_visible(user_id, n):
                return ToolResult(reply=f"Deleted item {n}.", tool="saved_item")
            return ToolResult(reply=f"I couldn't find item {n}.", tool="saved_item")
        if ordinal_match:
            n = ordinals[ordinal_match.group(1)]
            if self.saved_items.delete_visible(user_id, n):
                return ToolResult(reply=f"Deleted item {n}.", tool="saved_item")
            return ToolResult(reply=f"I couldn't find item {n}.", tool="saved_item")

        # --- delete by keyword/name match ---
        if self.saved_items.delete_matching_text(user_id, target):
            return ToolResult(reply=f"Removed it.", tool="saved_item")

        # --- fuzzy: try any word from target ---
        for word in target.split():
            if len(word) > 3 and self.saved_items.delete_matching_text(user_id, word):
                return ToolResult(reply=f"Removed the matching item.", tool="saved_item")

        return ToolResult(reply=f"I couldn't find anything matching '{target}'.", tool="saved_item")

    def _do_briefing(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        return ToolResult(reply=self.briefing.build_briefing(user_id), tool="briefing")

    def _do_search(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult | None:
        query = decision.args.get("query", "").strip() or text
        results = self.search_service.search(query)
        if not results:
            return ToolResult(reply="I couldn't find anything on that.", tool="search")
        # Hand the results to the model for a concise answer rather than dumping links.
        return self._answer_with_model(user_id, query, results, tool="search")

    def _do_general(
        self,
        decision: IntentDecision,
        user_id: int,
        text: str,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        user_msg = decision.args.get("query", "").strip() or text
        return self._answer_with_model(user_id, user_msg, [], tool="general_chat")

    # ------------------------------------------------ regex fallback cascade

    def _regex_fallback(
        self,
        text: str,
        user_id: int,
        telegram_chat_id: int,
        application: Application | None,
        context: UserContext,
    ) -> ToolResult:
        normalized = text.strip().lower()

        memory = self.memory.extract_memory(text)
        if memory:
            self.memory.save_memory(user_id, memory)
            self.saved_items.add(user_id, memory)
            return ToolResult(reply=f"Saved: {memory}.", tool="saved_item")

        note = self.notes.extract_note(text)
        if note:
            self.notes.save_note(user_id, note)
            self.saved_items.add(user_id, note)
            return ToolResult(reply=f"Saved: {note}.", tool="saved_item")

        if self._is_briefing_request(normalized):
            return ToolResult(reply=self.briefing.build_briefing(user_id), tool="briefing")

        if self._is_show_tasks_request(normalized):
            return ToolResult(reply=self.tasks.format_tasks(user_id), tool="task")

        deleted = self.tasks.extract_deletion(text)
        if deleted is not None:
            return ToolResult(reply=self.tasks.delete_task(user_id, deleted), tool="task")

        completed = self.tasks.extract_completion(text)
        if completed is not None:
            return ToolResult(reply=self.tasks.complete_task(user_id, completed), tool="task")

        # --- Natural-language delete/remove/clear (regex fallback when LLM is down) ---
        _DELETE_ALL = re.compile(
            r"^\s*(delete|remove|clear|wipe|erase)\s+(all|everything|all\s+(my\s+)?(tasks?|items?|reminders?))\s*$",
            re.IGNORECASE,
        )
        _DELETE_BY_ORDINAL = re.compile(
            r"^\s*(delete|remove|get\s+rid\s+of|clear)\s+(the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b",
            re.IGNORECASE,
        )
        _DELETE_NATURAL = re.compile(
            r"^\s*(delete|remove|get\s+rid\s+of|clear|erase)\s+(the\s+)?(?P<target>.+?)\s*(task|reminder|item|note)?\s*$",
            re.IGNORECASE,
        )
        _ordinals = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                     "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}

        if _DELETE_ALL.match(text):
            items = self.saved_items.list_active(user_id)
            count = len(items)
            for item in items:
                self.saved_items.delete_matching_text(user_id, item.text)
            return ToolResult(reply=f"Cleared all {count} item(s).", tool="saved_item")

        ord_match = _DELETE_BY_ORDINAL.match(text)
        if ord_match:
            word = re.search(r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)", text, re.IGNORECASE)
            if word:
                n = _ordinals[word.group(1).lower()]
                if self.saved_items.delete_visible(user_id, n):
                    return ToolResult(reply=f"Deleted item {n}.", tool="saved_item")
                return ToolResult(reply=f"I couldn't find item {n}.", tool="saved_item")

        nat_match = _DELETE_NATURAL.match(text)
        if nat_match:
            target = nat_match.group("target").strip()
            # try by number
            num = re.fullmatch(r"\d+", target)
            if num and self.saved_items.delete_visible(user_id, int(target)):
                return ToolResult(reply=f"Deleted item {target}.", tool="saved_item")
            # try by text match
            if self.saved_items.delete_matching_text(user_id, target):
                return ToolResult(reply="Removed it.", tool="saved_item")
            # fuzzy: any keyword
            for word in target.split():
                if len(word) > 3 and self.saved_items.delete_matching_text(user_id, word):
                    return ToolResult(reply="Removed the matching item.", tool="saved_item")

        reminder = self.reminders.extract_reminder(text, context)
        if reminder:
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
                reply=f"I'll remind you: {reminder.text}.",
                tool="reminder",
            )

        saved_reminder = self._extract_untimed_reminder(text)
        if saved_reminder:
            self.saved_items.add(user_id, saved_reminder)
            return ToolResult(reply=f"Saved: {saved_reminder}.", tool="saved_item")

        task = self.tasks.extract_task(text, context)
        if task:
            task_text, due_date = task
            self.tasks.save_task(user_id, task_text, due_date)
            return ToolResult(reply=f"Saved: {task_text}.", tool="saved_item")

        search_results: list[SearchResult] = []
        if self._should_search(normalized):
            search_results = self.search_service.search(self._search_query(text))
            if not search_results:
                return ToolResult(reply="Search is unavailable at the moment.", tool="search")

        return self._answer_with_model(user_id, text, search_results, tool="general_chat")

    # ------------------------------------------------------------- heuristics

    def _is_briefing_request(self, normalized: str) -> bool:
        return normalized in {
            "/briefing",
            "briefing",
            "daily briefing",
            "give me my briefing",
            "morning briefing",
        }

    def _is_show_items_request(self, normalized: str) -> bool:
        exact = normalized in {
            "show my items",
            "show saved items",
            "show saved things",
            "what did i save",
            "what do i need to remember",
            "what do i have to remember",
            "what do i have saved",
            "list saved items",
            "list items",
            "items",
        }
        return exact or self._is_show_tasks_request(normalized)

    def _is_show_tasks_request(self, normalized: str) -> bool:
        exact = normalized in {
            "show my tasks",
            "what tasks do i have",
            "what tasks do i have?",
            "list tasks",
            "tasks",
            "/tasks",
        }
        if exact:
            return True
        # Tightened: require an explicit listing verb alongside "task", to avoid
        # matching "I have a task for you" etc.
        return "task" in normalized and any(
            normalized.startswith(verb) for verb in ("show", "list", "what", "due ")
        )

    def _extract_untimed_reminder(self, text: str) -> str | None:
        match = re.match(
            r"^\s*remind\s+me\s+to\s+(?P<content>.+)$",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        content = match.group("content").strip().rstrip(".")
        return content or None

    def _should_search(self, normalized: str) -> bool:
        # Simple time / greeting questions the model can answer from context.
        skip_patterns = [
            "what time is it",
            "what's the time",
            "whats the time",
            "what is the time",
            "tell me the time",
        ]
        if any(pat in normalized for pat in skip_patterns):
            return False

        # Patterns that indicate the user wants live/current/external info.
        search_terms = [
            # Explicit search verbs
            "search",
            "look up",
            "research",
            # Time-sensitive / current event signals
            "weather",
            "news",
            "current ",
            "latest",
            "happening now",
            "right now",
            "today",
            "score",
            "match",
            "game",
            "who won",
            "who is playing",
            "fixture",
            "standings",
            "schedule",
            "update",
            # Question patterns about the world
            "what's the",
            "whats the",
            "what is the",
            "how much is",
            "price of",
            "who is",
            "where is",
            "when is",
            "what time",
            "how many",
            "what year",
            # Events / sports / entertainment
            "world cup",
            "election",
            "concert",
            "movie",
            "stock",
            "crypto",
            "bitcoin",
            "flight",
            "traffic",
        ]
        return any(term in normalized for term in search_terms)

    def _search_query(self, text: str) -> str:
        # Strip leading search verbs, pass the rest as the query.
        cleaned = re.sub(
            r"^\s*(search|look up|research|find|google|check)\s+",
            "",
            text,
            flags=re.I,
        ).strip()
        return cleaned or text

    # ----------------------------------------------------------------- helpers

    def _history(self, user_id: int) -> list[dict[str, str]]:
        rows = self.database.recent_history(
            user_id,
            limit=self.settings.history_window,
            max_chars=self.settings.history_max_chars,
        )
        history = [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in rows
        ]
        # Summarize dropped turns into a memory so context isn't lost.
        self._summarize_dropped(user_id)
        return history

    def _summarize_dropped(self, user_id: int) -> None:
        """If older turns were trimmed, summarize them into a memory."""
        dropped = self.database.history_before_cutoff(
            user_id,
            limit=self.settings.history_window,
            max_chars=self.settings.history_max_chars,
        )
        if not dropped:
            return

        # Build a concise transcript of the dropped turns.
        lines: list[str] = []
        for row in dropped:
            role = "User" if row["role"] == "user" else "Athena"
            lines.append(f"{role}: {row['content']}")

        transcript = "\n".join(lines)
        if len(transcript) < 50:
            return  # too short to bother summarizing

        prompt = (
            "Summarize the following older conversation into a single concise "
            "memory sentence (max 2 sentences). Capture any facts, preferences, "
            "or decisions the user shared. If there is nothing worth remembering, "
            "reply with just: (nothing)\n\n"
            f"{transcript}"
        )

        try:
            response = self.model_router.generate_response(
                user_message=prompt,
                memories=[],
                history=[],
                search_results=None,
                context=None,
                user_id=user_id,
            )
            summary = response.text.strip()
            if summary and summary != "(nothing)" and len(summary) > 5:
                self.memory.save_memory(user_id, f"[session memory] {summary}")
                logger.info("Stored session summary for user %d", user_id)
        except Exception:
            logger.exception("Session summarization failed for user %d", user_id)

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
        memories = saved_item_memories + self.memory.retrieve_relevant(user_id, user_message)
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
