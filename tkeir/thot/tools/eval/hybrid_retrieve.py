"""Title: BEIR / offline hybrid retrieve (multi-query corpus scoring).

Dataset-level first stage (BGE-M3 + BM25 RRF) and multi-query ColBERT
batching for evaluation. Production single-query ColBERT lives in
:mod:`thot.tools.search.rerank`.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

from thot.tools.search.rerank import (
    DEFAULT_COLBERT_TOP_M,
    DEFAULT_COLBERT_WEIGHT,
    DEFAULT_FIRST_STAGE_WEIGHT,
    DEFAULT_TAIL_WEIGHT,
    colbert_rerank,
    colbert_settings,
)

LOGGER = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

DEFAULT_RRF_K = 60
DEFAULT_POOL = 100

ProgressFn = Callable[[int, int, str], None]


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization for BM25."""
    return _TOKEN_RE.findall((text or "").lower())


def document_text(doc: dict[str, str] | str) -> str:
    """Join title+text for BEIR-style docs, or return a raw string."""
    if isinstance(doc, str):
        return doc.strip()
    title = (doc.get("title") or "").strip()
    body = (doc.get("text") or "").strip()
    return f"{title} {body}".strip() if title else body


def sparse_dot(query: dict[str, float], document: dict[str, float]) -> float:
    """Lexical (sparse) match score used by BGE-M3 hybrid retrieval."""
    if not query or not document:
        return 0.0
    score = 0.0
    for token, weight in query.items():
        other = document.get(token)
        if other:
            score += float(weight) * float(other)
    return score


def bge_hybrid_weights() -> tuple[float, float]:
    """Dense/sparse fusion weights from ``rag.yaml`` passage hybrid."""
    try:
        from thot.tools.search.rag_config import load_rag_config

        ranks = load_rag_config().dual_hybrid.rank_profiles or {}
        hybrid = ((ranks.get("passage") or {}).get("hybrid")) or {}
        dense_w = float(hybrid.get("dense", 0.70) or 0.70)
        sparse_w = float(hybrid.get("sparse", 0.20) or 0.20)
    except Exception:  # noqa: BLE001
        dense_w, sparse_w = 0.70, 0.20
    total = dense_w + sparse_w
    if total <= 0:
        return 1.0, 0.0
    return dense_w / total, sparse_w / total


def rrf_fuse_runs(
    *runs: dict[str, dict[str, float]],
    k: int = DEFAULT_RRF_K,
    top_k: int = DEFAULT_POOL,
) -> dict[str, dict[str, float]]:
    """Unweighted RRF over ``qid → {doc_id → score}`` runs."""
    if not runs:
        return {}
    query_ids: set[str] = set()
    for run in runs:
        query_ids.update(run.keys())
    fused: dict[str, dict[str, float]] = {}
    for qid in query_ids:
        scores: dict[str, float] = {}
        for run in runs:
            ranked = sorted(
                (run.get(qid) or {}).items(),
                key=lambda item: item[1],
                reverse=True,
            )
            for rank, (doc_id, _score) in enumerate(ranked, start=1):
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[
            : max(1, top_k)
        ]
        fused[qid] = {doc_id: float(score) for doc_id, score in top}
    return fused


def score_bm25(
    corpus: dict[str, dict[str, str]] | dict[str, str],
    queries: dict[str, str],
    *,
    top_k: int = DEFAULT_POOL,
) -> dict[str, dict[str, float]]:
    """In-memory BM25Okapi over title+text (BEIR baseline / hybrid arm)."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ImportError(
            "Missing dependency 'rank-bm25' (T-KEIR hybrid retrieve / BM25 arm). "
            "Install with: cd tkeir && uv sync --group beir --group models"
        ) from exc

    doc_ids = list(corpus.keys())
    tokenized = [tokenize(document_text(corpus[did])) for did in doc_ids]
    tokenized = [toks if toks else ["_"] for toks in tokenized]
    bm25 = BM25Okapi(tokenized)
    LOGGER.info("BM25 indexed %d documents", len(doc_ids))
    keep = max(1, int(top_k))
    results: dict[str, dict[str, float]] = {}
    for qid, qtext in queries.items():
        scores = bm25.get_scores(tokenize(qtext) or ["_"])
        if keep >= len(doc_ids):
            order = sorted(
                range(len(doc_ids)), key=lambda i: scores[i], reverse=True
            )
        else:
            import numpy as np

            arr = np.asarray(scores, dtype=np.float64)
            part = np.argpartition(-arr, keep)[:keep]
            order = part[np.argsort(-arr[part])]
        results[qid] = {
            doc_ids[int(i)]: float(scores[int(i)]) for i in order[:keep]
        }
    return results


def score_bge_hybrid(
    corpus: dict[str, dict[str, str]] | dict[str, str],
    queries: dict[str, str],
    *,
    model_id: str | None = None,
    batch_size: int = 32,
    top_k: int = DEFAULT_POOL,
) -> dict[str, dict[str, float]]:
    """BGE-M3 dense+sparse hybrid over a full corpus (eval / offline)."""
    import numpy as np

    from thot.tools.search.bge_m3 import encode_texts, resolve_bge_m3_path

    path = resolve_bge_m3_path(model_id)
    w_dense, w_sparse = bge_hybrid_weights()
    LOGGER.info(
        "BGE-M3 dense+sparse from %s (weights dense=%.3f sparse=%.3f batch=%d)",
        path,
        w_dense,
        w_sparse,
        batch_size,
    )
    query_ids = list(queries.keys())
    query_texts = [queries[qid] for qid in query_ids]
    LOGGER.info("Encoding %d queries with BGE-M3 dense+sparse…", len(query_texts))
    q_emb = encode_texts(query_texts, model_id=path, batch_size=batch_size)

    doc_ids = list(corpus.keys())
    doc_texts = [document_text(corpus[did]) for did in doc_ids]
    LOGGER.info("Encoding %d corpus docs with BGE-M3 dense+sparse…", len(doc_texts))
    d_emb = encode_texts(doc_texts, model_id=path, batch_size=batch_size)

    q_dense = np.asarray([row.dense for row in q_emb], dtype=np.float32)
    d_dense = np.asarray([row.dense for row in d_emb], dtype=np.float32)
    q_norm = np.linalg.norm(q_dense, axis=1, keepdims=True)
    d_norm = np.linalg.norm(d_dense, axis=1, keepdims=True)
    q_dense = q_dense / np.maximum(q_norm, 1e-12)
    d_dense = d_dense / np.maximum(d_norm, 1e-12)
    dense_scores = q_dense @ d_dense.T

    LOGGER.info(
        "Scoring hybrid dense+sparse for %d queries × %d docs…",
        len(query_ids),
        len(doc_ids),
    )
    results: dict[str, dict[str, float]] = {}
    keep = max(1, int(top_k))
    for qi, qid in enumerate(query_ids):
        q_sparse = q_emb[qi].sparse
        scores = dense_scores[qi] * w_dense
        if w_sparse > 0.0 and q_sparse:
            sparse_row = np.fromiter(
                (
                    sparse_dot(q_sparse, d_emb[di].sparse)
                    for di in range(len(doc_ids))
                ),
                dtype=np.float32,
                count=len(doc_ids),
            )
            sparse_max = float(sparse_row.max()) if sparse_row.size else 0.0
            if sparse_max > 0.0:
                scores = scores + (sparse_row / sparse_max) * w_sparse
        if keep >= len(doc_ids):
            order = np.argsort(-scores)
        else:
            part = np.argpartition(-scores, keep)[:keep]
            order = part[np.argsort(-scores[part])]
        results[qid] = {
            doc_ids[int(di)]: float(scores[int(di)]) for di in order[:keep]
        }
        if (qi + 1) % 50 == 0 or qi + 1 == len(query_ids):
            LOGGER.info(
                "BGE-M3 hybrid scored %d / %d queries",
                qi + 1,
                len(query_ids),
            )
    return results


def colbert_rerank_queries(
    corpus: dict[str, dict[str, str]] | dict[str, str],
    queries: dict[str, str],
    first_stage: dict[str, dict[str, float]],
    *,
    top_m: int = DEFAULT_COLBERT_TOP_M,
    top_k: int = DEFAULT_POOL,
    batch_size: int = 8,
    first_stage_weight: float = DEFAULT_FIRST_STAGE_WEIGHT,
    colbert_weight: float = DEFAULT_COLBERT_WEIGHT,
    tail_weight: float = DEFAULT_TAIL_WEIGHT,
    progress: ProgressFn | None = None,
) -> dict[str, dict[str, float]]:
    """Batch ColBERT MaxSim over many queries (eval / BEIR).

    Each query calls production :func:`thot.tools.search.rerank.colbert_rerank`.
    """
    out: dict[str, dict[str, float]] = {}
    total = len(queries)
    started = time.perf_counter()
    for index, (qid, qtext) in enumerate(queries.items(), start=1):
        hits = first_stage.get(qid) or {}
        candidates = [
            (doc_id, document_text(corpus[doc_id]), float(score))
            for doc_id, score in hits.items()
            if doc_id in corpus
        ]
        if not candidates:
            out[qid] = {}
            continue
        ranked = colbert_rerank(
            qtext,
            candidates,
            top_m=top_m,
            top_k=top_k,
            batch_size=batch_size,
            first_stage_weight=first_stage_weight,
            colbert_weight=colbert_weight,
            tail_weight=tail_weight,
        )
        out[qid] = {doc_id: float(score) for doc_id, score in ranked}
        if progress is not None:
            progress(index, total, str(qid))
        elif index == 1 or index >= total or index % max(1, total // 20) == 0:
            elapsed = max(1e-6, time.perf_counter() - started)
            LOGGER.info(
                "ColBERT rerank %d/%d (%.2f q/s)",
                index,
                total,
                index / elapsed,
            )
    return out


def retrieve_hybrid(
    corpus: dict[str, dict[str, str]] | dict[str, str],
    queries: dict[str, str],
    *,
    top_k: int = DEFAULT_POOL,
    pool: int | None = None,
    rrf_k: int | None = None,
    colbert_top_m: int | None = None,
    batch_size: int = 32,
    colbert_batch_size: int | None = None,
    model_id: str | None = None,
    progress: ProgressFn | None = None,
    ontology_payload: dict[str, Any] | None = None,
    language: str = "en",
) -> dict[str, dict[str, float]]:
    """Eval retrieve: BGE-M3 + BM25 RRF → optional long-query ontology → ColBERT.

    Long queries (``nlp_seed_expansion``) run NLP + ontology expansion +
    :class:`~thot.tools.search.ontology_scorer.OntologyRescorer` on the
    first-stage pool before ColBERT. Short queries keep the plain RRF path.
    """
    settings = colbert_settings()
    pool_n = int(pool if pool is not None else max(top_k, settings["pool"]))
    rrf_k = int(rrf_k if rrf_k is not None else settings["rrf_k"])
    top_m = int(
        colbert_top_m if colbert_top_m is not None else settings["top_m"]
    )
    cb_batch = int(
        colbert_batch_size
        if colbert_batch_size is not None
        else settings["batch_size"]
    )
    LOGGER.info(
        "T-KEIR retrieve_hybrid (eval): BGE-M3 + BM25 RRF (k=%d pool=%d) "
        "+ optional long-query ontology + ColBERT top_m=%d → top_k=%d",
        rrf_k,
        pool_n,
        top_m,
        top_k,
    )
    bge_run = score_bge_hybrid(
        corpus,
        queries,
        model_id=model_id,
        batch_size=batch_size,
        top_k=pool_n,
    )
    bm25_run = score_bm25(corpus, queries, top_k=pool_n)
    fused = rrf_fuse_runs(bge_run, bm25_run, k=rrf_k, top_k=pool_n)

    if ontology_payload:
        from thot.tasks.answer_generation.query_enrichment import (
            enrich_first_stage_runs,
        )

        fused = enrich_first_stage_runs(
            corpus,
            queries,
            fused,
            ontology_payload=ontology_payload,
            language=language,
        )

    if not settings["enabled"]:
        return {
            qid: dict(
                sorted(hits.items(), key=lambda i: i[1], reverse=True)[:top_k]
            )
            for qid, hits in fused.items()
        }
    return colbert_rerank_queries(
        corpus,
        queries,
        fused,
        top_m=top_m,
        top_k=top_k,
        batch_size=cb_batch,
        first_stage_weight=float(settings["first_stage_weight"]),
        colbert_weight=float(settings["colbert_weight"]),
        tail_weight=float(settings["tail_weight"]),
        progress=progress,
    )
