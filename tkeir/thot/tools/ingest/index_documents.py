# -*- coding: utf-8 -*-
"""Title: Index documents CLI (compat entrypoint).

Delegates to :mod:`thot.tools.ingest.index_passages` (global/user schemas).

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
from typing import Any

from thot.tools.ingest.index_passages import (
    ensure_golden_chunks_for_index,
    index_pipeline_document,
)
from thot.tools.search.vespa_client import VespaClient

LOGGER = logging.getLogger(__name__)

# Re-export for tests / callers that imported the helper from here.
_ensure_golden_chunks_for_index = ensure_golden_chunks_for_index


def _load_pipeline_document(path: Path) -> dict[str, Any]:
    """Load one pipeline JSON file.

    Example:
        >>> import tempfile, json
        >>> from pathlib import Path
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     path = Path(temp_dir) / "doc.json"
        ...     _ = path.write_text(json.dumps({"title": "x"}), encoding="utf-8")
        ...     _load_pipeline_document(path)["title"]
        'x'
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object in {path}")
    return payload


async def index_directory(
    input_dir: Path,
    *,
    pattern: str,
    vespa: VespaClient,
    target: str = "both",
    max_workers: int | None = None,
) -> tuple[int, int]:
    """Index every pipeline file matching ``pattern`` under ``input_dir``.

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.index_documents import index_directory
        >>> inspect.iscoroutinefunction(index_directory)
        True
    """
    del max_workers  # sequential: FlagEmbedding + Vespa
    paths = sorted(input_dir.glob(pattern))
    if not paths:
        LOGGER.warning(
            "No pipeline files found in %s (%s)", input_dir, pattern
        )
        return 0, 0

    document_count = 0
    passage_count = 0
    for path in paths:
        try:
            document = _load_pipeline_document(path)
            result = await index_pipeline_document(
                document,
                vespa=vespa,
                target=target,  # type: ignore[arg-type]
            )
            document_count += result.document_count
            passage_count += result.passage_count
            LOGGER.info(
                "Indexed %s (%d passages) total_ms=%.1f",
                path.name,
                result.passage_count,
                result.timings.total_ms,
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to index %s", path)
    return document_count, passage_count


async def _async_main(args: argparse.Namespace) -> int:
    """CLI async entry: index pipeline files from ``args.input``.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_async_main)
        True
    """
    from thot.core.StructuredLogging import configure_text_logging

    configure_text_logging(level=logging.INFO, force=True)
    input_dir = Path(args.input).resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    async with VespaClient() as vespa:
        if not await vespa.health():
            raise SystemExit("Vespa is not ready. Run: make bootstrap")
        documents, passages = await index_directory(
            input_dir,
            pattern=args.pattern,
            vespa=vespa,
            target=args.target,
        )
    LOGGER.info(
        "Indexing complete: %d document(s), %d passage(s)",
        documents,
        passages,
    )
    return 0


def main() -> None:
    """Parse CLI arguments and index pipeline files into Vespa.

    Example:
        >>> from thot.tools.ingest.index_documents import main
        >>> callable(main)
        True
    """
    parser = argparse.ArgumentParser(
        description="Index pipeline JSON into Vespa global/user passages"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Directory of pipeline JSON files",
    )
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Glob under --input (default: *.json)",
    )
    parser.add_argument(
        "--target",
        choices=("global", "user", "both"),
        default="both",
        help="Vespa schema target (default: both)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Ignored (kept for CLI compatibility)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    main()
