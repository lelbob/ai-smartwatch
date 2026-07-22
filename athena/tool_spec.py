"""Tool catalogue for LLM-driven intent classification (P3).

Describes each Athena tool the way you would describe an API to a developer, so
the intent classifier can pick the right one and surface missing parameters.
The argument keys here are the contract between the classifier's JSON output
and the executor in tool_router.
"""

from __future__ import annotations

# Tools the classifier may choose. ``general_chat`` is the no-op fallback.
TOOLS: tuple[str, ...] = (
    "memory",
    "note",
    "task",
    "reminder",
    "delete",
    "briefing",
    "search",
    "general_chat",
)


TOOL_DESCRIPTIONS: dict[str, str] = {
    "memory": (
        "Store or recall a personal fact the user wants Athena to remember long "
        "term. Examples: 'remember that my physics exam is Friday', 'when is my "
        "physics exam?'. Args: content (str) - the fact to store; for a recall "
        "query leave content empty and the memory store will be searched."
    ),
    "note": (
        "Save a quick note. Examples: 'save a note that I need a new soldering "
        "iron', 'note: buy milk'. Internally this is just a saved item. "
        "Args: content (str) - the text to save."
    ),
    "task": (
        "Add, list, complete, or delete saved items/tasks/to-dos. Examples: 'add a task to "
        "finish the report', 'what tasks do I have?', 'complete task 2', "
        "'delete task 2'. Args: content (str) - task text (empty for listing); "
        "due (str) - natural-language due date, optional. Tasks do not need a due date."
    ),
    "reminder": (
        "Schedule a reminder. Examples: 'remind me tomorrow to study', 'remind "
        "me to call mom at 5pm'. Args: content (str) - what to be reminded "
        "about; when (str) - natural-language time, optional. If the user omits "
        "a time, save the item without asking a follow-up question."
    ),
    "briefing": (
        "Give the user their daily briefing (tasks due, reminders, latest "
        "note, weather). Use for 'briefing', 'what's my day look like'. No args."
    ),
    "delete": (
        "Delete or remove a saved item, task, or reminder. Use this for any "
        "request to delete, remove, clear, or get rid of a saved item. "
        "Examples: 'delete the dog task', 'remove the first item', "
        "'get rid of the read a book reminder', 'clear all my tasks', "
        "'delete everything'. "
        "Args: target (str) - what the user wants deleted, exactly as they said it. "
        "Use 'all' if the user wants everything cleared."
    ),
    "search": (
        "Look up current external information the assistant would not know: "
        "weather, news, recent events, facts. Args: query (str)."
    ),
    "general_chat": (
        "Conversational reply, greetings, opinions, and anything not handled "
        "by another tool. No args."
    ),
}


# Required argument fields per tool. Used to detect missing information (P4).
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "memory": (),
    "note": ("content",),
    "task": (),
    "reminder": ("content",),
    "delete": ("target",),
    "briefing": (),
    "search": ("query",),
    "general_chat": (),
}


def build_catalogue_text() -> str:
    """Render the tool catalogue for inclusion in the classifier prompt."""

    lines = []
    for name in TOOLS:
        lines.append(f"- {name}: {TOOL_DESCRIPTIONS[name]}")
    return "\n".join(lines)


# Short, user-facing capability summary injected into the conversational prompt
# so the chat model knows what Athena can actually do (and can tell the user).
CAPABILITY_SUMMARY = """\
You have these tools, applied automatically before you reply:
- Memory: long-term facts about the user ("my exam is Friday", recall on demand).
- Notes: quick saved notes.
- Tasks: to-do items with optional due dates.
- Reminders: scheduled notifications (timezone-aware).
- Briefing: on-demand daily summary of tasks/reminders/weather.
- Search: current information you would not know (weather, news).
If the user asks to save/note/remember/add something, it has likely already
been handled — acknowledge in one short sentence. If they ask for something a
tool could provide and it was NOT provided, tell them how to phrase it."""
