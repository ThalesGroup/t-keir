"""Title: Collect → well-formatted markdown documents (no NLP, no disk store).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from thot.action.correlation import generate_trace_id
from thot.action.models import utc_now_rfc3339
from thot.core.StructuredLogging import log_structured
from thot.tools.collector.config import CollectorSettings
from thot.tools.collector.convert import (
    bytes_to_markdown,
    format_collected_markdown,
)
from thot.tools.collector.dedupe import (
    CollectorDedupeIndex,
    dedupe_index_for_workspace,
)
from thot.tools.collector.searxng import searxng_search

LOGGER = logging.getLogger(__name__)

_SAFE_SEGMENT = re.compile(r"[^\w.\-]+")


def _filename_for_url(url: str, content_type: str | None) -> str:
    """Derive a download filename for converter selection.

    Example:
        >>> _filename_for_url("https://ex.com/a/b.html", "text/html")
        'b.html'
    """
    name = Path(urlparse(url).path).name or "document"
    if "." not in name:
        ctype = (content_type or "").split(";")[0].strip().lower()
        if "pdf" in ctype:
            name += ".pdf"
        elif "html" in ctype or not ctype:
            name += ".html"
        else:
            name += ".bin"
    return name


def markdown_filename(url: str, title: str | None = None) -> str:
    """Suggested ``{slug}__{sha12}.md`` name for a collected URL (not written).

    Example:
        >>> name = markdown_filename("https://ex.example/a/b", "Hello World")
        >>> name.endswith(".md") and "__" in name
        True
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    slug_src = (title or "").strip() or Path(urlparse(url).path).name or "page"
    slug = _SAFE_SEGMENT.sub("_", slug_src).strip("._")[:60] or "page"
    return f"{slug}__{digest}.md"


async def fetch_url_bytes(
    url: str,
    *,
    timeout_s: float,
    user_agent: str,
) -> tuple[bytes, str, str | None]:
    """Download a result URL and return ``(bytes, filename, content_type)``.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.service import fetch_url_bytes
        >>> inspect.iscoroutinefunction(fetch_url_bytes)
        True
    """
    headers = {"User-Agent": user_agent, "Accept": "*/*"}
    async with httpx.AsyncClient(
        timeout=timeout_s, follow_redirects=True, headers=headers
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        ctype = response.headers.get("content-type")
        filename = _filename_for_url(url, ctype)
        return response.content, filename, ctype


def load_dedupe_index(settings: CollectorSettings) -> CollectorDedupeIndex:
    """Load the workspace-backed SimHash / URL dedupe index.

    Example:
        >>> from thot.tools.collector.config import collector_settings
        >>> from thot.tools.collector.service import load_dedupe_index
        >>> idx = load_dedupe_index(collector_settings())
        >>> idx.path.name
        'simhashes.jsonl'
    """
    return dedupe_index_for_workspace(
        settings.workspace,
        max_hamming=settings.simhash_max_hamming,
    )


async def collect_markdown(
    settings: CollectorSettings,
    *,
    query: str,
    topic: str | None = None,
    max_results: int | None = None,
    language: str | None = None,
    dedupe: CollectorDedupeIndex | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Search SearXNG; fetch hits; return one per-query result row.

    Callers wrap the row with :func:`wrap_collect_results` so the public API
    is always ``{"results": [<row>, ...]}``. Documents are returned only (not
    written to disk). Near-duplicates and exact URL repeats are skipped.
    Does **not** run the NLP pipeline or attach ontologies.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.service import collect_markdown
        >>> inspect.iscoroutinefunction(collect_markdown)
        True
    """
    correlation_id = correlation_id or generate_trace_id()
    started = utc_now_rfc3339()
    index = dedupe or load_dedupe_index(settings)
    limit = max_results if max_results is not None else settings.max_results
    hits = await searxng_search(
        query,
        base_url=settings.searxng_url,
        max_results=limit,
        timeout_s=settings.fetch_timeout_s,
        language=language,
    )
    documents: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for hit in hits:
        url = hit["url"]
        try:
            if index.known_url(url):
                duplicates.append(
                    {
                        "url": url,
                        "title": hit.get("title"),
                        "reason": "url",
                        "query": query,
                    }
                )
                continue
            raw, filename, ctype = await fetch_url_bytes(
                url,
                timeout_s=settings.fetch_timeout_s,
                user_agent=settings.user_agent,
            )
            body = bytes_to_markdown(
                raw, filename=filename, content_type=ctype
            )
            if not body.strip():
                errors.append(
                    {"url": url, "error": "empty markdown after conversion"}
                )
                continue
            hit_dedupe = index.probe_and_register(url, body)
            if hit_dedupe.is_duplicate:
                duplicates.append(
                    {
                        "url": url,
                        "title": hit.get("title"),
                        "reason": hit_dedupe.reason,
                        "matched_url": hit_dedupe.matched_url,
                        "simhash": (
                            f"{hit_dedupe.simhash:016x}"
                            if hit_dedupe.simhash is not None
                            else None
                        ),
                        "matched_simhash": (
                            f"{hit_dedupe.matched_simhash:016x}"
                            if hit_dedupe.matched_simhash is not None
                            else None
                        ),
                        "query": query,
                    }
                )
                continue
            title = (hit.get("title") or "").strip() or url
            collected_at = utc_now_rfc3339()
            markdown = format_collected_markdown(
                body,
                title=title,
                source_url=url,
                query=query,
                topic=topic,
                engine=hit.get("engine"),
                snippet=hit.get("content"),
                collected_at=collected_at,
                content_type=ctype,
            )
            documents.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": hit.get("content"),
                    "engine": hit.get("engine"),
                    "topic": topic,
                    "query": query,
                    "filename": markdown_filename(url, title),
                    "markdown_chars": len(markdown),
                    "markdown": markdown,
                    "simhash": (
                        f"{hit_dedupe.simhash:016x}"
                        if hit_dedupe.simhash is not None
                        else None
                    ),
                    "collected_at": collected_at,
                }
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.info("collect failed for %s: %s", url, exc)
            log_structured(
                "warning",
                "collect url failed",
                correlation_id=correlation_id,
                url=url,
                query=query,
                error=str(exc),
            )
            errors.append({"url": url, "error": str(exc)})

    ended = utc_now_rfc3339()
    log_structured(
        "info",
        "collect query finished",
        correlation_id=correlation_id,
        query=query,
        topic=topic,
        searxng_hits=len(hits),
        documents=len(documents),
        duplicates=len(duplicates),
        errors=len(errors),
        started_at=started,
        ended_at=ended,
    )
    # Single-query collect wraps this row in ``{"results": [row]}``.
    return {
        "correlation_id": correlation_id,
        "query": query,
        "topic": topic,
        "language_hint": language,
        "searxng_hits": len(hits),
        "documents": documents,
        "duplicates": duplicates,
        "errors": errors,
        "dedupe": {
            "index_size": index.size,
            "max_hamming": index.max_hamming,
            "path": str(index.path),
        },
        "started_at": started,
        "ended_at": ended,
    }


def wrap_collect_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap per-query collect rows in the public ``{"results": [...]}`` table.

    ``/collect`` always has one row; ``/collect/batch`` has one row per query.

    Example:
        >>> from thot.tools.collector.service import wrap_collect_results
        >>> wrap_collect_results([{"query": "a", "documents": []}])["results"][0]["query"]
        'a'
    """
    return {"results": list(rows)}


# Back-compat alias for older imports / scripts.
collect_and_analyze = collect_markdown


async def collect_queries_batch(
    settings: CollectorSettings,
    *,
    queries: list[dict[str, Any]],
    dedupe: CollectorDedupeIndex | None = None,
    concurrency: int | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Collect several queries concurrently; return a ``results`` table.

    Each item in ``queries`` is a mapping with at least ``query`` and optional
    ``topic``, ``max_results``, ``language``. Response is
    ``{"results": [<per-query row>, ...]}`` (same row shape as single collect).
    Documents are returned only (not written to disk). Shared SimHash index.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.service import collect_queries_batch
        >>> inspect.iscoroutinefunction(collect_queries_batch)
        True
    """
    if not queries:
        raise ValueError("queries must be a non-empty list")
    correlation_id = correlation_id or generate_trace_id()
    index = dedupe or load_dedupe_index(settings)
    limit = max(
        1,
        concurrency if concurrency is not None else settings.batch_concurrency,
    )
    semaphore = asyncio.Semaphore(limit)

    async def _one(item: dict[str, Any]) -> dict[str, Any]:
        q = str(item.get("query") or "").strip()
        if not q:
            now = utc_now_rfc3339()
            return {
                "correlation_id": correlation_id,
                "query": q,
                "topic": item.get("topic"),
                "language_hint": item.get("language"),
                "searxng_hits": 0,
                "documents": [],
                "duplicates": [],
                "errors": [{"url": "", "error": "empty query"}],
                "dedupe": {
                    "index_size": index.size,
                    "max_hamming": index.max_hamming,
                    "path": str(index.path),
                },
                "started_at": now,
                "ended_at": now,
            }
        async with semaphore:
            return await collect_markdown(
                settings,
                query=q,
                topic=item.get("topic"),
                max_results=item.get("max_results"),
                language=item.get("language"),
                dedupe=index,
                correlation_id=correlation_id,
            )

    rows = list(await asyncio.gather(*[_one(item) for item in queries]))
    return wrap_collect_results(rows)
