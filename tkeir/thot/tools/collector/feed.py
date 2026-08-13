"""Title: Collector feed orchestration (Osiris → queries → SearXNG → markdown).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from thot.tools.collector.config import CollectorSettings
from thot.tools.collector.dedupe import CollectorDedupeIndex
from thot.tools.collector.forge import (
    collect_seeds,
    forge_queries_from_osiris_data,
)
from thot.tools.collector.forge_config import load_forge_config
from thot.tools.collector.nlp_forge import (
    forge_queries_from_osiris_seeds_nlp,
    save_forged_queries,
)
from thot.tools.collector.osiris_client import collect_osiris_buckets
from thot.tools.collector.service import collect_queries_batch

LOGGER = logging.getLogger(__name__)

# In-process last feed (filled only when Osiris/user triggers /feed).
_LAST_FEED: dict[str, Any] | None = None


def get_last_feed() -> dict[str, Any] | None:
    """Return the most recent feed payload (or ``None``)."""
    return _LAST_FEED


def set_last_feed(feed: dict[str, Any]) -> None:
    """Store feed for ``GET /feed`` and wiki iteration."""
    global _LAST_FEED
    _LAST_FEED = feed


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def flatten_documents(
    results: list[dict[str, Any]],
    queries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten batch rows into feed documents (keep markdown for UI).

    Prefers substantive prose; drops chrome-heavy pages when a better
    sibling document exists for the same query.
    """
    from thot.tools.collector.convert import clean_markdown, is_substantive_markdown

    by_q = {str(q.get("query") or "").lower(): q for q in queries}
    seen: set[str] = set()
    docs: list[dict[str, Any]] = []
    for row in results:
        qtext = str(row.get("query") or "").strip()
        forged = by_q.get(qtext.lower()) or {}
        for doc in row.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            url = str(doc.get("url") or "").rstrip("/").lower()
            if not url or url in seen:
                continue
            md = clean_markdown(str(doc.get("markdown") or ""))
            if md and not is_substantive_markdown(md, min_chars=80):
                # Keep root-style thin seeds; drop empty chrome pages.
                if not doc.get("fetch_fallback") and len(md) < 120:
                    continue
            seen.add(url)
            coords = forged.get("coords")
            lat = coords[0] if isinstance(coords, list) and len(coords) >= 2 else None
            lng = coords[1] if isinstance(coords, list) and len(coords) >= 2 else None
            docs.append(
                {
                    **doc,
                    "markdown": md or doc.get("markdown"),
                    "query": qtext or doc.get("query"),
                    "queryId": forged.get("id"),
                    "queryApi": forged.get("api"),
                    "querySource": forged.get("source"),
                    "querySnippet": forged.get("snippet"),
                    "queryTimestamp": forged.get("timestamp"),
                    "lat": lat if doc.get("lat") is None else doc.get("lat"),
                    "lng": lng if doc.get("lng") is None else doc.get("lng"),
                    "anchorLat": lat if doc.get("anchorLat") is None else doc.get("anchorLat"),
                    "anchorLng": lng if doc.get("anchorLng") is None else doc.get("anchorLng"),
                    "is_root": False,
                }
            )
    # Prefer longer substantive docs first (wiki ranking still reorders).
    docs.sort(
        key=lambda d: int(d.get("markdown_chars") or len(str(d.get("markdown") or ""))),
        reverse=True,
    )
    return docs


def _merge_root_first(
    roots: list[dict[str, Any]],
    searx_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Osiris root documents always precede SearXNG expansion hits."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for doc in list(roots) + list(searx_docs):
        if not isinstance(doc, dict):
            continue
        key = str(doc.get("url") or doc.get("title") or "").rstrip("/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(doc)
    return out


async def build_feed(
    settings: CollectorSettings,
    *,
    data: dict[str, Any] | None = None,
    queries: list[dict[str, Any]] | None = None,
    max_queries: int = 40,
    max_results_per_query: int | None = None,
    map_center: dict[str, float] | None = None,
    dedupe: CollectorDedupeIndex | None = None,
    include_wiki: bool = True,
    wiki_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Osiris buckets → (NLP) forge → collect/batch → flat feed for Osiris map.

    When ``nlp_forge.enabled`` (forge.yaml), opens seed feed URLs, cleans /
    chunks text, forges queries from SVO/keywords, and pins root documents
    first for wiki. Forged queries are saved under the workspace when
    ``save_queries`` is true (default).
    """
    forge_cfg = load_forge_config()
    from thot.tools.collector.pipeline_status import PIPELINE_STATUS

    PIPELINE_STATUS.set_phase(
        "osiris_apis",
        detail="Collecting Osiris API buckets" if not data else "Using provided buckets",
        progress=0.2,
    )
    buckets = data
    if not buckets:
        if not settings.osiris_base_url:
            return {
                "ok": False,
                "code": "NO_OSIRIS_URL",
                "error": "Set OSIRIS_BASE_URL (e.g. http://127.0.0.1:3000) for /feed routing",
                "queries": [],
                "documents": [],
                "results": [],
                "wiki": wiki_state,
                "generatedAt": _now_iso(),
            }
        buckets = await collect_osiris_buckets(settings.osiris_base_url)

    root_docs: list[dict[str, Any]] = []
    forge_mode = "classic"
    seed_count = 0

    if queries:
        forged = list(queries)
        forge_mode = "provided"
    elif forge_cfg.nlp.enabled and buckets:
        PIPELINE_STATUS.set_phase(
            "fetch_seeds",
            detail="Opening seed URLs + NLP forge (SVO/keywords + geocode)",
            progress=0.2,
        )
        seeds = collect_seeds(buckets)
        seed_count = len(seeds)
        if seeds:
            forged, root_docs = await forge_queries_from_osiris_seeds_nlp(
                settings,
                seeds,
                max_queries=max_queries,
                forge_cfg=forge_cfg,
            )
            forge_mode = "nlp_seed"
            if not forged:
                forged = forge_queries_from_osiris_data(
                    buckets,
                    max_queries=max_queries,
                    map_center=map_center,
                )
                forge_mode = "classic_fallback"
        else:
            forged = forge_queries_from_osiris_data(
                buckets,
                max_queries=max_queries,
                map_center=map_center,
            )
            forge_mode = "classic"
    else:
        if buckets:
            seed_count = len(collect_seeds(buckets))
        forged = forge_queries_from_osiris_data(
            buckets,
            max_queries=max_queries,
            map_center=map_center,
        )
        forge_mode = "classic"

    forged = forged[: max(1, max_queries)] if forged else []

    PIPELINE_STATUS.set_phase(
        "forge",
        detail=f"{len(forged)} forged quer{'y' if len(forged) == 1 else 'ies'} ({forge_mode})",
        progress=0.9,
        query_count=len(forged),
        seed_count=seed_count,
    )

    saved_path = save_forged_queries(
        settings.workspace,
        forged,
        enabled=forge_cfg.save_queries,
        label=forge_mode,
    )

    if not forged:
        feed = {
            "ok": False,
            "code": "NO_QUERIES",
            "error": "No forged queries from Osiris buckets",
            "queries": [],
            "documents": root_docs,
            "results": [],
            "wiki": wiki_state if include_wiki else None,
            "osiris_base_url": settings.osiris_base_url,
            "agent_url": settings.agent_url,
            "osint_sources_path": settings.osint_sources_path,
            "forge_mode": forge_mode,
            "forge_config": str(forge_cfg.path),
            "queries_saved": str(saved_path) if saved_path else None,
            "seedCount": seed_count,
            "rootDocumentCount": len(root_docs),
            "generatedAt": _now_iso(),
        }
        set_last_feed(feed)
        return feed

    batch_items = [
        {
            "query": q["query"],
            "topic": f"osiris/{q.get('api') or 'osiris'}",
            "max_results": max_results_per_query or settings.max_results,
            "language": "en",
            "categories": q.get("categories") or settings.searx_categories,
            "engines": settings.searx_engines,
            "safesearch": settings.searx_safesearch,
            "time_range": settings.searx_time_range or None,
        }
        for q in forged
    ]

    PIPELINE_STATUS.set_phase(
        "searx",
        detail=f"SearXNG batch · {len(batch_items)} quer{'y' if len(batch_items) == 1 else 'ies'}",
        progress=0.1,
        query_count=len(batch_items),
    )
    table = await collect_queries_batch(
        settings,
        queries=batch_items,
        dedupe=dedupe,
        concurrency=settings.batch_concurrency,
    )
    results = list(table.get("results") or [])
    searx_docs = flatten_documents(results, forged)
    documents = _merge_root_first(root_docs, searx_docs)
    PIPELINE_STATUS.set_phase(
        "searx",
        detail=f"{len(documents)} documents collected",
        progress=1.0,
        document_count=len(documents),
        query_count=len(forged),
    )

    feed = {
        "ok": True,
        "queries": forged,
        "documents": documents,
        "results": results,
        "queryCount": len(forged),
        "documentCount": len(documents),
        "rootDocumentCount": len(root_docs),
        "seedCount": seed_count,
        "wiki": wiki_state if include_wiki else None,
        "osiris_base_url": settings.osiris_base_url,
        "agent_url": settings.agent_url,
        "osint_sources_path": settings.osint_sources_path,
        "forge_mode": forge_mode,
        "forge_config": str(forge_cfg.path),
        "queries_saved": str(saved_path) if saved_path else None,
        "generatedAt": _now_iso(),
    }
    set_last_feed(feed)
    LOGGER.info(
        "feed built mode=%s seeds=%s queries=%s roots=%s documents=%s saved=%s",
        forge_mode,
        seed_count,
        len(forged),
        len(root_docs),
        len(documents),
        saved_path,
    )
    return feed
