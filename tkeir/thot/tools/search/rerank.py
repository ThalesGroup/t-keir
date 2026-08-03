"""Title: Rerank

Second-stage rerank of retrieval hits.

- Cross-encoder / embedding cosine over Vespa children
  (:func:`rerank_vespa_children`)
- BGE-M3 ColBERT MaxSim for **one query × N candidates**
  (:func:`colbert_rerank`) — production path after Vespa hybrid

Multi-query / dataset batch ColBERT lives under ``thot.tools.eval``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)

_ALLOWED_STRATEGIES = frozenset({"cross_encoder", "embedding_cosine"})
_DEFAULT_STRATEGY = "embedding_cosine"

DEFAULT_COLBERT_TOP_M = 40
DEFAULT_FIRST_STAGE_WEIGHT = 0.55
DEFAULT_COLBERT_WEIGHT = 0.45
DEFAULT_TAIL_WEIGHT = 0.15


class RerankClient(Protocol):
    """Minimal async client used by :func:`rerank_vespa_children`.

    Example:
        >>> import inspect
        >>> inspect.isabstract(RerankClient.rerank)
        False
    """

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
    """Return an allowed rerank strategy (never LLM).

    Example:
        >>> _resolve_strategy("embedding_cosine")
        'embedding_cosine'
        >>> _resolve_strategy("llm_judge")
        'embedding_cosine'
    """
    chosen = str(strategy or _DEFAULT_STRATEGY).strip().lower()
    if chosen not in _ALLOWED_STRATEGIES:
        return _DEFAULT_STRATEGY
    return chosen


def hit_text_for_rerank(fields: dict[str, Any]) -> str:
    """Build the document string scored by the reranker.

    Prefers chunk ``text_raw``, then joined ``content``, then ``title``.

    Example:
        >>> hit_text_for_rerank({"text_raw": "Core passage"})
        'Core passage'
        >>> hit_text_for_rerank({"content": ["Part one", "Part two"]})
        'Part one Part two'
    """
    text = str(fields.get("text_raw") or "").strip()
    if text:
        return text
    content = fields.get("content") or fields.get("parent_content") or []
    if isinstance(content, list):
        joined = " ".join(str(part) for part in content if part).strip()
        if joined:
            return joined
    return str(fields.get("title") or fields.get("parent_title") or "").strip()


async def rerank_vespa_children(
    llm: RerankClient,
    query: str,
    children: list[dict[str, Any]],
    *,
    top_n: int | None = None,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    """Reorder Vespa ``root.children`` using the configured rerank strategy.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(rerank_vespa_children)
        True
    """
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


def colbert_settings() -> dict[str, Any]:
    """Load ColBERT knobs from ``rag.yaml`` ``dual_hybrid.colbert``.

    Example:
        >>> settings = colbert_settings()
        >>> "top_m" in settings and settings["top_m"] >= 1
        True
    """
    try:
        from thot.tools.search.rag_config import load_rag_config

        cfg = load_rag_config().dual_hybrid
        cb = getattr(cfg, "colbert", None)
        if cb is None:
            raise AttributeError("no colbert")
        return {
            "enabled": bool(getattr(cb, "enabled", True)),
            "top_m": int(getattr(cb, "top_m", DEFAULT_COLBERT_TOP_M)),
            "first_stage_weight": float(
                getattr(cb, "first_stage_weight", DEFAULT_FIRST_STAGE_WEIGHT)
            ),
            "colbert_weight": float(
                getattr(cb, "colbert_weight", DEFAULT_COLBERT_WEIGHT)
            ),
            "tail_weight": float(
                getattr(cb, "tail_weight", DEFAULT_TAIL_WEIGHT)
            ),
            "batch_size": int(getattr(cb, "batch_size", 8)),
            "rrf_k": int(getattr(cb, "rrf_k", 60)),
            "pool": int(getattr(cb, "pool", 100)),
        }
    except Exception:  # noqa: BLE001
        return {
            "enabled": True,
            "top_m": DEFAULT_COLBERT_TOP_M,
            "first_stage_weight": DEFAULT_FIRST_STAGE_WEIGHT,
            "colbert_weight": DEFAULT_COLBERT_WEIGHT,
            "tail_weight": DEFAULT_TAIL_WEIGHT,
            "batch_size": 8,
            "rrf_k": 60,
            "pool": 100,
        }


def colbert_late_interaction(query_vecs: Any, doc_vecs: Any) -> float:
    """MaxSim late interaction (ColBERT) between one query and one document.

    Example:
        >>> import numpy as np
        >>> round(colbert_late_interaction(
        ...     np.array([[1.0, 0.0]]),
        ...     np.array([[1.0, 0.0]]),
        ... ), 6)
        1.0
    """
    import numpy as np

    q = np.asarray(query_vecs, dtype=np.float32)
    d = np.asarray(doc_vecs, dtype=np.float32)
    if q.ndim == 1:
        q = q.reshape(1, -1)
    if d.ndim == 1:
        d = d.reshape(1, -1)
    if q.size == 0 or d.size == 0:
        return 0.0
    q_n = np.linalg.norm(q, axis=1, keepdims=True)
    d_n = np.linalg.norm(d, axis=1, keepdims=True)
    q = q / np.maximum(q_n, 1e-12)
    d = d / np.maximum(d_n, 1e-12)
    sim = q @ d.T
    return float(sim.max(axis=1).sum() / max(q.shape[0], 1))


def colbert_rerank(
    query: str,
    candidates: list[tuple[str, str, float]],
    *,
    top_m: int | None = None,
    top_k: int | None = None,
    batch_size: int | None = None,
    first_stage_weight: float | None = None,
    colbert_weight: float | None = None,
    tail_weight: float | None = None,
) -> list[tuple[str, float]]:
    """ColBERT MaxSim rerank for **one query** and **N** candidate passages.

    Production path: Vespa (or other first stage) returns candidates; this
    re-scores the top-``top_m`` texts with BGE-M3 ColBERT vectors and blends
    with first-stage scores.

    Args:
        query: Raw query text.
        candidates: ``(doc_id, text, first_stage_score)`` unsorted or ranked.
        top_m / top_k / weights: Override ``rag.yaml`` ``dual_hybrid.colbert``.

    Returns:
        ``(doc_id, blended_score)`` best first.

    Example:
        >>> colbert_rerank("query", [])
        []
        >>> colbert_rerank("q", [("d1", "text", 0.5)])[0][0]
        'd1'
    """
    settings = colbert_settings()
    if not settings["enabled"] or not candidates:
        ranked = sorted(candidates, key=lambda row: row[2], reverse=True)
        limit = top_k or len(ranked)
        return [
            (doc_id, float(score)) for doc_id, _text, score in ranked[:limit]
        ]

    from thot.tools.search.bge_m3 import encode_colbert_vecs

    top_m = int(top_m if top_m is not None else settings["top_m"])
    top_k = int(top_k if top_k is not None else len(candidates))
    batch_size = int(
        batch_size if batch_size is not None else settings["batch_size"]
    )
    fs_w = float(
        first_stage_weight
        if first_stage_weight is not None
        else settings["first_stage_weight"]
    )
    cb_w = float(
        colbert_weight
        if colbert_weight is not None
        else settings["colbert_weight"]
    )
    tail_w = float(
        tail_weight if tail_weight is not None else settings["tail_weight"]
    )

    ordered = sorted(candidates, key=lambda row: row[2], reverse=True)
    pool = ordered[: max(1, top_m)]
    cand_ids = [doc_id for doc_id, _text, _score in pool]
    texts = [text for _doc_id, text, _score in pool]
    hits = {doc_id: float(score) for doc_id, _text, score in ordered}

    colbert = encode_colbert_vecs([query, *texts], batch_size=batch_size)
    if colbert is None or len(colbert) < 2:
        return [
            (doc_id, float(score)) for doc_id, _text, score in ordered[:top_k]
        ]

    q_vecs = colbert[0]
    cb_scores = {
        doc_id: colbert_late_interaction(q_vecs, colbert[i + 1])
        for i, doc_id in enumerate(cand_ids)
    }
    cb_max = max(cb_scores.values()) if cb_scores else 0.0
    fs_max = max((hits.get(d, 0.0) for d in cand_ids), default=0.0)
    blended: dict[str, float] = {}
    for doc_id in cand_ids:
        fs = float(hits.get(doc_id, 0.0))
        fs_n = (fs / fs_max) if fs_max > 0 else 0.0
        cb_n = (cb_scores[doc_id] / cb_max) if cb_max > 0 else 0.0
        blended[doc_id] = fs_w * fs_n + cb_w * cb_n
    for doc_id, score in hits.items():
        if doc_id not in blended:
            blended[doc_id] = tail_w * (
                float(score) / fs_max if fs_max > 0 else 0.0
            )
    top = sorted(blended.items(), key=lambda item: item[1], reverse=True)[
        : max(1, top_k)
    ]
    return [(doc_id, float(score)) for doc_id, score in top]
