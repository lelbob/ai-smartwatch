"""SearXNG search integration."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    # Optional full-text extract fetched from the page itself (truncated).
    # Richer than SearXNG's snippet, which is often just a page description.
    page_text: str = ""


class SearchService:
    """Queries a local SearXNG instance and optionally fetches page content."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 8.0,
        fetch_pages: bool = True,
        page_char_limit: int = 1200,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.fetch_pages = fetch_pages
        self.page_char_limit = page_char_limit

    def search(self, query: str, limit: int = 5, fetch_pages: bool | None = None) -> list[SearchResult]:
        if not query.strip():
            return []

        do_fetch = self.fetch_pages if fetch_pages is None else fetch_pages

        try:
            # Explicit Accept header + charset handling: SearXNG JSON should be
            # UTF-8, but the underlying server sometimes mis-advertises the
            # charset, producing mojibake like "89A°" instead of "89°".
            response = httpx.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json"},
                timeout=self.timeout_seconds,
                headers={"Accept": "application/json; charset=utf-8"},
            )
            response.raise_for_status()
            # Force UTF-8 decode regardless of the (possibly wrong) server header.
            raw = response.content.decode("utf-8", errors="replace")
            import json as _json
            payload = _json.loads(raw)
        except Exception:
            logger.exception("SearXNG search failed")
            return []

        results: list[SearchResult] = []
        for item in payload.get("results", []):
            title = _clean(item.get("title"))
            url = _clean(item.get("url"))
            snippet = _clean(item.get("content") or item.get("snippet"))
            if title and url:
                results.append(SearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= limit:
                break

        # Enrich the top results with page content for a real answer.
        if do_fetch and results:
            results = [
                replace(result, page_text=self._fetch_page_text(result.url))
                for result in results[:3]
            ] + results[3:]

        return results

    def fetch_page(self, url: str, timeout: float | None = None) -> str:
        """Public helper: fetch a URL and return cleaned text."""
        return self._fetch_page_text(url, timeout=timeout)

    def _fetch_page_text(self, url: str, timeout: float | None = None) -> str:
        """Fetch a page and return cleaned, truncated plain text."""
        if not url or not url.startswith(("http://", "https://")):
            return ""
        try:
            resp = httpx.get(
                url,
                timeout=timeout or self.timeout_seconds,
                headers={
                    "User-Agent": "AthenaAI/1.0 (personal-assistant; +https://github.com/athena)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            )
            resp.raise_for_status()
            return _html_to_text(resp.content.decode("utf-8", errors="replace"))[: self.page_char_limit]
        except Exception:
            logger.debug("Page fetch failed: %s", url, exc_info=True)
            return ""


# --------------------------------------------------------------------- helpers


_MOJIBAKE_REPLACEMENTS = {
    # Common UTF-8-as-Latin1 mojibake seen in SearXNG snippets.
    "Ã‚Â°": "°",
    "Ã‚Â·": "·",
    "Ã¢Â€Â™": "'",
    "Ã¢Â€Âœ": '"',
    "Ã¢Â€Â": '"',
    "Ã¢Â€": "—",
    "Ã‚Â": "",
    "Ã©": "é",
    "Ã¨": "è",
    "Ã¡": "á",
    "Ã­": "í",
    "Ã³": "ó",
    "Ã±": "ñ",
    "Ã§": "ç",
}


def _clean(value: object) -> str:
    """Decode common mojibake and normalize whitespace."""
    if value is None:
        return ""
    text = str(value)
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    # Collapse whitespace runs.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _html_to_text(html: str) -> str:
    """Very small HTML-to-text converter: drop tags/scripts, keep text."""
    # Remove script/style blocks entirely.
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Block tags -> newline so text doesn't run together.
    html = re.sub(r"<\s*(p|div|br|li|h[1-6]|tr)\b[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Strip all remaining tags.
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode the most common entities.
    html = (
        html.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&deg;", "°")
        .replace("&middot;", "·")
        .replace("&ndash;", "–")
        .replace("&mdash;", "—")
    )
    # Collapse whitespace but preserve line breaks.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in html.splitlines()]
    return "\n".join(line for line in lines if line)
