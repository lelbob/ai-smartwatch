"""On-demand daily briefing generation."""

from __future__ import annotations

import logging
from datetime import datetime

from .database import Database
from .model_router import ModelRouter
from .saved_items import SavedItemsService
from .search_service import SearchService

logger = logging.getLogger(__name__)


class BriefingService:
    """Builds a short butler-style briefing when asked."""

    def __init__(
        self,
        database: Database,
        search_service: SearchService,
        location: str,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.database = database
        self.search_service = search_service
        self.location = location
        self.model_router = model_router
        self.saved_items = SavedItemsService()

    def build_briefing(self, user_id: int) -> str:
        now = datetime.now()
        lines = [now.strftime("%A, %B %d.")]
        saved_items = self.saved_items.list_active(user_id)

        if saved_items:
            user_row = self.database.get_user(user_id)
            user_tz = user_row["timezone"] if user_row else None
            
            task_lines = []
            for item in saved_items[:5]:
                time_str = ""
                if item.remind_at:
                    try:
                        import zoneinfo
                        dt = datetime.fromisoformat(item.remind_at)
                        if user_tz:
                            try:
                                tz = zoneinfo.ZoneInfo(user_tz)
                                dt = dt.astimezone(tz)
                            except Exception:
                                pass
                        time_str = f" - {dt.hour:02d}:{dt.minute:02d} {dt.month}/{dt.day}/{dt.year}"
                    except Exception:
                        pass
                task_lines.append(f"- {item.text}{time_str}")
            lines.append("Open tasks:\n" + "\n".join(task_lines))
        else:
            lines.append("No open tasks.")

        reminders = self.database.upcoming_reminders(user_id, now, hours=24, limit=3)
        if reminders:
            lines.append(f"{len(reminders)} reminder(s) in the next 24 hours.")

        notes = self.database.recent_notes(user_id, limit=1)
        if notes:
            lines.append(f"Latest note: {notes[0]['content']}")

        weather = self._weather_line()
        if weather:
            lines.append(weather)

        return "\n".join(lines[:6])

    def _weather_line(self) -> str | None:
        if not self.location:
            return None
        results = self.search_service.search(
            f"{self.location} weather today conditions temperature",
            limit=5,
        )
        if not results:
            return None

        # If a model router is available, use it to extract real weather info
        # from the search results instead of returning raw SearXNG snippets.
        if self.model_router:
            return self._weather_from_model(results)

        # Fallback: best snippet (still not great but better than a page title).
        best = max(results, key=lambda r: len(r.snippet or ""))
        snippet = best.snippet or best.title
        return snippet[:180].rstrip()

    def _weather_from_model(self, results: list) -> str | None:
        """Ask the model to extract a concise weather summary from search results."""
        results_text = "\n".join(
            f"- {r.title}: {r.snippet}" for r in results if r.snippet
        )
        if not results_text.strip():
            return None

        prompt = (
            "You are a weather briefing assistant. Given these search results about "
            f"the weather in {self.location}, extract the current conditions and today's "
            "forecast into ONE concise sentence (max 25 words). Include temperature if "
            "available. Do not add filler. If the results have no actual weather data, "
            'reply with just: (no data)\n\n'
            f"Search results:\n{results_text}"
        )
        try:
            response = self.model_router.generate_response(
                user_message=prompt,
                memories=[],
                history=[],
                search_results=None,
                context=None,
            )
            text = response.text.strip()
            if text and text != "(no data)":
                return text[:200]
        except Exception:
            logger.warning("Weather model extraction failed", exc_info=True)
        return None
