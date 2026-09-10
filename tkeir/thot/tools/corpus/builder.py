"""Title: Build a record-oriented corpus from markdown

Assemble ``{"dataset": {…}, "records": […]}`` from a directory of
markdown files, or from a mixed-format tree converted with
:class:`UniversalConverter`. ``dataset.record_count`` is always the
record list length. The payload is the shape expected by
``POST /ingest/json-records``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from thot.tools.corpus.adaptive import AdaptiveLimiter, plan_workers
from thot.tools.corpus.convert_tree import (
    convert_source_tree,
    default_ocr_config,
)
from thot.tools.corpus.markdown_records import (
    iter_markdown_files,
    markdown_file_to_record,
)
from thot.tools.corpus.progress import (
    ProgressClock,
    RunStats,
    log_run_summary,
)
from thot.tools.corpus.schema import (
    RecordCorpus,
    validate_record,
    validate_record_corpus,
)

LOGGER = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """UTC timestamp with a ``Z`` suffix (C2 ``generated_utc`` style).

    Returns:
        ISO-8601 UTC time truncated to seconds, ending with ``Z``.

    Example:
        >>> utc_now_iso().endswith("Z")
        True
    """
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_dataset(
    *,
    name: str,
    version: str = "1.0.0",
    record_count: int,
    generated_utc: str | None = None,
    languages: list[str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``dataset`` object.

    Args:
        name: ``dataset.name`` (required by ingest validation).
        version: ``dataset.version``.
        record_count: Number of records (always overwritten).
        generated_utc: Optional fixed timestamp for tests.
        languages: ``dataset.languages`` (default ``["en"]``).
        extra: Optional extra keys merged first.

    Returns:
        Dataset mapping.

    Example:
        >>> block = build_dataset(name="demo", record_count=2)
        >>> block["name"], block["record_count"]
        ('demo', 2)
    """
    dataset: dict[str, Any] = {}
    if extra:
        dataset.update(dict(extra))
    dataset["name"] = name
    dataset["version"] = version
    dataset["generated_utc"] = generated_utc or utc_now_iso()
    dataset["record_count"] = int(record_count)
    dataset["languages"] = list(languages or ["en"])
    return dataset


def corpus_from_markdown_dir(
    input_dir: str | Path,
    *,
    name: str | None = None,
    version: str = "1.0.0",
    note: str | None = None,
    languages: list[str] | None = None,
    dataset_extra: Mapping[str, Any] | None = None,
    recursive: bool = True,
    skip_empty: bool = False,
    generated_utc: str | None = None,
    workers: int | None = None,
) -> RecordCorpus:
    """Walk ``input_dir`` and return a validated record corpus.

    Args:
        input_dir: Directory of ``.md`` / ``.markdown`` files.
        name: ``dataset.name`` (default: directory name).
        version: ``dataset.version``.
        note: Optional ``dataset.note``.
        languages: ``dataset.languages``.
        dataset_extra: Extra keys merged into ``dataset``.
        recursive: Walk subdirectories when True.
        skip_empty: Drop files whose narrative ``text`` is blank.
        generated_utc: Optional fixed timestamp for tests.
        workers: Thread count. ``None`` / ``0`` = adaptive; ``>= 1`` = fixed.

    Returns:
        Validated ``{dataset, records}`` payload.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> from thot.tools.corpus.builder import corpus_from_markdown_dir
        >>> tmp = Path(tempfile.mkdtemp())
        >>> _ = (tmp / "a.md").write_text(
        ...     "# A\\n\\nHello.\\n", encoding="utf-8"
        ... )
        >>> payload = corpus_from_markdown_dir(tmp, name="demo", workers=1)
        >>> payload["records"][0]["doc_id"]
        'a'
        >>> payload["dataset"]["record_count"]
        1
    """
    root = Path(input_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    files = iter_markdown_files(root, recursive=recursive)
    if not files:
        raise ValueError(f"no markdown files under {root}")
    plan = plan_workers(
        files,
        requested=workers,
        ocr_enabled=False,
        captions=False,
    )
    limiter = AdaptiveLimiter(
        initial=plan.initial,
        maximum=plan.maximum,
        minimum=plan.minimum,
    )
    stats = RunStats(
        label="compile",
        files_total=len(files),
        workers_initial=plan.initial,
        workers_peak=plan.initial,
        workers_adaptive=plan.adaptive,
        cpu_count=plan.cpu_count,
    )
    clock = ProgressClock(total=len(files), label="compile")
    LOGGER.info(
        "Compiling %d markdown files with %s threads "
        "(start %d, cap %d, cpu=%d)",
        len(files),
        "adaptive" if plan.adaptive else "fixed",
        plan.initial,
        plan.maximum,
        plan.cpu_count,
    )
    pending = len(files)
    pending_lock = threading.Lock()
    started = time.perf_counter()

    def _read_one(path: Path) -> tuple[dict[str, Any] | None, str, float]:
        limiter.acquire()
        t0 = time.perf_counter()
        rel = path.relative_to(root).as_posix()
        record: dict[str, Any] | None = None
        error = ""
        try:
            try:
                record = markdown_file_to_record(root, path)
            except Exception as exc:  # noqa: BLE001
                error = f"{rel}: {exc}"
            return record, error, time.perf_counter() - t0
        finally:
            with pending_lock:
                nonlocal pending
                pending -= 1
                left = pending
            limiter.release(time.perf_counter() - t0, remaining=left)

    parsed: dict[Path, tuple[dict[str, Any] | None, str, float]] = {}
    with ThreadPoolExecutor(max_workers=plan.pool_size) as pool:
        futures = {pool.submit(_read_one, path): path for path in files}
        for future in as_completed(futures):
            path = futures[future]
            rel = path.relative_to(root).as_posix()
            record, error, seconds = future.result()
            parsed[path] = (record, error, seconds)
            stats.workers_peak = limiter.peak
            status = "error" if error else "compiled"
            clock.tick(
                rel=rel,
                kind="md",
                duration=seconds,
                workers=limiter.current,
                status=status,
            )

    records: list[dict[str, Any]] = []
    for path in files:
        record, error, _seconds = parsed[path]
        if error:
            stats.errors += 1
            stats.skipped += 1
            if len(stats.error_samples) < 8:
                stats.error_samples.append(error)
            LOGGER.warning("compile skip %s", error)
            continue
        assert record is not None
        empty = not str(record.get("text") or "").strip()
        if empty and skip_empty:
            stats.skipped += 1
            continue
        try:
            validate_record(record, index=len(records))
        except ValueError as exc:
            if skip_empty:
                stats.errors += 1
                stats.skipped += 1
                rel = path.relative_to(root).as_posix()
                msg = f"{rel}: {exc}"
                if len(stats.error_samples) < 8:
                    stats.error_samples.append(msg)
                LOGGER.warning("compile skip %s", msg)
                continue
            raise
        records.append(record)
        stats.written += 1
        stats.record_kind("md")
        stats.bytes_in += len(str(record.get("text") or "").encode("utf-8"))
    stats.elapsed_seconds = time.perf_counter() - started
    log_run_summary(stats, logger=LOGGER)
    if not records:
        raise ValueError(f"no non-empty markdown records under {root}")
    extra: dict[str, Any] = dict(dataset_extra or {})
    if note:
        extra["note"] = note
    dataset = build_dataset(
        name=name or root.name,
        version=version,
        record_count=len(records),
        generated_utc=generated_utc,
        languages=languages,
        extra=extra,
    )
    payload: dict[str, Any] = {"dataset": dataset, "records": records}
    return validate_record_corpus(payload)


def corpus_from_source_dir(
    input_dir: str | Path,
    markdown_dir: str | Path,
    *,
    name: str | None = None,
    version: str = "1.0.0",
    note: str | None = None,
    languages: list[str] | None = None,
    dataset_extra: Mapping[str, Any] | None = None,
    recursive: bool = True,
    skip_empty: bool = True,
    skip_unknown: bool = False,
    generated_utc: str | None = None,
    ocr_config: Mapping[str, Any] | None = None,
    workers: int | None = None,
    force: bool = False,
) -> RecordCorpus:
    """Convert a mixed-format tree to markdown, then build a record corpus.

    ``markdown_dir`` mirrors ``input_dir`` with one ``.md`` file per source
    (UniversalConverter ``auto`` classification). JSON records are compiled
    from that markdown tree as usual.

    Args:
        input_dir: Heterogeneous source directory.
        markdown_dir: Destination markdown-only tree.
        name: ``dataset.name`` (default: source directory name).
        version: ``dataset.version``.
        note: Optional ``dataset.note``.
        languages: ``dataset.languages``.
        dataset_extra: Extra keys merged into ``dataset``.
        recursive: Walk subdirectories when True.
        skip_empty: Drop blank extracts and blank markdown records.
        skip_unknown: Drop files classified as ``unknown``.
        generated_utc: Optional fixed timestamp for tests.
        ocr_config: Optional OCR settings (default: ``converter.yaml``).
        workers: Thread count. ``None`` / ``0`` = adaptive; ``>= 1`` = fixed.
        force: Re-convert even when the markdown sidecar already exists.

    Returns:
        Validated ``{dataset, records}`` payload.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> from thot.tools.corpus.builder import corpus_from_source_dir
        >>> src = Path(tempfile.mkdtemp())
        >>> md = Path(tempfile.mkdtemp())
        >>> _ = (src / "hello.txt").write_text(
        ...     "Hello from a text file.\\n", encoding="utf-8"
        ... )
        >>> payload = corpus_from_source_dir(
        ...     src,
        ...     md,
        ...     name="demo",
        ...     ocr_config={"enabled": False},
        ...     workers=1,
        ... )
        >>> payload["records"][0]["source_format"]
        'txt'
        >>> payload["dataset"]["record_count"]
        1
    """
    convert_source_tree(
        input_dir,
        markdown_dir,
        recursive=recursive,
        skip_unknown=skip_unknown,
        skip_empty=skip_empty,
        ocr_config=(
            ocr_config if ocr_config is not None else default_ocr_config()
        ),
        workers=workers,
        force=force,
    )
    return corpus_from_markdown_dir(
        markdown_dir,
        name=name or Path(input_dir).expanduser().resolve().name,
        version=version,
        note=note,
        languages=languages,
        dataset_extra=dataset_extra,
        recursive=recursive,
        skip_empty=skip_empty,
        generated_utc=generated_utc,
        workers=workers,
    )


def write_record_corpus(
    payload: Mapping[str, Any],
    output: str | Path,
    *,
    indent: int = 2,
) -> Path:
    """Write a validated corpus to ``output`` (UTF-8 JSON).

    Args:
        payload: ``{dataset, records}`` mapping.
        output: Destination JSON path.
        indent: ``json.dumps`` indent.

    Returns:
        Resolved output path.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> from thot.tools.corpus.builder import write_record_corpus
        >>> out = Path(tempfile.mkdtemp()) / "c.json"
        >>> path = write_record_corpus(
        ...     {
        ...         "dataset": {"name": "d"},
        ...         "records": [
        ...             {"doc_id": "1", "title": "T", "text": "b"}
        ...         ],
        ...     },
        ...     out,
        ... )
        >>> path.name
        'c.json'
    """
    validated = validate_record_corpus(dict(payload))
    dest = Path(output).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(validated, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )
    return dest
