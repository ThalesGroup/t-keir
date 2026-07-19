# -*- coding: utf-8 -*-
"""Aggregate chunk hits into document scores for search APIs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AggregatedDocument:
    """Document-level score built from one or more chunk hits."""

    document_id: str
    score: float
    chunk_ids: list[str]
    title: str = ""
    max_chunk_score: float = 0.0
    hit_count: int = 0


def document_score_from_chunks(
    chunk_scores: list[float],
    *,
    multi_hit_bonus: float = 0.05,
) -> float:
    """Combine chunk scores into a document score.

    Uses ``max(chunk) + bonus * log1p(hit_count)`` so multi-evidence documents
    rise without language-specific heuristics.

    Example:
        >>> round(document_score_from_chunks([0.8]), 6)
        0.834657
    """
    if not chunk_scores:
        return 0.0
    best = max(chunk_scores)
    return best + multi_hit_bonus * math.log1p(len(chunk_scores))


def aggregate_chunks_to_documents(
    chunks: list[dict[str, Any]],
    *,
    multi_hit_bonus: float = 0.05,
) -> list[AggregatedDocument]:
    """Group scored chunks by ``parent_doc_id`` / ``document_id``.

    Each chunk mapping should provide:
    - ``document_id`` or ``parent_doc_id``
    - ``chunk_id``
    - ``score`` (float)
    - optional ``title``

    Returns:
        Documents sorted by score descending.

    Example:
        >>> docs = aggregate_chunks_to_documents([
        ...     {"document_id": "d1", "chunk_id": "c1", "score": 0.9, "title": "A"},
        ...     {"document_id": "d1", "chunk_id": "c2", "score": 0.5},
        ... ])
        >>> docs[0].document_id
        'd1'
        >>> docs[0].hit_count
        2
    """
    buckets: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        doc_id = str(
            chunk.get("document_id") or chunk.get("parent_doc_id") or ""
        ).strip()
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if not doc_id or not chunk_id:
            continue
        try:
            score_raw = chunk.get("score")
            if score_raw is None:
                continue
            score = float(score_raw)
        except (TypeError, ValueError):
            continue
        bucket = buckets.setdefault(
            doc_id,
            {
                "scores": [],
                "chunk_ids": [],
                "title": str(chunk.get("title") or ""),
            },
        )
        bucket["scores"].append(score)
        bucket["chunk_ids"].append(chunk_id)
        if not bucket["title"] and chunk.get("title"):
            bucket["title"] = str(chunk.get("title") or "")

    documents: list[AggregatedDocument] = []
    for doc_id, bucket in buckets.items():
        scores = bucket["scores"]
        documents.append(
            AggregatedDocument(
                document_id=doc_id,
                score=document_score_from_chunks(
                    scores, multi_hit_bonus=multi_hit_bonus
                ),
                chunk_ids=list(bucket["chunk_ids"]),
                title=str(bucket["title"] or ""),
                max_chunk_score=max(scores) if scores else 0.0,
                hit_count=len(scores),
            )
        )
    documents.sort(key=lambda item: item.score, reverse=True)
    return documents
