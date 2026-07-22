"""Geolocation helpers for shared Telegram locations.

Resolves a (latitude, longitude) pair into city, country, and IANA timezone.
Timezone lookup is offline via ``timezonefinder``; city/country use Nominatim
(OpenStreetMap), which is free but rate-limited, so results are cached by
rounded coordinates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedLocation:
    city: str | None
    country: str | None
    timezone: str | None


class GeoService:
    """Resolves coordinates to city/country/timezone."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 6.0,
        cache: dict[tuple[int, int], ResolvedLocation] | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self._cache = cache if cache is not None else {}

        # timezonefinder is a pure-data, offline lookup.
        try:
            from timezonefinder import TimezoneFinder

            self._tz_finder: TimezoneFinder | None = TimezoneFinder()
        except Exception:
            logger.warning(
                "timezonefinder is not installed; location timezones will be unknown."
            )
            self._tz_finder = None

    def resolve(self, latitude: float, longitude: float) -> ResolvedLocation:
        # Round to ~1km so repeated shares hit the cache instead of Nominatim.
        key = (round(latitude, 3), round(longitude, 3))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        timezone = self._lookup_timezone(latitude, longitude)
        city, country = self._reverse_geocode(latitude, longitude)
        resolved = ResolvedLocation(city=city, country=country, timezone=timezone)
        self._cache[key] = resolved
        return resolved

    def _lookup_timezone(self, latitude: float, longitude: float) -> str | None:
        if self._tz_finder is None:
            return None
        try:
            name = self._tz_finder.timezone_at(lat=latitude, lng=longitude)
            return name
        except Exception:
            logger.exception("timezonefinder lookup failed")
            return None

    def _reverse_geocode(
        self, latitude: float, longitude: float
    ) -> tuple[str | None, str | None]:
        params = {
            "format": "jsonv2",
            "lat": latitude,
            "lon": longitude,
            "zoom": 10,
            "addressdetails": 1,
        }
        headers = {"User-Agent": self.user_agent}
        try:
            response = httpx.get(
                "https://nominatim.openstreetmap.org/reverse",
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            address = response.json().get("address", {})
        except Exception:
            logger.warning("Nominatim reverse geocoding failed", exc_info=True)
            return None, None

        city = address.get("city") or address.get("town") or address.get("village")
        country = address.get("country")
        return city, country
