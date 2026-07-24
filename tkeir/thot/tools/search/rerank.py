"""Title: Rerank

Rerank Vespa / retrieval hits with ``cross_encoder`` or ``embedding_cosine``.
LLM / generative rerank is forbidden.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)

_ALLOWED_STRATEGIES = frozenset({"cross_encoder", "embedding_cosine"})
_DEFAULT_STRATEGY = "cross_encoder"


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
        """Rerank documents for a query (cross-encoder or embedding cosine).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(RerankClient.rerank)
            True
        """


def _resolve_strategy(strategy: str | None) -> str:
    """Return an allowed rerank strategy (never LLM)."""
    chosen = str(strategy or _DEFAULT_STRATEGY).strip().lower()
    if chosen not in _ALLOWED_STRATEGIES:
        return _DEFAULT_STRATEGY
    return chosen


def hit_text_for_rerank(fields: dict[str, Any]) -> str:
    """Build the document string scored by the reranker.

    Prefers chunk ``text_raw``, then joined ``content``, then ``title``.
    """
    text = str(fields.get("text_raw") or "").strip()
    if text:
        return text
    content = fields.get("content") or fields.get("parent_content") or []
    if isinstance(content, list):
        joined = " ".join(str(part) for part in content if part).strip()
        if joined:
            return joined
    return str(
        fields.get("title") or fields.get("parent_title") or ""
    ).strip()


async def rerank_scored_texts(
    llm: RerankClient,
    query: str,
    items: list[tuple[str, float]],
    *,
    top_n: int | None = None,
    strategy: str | None = None,
) -> list[tuple[str, float]]:
    """Rerank ``(text, prior_score)`` pairs (cross-encoder or cosine)."""
    if not items:
        return []
    chosen = _resolve_strategy(strategy)
    documents = [text for text, _ in items]
    ranked = await llm.rerank(
        query,
        documents,
        top_n=top_n,
        strategy=chosen,
    )
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
    """Reorder Vespa ``root.children`` using the configured rerank strategy."""
    if not children:
        return []
    chosen = _resolve_strategy(strategy)
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

    ranked = await llm.rerank(
        query,
        texts,
        top_n=top_n,
        strategy=chosen,
    )
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
        chosen,
    )
    return reordered
