"""Title: Rerank

Rerank Vespa / retrieval hits via :class:`UnifiedLLMWrapper.rerank`.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)


class RerankClient(Protocol):
    """Minimal async client used by :func:`rerank_scored_texts`."""

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        strategy: str | None = None,
    ) -> list[dict[str, Any]]:
        """Rerank documents for a query.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(RerankClient.rerank)
            True
        """


def hit_text_for_rerank(fields: dict[str, Any]) -> str:
    """Build the document string scored by the cross-encoder.

    Prefers chunk ``text_raw``, then joined ``parent_content``, then title.

    Args:
        fields: Vespa hit ``fields`` mapping.

    Returns:
        Non-empty text when available, else empty string.

    Example:
        >>> hit_text_for_rerank({"text_raw": "chunk", "parent_title": "T"})
        'chunk'
    """
    text = str(fields.get("text_raw") or "").strip()
    if text:
        return text
    parent = fields.get("parent_content") or []
    if isinstance(parent, list):
        joined = " ".join(str(part) for part in parent if part).strip()
        if joined:
            return joined
    return str(fields.get("parent_title") or "").strip()


async def rerank_scored_texts(
    llm: RerankClient,
    query: str,
    items: list[tuple[str, float]],
    *,
    top_n: int | None = None,
    strategy: str | None = None,
) -> list[tuple[str, float]]:
    """Rerank ``(text, prior_score)`` pairs; preserve length order by relevance.

    Args:
        llm: Wrapper exposing ``rerank``.
        query: User / claim query.
        items: Candidate texts with first-stage scores.
        top_n: Optional truncate after rerank.
        strategy: Optional ``cross_encoder`` / ``embedding_cosine`` override.

    Returns:
        Reordered ``(text, rerank_score)`` list.

    Example:
        >>> import asyncio
        >>> class _Stub:
        ...     async def rerank(self, query, documents, *, top_n=None, strategy=None):
        ...         return [{"index": 1, "relevance_score": 0.9},
        ...                 {"index": 0, "relevance_score": 0.1}]
        >>> asyncio.run(rerank_scored_texts(
        ...     _Stub(), "q", [("a", 1.0), ("b", 0.5)], top_n=2,
        ... ))
        [('b', 0.9), ('a', 0.1)]
    """
    if not items:
        return []
    documents = [text for text, _ in items]
    ranked = await llm.rerank(query, documents, top_n=top_n, strategy=strategy)
    out: list[tuple[str, float]] = []
    for entry in ranked:
        index = int(entry["index"])
        if index < 0 or index >= len(items):
            continue
        out.append((items[index][0], float(entry["relevance_score"])))
    if not out:
        return items[:top_n] if top_n else items
    return out


async def rerank_vespa_children(
    llm: RerankClient,
    query: str,
    children: list[dict[str, Any]],
    *,
    top_n: int | None = None,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    """Reorder Vespa ``root.children`` using the configured reranker model.

    Args:
        llm: Wrapper exposing ``rerank``.
        query: Query text for the cross-encoder / cosine scorer.
        children: Vespa hit children.
        top_n: Keep at most this many after rerank.
        strategy: Optional ``cross_encoder`` / ``embedding_cosine`` override.

    Returns:
        Children with ``relevance`` replaced by rerank scores, sorted desc.

    Example:
        >>> import asyncio
        >>> class _Stub:
        ...     async def rerank(self, query, documents, *, top_n=None, strategy=None):
        ...         return [{"index": 0, "relevance_score": 0.42}]
        >>> kids = [{"fields": {"text_raw": "doc"}, "relevance": 1.0}]
        >>> out = asyncio.run(rerank_vespa_children(_Stub(), "q", kids, top_n=1))
        >>> out[0]["relevance"]
        0.42
    """
    if not children:
        return []
    texts: list[str] = []
    usable: list[dict[str, Any]] = []
    for child in children:
        fields = child.get("fields") or {}
        text = hit_text_for_rerank(fields)
        if not text:
            continue
        texts.append(text)
        usable.append(child)
    if not usable:
        LOGGER.warning("Rerank skipped: no hit text available")
        return children[:top_n] if top_n else children

    ranked = await llm.rerank(query, texts, top_n=top_n, strategy=strategy)
    reordered: list[dict[str, Any]] = []
    for entry in ranked:
        index = int(entry["index"])
        if index < 0 or index >= len(usable):
            continue
        child = dict(usable[index])
        child["relevance"] = float(entry["relevance_score"])
        reordered.append(child)
    if not reordered:
        return usable[:top_n] if top_n else usable
    LOGGER.info(
        "Reranked %d / %d Vespa hits (kept=%d strategy=%s)",
        len(usable),
        len(children),
        len(reordered),
        strategy or "default",
    )
    return reordered
