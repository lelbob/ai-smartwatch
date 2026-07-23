"""Gemini prompt assembly.

The ModelRouter talks to the Gemini SDK directly; this module is responsible
only for composing the butler-style prompt that gets sent to whichever model
is selected. Prompt construction is kept separate from API calls so it can be
unit-tested without a network connection.
"""

from __future__ import annotations

from .context_service import UserContext
from .search_service import SearchResult
from .tool_spec import CAPABILITY_SUMMARY


def build_prompt(
    user_message: str,
    memories: list[str],
    history: list[dict[str, str]],
    search_results: list[SearchResult] | None = None,
    context: UserContext | None = None,
) -> str:
    memory_block = "\n".join(f"- {memory}" for memory in memories) or "- No saved memories yet."
    history_block = (
        "\n".join(f"{item['role']}: {item['content']}" for item in history)
        or "No prior conversation in this chat."
    )
    search_block = _format_search_results(search_results or [])
    context_block = _format_context(context)
    has_real_results = bool(search_results) and search_block != "- No search results used."
    search_instruction = ""
    if has_real_results:
        search_instruction = """
Answering from search results:
- When search results are provided below, you MUST answer the user's question
  using the information in those results. Synthesize a clear, direct answer.
- Do NOT say "I don't have enough information" or "I can't find that" when
  search results are available. Use them.
- If the results partially cover the question, answer with what is available
  and note what is missing in one sentence.
- If the results are genuinely irrelevant, say you could not find a good answer.
"""

    return f"""
You are Athena, a private personal butler and assistant.

Your character:
- Calm, efficient, precise, and helpful. A professional butler.
- Default to a single sentence. At most three short sentences, and only when the
  user explicitly asks for detail or several things need stating.
- Never use emoji.
- Never use enthusiastic filler: no "Sure!", "Of course!", "I'd be happy to",
  "Absolutely!", or similar generic AI phrases. Start directly with the answer.
- Do not sound chatty, warm, or overly friendly. Respectful, not effusive.
- Be honest and direct when you do not know something.
- Focus on the user's current request and nothing else.
- For greetings (hi, hello, hey, good morning, etc.), reply with a brief natural
  greeting. Do NOT recite the date, time, timezone, or any system context unless
  the user explicitly asks for it.
{search_instruction}
{CAPABILITY_SUMMARY}

{context_block}

Saved memories:
{memory_block}

Search results:
{search_block}

Recent conversation:
{history_block}

User message:
{user_message}

Reply as Athena.
""".strip()


def _format_context(context: UserContext | None) -> str:
    if context is None:
        return "SYSTEM CONTEXT\n(unknown)"
    return context.to_prompt_block()


def _format_search_results(results: list[SearchResult]) -> str:
    if not results:
        return "- No search results used."
    lines = []
    for i, result in enumerate(results, start=1):
        snippet = f"\n  Snippet: {result.snippet}" if result.snippet else ""
        # Prefer rich page text when we have it; it carries the actual answer.
        page = f"\n  Page content: {result.page_text}" if result.page_text else ""
        lines.append(f"[{i}] {result.title}\n  URL: {result.url}{snippet}{page}")
    return "\n".join(lines)
