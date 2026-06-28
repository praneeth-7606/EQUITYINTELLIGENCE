import html
import logging
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests
import urllib3

logger = logging.getLogger("stock_intelligence.web_research")


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(text).split())


def _unwrap_result_url(value: str) -> str:
    decoded = html.unescape(value)
    if decoded.startswith("//"):
        decoded = f"https:{decoded}"
    parsed = urlparse(decoded)
    target = parse_qs(parsed.query).get("uddg", [None])[0]
    return unquote(target) if target else decoded


class WebResearchTool:
    """Keyless search fallback returning source titles, snippets, and URLs."""

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        )
    }

    @classmethod
    def search(cls, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                cls.SEARCH_URL,
                params={"q": query},
                headers=cls.HEADERS,
                timeout=8,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"Verified web search failed for '{query}': {exc}")
            try:
                # Search terms contain only the public company question, never portfolio data.
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                response = requests.get(
                    cls.SEARCH_URL,
                    params={"q": query},
                    headers=cls.HEADERS,
                    timeout=8,
                    verify=False,
                )
                response.raise_for_status()
            except Exception as fallback_exc:
                logger.warning(f"Web search fallback failed for '{query}': {fallback_exc}")
                return []

        anchors = re.findall(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            response.text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippets = re.findall(
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|'
            r'<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
            response.text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        results: list[dict[str, Any]] = []
        for index, (raw_url, raw_title) in enumerate(anchors[:max_results]):
            snippet_match = snippets[index] if index < len(snippets) else ("", "")
            url = _unwrap_result_url(raw_url)
            if not url.startswith(("http://", "https://")):
                continue
            results.append(
                {
                    "title": _clean_html(raw_title),
                    "url": url,
                    "snippet": _clean_html(snippet_match[0] or snippet_match[1]),
                }
            )
        return results
