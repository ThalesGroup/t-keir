"""Title: Cluster wiki evidence chunks with BGE-M3 + agglomerative clustering.

Groups semantically related golden chunks, then selects a few members
nearest each cluster centroid for the LLM fold (full cluster kept for
Sources / citations).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

LOGGER = logging.getLogger(__name__)


def _chunk_text(chunk: dict[str, Any]) -> str:
    title = str(chunk.get("title") or "").strip()
    body = str(chunk.get("text_raw") or chunk.get("text") or "").strip()
    info = str(chunk.get("information") or "").strip()
    parts = [p for p in (title, body[:2000], info[:400]) if p]
    return "\n".join(parts) or "empty"


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _hash_bag_vector(text: str, dim: int = 256) -> list[float]:
    """Fallback dense-ish bag when BGE-M3 is unavailable."""
    vec = [0.0] * dim
    for tok in re.findall(r"[A-Za-z0-9]{3,}", (text or "").lower()):
        h = hash(tok) % dim
        vec[h] += 1.0
    return _l2_normalize(vec)


def encode_chunk_vectors(chunks: list[dict[str, Any]]) -> list[list[float]]:
    """Encode chunks with BGE-M3 dense vectors (hash bag fallback)."""
    texts = [_chunk_text(c) for c in chunks]
    if not texts:
        return []
    try:
        from thot.tools.search.bge_m3 import encode_texts, local_bge_m3_ready

        if local_bge_m3_ready():
            embs = encode_texts(texts, batch_size=min(16, len(texts)))
            return [_l2_normalize(list(e.dense)) for e in embs]
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("BGE-M3 encode failed for clustering (%s) — hash fallback", exc)
    return [_hash_bag_vector(t) for t in texts]


def _cosine(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


def select_near_centroids(
    clusters: list[list[dict[str, Any]]],
    *,
    per_cluster: int = 2,
    vectors_by_id: dict[str, list[float]] | None = None,
) -> list[list[dict[str, Any]]]:
    """For each cluster, keep the ``per_cluster`` chunks closest to the centroid.

    Used so the LLM fold only sees a few representative chunks while Sources
    can still cite the full cluster membership.
    """
    k = max(1, int(per_cluster))
    out: list[list[dict[str, Any]]] = []
    for group in clusters:
        if not group:
            continue
        if len(group) <= k:
            out.append(list(group))
            continue
        vecs: list[list[float]] = []
        for c in group:
            cid = str(c.get("chunk_id") or id(c))
            if vectors_by_id and cid in vectors_by_id:
                vecs.append(vectors_by_id[cid])
            else:
                vecs.append(encode_chunk_vectors([c])[0])
        dim = len(vecs[0])
        centroid = [sum(row[i] for row in vecs) / len(vecs) for i in range(dim)]
        centroid = _l2_normalize(centroid)
        ranked = sorted(
            range(len(group)),
            key=lambda i: -_cosine(vecs[i], centroid),
        )
        chosen = [group[i] for i in ranked[:k]]
        for c in chosen:
            c["near_centroid"] = True
        out.append(chosen)
    LOGGER.info(
        "near-centroid selection per_cluster=%s → sizes=%s (from %s)",
        k,
        [len(g) for g in out],
        [len(g) for g in clusters],
    )
    return out


def cluster_chunks_agglomerative(
    chunks: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.55,
    max_clusters: int | None = None,
    per_cluster_for_llm: int | None = None,
) -> list[list[dict[str, Any]]]:
    """Agglomerative clustering (average linkage, cosine) over chunk embeddings.

    ``similarity_threshold`` maps to ``distance_threshold = 1 - threshold``.
    When ``per_cluster_for_llm`` is set, each returned cluster is reduced to
    that many members nearest the centroid (for LLM fold).

    Returns:
        Ordered list of clusters (each a non-empty list of chunk dicts).
    """
    if not chunks:
        return []
    if len(chunks) == 1:
        return [list(chunks)]

    vectors = encode_chunk_vectors(chunks)
    try:
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("sklearn clustering unavailable (%s) — one cluster", exc)
        clusters = [list(chunks)]
        if per_cluster_for_llm:
            return select_near_centroids(clusters, per_cluster=per_cluster_for_llm)
        return clusters

    matrix = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms

    distance_threshold = max(0.05, min(1.5, 1.0 - float(similarity_threshold)))
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    labels = clustering.fit_predict(matrix)
    grouped: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        grouped.setdefault(int(lab), []).append(i)

    clusters = [[chunks[i] for i in idxs] for idxs in grouped.values()]
    clusters.sort(key=lambda c: (-len(c), str(c[0].get("chunk_id") or "")))

    if max_clusters and len(clusters) > max_clusters:
        while len(clusters) > max_clusters:
            clusters.sort(key=len)
            small = clusters.pop(0)
            clusters[-1].extend(small)
        clusters.sort(key=lambda c: (-len(c), str(c[0].get("chunk_id") or "")))

    LOGGER.info(
        "chunk clusters=%s sizes=%s threshold=%.2f",
        len(clusters),
        [len(c) for c in clusters],
        similarity_threshold,
    )
    if per_cluster_for_llm:
        by_id = {
            str(chunks[i].get("chunk_id") or id(chunks[i])): list(matrix[i])
            for i in range(len(chunks))
        }
        return select_near_centroids(
            clusters,
            per_cluster=int(per_cluster_for_llm),
            vectors_by_id=by_id,
        )
    return clusters
