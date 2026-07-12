# -*- coding: utf-8 -*-
"""Index pipeline JSON documents into Vespa document and chunk schemas."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from thot.tools.search.llm_wrapper import UnifiedLLMWrapper
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
    return {
        "source_doc_id": sanitize_vespa_string(document["source_doc_id"]),
        "title": sanitize_vespa_string(document.get("title") or ""),
        "content": sanitize_vespa_strings(document.get("content") or []),
        "rdf_graph_serialized": sanitize_vespa_string(
            ontology.get("rdf_graph_serialized", "")
        ),
        "shacl_status": sanitize_vespa_string(
            ontology.get("shacl_status", "")
        ),
    }


async def index_pipeline_document(
    document: dict[str, Any],
    *,
    vespa: VespaClient,
    llm: UnifiedLLMWrapper,
) -> tuple[int, int]:
    """Index one pipeline document and its golden chunks into Vespa.

    Args:
        document: Parsed pipeline JSON with ``golden_chunks``.
        vespa: Connected Vespa client.
        llm: Embedding provider used for chunk and question vectors.

    Returns:
        Tuple ``(document_count, chunk_count)`` where ``document_count`` is
        always ``1`` when indexing succeeds.

    Example:
        >>> import asyncio
        >>> from thot.tools.search.index_documents import index_pipeline_document
        >>> asyncio.run(index_pipeline_document({}, vespa=None, llm=None))  # doctest: +SKIP
    """
    source_doc_id = document["source_doc_id"]
    await vespa.upsert_document(_document_fields(document), source_doc_id)
    parent_ref = document_vespa_id(source_doc_id)

    chunk_count = 0
    for chunk in document.get("golden_chunks") or []:
        chunk_id = chunk.get("chunk_id")
        index_text = chunk_embedding_text(chunk)
        if not chunk_id or not index_text:
            continue

        chunk_embedding = await llm.embed(index_text)
        question_texts = [
            (item.get("question_text") or "").strip()
            for item in chunk.get("synthetic_questions") or []
        ]
        question_texts = [text for text in question_texts if text]
        question_embeddings = (
            await llm.embed_batch(question_texts) if question_texts else []
        )

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
        await vespa.upsert_chunk(fields, chunk_id)
        chunk_count += 1

    return 1, chunk_count


async def index_directory(
    input_dir: Path,
    *,
    pattern: str,
    vespa: VespaClient,
    llm: UnifiedLLMWrapper,
) -> tuple[int, int]:
    """Index every pipeline file matching ``pattern`` under ``input_dir``.

    Args:
        input_dir: Directory containing pipeline JSON files.
        pattern: Glob pattern passed to :meth:`Path.glob`.
        vespa: Connected Vespa client.
        llm: Embedding provider used for chunk and question vectors.

    Returns:
        Tuple ``(document_count, chunk_count)`` aggregated across all files.

    Example:
        >>> import asyncio
        >>> from pathlib import Path
        >>> from thot.tools.search.index_documents import index_directory
        >>> asyncio.run(index_directory(Path("."), pattern="*.json", vespa=None, llm=None))  # doctest: +SKIP
    """
    document_count = 0
    chunk_count = 0
    paths = sorted(input_dir.glob(pattern))
    if not paths:
        LOGGER.warning(
            "No pipeline files found in %s (%s)", input_dir, pattern
        )

    for path in paths:
        try:
            pipeline_document = _load_pipeline_document(path)
            docs, chunks = await index_pipeline_document(
                pipeline_document,
                vespa=vespa,
                llm=llm,
            )
            document_count += docs
            chunk_count += chunks
            LOGGER.info(
                "Indexed %s (%d chunks)",
                path.name,
                chunks,
            )
        except Exception:
            LOGGER.exception("Failed to index %s", path)
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
            "Using provider=%s embedding_model=%s",
            llm._config.provider.value,
            llm._config.embedding_model,
        )
        if not await vespa.health():
            raise SystemExit(
                "Vespa is not ready (config server, deployed application, "
                "or document API). Run: cd vespa && make bootstrap"
            )
        documents, chunks = await index_directory(
            input_dir,
            pattern=args.pattern,
            vespa=vespa,
            llm=llm,
        )
    LOGGER.info(
        "Indexing complete: %d document(s), %d chunk(s)",
        documents,
        chunks,
    )
    if pipeline_paths and documents == 0:
        raise SystemExit(
            f"Indexing failed: 0/{len(pipeline_paths)} documents indexed. "
            "Check Vespa logs (`cd vespa && make logs`) and the embedding "
            "provider (default: Ollama with bge-m3)."
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
    raise SystemExit(asyncio.run(_async_main(parser.parse_args())))


if __name__ == "__main__":
    main()
