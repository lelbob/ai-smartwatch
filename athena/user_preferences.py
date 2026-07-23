"""Per-user preference storage (P2).

Tracks whether the user wants voice replies and which voice model to use.
Onboarding ("Would you like voice replies?") is driven through the
conversation_state mechanism so the bot can ask once and remember the answer
across sessions.
"""

from __future__ import annotations

import re

from .database import Database


AFFIRMATIVE = re.compile(
    r"^\s*(yes|y|yeah|yep|sure|ok|okay|please|affirmative|do|voice)\b",
    re.IGNORECASE,
)
NEGATIVE = re.compile(
    r"^\s*(no|n|nope|nah|negative|don't|do not|text)\b", re.IGNORECASE
)


class PreferenceService:
    """Reads and writes user voice-reply preferences."""

    PENDING_TOOL = "set_voice_preference"

    def __init__(self, database: Database, default_voice: str | None = None) -> None:
        self.database = database
        self.default_voice = default_voice

    def get(self, user_id: int) -> bool | None:
        """Return True/False if a preference is stored, else None (unknown)."""

        row = self.database.get_preference(user_id)
        if row is None:
            return None
        return bool(row["voice_replies_enabled"])

    def preferred_voice(self, user_id: int) -> str | None:
        row = self.database.get_preference(user_id)
        if row is None:
            return None
        voice = row["preferred_voice"]
        return str(voice) if voice else None

    def set(self, user_id: int, enabled: bool, voice: str | None = None) -> None:
        self.database.upsert_preference(
            user_id=user_id,
            voice_replies_enabled=enabled,
            preferred_voice=voice or self.default_voice,
        )

    # ----------------------------------------------------------- onboarding

    def begin_onboarding(self, user_id: int) -> str:
        """Ask the onboarding question and record a pending action."""

        self.database.set_pending_action(
            user_id=user_id,
            pending_tool=self.PENDING_TOOL,
            args_json="{}",
            missing_fields_json='["voice_replies_enabled"]',
            question="Would you like voice replies?",
        )
        return "Would you like voice replies?"

    def interpret_answer(self, text: str) -> bool | None:
        """Classify a free-text answer to the onboarding question."""

        if AFFIRMATIVE.search(text):
            return True
        if NEGATIVE.search(text):
            return False
        return None
