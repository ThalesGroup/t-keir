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


    Example:
        >>> from thot.tools.ingest.index_passages import ensure_golden_chunks_for_index
        >>> doc = ensure_golden_chunks_for_index({"source_doc_id": "d1", "title": "Hi"})
        >>> doc["golden_chunks"][0]["text_raw"]
        'Hi'
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
        LOGGER.warning(
            "No content/title to synthesize chunk for %s", source_id
        )
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
    *,
    service: Any | None = None,
) -> tuple[list[str], list[str], list[dict[str, Any]], Any]:
    """Return concept ids, expansion labels, relation structs, catalog delta.

    Concept ids feed Vespa ``ontology_concepts`` / ``ontology_concept_ids``.
    Expansion labels are kept for dumps / analysis only — sparse vectors stay
    pure BGE-M3.

    Example:
        >>> chunk = {"text_raw": "Maritime analytics"}
        >>> document = {
        ...     "document_ontology": {"json_ld": '[{"identifier": "MARITIME"}]'},
        ... }
        >>> concepts, _labels, _rels, _cat = _ontology_fields_for_chunk(
        ...     chunk, document, None
        ... )
        >>> "MARITIME" in concepts
        True
    """
    from thot.ontology.service import OntologyService
    from thot.ontology.vespa import chunk_ontology_vespa_fields

    svc = service or OntologyService.from_business_payload(ontology_payload)
    enrichment = svc.enrich_chunk(
        chunk, document, ontology_payload=ontology_payload
    )
    vespa_fields = chunk_ontology_vespa_fields(
        enrichment.concept_ids,
        enrichment.relations,
        max_concepts=svc.max_concepts,
        max_relations=svc.max_relations,
    )
    return (
        list(vespa_fields["ontology_concept_ids"]),
        list(enrichment.expansion_labels)[:96],
        list(vespa_fields["ontology_relations"]),
        enrichment.catalog,
    )


def _ontology_concept_list(
    chunk: dict[str, Any],
    document: dict[str, Any],
    ontology_payload: dict[str, Any] | None,
) -> list[str]:
    """Build ``ontology_concepts`` from SVO / json_ld / external ontology.

    Example:
        >>> chunk = {"text_raw": "Maritime analytics"}
        >>> document = {
        ...     "document_ontology": {"json_ld": '[{"identifier": "MARITIME"}]'},
        ... }
        >>> "MARITIME" in _ontology_concept_list(chunk, document, None)
        True
    """
    concepts, _labels, _rels, _cat = _ontology_fields_for_chunk(
        chunk, document, ontology_payload
    )
    return concepts


def _resolve_index_dump_dir(dump: IndexDumpConfig) -> Path:
    """Resolve dump directory (absolute, or relative to repo root).

    Example:
        >>> _resolve_index_dump_dir(IndexDumpConfig(path="reports/index_dumps")).name
        'index_dumps'
    """
    raw = (
        dump.path or IndexDumpConfig().path
    ).strip() or IndexDumpConfig().path
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(repo_root()) / path
    return path


def _safe_dump_stem(source_ref: str) -> str:
    """Filesystem-safe stem from a document / BEIR source ref.

    Example:
        >>> _safe_dump_stem("beir/scifact/doc-1")
        'beir_scifact_doc-1'
    """
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

    Example:
        >>> import tempfile
        >>> from thot.tools.search.dual_hybrid_config import IndexDumpConfig
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     dump = IndexDumpConfig(enabled=True, path=temp_dir)
        ...     path = _write_index_dump(
        ...         dump=dump,
        ...         source_ref="doc1",
        ...         dataset=None,
        ...         passages=[{"chunk_id": "c1"}],
        ...     )
        ...     path is not None and path.is_file()
        True
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
    ontology_relations: list[dict[str, Any]] | None = None,
    parent_doc_id: str = "",
) -> dict[str, Any]:
    """Build Vespa passage field dict for one golden chunk.

    ``parent_doc_id`` is the indexed ``corpus_doc`` key this chunk was
    extracted from.

    Example:
        >>> fields = _passage_fields(
        ...     chunk={"chunk_id": "c1", "text_raw": "hello"},
        ...     document={"source_doc_id": "doc1"},
        ...     dense=[0.1, 0.2],
        ...     sparse={"3": 0.5},
        ...     ontology_concepts=["c1"],
        ...     embedding_dim=2,
        ...     parent_doc_id="abc",
        ... )
        >>> fields["source_ref"]
        'doc1'
        >>> fields["parent_doc_id"]
        'abc'
        >>> fields["chunk_id"]
        'c1'
        >>> fields["freshness_ttl_seconds"]
        0
    """
    text = chunk_embedding_text(chunk) or str(chunk.get("text_raw") or "")
    source_ref = str(
        document.get("source_doc_id")
        or document.get("source")
        or chunk.get("parent_doc_id")
        or ""
    )
    from thot.ontology.model import OntologyRelation
    from thot.ontology.vespa import chunk_ontology_vespa_fields

    rel_models = [
        OntologyRelation(
            subject_id=str(row.get("subject_id") or ""),
            predicate_id=str(row.get("predicate_id") or ""),
            object_id=str(row.get("object_id") or ""),
            confidence=float(row.get("confidence") or 1.0),
        )
        for row in ontology_relations or []
        if row
    ]
    extra = chunk_ontology_vespa_fields(
        ontology_concepts,
        rel_models,
        max_concepts=max(len(ontology_concepts), 1),
        max_relations=max(len(rel_models), 1),
    )
    chunk_id = str(chunk.get("chunk_id") or "")
    indexed_parent = parent_doc_id or ""
    if not indexed_parent and source_ref:
        from thot.tools.ingest.document_index import corpus_doc_docid

        indexed_parent = corpus_doc_docid(source_ref)
    fields: dict[str, Any] = {
        "source_ref": sanitize_vespa_string(source_ref),
        "parent_doc_id": sanitize_vespa_string(indexed_parent),
        "chunk_id": sanitize_vespa_string(chunk_id),
        "chunk_text": sanitize_vespa_string(text),
        "dense_vector": vespa_dense_tensor(dense, embedding_dim),
        "sparse_vector": vespa_sparse_tensor(sparse),
        "ontology_concepts": [
            sanitize_vespa_string(cid)
            for cid in extra["ontology_concepts"]
            if cid
        ],
        "ontology_concept_ids": [
            sanitize_vespa_string(cid)
            for cid in extra["ontology_concept_ids"]
            if cid
        ],
        "ontology_relations": list(extra["ontology_relations"]),
        "ontology_rel_keys": [
            sanitize_vespa_string(key) for key in extra["ontology_rel_keys"]
        ],
        # Explicit keep: unset int attributes can confuse GC selection on
        # the ``global`` cluster (ontology_concept has no TTL selection).
        "freshness_ttl_seconds": 0,
        "pinned": False,
        "doc_timestamp": int(time.time()),
        "source_type": "ingest",
    }
    if userspace_id:
        fields["userspace_id"] = sanitize_vespa_string(userspace_id)
    return fields


async def _index_corpus_doc(
    vespa: VespaClient,
    *,
    document: dict[str, Any],
    source_ref: str,
    parent_doc_id: str,
    chunks: list[dict[str, Any]],
    embeddings: list[Any],
    embedding_dim: int,
    concept_ids: list[str],
    rel_keys: list[str],
    cfg: Any,
) -> None:
    """Write one ``corpus_doc`` row (classical index + tags + simhash).

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.index_passages import _index_corpus_doc
        >>> inspect.iscoroutinefunction(_index_corpus_doc)
        True
    """
    from thot.tools.ingest.document_index import (
        DocumentIndexMeta,
        build_corpus_doc_fields,
        mean_dense,
        merge_sparse,
        pick_near_duplicate,
    )

    chunk_texts = [
        chunk_embedding_text(chunk) or str(chunk.get("text_raw") or "")
        for chunk in chunks
    ]
    meta = DocumentIndexMeta.from_document(
        document,
        chunk_texts,
        prefix_bits=int(cfg.simhash_prefix_bits),
        max_doc_text_chars=int(cfg.max_doc_text_chars),
    )
    duplicate_of = ""
    try:
        neighbors = await vespa.find_corpus_docs_by_simhash_prefix(
            meta.simhash_prefix
        )
        duplicate_of = pick_near_duplicate(
            meta.simhash,
            neighbors,
            source_ref=source_ref,
            max_hamming=int(cfg.simhash_max_hamming),
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("simhash neighbor lookup skipped: %s", exc)
    dense = mean_dense([list(emb.dense) for emb in embeddings], embedding_dim)
    fields = build_corpus_doc_fields(
        meta,
        dense=dense,
        sparse=merge_sparse([dict(emb.sparse) for emb in embeddings]),
        embedding_dim=embedding_dim,
        chunk_ids=[str(chunk.get("chunk_id") or "") for chunk in chunks],
        ontology_concept_ids=concept_ids,
        ontology_rel_keys=rel_keys,
        duplicate_of=duplicate_of,
    )
    await vespa.upsert_corpus_doc(fields, parent_doc_id)
    if duplicate_of:
        LOGGER.info(
            "corpus_doc near-duplicate source=%s of=%s",
            source_ref,
            duplicate_of,
        )


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


    Example:
        >>> import inspect
        >>> from thot.tools.ingest.index_passages import index_pipeline_document
        >>> inspect.iscoroutinefunction(index_pipeline_document)
        True
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

    from thot.ontology.catalog_sync import sync_corpus_ontology
    from thot.ontology.identity import relation_key
    from thot.ontology.model import Ontology
    from thot.ontology.service import OntologyService
    from thot.tools.ingest.document_index import corpus_doc_docid

    layer = rag.dual_hybrid.ontology_layer
    doc_index_cfg = rag.dual_hybrid.document_index
    ont_service = OntologyService.from_business_payload(
        ontology_payload,
        json_structural=bool(layer.json_structural_concepts),
        max_concepts=int(layer.max_concepts_per_chunk),
        max_relations=int(layer.max_relations_per_chunk),
    )
    space = normalize_user_space(user_space or resolve_vespa_user_space(None))
    parent_doc_id = corpus_doc_docid(str(source_doc_id))

    merged_catalog = Ontology()
    prepared = []
    for chunk, emb in zip(chunks, embeddings, strict=True):
        concepts, expansion_labels, relations, catalog = (
            _ontology_fields_for_chunk(
                chunk,
                document,
                ontology_payload,
                service=ont_service,
            )
        )
        merged_catalog = merged_catalog.extend(catalog)
        prepared.append((chunk, emb, concepts, expansion_labels, relations))

    t_vespa = time.perf_counter()
    if layer.index_concepts or layer.index_triples:
        try:
            await sync_corpus_ontology(
                vespa,
                merged_catalog,
                source_ref=str(source_doc_id),
                index_concepts=bool(layer.index_concepts),
                index_triples=bool(layer.index_triples),
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("corpus ontology catalog sync failed: %s", exc)

    written = 0
    dump_passages: list[dict[str, Any]] = []
    all_concept_ids: list[str] = []
    all_rel_keys: list[str] = []
    seen_concepts: set[str] = set()
    seen_rels: set[str] = set()
    for chunk, emb, concepts, expansion_labels, relations in prepared:
        passage_id = str(chunk.get("chunk_id"))
        chunk_text = chunk_embedding_text(chunk) or str(
            chunk.get("text_raw") or ""
        )
        sparse = emb.sparse
        if target in ("global", "both"):
            fields = _passage_fields(
                chunk=chunk,
                document=document,
                dense=emb.dense,
                sparse=sparse,
                ontology_concepts=concepts,
                embedding_dim=embedding_dim,
                ontology_relations=relations,
                parent_doc_id=parent_doc_id,
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
                ontology_relations=relations,
                parent_doc_id=parent_doc_id,
            )
            await vespa.upsert_user_passage(
                fields, passage_id, user_space=space
            )
        for cid in concepts:
            key = str(cid).strip()
            folded = key.casefold()
            if key and folded not in seen_concepts:
                seen_concepts.add(folded)
                all_concept_ids.append(key)
        for row in relations:
            rel_key = relation_key(
                str(row.get("subject_id") or ""),
                str(row.get("predicate_id") or ""),
                str(row.get("object_id") or ""),
            )
            if rel_key not in seen_rels and "|" in rel_key:
                seen_rels.add(rel_key)
                all_rel_keys.append(rel_key)
        dump_passages.append(
            {
                "chunk_id": passage_id,
                "chunk": chunk_text,
                "document_ref": str(source_doc_id),
                "parent_doc_id": parent_doc_id,
                "sparse_vector": dict(sparse),
                "ontology_concepts": list(concepts),
                "ontology_concept_ids": list(concepts),
                "ontology_relations": list(relations),
                "expansion_labels": list(expansion_labels),
            }
        )
        written += 1

    if doc_index_cfg.enabled and target in ("global", "both") and written:
        try:
            await _index_corpus_doc(
                vespa,
                document=document,
                source_ref=str(source_doc_id),
                parent_doc_id=parent_doc_id,
                chunks=chunks,
                embeddings=embeddings,
                embedding_dim=embedding_dim,
                concept_ids=all_concept_ids[: doc_index_cfg.max_concept_ids],
                rel_keys=all_rel_keys,
                cfg=doc_index_cfg,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "corpus_doc index failed source=%s: %s",
                source_doc_id,
                exc,
            )

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
