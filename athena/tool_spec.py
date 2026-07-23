"""Tool catalogue for the two-step Athena classifier.

Four tool categories and their human-readable descriptions, used to build
the Step 1 classification prompt.
"""

from __future__ import annotations

# The four tool categories recognised by StepClassifier.
TOOLS: tuple[str, ...] = ("task", "search", "chat", "briefing")

# Human-readable one-liners shown in Step 1 prompts.
TOOL_DESCRIPTIONS: dict[str, str] = {
    "task": (
        "Add, delete, complete, or list tasks, reminders, notes, and memories. "
        "Also recall previously saved facts."
    ),
    "search": "Look up live or current information (weather, news, prices, events, etc.)",
    "chat": "Greetings, opinions, general conversation, or anything not covered above.",
    "briefing": "Deliver the user's daily summary/briefing.",
}

# Capability summary injected into the chat-response system prompt so the
# model knows what Athena can do when conversing freely.
CAPABILITY_SUMMARY = (
    "You are Athena, a voice-first personal assistant for smartwatches. "
    "You can manage tasks and reminders (add, delete, complete, list), "
    "save notes and memories, look up live information via web search, "
    "and deliver a daily briefing with weather and upcoming items."
)
