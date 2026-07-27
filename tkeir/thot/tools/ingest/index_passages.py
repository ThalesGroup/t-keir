"""Title: Index passages into Vespa (ingest).

Embeds NLP pipeline golden chunks with BGE-M3 **dense+sparse** (first-stage
hybrid) and upserts ``global`` / ``user`` schemas. ColBERT MaxSim is
query-time only (:mod:`thot.tools.search.rerank`) from the same
BGE-M3 weights — not stored in Vespa. Lives under ``thot.tools.ingest``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from thot.core.TkeirPaths import repo_root
from thot.tools.search.bge_m3 import (
    BGE_M3_DENSE_DIM,
    encode_texts,
    vespa_dense_tensor,
    vespa_sparse_tensor,
)
from thot.tools.search.business_ontology import (
    annotate_document_with_business_ontology,
    resolve_index_ontology_payload,
)
from thot.tools.search.chunk_ontology import chunk_ontology_fields
from thot.tools.search.dual_hybrid_config import IndexDumpConfig
from thot.tools.search.rag_config import load_rag_config
from thot.tools.search.vespa_client import (
    VespaClient,
    chunk_embedding_text,
    sanitize_vespa_string,
)

LOGGER = logging.getLogger(__name__)

IndexTarget = Literal["global", "user", "both"]

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def ensure_golden_chunks_for_index(document: dict[str, Any]) -> dict[str, Any]:
    """Guarantee at least one indexable golden chunk.

    When NLP produced no chunks, synthesize one from content/title so
    passages can still be embedded and upserted.
    """
    chunks = document.get("golden_chunks") or []
    for chunk in chunks:
        if chunk.get("chunk_id") and chunk_embedding_text(chunk):
            return document

    source_id = str(
        document.get("source_doc_id") or document.get("source") or "document"
    )
    content = document.get("content") or []
    if isinstance(content, list):
        text = " ".join(str(part) for part in content if part).strip()
    else:
        text = str(content or "").strip()
    if not text:
        text = (document.get("title") or "").strip()
    if not text:
        LOGGER.warning("No content/title to synthesize chunk for %s", source_id)
        return document

    document = dict(document)
    document["golden_chunks"] = [
        {
            "chunk_id": f"{source_id}#chunk-0-index",
            "parent_doc_id": source_id,
            "text_raw": text,
            "search_vector_payload": text,
            "metadata": {"source": "index_fallback"},
        }
    ]
    LOGGER.info("Synthesized fallback golden chunk for %s", source_id)
    return document


# Backward-compatible alias.
_ensure_golden_chunks_for_index = ensure_golden_chunks_for_index


@dataclass(frozen=True)
class IndexTimings:
    """Stage timings for one pipeline document (milliseconds)."""

    nlp_ms: float = 0.0
    embed_ms: float = 0.0
    vespa_ms: float = 0.0
    total_ms: float = 0.0


@dataclass(frozen=True)
class IndexDocumentResult:
    """Counts + timings for one indexed document."""

    document_count: int
    passage_count: int
    timings: IndexTimings


def _ontology_fields_for_chunk(
    chunk: dict[str, Any],
    document: dict[str, Any],
    ontology_payload: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """Return ``(ontology_concepts, expansion_labels)`` for a chunk.

    Concept ids feed Vespa ``ontology_concepts``. Expansion labels are kept for
    dumps / analysis only — sparse vectors stay pure BGE-M3. Document
    ``core_concepts`` stay on the analyzed dump, not on every passage.
    """
    fields = chunk_ontology_fields(
        chunk, document, ontology_payload=ontology_payload
    )
    concepts: list[str] = []
    seen: set[str] = set()
    for cid in list(fields.get("concept_ids") or []) + list(
        fields.get("linked_concept_ids") or []
    ):
        key = str(cid).strip()
        if not key or key.casefold() in seen:
            continue
        seen.add(key.casefold())
        concepts.append(key)
    labels = [
        str(lab).strip()
        for lab in (fields.get("expansion_labels") or [])
        if lab and str(lab).strip()
    ]
    return concepts[:64], labels[:96]


def _ontology_concept_list(
    chunk: dict[str, Any],
    document: dict[str, Any],
    ontology_payload: dict[str, Any] | None,
) -> list[str]:
    """Build ``ontology_concepts`` from SVO / json_ld / external ontology."""
    concepts, _labels = _ontology_fields_for_chunk(
        chunk, document, ontology_payload
    )
    return concepts


def _resolve_index_dump_dir(dump: IndexDumpConfig) -> Path:
    """Resolve dump directory (absolute, or relative to repo root)."""
    raw = (dump.path or IndexDumpConfig().path).strip() or IndexDumpConfig().path
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(repo_root()) / path
    return path


def _safe_dump_stem(source_ref: str) -> str:
    """Filesystem-safe stem from a document / BEIR source ref."""
    cleaned = _SAFE_NAME_RE.sub("_", (source_ref or "document").strip())
    cleaned = cleaned.strip("._") or "document"
    return cleaned[:180]


def _write_index_dump(
    *,
    dump: IndexDumpConfig,
    source_ref: str,
    dataset: str | None,
    passages: list[dict[str, Any]],
    document: dict[str, Any] | None = None,
) -> Path | None:
    """Write one JSON file for an indexed document when dump is enabled.

    Includes passages (chunk / sparse / concepts). When
    ``dump.save_document`` is true, also stores the full analyzed pipeline
    document (with external ontology + KG provenance) under
    ``analyzed_document``.
    """
    if not dump.enabled or not passages:
        return None
    root = _resolve_index_dump_dir(dump)
    if dataset:
        root = root / _safe_dump_stem(str(dataset))
    root.mkdir(parents=True, exist_ok=True)
    out_path = root / f"{_safe_dump_stem(source_ref)}.json"
    payload: dict[str, Any] = {
        "source_ref": source_ref,
        "dataset": dataset,
        "passages": passages,
    }
    if dump.save_document and document is not None:
        payload["analyzed_document"] = document
        payload["core_concepts"] = list(document.get("core_concepts") or [])
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(tmp_path, out_path)
    return out_path


def _passage_fields(
    *,
    chunk: dict[str, Any],
    document: dict[str, Any],
    dense: list[float],
    sparse: dict[str, float],
    ontology_concepts: list[str],
    embedding_dim: int,
    userspace_id: str | None = None,
) -> dict[str, Any]:
    text = chunk_embedding_text(chunk) or str(chunk.get("text_raw") or "")
    source_ref = str(
        document.get("source_doc_id")
        or document.get("source")
        or chunk.get("parent_doc_id")
        or ""
    )
    fields: dict[str, Any] = {
        "source_ref": sanitize_vespa_string(source_ref),
        "chunk_text": sanitize_vespa_string(text),
        "dense_vector": vespa_dense_tensor(dense, embedding_dim),
        "sparse_vector": vespa_sparse_tensor(sparse),
        "ontology_concepts": [
            sanitize_vespa_string(cid) for cid in ontology_concepts if cid
        ],
    }
    if userspace_id:
        fields["userspace_id"] = sanitize_vespa_string(userspace_id)
    return fields


async def index_pipeline_document(
    document: dict[str, Any],
    *,
    vespa: VespaClient,
    target: IndexTarget = "both",
    user_space: str | None = None,
    ontology_payload: dict[str, Any] | None = None,
    dataset: str | None = None,
    nlp_ms: float = 0.0,
    model_id: str | None = None,
) -> IndexDocumentResult:
    """Index golden chunks into ``global`` and/or ``user`` Vespa schemas.

    Args:
        document: Pipeline JSON with ``golden_chunks``.
        vespa: Connected Vespa client.
        target: ``global`` | ``user`` | ``both``.
        user_space: Required for ``user`` / ``both``.
        ontology_payload: Optional external business ontology.
        dataset: Dataset name for ontology auto-load.
        nlp_ms: Upstream NLP timing.
        model_id: Optional local model path (default ``resources/modeling/net/bge-m3``).

    Returns:
        Document/passage counts and timings.
    """
    from thot.tools.search.user_space import resolve_vespa_user_space
    from thot.tools.search.vespa_client import normalize_user_space

    t0 = time.perf_counter()
    rag = load_rag_config()
    embedding_dim = int(rag.models.embedding_dim or BGE_M3_DENSE_DIM)
    model = model_id or None  # resolve via resources/modeling/net/bge-m3

    source_doc_id = document.get("source_doc_id") or document.get("source")
    if not source_doc_id:
        raise KeyError("source_doc_id required before indexing")
    document = dict(document)
    document["source_doc_id"] = str(source_doc_id)
    document = ensure_golden_chunks_for_index(document)

    if rag.dual_hybrid.business_ontology.index_enabled:
        resolved, resolved_ds = resolve_index_ontology_payload(
            document, dataset=dataset, ontology_payload=ontology_payload
        )
        if resolved_ds and not document.get("dataset"):
            document["dataset"] = resolved_ds
        if resolved:
            document = annotate_document_with_business_ontology(
                document, resolved
            )
            ontology_payload = resolved
    else:
        ontology_payload = None

    chunks: list[dict[str, Any]] = []
    texts: list[str] = []
    for chunk in document.get("golden_chunks") or []:
        text = chunk_embedding_text(chunk)
        if not chunk.get("chunk_id") or not text:
            continue
        chunks.append(chunk)
        texts.append(text)
    if not chunks:
        timings = IndexTimings(
            nlp_ms=float(nlp_ms),
            total_ms=(time.perf_counter() - t0) * 1000,
        )
        return IndexDocumentResult(1, 0, timings)

    t_emb = time.perf_counter()
    embeddings = await asyncio.to_thread(
        encode_texts, texts, model_id=model, dense_dim=embedding_dim
    )
    embed_ms = (time.perf_counter() - t_emb) * 1000

    space = normalize_user_space(user_space or resolve_vespa_user_space(None))
    t_vespa = time.perf_counter()
    written = 0
    dump_passages: list[dict[str, Any]] = []
    for chunk, emb in zip(chunks, embeddings, strict=True):
        concepts, expansion_labels = _ontology_fields_for_chunk(
            chunk, document, ontology_payload
        )
        passage_id = str(chunk.get("chunk_id"))
        chunk_text = chunk_embedding_text(chunk) or str(
            chunk.get("text_raw") or ""
        )
        # Pure BGE-M3 sparse (no content/ontology merge — BM25 + attributes
        # cover lexical/ontology; enrichment previously hurt SciFact).
        sparse = emb.sparse
        if target in ("global", "both"):
            fields = _passage_fields(
                chunk=chunk,
                document=document,
                dense=emb.dense,
                sparse=sparse,
                ontology_concepts=concepts,
                embedding_dim=embedding_dim,
            )
            await vespa.upsert_global_passage(fields, passage_id)
        if target in ("user", "both"):
            fields = _passage_fields(
                chunk=chunk,
                document=document,
                dense=emb.dense,
                sparse=sparse,
                ontology_concepts=concepts,
                embedding_dim=embedding_dim,
                userspace_id=space,
            )
            await vespa.upsert_user_passage(
                fields, passage_id, user_space=space
            )
        dump_passages.append(
            {
                "chunk_id": passage_id,
                "chunk": chunk_text,
                "document_ref": str(source_doc_id),
                "sparse_vector": dict(sparse),
                "ontology_concepts": list(concepts),
                "expansion_labels": list(expansion_labels),
            }
        )
        written += 1
    vespa_ms = (time.perf_counter() - t_vespa) * 1000

    dump_cfg = rag.dual_hybrid.index_dump
    dump_path = _write_index_dump(
        dump=dump_cfg,
        source_ref=str(source_doc_id),
        dataset=str(dataset or document.get("dataset") or "") or None,
        passages=dump_passages,
        document=document,
    )
    if dump_path is not None:
        LOGGER.debug("Index dump written %s", dump_path)

    timings = IndexTimings(
        nlp_ms=round(float(nlp_ms), 3),
        embed_ms=round(embed_ms, 3),
        vespa_ms=round(vespa_ms, 3),
        total_ms=round((time.perf_counter() - t0) * 1000, 3),
    )
    LOGGER.info(
        "Indexed source=%s passages=%d target=%s embed_ms=%.1f vespa_ms=%.1f",
        source_doc_id,
        written,
        target,
        timings.embed_ms,
        timings.vespa_ms,
    )
    return IndexDocumentResult(1, written, timings)
