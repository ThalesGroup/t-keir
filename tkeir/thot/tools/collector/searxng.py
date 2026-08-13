"""Title: SearXNG JSON search client.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any

import httpx


class SearxngError(RuntimeError):
    """Raised when SearXNG search fails."""


def normalize_searxng_results(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Extract ``[{url, title, content, engine}, …]`` from a SearXNG JSON body.

    Example:
        >>> normalize_searxng_results({
        ...     "results": [{"url": "https://a", "title": "A", "content": "x"}]
        ... })
        [{'url': 'https://a', 'title': 'A', 'content': 'x', 'engine': ''}]
    """
    rows: list[dict[str, str]] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        rows.append(
            {
                "url": url,
                "title": str(item.get("title") or "").strip(),
                "content": (
                    str(
                        item.get("content") or item.get("snippet") or ""
                    ).strip()
                ),
                "engine": str(item.get("engine") or "").strip(),
            }
        )
    return rows


async def searxng_search(
    query: str,
    *,
    base_url: str,
    max_results: int = 5,
    timeout_s: float = 30.0,
    language: str | None = None,
    categories: str | None = None,
    engines: str | None = None,
    safesearch: int | None = None,
    time_range: str | None = None,
) -> list[dict[str, str]]:
    """Query SearXNG ``/search?format=json`` and return normalized hits.

    Args:
        query: Search string.
        base_url: SearXNG origin (e.g. ``http://127.0.0.1:8888``).
        max_results: Cap on returned hits.
        timeout_s: HTTP timeout.
        language: Optional ``language`` query param.
        categories: Optional ``categories`` query param (e.g. ``general,news``).
        engines: Optional comma-separated engine names.
        safesearch: Optional ``0`` / ``1`` / ``2`` (strict).
        time_range: Optional ``day`` / ``week`` / ``month`` / ``year``.

    Returns:
        Normalized result dicts.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.searxng import searxng_search
        >>> inspect.iscoroutinefunction(searxng_search)
        True
    """
    q = (query or "").strip()
    if not q:
        raise SearxngError("query is required")
    params: dict[str, str] = {"q": q, "format": "json"}
    if language:
        params["language"] = language
    if categories:
        params["categories"] = categories
    if engines:
        params["engines"] = engines
    if safesearch is not None:
        params["safesearch"] = str(int(safesearch))
    if time_range:
        params["time_range"] = time_range
    url = f"{base_url.rstrip('/')}/search"
    try:
        async with httpx.AsyncClient(
            timeout=timeout_s, follow_redirects=True
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise SearxngError(f"SearXNG request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise SearxngError("SearXNG returned non-object JSON")
    return normalize_searxng_results(payload)[: max(1, int(max_results))]
