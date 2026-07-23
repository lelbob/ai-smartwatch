"""Antigravity Diagnostic Troubleshooting Tool for Athena AI.

Usage:
    python -m scripts.troubleshoot "remind me next Friday at 5pm to read a book"
    python -m scripts.troubleshoot --tasks
    python -m scripts.troubleshoot --interactive
"""

from __future__ import annotations

import sys
import json
import argparse
import logging
from datetime import datetime, timezone

from google import genai

from athena.config import load_settings
from athena.context_service import ContextService
from athena.database import Database
from athena.debug_log import PromptLogger
from athena.intent_classifier import IntentClassifier
from athena.memory import MemoryService
from athena.model_router import ModelRouter
from athena.notes import NotesService
from athena.reminders import RemindersService
from athena.saved_items import SavedItemsService
from athena.search_service import SearchService
from athena.tasks import TasksService
from athena.briefing import BriefingService
from athena.tool_router import ToolRouter


def setup_pipeline():
    settings = load_settings()
    logging.basicConfig(level=logging.WARNING)

    database = Database(settings.database_path)
    database.initialize()

    gemini_client = (
        genai.Client(api_key=settings.gemini_api_key)
        if settings.gemini_api_key
        else None
    )

    prompt_logger = PromptLogger(settings.prompt_log_path)
    context_service = ContextService(database, settings)
    classifier = IntentClassifier(
        gemini_client, settings.gemini_flash_model, prompt_logger=prompt_logger
    )
    model_router = ModelRouter(settings)
    search_service = SearchService(settings.searxng_url)
    memory = MemoryService(database)
    notes = NotesService(database)
    saved_items = SavedItemsService()
    tasks = TasksService(database, saved_items=saved_items)
    reminders = RemindersService(database)
    briefing = BriefingService(database, search_service, settings.athena_location, model_router=model_router)

    router = ToolRouter(
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

    return database, context_service, classifier, router, saved_items


def diagnose_prompt(prompt: str, user_id: int = 1) -> None:
    database, context_service, classifier, router, saved_items = setup_pipeline()
    context = context_service.get_context(user_id)
    history = []

    print("\n" + "=" * 70)
    print(f"PROMPT TEST: {prompt!r}")
    print("=" * 70)
    print(f"[CONTEXT] Timezone: {context.timezone} | Time: {context.time} ({context.date}) | Location: {context.location}")

    # 1. Intent Classification Step
    print("\n--- 1. INTENT CLASSIFIER ---")
    decision = classifier.classify(prompt, history, context)
    if decision is None:
        print("Classifier returned: None (will use regex fallback cascade)")
    else:
        print(f"Tool Chosen        : {decision.tool}")
        print(f"Extracted Args     : {decision.args}")
        print(f"Confidence         : {decision.confidence:.2f}")
        print(f"Missing Fields     : {decision.missing_fields}")
        print(f"Needs Clarification: {decision.needs_clarification}")

    # 2. Execution Step
    print("\n--- 2. PIPELINE EXECUTION ---")
    result = router.route(prompt, user_id=user_id, telegram_chat_id=user_id, application=None)
    print(f"Tool Executed : {result.tool}")
    print(f"Model Used    : {result.model_name}")
    print(f"Used Search   : {result.used_search}")
    print(f"Butler Reply  : {result.reply!r}")

    # 3. Active Tasks / Saved Items State Check
    print("\n--- 3. ACTIVE TASKS FILE STATE ---")
    active_items = saved_items.list_active(user_id)
    if not active_items:
        print("(No active saved items/tasks)")
    else:
        for item in active_items:
            remind_status = f"VALID ({item.remind_at})" if item.remind_at else "NULL (no time attached)"
            print(f"  [{item.id}] Text: {item.text!r} | remind_at: {remind_status}")

    print("=" * 70 + "\n")


def show_tasks(user_id: int = 1) -> None:
    saved_items = SavedItemsService()
    active_items = saved_items.list_active(user_id)
    print(f"\nActive Tasks in File for User {user_id}: ({len(active_items)} total)")
    for item in active_items:
        remind_status = item.remind_at if item.remind_at else "NULL"
        print(f"  ID {item.id:2d} | Text: {item.text!r} | Due: {remind_status}")


def interactive_mode(user_id: int = 1) -> None:
    print("\nEntering Athena Troubleshooting REPL. Type 'exit' or Ctrl+C to quit.\n")
    while True:
        try:
            prompt = input("athena-test> ").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit"):
                break
            if prompt.lower() in ("tasks", "list"):
                show_tasks(user_id)
                continue
            diagnose_prompt(prompt, user_id=user_id)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Athena Bot Troubleshooting Tool for Antigravity")
    parser.add_argument("prompt", nargs="?", help="User prompt to diagnose")
    parser.add_argument("--tasks", action="store_true", help="Show current active saved items/tasks")
    parser.add_argument("--interactive", "-i", action="store_true", help="Enter interactive REPL mode")
    parser.add_argument("--user-id", type=int, default=1, help="User ID to test with (default: 1)")

    args = parser.parse_args()

    if args.tasks:
        show_tasks(args.user_id)
    elif args.interactive:
        interactive_mode(args.user_id)
    elif args.prompt:
        diagnose_prompt(args.prompt, args.user_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
