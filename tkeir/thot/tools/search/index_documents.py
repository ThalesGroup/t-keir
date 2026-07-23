# -*- coding: utf-8 -*-
"""Title: Index documents

Index pipeline JSON documents into Vespa document and chunk schemas.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Protocol

from thot.core.LlmWrapper import UnifiedLLMWrapper
from thot.tools.search.rag_config import load_rag_config
from thot.tools.search.vespa_client import (
    VespaClient,
    build_chunk_tensor,
    build_questions_tensor,
    chunk_embedding_text,
    document_vespa_id,
    sanitize_vespa_string,
    sanitize_vespa_strings,
)

LOGGER = logging.getLogger(__name__)

# Serialize embedding calls: concurrent Ollama/vLLM requests stall easily.
_EMBED_LOCK = asyncio.Lock()


class EmbeddingProvider(Protocol):
    """Minimal embedding surface used while indexing into Vespa."""

    async def embed(self, text: str) -> list[float]:
        """Embed one text.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(EmbeddingProvider.embed)
            True
        """

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(EmbeddingProvider.embed_batch)
            True
        """


def _load_pipeline_document(path: Path) -> dict[str, Any]:
    """Load and validate a pipeline JSON document from disk.

    Args:
        path: Path to a ``*.pipeline.json`` file.

    Returns:
        Parsed pipeline document with required ``source_doc_id`` and ``content``.

    Raises:
        ValueError: When required fields are missing.

    Example:
        >>> import json
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tools.search.index_documents import _load_pipeline_document
        >>> with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        ...     json.dump({"source_doc_id": "doc", "content": ["hi"]}, handle)
        ...     path = Path(handle.name)
        >>> try:
        ...     _load_pipeline_document(path)["source_doc_id"]
        ... finally:
        ...     path.unlink()
        'doc'
    """
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    if "source_doc_id" not in document:
        raise ValueError(f"Missing source_doc_id in {path}")
    if "content" not in document:
        raise ValueError(f"Missing content in {path}")
    return document


def _document_fields(document: dict[str, Any]) -> dict[str, Any]:
    """Map a pipeline document to Vespa parent-document field names.

    Args:
        document: Pipeline output containing ``source_doc_id``, ``title``,
            ``content``, and optional ``document_ontology``.

    Returns:
        Sanitized field dict ready for :meth:`VespaClient.upsert_document`.

    Example:
        >>> from thot.tools.search.index_documents import _document_fields
        >>> fields = _document_fields({
        ...     "source_doc_id": "file://doc.pdf",
        ...     "title": "Doc",
        ...     "content": ["hello"],
        ...     "document_ontology": {"shacl_status": "ok"},
        ... })
        >>> fields["title"]
        'Doc'
    """
    ontology = document.get("document_ontology") or {}
    json_ld = ontology.get("json_ld") or ontology.get(
        "rdf_graph_serialized", ""
    )
    return {
        "source_doc_id": sanitize_vespa_string(document["source_doc_id"]),
        "title": sanitize_vespa_string(document.get("title") or ""),
        "content": sanitize_vespa_strings(document.get("content") or []),
        "json_ld": sanitize_vespa_string(json_ld),
        "shacl_status": sanitize_vespa_string(
            ontology.get("shacl_status", "")
        ),
    }


async def _embed_batch_locked(
    llm: EmbeddingProvider, texts: list[str]
) -> list[list[float]]:
    """Run ``embed_batch`` under the process-wide embedding lock."""
    if not texts:
        return []
    async with _EMBED_LOCK:
        return await llm.embed_batch(texts)


async def _upsert_chunk_fields(
    *,
    chunk: dict[str, Any],
    chunk_embedding: list[float],
    question_embeddings: list[list[float]],
    document: dict[str, Any],
    parent_ref: str,
    vespa: VespaClient,
    user_space: str,
) -> bool:
    """Upsert one chunk (embeddings already computed). Returns True on success."""
    chunk_id = chunk.get("chunk_id")
    index_text = chunk_embedding_text(chunk)
    if not chunk_id or not index_text:
        return False

    fields = {
        "chunk_id": sanitize_vespa_string(chunk_id),
        "doc_ref": parent_ref,
        "parent_title": sanitize_vespa_string(document.get("title") or ""),
        "parent_content": sanitize_vespa_strings(
            document.get("content") or []
        ),
        "text_raw": index_text,
        "chunk_embedding": build_chunk_tensor(
            chunk_embedding,
            vespa.config.embedding_dim,
        ),
        "questions_embeddings": build_questions_tensor(
            question_embeddings,
            vespa.config.embedding_dim,
        ),
    }
    await vespa.upsert_chunk(fields, chunk_id, user_space=user_space)
    return True


def _collect_indexable_chunks(
    document: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[list[str]]]:
    """Collect chunks with ids/text and their synthetic question groups."""
    ready_chunks: list[dict[str, Any]] = []
    index_texts: list[str] = []
    question_groups: list[list[str]] = []
    for chunk in document.get("golden_chunks") or []:
        chunk_id = chunk.get("chunk_id")
        index_text = chunk_embedding_text(chunk)
        if not chunk_id or not index_text:
            continue
        ready_chunks.append(chunk)
        index_texts.append(index_text)
        question_texts = [
            (item.get("question_text") or "").strip()
            for item in chunk.get("synthetic_questions") or []
        ]
        question_groups.append([text for text in question_texts if text])
    return ready_chunks, index_texts, question_groups


def _split_question_embeddings(
    flat_question_embeddings: list[list[float]],
    question_groups: list[list[str]],
) -> list[list[list[float]]]:
    """Partition flat question embeddings into per-chunk groups."""
    question_embeddings_by_chunk: list[list[list[float]]] = []
    cursor = 0
    for group in question_groups:
        n = len(group)
        question_embeddings_by_chunk.append(
            flat_question_embeddings[cursor : cursor + n]
        )
        cursor += n
    return question_embeddings_by_chunk


async def index_pipeline_document(
    document: dict[str, Any],
    *,
    vespa: VespaClient,
    llm: EmbeddingProvider,
    max_chunk_workers: int | None = None,
    user_space: str | None = None,
) -> tuple[int, int]:
    """Index one pipeline document and its golden chunks into Vespa.

    Embeddings are batched and serialized (safe for Ollama). Only Vespa
    chunk upserts may run concurrently (``vespa.concurrency.chunk_workers``).

    Args:
        document: Parsed pipeline JSON with ``golden_chunks``.
        vespa: Connected Vespa client.
        llm: Embedding provider used for chunk and question vectors.
        max_chunk_workers: Optional override for parallel chunk upserts.
        user_space: Streaming group (Keycloak principal); defaults to config.

    Returns:
        Tuple ``(document_count, chunk_count)`` where ``document_count`` is
        always ``1`` when indexing succeeds.

    Example:
        >>> import asyncio
        >>> from thot.tools.search.index_documents import index_pipeline_document
        >>> asyncio.run(index_pipeline_document({}, vespa=None, llm=None))  # doctest: +SKIP
    """
    from thot.tools.search.user_space import resolve_vespa_user_space
    from thot.tools.search.vespa_client import normalize_user_space

    source_doc_id = document.get("source_doc_id") or document.get("source")
    if not source_doc_id:
        raise KeyError(
            "source_doc_id (or source) is required on pipeline documents "
            "before Vespa indexing"
        )
    source_doc_id = str(source_doc_id)
    document["source_doc_id"] = source_doc_id
    space = normalize_user_space(user_space or resolve_vespa_user_space(None))
    await vespa.upsert_document(
        _document_fields(document), source_doc_id, user_space=space
    )
    parent_ref = document_vespa_id(source_doc_id, user_space=space)

    ready_chunks, index_texts, question_groups = _collect_indexable_chunks(
        document
    )
    if not ready_chunks:
        return 1, 0

    chunk_embeddings = await _embed_batch_locked(llm, index_texts)

    flat_questions = [text for group in question_groups for text in group]
    flat_question_embeddings = await _embed_batch_locked(llm, flat_questions)
    question_embeddings_by_chunk = _split_question_embeddings(
        flat_question_embeddings, question_groups
    )

    workers = max(
        1,
        int(
            max_chunk_workers
            if max_chunk_workers is not None
            else load_rag_config().vespa.concurrency.chunk_workers
        ),
    )
    semaphore = asyncio.Semaphore(workers)

    async def _one(
        chunk: dict[str, Any],
        embedding: list[float],
        question_embeddings: list[list[float]],
    ) -> bool:
        async with semaphore:
            return await _upsert_chunk_fields(
                chunk=chunk,
                chunk_embedding=embedding,
                question_embeddings=question_embeddings,
                document=document,
                parent_ref=parent_ref,
                vespa=vespa,
                user_space=space,
            )

    outcomes = await asyncio.gather(
        *(
            _one(chunk, embedding, q_embs)
            for chunk, embedding, q_embs in zip(
                ready_chunks,
                chunk_embeddings,
                question_embeddings_by_chunk,
                strict=True,
            )
        )
    )
    return 1, sum(1 for ok in outcomes if ok)


async def index_directory(
    input_dir: Path,
    *,
    pattern: str,
    vespa: VespaClient,
    llm: EmbeddingProvider,
    max_workers: int | None = None,
) -> tuple[int, int]:
    """Index every pipeline file matching ``pattern`` under ``input_dir``.

    Documents are processed with a bounded worker pool
    (``vespa.concurrency.index_workers``). Embeddings stay serialized.

    Args:
        input_dir: Directory containing pipeline JSON files.
        pattern: Glob pattern passed to :meth:`Path.glob`.
        vespa: Connected Vespa client.
        llm: Embedding provider used for chunk and question vectors.
        max_workers: Optional override for parallel document indexing.

    Returns:
        Tuple ``(document_count, chunk_count)`` aggregated across all files.

    Example:
        >>> import asyncio
        >>> from pathlib import Path
        >>> from thot.tools.search.index_documents import index_directory
        >>> asyncio.run(index_directory(Path("."), pattern="*.json", vespa=None, llm=None))  # doctest: +SKIP
    """
    paths = sorted(input_dir.glob(pattern))
    if not paths:
        LOGGER.warning(
            "No pipeline files found in %s (%s)", input_dir, pattern
        )
        return 0, 0

    workers = max(
        1,
        int(
            max_workers
            if max_workers is not None
            else load_rag_config().vespa.concurrency.index_workers
        ),
    )
    semaphore = asyncio.Semaphore(workers)

    async def _one(path: Path) -> tuple[int, int]:
        async with semaphore:
            try:
                pipeline_document = _load_pipeline_document(path)
                docs, chunks = await index_pipeline_document(
                    pipeline_document,
                    vespa=vespa,
                    llm=llm,
                )
                LOGGER.info("Indexed %s (%d chunks)", path.name, chunks)
                return docs, chunks
            except Exception:
                LOGGER.exception("Failed to index %s", path)
                return 0, 0

    # Bounded concurrency without scheduling the entire corpus at once when
    # workers==1 (sequential). For workers>1, gather is fine for typical dirs.
    results = await asyncio.gather(*(_one(path) for path in paths))
    document_count = sum(docs for docs, _ in results)
    chunk_count = sum(chunks for _, chunks in results)
    return document_count, chunk_count


async def _async_main(args: argparse.Namespace) -> int:
    """Run the indexing CLI workflow asynchronously.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Process exit code (``0`` on success).

    Example:
        >>> import asyncio
        >>> from thot.tools.search.index_documents import _async_main
        >>> asyncio.run(_async_main(None))  # doctest: +SKIP
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    input_dir = Path(args.input).resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    pipeline_paths = sorted(input_dir.glob(args.pattern))

    async with UnifiedLLMWrapper() as llm, VespaClient() as vespa:
        LOGGER.info(
            "Using provider=%s embedding_model=%s ollama_base_url=%s",
            llm._config.provider.value,
            llm._config.embedding_model,
            llm._config.ollama_base_url,
        )
        await llm.verify_provider(pull_missing=True, include_reranker=False)
        if not await vespa.health():
            raise SystemExit(
                "Vespa is not ready (config server, deployed application, "
                "or document API). Run: make bootstrap"
            )
        documents, chunks = await index_directory(
            input_dir,
            pattern=args.pattern,
            vespa=vespa,
            llm=llm,
            max_workers=args.workers,
        )
    LOGGER.info(
        "Indexing complete: %d document(s), %d chunk(s)",
        documents,
        chunks,
    )
    if pipeline_paths and documents == 0:
        raise SystemExit(
            f"Indexing failed: 0/{len(pipeline_paths)} documents indexed. "
            "Check Vespa logs (`make logs`) and the embedding "
            "provider (default: Ollama with bge-m3 at "
            "OLLAMA_BASE_URL, e.g. http://host.docker.internal:11434 in devcontainer)."
        )
    return 0


def main() -> None:
    """Parse CLI arguments and index pipeline files into Vespa.

    Example:
        >>> from thot.tools.search.index_documents import main
        >>> main()  # doctest: +SKIP
    """
    parser = argparse.ArgumentParser(
        description="Index pipeline JSON files into Vespa document/chunk schemas.",
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Directory containing *.pipeline.json files",
    )
    parser.add_argument(
        "--pattern",
        default="*.pipeline.json",
        help="Glob pattern for pipeline files (default: *.pipeline.json)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel document workers (default: rag.yaml vespa.concurrency.index_workers)",
    )
    raise SystemExit(asyncio.run(_async_main(parser.parse_args())))


if __name__ == "__main__":
    main()
