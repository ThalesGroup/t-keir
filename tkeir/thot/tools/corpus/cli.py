"""Title: Generate a record-oriented corpus JSON from markdown

Runnable: ``python -m thot.tools.corpus`` or ``tkeir-corpus``.

Markdown-only trees compile directly. Mixed-format directories are
converted with :class:`UniversalConverter` into a parallel markdown
tree, then compiled to the same ``{dataset, records}`` JSON.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from thot.tools.corpus.builder import (
    corpus_from_markdown_dir,
    corpus_from_source_dir,
    write_record_corpus,
)
from thot.tools.corpus.convert_tree import (
    default_ocr_config,
    has_non_markdown_files,
)


def _load_dataset_extra(path: str | None) -> dict[str, Any]:
    """Load optional extra ``dataset`` fields from a JSON object file.

    Args:
        path: Path to a JSON object, or ``None``.

    Returns:
        Mapping merged into ``dataset`` (empty when ``path`` is None).

    Example:
        >>> _load_dataset_extra(None)
        {}
    """
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--dataset-json must contain a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    """CLI parser for markdown → record-oriented JSON.

    Returns:
        Configured argument parser.

    Example:
        >>> build_parser().prog
        'tkeir-corpus'
    """
    parser = argparse.ArgumentParser(
        prog="tkeir-corpus",
        description=(
            "Build a record-oriented corpus JSON "
            "({dataset, records}) from a markdown directory, or from a "
            "mixed-format tree converted with UniversalConverter. "
            "Each record has mandatory doc_id, title, and text "
            "(POST /ingest/json-records shape)."
        ),
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        required=True,
        help=(
            "Source directory: markdown, and/or any format "
            "UniversalConverter can read (PDF, Office, HTML, image, "
            "ZIP, JSON, CSV, …)"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output JSON path",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="dataset.name (default: input directory name)",
    )
    parser.add_argument(
        "--version",
        default="1.0.0",
        help="dataset.version (default: 1.0.0)",
    )
    parser.add_argument(
        "--note",
        default=None,
        help="dataset.note",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Primary dataset.languages entry (default: en)",
    )
    parser.add_argument(
        "--dataset-json",
        default=None,
        help="JSON object merged into dataset (name/count still set)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only read markdown in the top of --input-dir",
    )
    empty = parser.add_mutually_exclusive_group()
    empty.add_argument(
        "--skip-empty",
        action="store_true",
        help="Skip files whose text body is empty (default)",
    )
    empty.add_argument(
        "--keep-empty",
        action="store_true",
        help="Fail when a record has blank text instead of skipping it",
    )
    parser.add_argument(
        "-m",
        "--markdown-dir",
        default=None,
        help=(
            "Write the converted markdown tree here (mirrors --input-dir). "
            "Required for mixed-format sources unless you rely on the "
            "default <input>-markdown sibling"
        ),
    )
    parser.add_argument(
        "--convert",
        action="store_true",
        help=(
            "Force UniversalConverter even when --input-dir is already "
            "markdown-only"
        ),
    )
    parser.add_argument(
        "--skip-unknown",
        action="store_true",
        help="Skip files UniversalConverter classifies as unknown",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR / image analysis during conversion",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Conversion/compile threads (0=adaptive from CPU and file mix, "
            "1=sequential, N=fixed pool)"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-convert sources even when the markdown sidecar already exists"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate the corpus file. Returns a process exit code.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` on success, ``1`` on validation or I/O errors.

    Example:
        >>> callable(main)
        True
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.workers < 0:
        parser.error("--workers must be >= 0")
    from thot.core.StructuredLogging import configure_text_logging

    configure_text_logging(level=logging.INFO, force=True)
    try:
        extra = _load_dataset_extra(args.dataset_json)
        input_dir = Path(args.input_dir)
        recursive = not args.no_recursive
        skip_empty = not args.keep_empty
        convert = bool(args.convert or args.markdown_dir)
        if not convert and input_dir.is_dir():
            convert = has_non_markdown_files(
                input_dir.expanduser().resolve(),
                recursive=recursive,
            )
        if convert:
            md_dir = (
                Path(args.markdown_dir)
                if args.markdown_dir
                else input_dir.expanduser().resolve().parent
                / f"{input_dir.expanduser().resolve().name}-markdown"
            )
            ocr = {"enabled": False} if args.no_ocr else default_ocr_config()
            payload = corpus_from_source_dir(
                input_dir,
                md_dir,
                name=args.name,
                version=args.version,
                note=args.note,
                languages=[args.language],
                dataset_extra=extra,
                recursive=recursive,
                skip_empty=skip_empty,
                skip_unknown=args.skip_unknown,
                ocr_config=ocr,
                workers=args.workers,
                force=args.force,
            )
            logging.info("Markdown tree → %s", md_dir.resolve())
        else:
            payload = corpus_from_markdown_dir(
                args.input_dir,
                name=args.name,
                version=args.version,
                note=args.note,
                languages=[args.language],
                dataset_extra=extra,
                recursive=recursive,
                skip_empty=skip_empty,
                workers=args.workers,
            )
        dest = write_record_corpus(payload, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logging.error("%s", exc)
        return 1
    logging.info(
        "Wrote %s records → %s",
        payload["dataset"]["record_count"],
        dest,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
