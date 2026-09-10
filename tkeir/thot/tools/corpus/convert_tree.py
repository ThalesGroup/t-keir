"""Title: Convert a mixed-format source tree to markdown

Walk a heterogeneous directory with :class:`UniversalConverter` and write
a parallel tree that contains **only markdown**. Each source file becomes
one ``.md`` file at the same relative path (original name kept, ``.md``
appended when the source was not already markdown).

The markdown includes a ``## Information`` block so
``tkeir-corpus`` / :func:`corpus_from_markdown_dir` can emit the usual
``{dataset, records}`` JSON with original format extras.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from thot.tasks.converters.UniversalConverter import (
    UniversalConverter,
    classify_kind,
)
from thot.tasks.converters.image_analysis import raster_is_below_analysis_size
from thot.tools.corpus.adaptive import AdaptiveLimiter, plan_workers
from thot.tools.corpus.markdown_records import (
    _MARKDOWN_SUFFIXES,
    parse_information_section,
)
from thot.tools.corpus.progress import (
    ProgressClock,
    RunStats,
    log_run_summary,
)

LOGGER = logging.getLogger(__name__)

_SKIP_FILE_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini"})
_SKIP_DIR_NAMES = frozenset({"__macosx", ".git", ".svn", "node_modules"})

_DEFAULT_OCR: dict[str, Any] = {
    "enabled": True,
    "mode": "tesseract",
    "analyze-images": True,
    "captions": True,
    "languages": "eng+fra+deu+spa+ita+nld+por+pol+ara",
    "min-image-pixels": 256 * 256,
    "min-page-text-chars": 40,
    "render-dpi": 200,
    "max-embedded-images": 256,
    "max-pdf-images-per-page": 32,
}


def default_ocr_config() -> dict[str, Any]:
    """Load OCR settings from ``configs/converter.yaml`` when present.

    OCR and BLIP captions default **on**. Missing keys are filled from
    :data:`_DEFAULT_OCR`.

    Returns:
        OCR mapping (never ``None``).

    Example:
        >>> cfg = default_ocr_config()
        >>> cfg["enabled"] and cfg["captions"]
        True
    """
    merged = dict(_DEFAULT_OCR)
    try:
        import yaml
        from thot.core.TkeirPaths import configs_dir

        path = configs_dir() / "converter.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError):
        return merged
    if not isinstance(payload, dict):
        return merged
    converter = payload.get("converter")
    if not isinstance(converter, dict):
        return merged
    settings = converter.get("settings")
    if not isinstance(settings, dict):
        return merged
    ocr = settings.get("ocr")
    if isinstance(ocr, dict):
        merged.update(ocr)
    return merged


def is_markdown_path(path: Path) -> bool:
    """Return True when ``path`` is a markdown file.

    Example:
        >>> is_markdown_path(Path("note.MD"))
        True
        >>> is_markdown_path(Path("scan.pdf"))
        False
    """
    return path.suffix.lower() in _MARKDOWN_SUFFIXES


def source_format_of(path: Path) -> str:
    """Original file format (extension, not the markdown sidecar).

    Args:
        path: Source file path (not the converted ``.md``).

    Returns:
        Lowercase extension without the dot, or ``unknown``.

    Example:
        >>> source_format_of(Path("maps/a.PDF"))
        'pdf'
        >>> source_format_of(Path("README"))
        'unknown'
    """
    suffix = path.suffix.lower().lstrip(".")
    return suffix or "unknown"


def markdown_dest_path(src_root: Path, dest_root: Path, src: Path) -> Path:
    """Map a source file to its markdown path under ``dest_root``.

    Markdown sources keep their relative path. Other files keep the
    original name and gain a ``.md`` suffix (``a.pdf`` → ``a.pdf.md``)
    so two stems cannot collide.

    Example:
        >>> markdown_dest_path(
        ...     Path("/in"), Path("/out"), Path("/in/r/a.pdf")
        ... ).as_posix()
        '/out/r/a.pdf.md'
        >>> markdown_dest_path(
        ...     Path("/in"), Path("/out"), Path("/in/n/a.md")
        ... ).as_posix()
        '/out/n/a.md'
    """
    rel = src.relative_to(src_root)
    if is_markdown_path(src):
        return dest_root / rel
    return dest_root / Path(*rel.parts[:-1], rel.name + ".md")


def iter_source_files(
    root: Path,
    *,
    recursive: bool = True,
    skip_under: Path | None = None,
) -> list[Path]:
    """Return sorted files to convert under ``root``.

    Hidden path segments (``.git``, …), macOS junk names, and an optional
    destination tree nested inside ``root`` are skipped.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.mkdtemp())
        >>> _ = (tmp / "a.txt").write_text("hi", encoding="utf-8")
        >>> _ = (tmp / ".hidden").mkdir()
        >>> _ = (tmp / ".hidden" / "x.txt").write_text("x", encoding="utf-8")
        >>> [p.name for p in iter_source_files(tmp)]
        ['a.txt']
    """
    if recursive:
        found = [path for path in root.rglob("*") if path.is_file()]
    else:
        found = [path for path in root.iterdir() if path.is_file()]
    skip_resolved = skip_under.resolve() if skip_under is not None else None
    kept: list[Path] = []
    for path in found:
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if any(part.casefold() in _SKIP_DIR_NAMES for part in rel.parts):
            continue
        if path.name.casefold() in _SKIP_FILE_NAMES:
            continue
        if skip_resolved is not None:
            try:
                path.resolve().relative_to(skip_resolved)
            except ValueError:
                pass
            else:
                continue
        kept.append(path)

    def _sort_key(path: Path) -> str:
        return path.relative_to(root).as_posix().casefold()

    return sorted(kept, key=_sort_key)


def has_non_markdown_files(root: Path, *, recursive: bool = True) -> bool:
    """True when ``root`` contains at least one non-markdown source file.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.mkdtemp())
        >>> _ = (tmp / "a.md").write_text("# A\\n\\nHi.\\n", encoding="utf-8")
        >>> has_non_markdown_files(tmp)
        False
        >>> _ = (tmp / "b.txt").write_text("x", encoding="utf-8")
        >>> has_non_markdown_files(tmp)
        True
    """
    for path in iter_source_files(root, recursive=recursive):
        if not is_markdown_path(path):
            return True
    return False


def _scalar_markdown(value: Any) -> str:
    """Render an Information bullet value.

    Example:
        >>> _scalar_markdown("pdf")
        'pdf'
        >>> _scalar_markdown(True)
        'true'
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    if " " in text or "/" in text or text.startswith("."):
        return f"`{text}`"
    return text


def document_to_markdown(
    document: Mapping[str, Any],
    *,
    source_rel: str,
    source_format: str,
    file_type: str,
) -> str:
    """Serialize a UniversalConverter document to corpus markdown.

    Prefers the raw ``markdown`` extract (original headings/tables). Falls
    back to ``title`` + ``content`` blocks. Always appends ``## Information``
    with original path / format / type (not the markdown sidecar).

    Example:
        >>> md = document_to_markdown(
        ...     {"title": "Hello", "content": ["World."], "markdown": "World."},
        ...     source_rel="n/a.txt",
        ...     source_format="txt",
        ...     file_type="raw",
        ... )
        >>> md.startswith("# Hello")
        True
        >>> "source_format" in md and "txt" in md
        True
    """
    title = str(document.get("title") or Path(source_rel).name).strip()
    raw = str(document.get("markdown") or "").strip()
    if not raw:
        blocks = [
            str(part).strip()
            for part in document.get("content") or []
            if str(part).strip()
        ]
        raw = "\n\n".join(blocks).strip()
    body, existing = parse_information_section(raw)
    if title and not body.lstrip().startswith("#"):
        body = f"# {title}\n\n{body}".strip()
    extras: dict[str, Any] = dict(existing)
    extras["source_path"] = source_rel
    extras["source_format"] = source_format
    extras["file_type"] = file_type
    lines = [body.rstrip(), "", "## Information", ""]
    for key in ("source_path", "source_format", "file_type"):
        value = extras.pop(key)
        lines.append(f"- **{key}:** {_scalar_markdown(value)}")
    for key, value in extras.items():
        if key.casefold() in {"source", "title", "text", "doc_id"}:
            continue
        if isinstance(value, dict):
            lines.append(f"- **{key}:**")
            for child_key, child in value.items():
                lines.append(f"  - **{child_key}:** {_scalar_markdown(child)}")
            continue
        lines.append(f"- **{key}:** {_scalar_markdown(value)}")
    return "\n".join(lines).rstrip() + "\n"


def convert_one_file(
    path: Path,
    *,
    ocr_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run :meth:`UniversalConverter.convert` on one file.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> tmp = Path(tempfile.mkdtemp()) / "n.txt"
        >>> _ = tmp.write_text("Hello world", encoding="utf-8")
        >>> doc = convert_one_file(tmp, ocr_config={"enabled": False})
        >>> "Hello" in (doc.get("markdown") or "")
        True
        >>> doc["conversion-info"]["datatype"]
        'raw'
    """
    data = path.read_bytes()
    ocr = dict(ocr_config) if ocr_config else None
    return UniversalConverter.convert(
        data,
        str(path),
        "auto",
        ocr_config=ocr,
    )


def skip_icon_raster(path: Path, data: bytes) -> bool:
    """Return True when a standalone raster is too small to analyse.

    Icons (both sides under 256) are omitted from the markdown tree and
    corpus JSON.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> buf = BytesIO()
        >>> Image.new("RGB", (32, 32), "red").save(buf, format="PNG")
        >>> skip_icon_raster(Path("icon.png"), buf.getvalue())
        True
        >>> buf = BytesIO()
        >>> Image.new("RGB", (256, 256), "navy").save(buf, format="PNG")
        >>> skip_icon_raster(Path("map.png"), buf.getvalue())
        False
    """
    if classify_kind(str(path), data) != "image":
        return False
    return raster_is_below_analysis_size(data)


@dataclass
class FileOutcome:
    """Result of converting one source file.

    Example:
        >>> FileOutcome(rel="a.txt", status="written").status
        'written'
    """

    rel: str
    status: str
    kind: str = ""
    dest: Path | None = None
    error: str = ""
    bytes_in: int = 0
    bytes_out: int = 0
    seconds: float = 0.0


@dataclass
class ConvertTreeResult:
    """Outcome of converting a source directory to markdown.

    Example:
        >>> ConvertTreeResult(markdown_dir=Path("/out")).written
        []
    """

    markdown_dir: Path
    written: list[Path] = field(default_factory=list)
    skipped: int = 0
    cached: int = 0
    errors: list[str] = field(default_factory=list)
    stats: RunStats = field(default_factory=lambda: RunStats(label="convert"))


def _ocr_flags(ocr: Mapping[str, Any]) -> tuple[bool, bool]:
    """Return ``(ocr_enabled, captions_enabled)`` from converter OCR settings.

    Example:
        >>> _ocr_flags({"enabled": False})
        (False, False)
        >>> _ocr_flags({"enabled": True, "captions": True})
        (True, True)
    """
    enabled = bool(ocr.get("enabled", True))
    if "captions" in ocr:
        captions = bool(ocr["captions"])
    elif "blip" in ocr:
        captions = bool(ocr["blip"])
    else:
        captions = enabled
    return enabled, captions


def existing_markdown(dest: Path) -> bool:
    """Return True when a previous convert already wrote ``dest``.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> path = Path(tempfile.mkdtemp()) / "a.md"
        >>> existing_markdown(path)
        False
        >>> _ = path.write_text("# x\\n\\nHi.\\n", encoding="utf-8")
        >>> existing_markdown(path)
        True
    """
    try:
        return dest.is_file() and dest.stat().st_size > 0
    except OSError:
        return False


def _convert_one_source(
    path: Path,
    *,
    src_root: Path,
    dest_root: Path,
    ocr: dict[str, Any],
    skip_unknown: bool,
    skip_empty: bool,
    force: bool = False,
) -> FileOutcome:
    """Convert one file to markdown (thread worker body).

    Example:
        >>> callable(_convert_one_source)
        True
    """
    rel = path.relative_to(src_root).as_posix()
    dest = markdown_dest_path(src_root, dest_root, path)
    started = time.perf_counter()
    if not force and existing_markdown(dest):
        size = dest.stat().st_size
        return FileOutcome(
            rel=rel,
            status="cached",
            kind="cached",
            dest=dest,
            bytes_out=size,
            seconds=time.perf_counter() - started,
        )
    try:
        data = path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        return FileOutcome(
            rel=rel,
            status="error",
            error=f"{rel}: {exc}",
            seconds=time.perf_counter() - started,
        )
    bytes_in = len(data)
    if skip_icon_raster(path, data):
        return FileOutcome(
            rel=rel,
            status="skipped",
            kind="icon",
            bytes_in=bytes_in,
            seconds=time.perf_counter() - started,
        )
    try:
        document = UniversalConverter.convert(
            data,
            str(path),
            "auto",
            ocr_config=ocr,
        )
    except Exception as exc:  # noqa: BLE001
        return FileOutcome(
            rel=rel,
            status="error",
            error=f"{rel}: {exc}",
            bytes_in=bytes_in,
            seconds=time.perf_counter() - started,
        )
    info = document.get("conversion-info") or {}
    kind = str(info.get("datatype") or "unknown").strip() or "unknown"
    if skip_unknown and kind == "unknown":
        return FileOutcome(
            rel=rel,
            status="skipped",
            kind=kind,
            bytes_in=bytes_in,
            seconds=time.perf_counter() - started,
        )
    markdown = document_to_markdown(
        document,
        source_rel=rel,
        source_format=source_format_of(path),
        file_type=kind,
    )
    empty = not parse_information_section(markdown)[0].strip()
    if empty and kind == "image":
        return FileOutcome(
            rel=rel,
            status="skipped",
            kind=kind,
            bytes_in=bytes_in,
            seconds=time.perf_counter() - started,
        )
    if empty and skip_empty:
        LOGGER.debug("write empty sidecar for cache %s", rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    encoded = markdown.encode("utf-8")
    dest.write_text(markdown, encoding="utf-8")
    return FileOutcome(
        rel=rel,
        status="written",
        kind=kind,
        dest=dest,
        bytes_in=bytes_in,
        bytes_out=len(encoded),
        seconds=time.perf_counter() - started,
    )


def convert_source_tree(
    input_dir: str | Path,
    markdown_dir: str | Path,
    *,
    recursive: bool = True,
    skip_unknown: bool = False,
    skip_empty: bool = False,
    ocr_config: Mapping[str, Any] | None = None,
    workers: int | None = None,
    force: bool = False,
) -> ConvertTreeResult:
    """Convert every managed file under ``input_dir`` into ``markdown_dir``.

    The destination tree mirrors the source layout. UniversalConverter
    classifies each file (``auto``) and extracts markdown for every
    datatype it manages (PDF, Office, HTML, image, ZIP, JSON, CSV, …).

    Conversion uses an adaptive thread pool (CPU + heavy-file mix) unless
    ``workers`` is a positive override. Progress logs elapsed time and ETA;
    a summary is printed when the tree finishes. Sources whose markdown
    sidecar already exists are skipped unless ``force`` is True.

    Args:
        input_dir: Heterogeneous source directory.
        markdown_dir: Destination markdown-only tree.
        recursive: Walk subdirectories when True.
        skip_unknown: Drop files classified as ``unknown``.
        skip_empty: Drop conversions whose extract is blank.
        ocr_config: Optional OCR settings for images / scanned PDFs.
            ``None`` uses :func:`default_ocr_config` (OCR and BLIP on).
        workers: Thread count. ``None`` / ``0`` = adaptive; ``>= 1`` = fixed.
        force: Re-convert even when the markdown sidecar already exists.

    Returns:
        Paths written plus skip/error counts and :class:`RunStats`.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> src = Path(tempfile.mkdtemp())
        >>> dest = Path(tempfile.mkdtemp())
        >>> _ = (src / "notes").mkdir()
        >>> _ = (src / "notes" / "a.txt").write_text(
        ...     "Hello from text.\\n", encoding="utf-8"
        ... )
        >>> result = convert_source_tree(
        ...     src, dest, ocr_config={"enabled": False}, workers=1
        ... )
        >>> result.written[0].name
        'a.txt.md'
        >>> "Hello" in result.written[0].read_text(encoding="utf-8")
        True
    """
    src_root = Path(input_dir).expanduser().resolve()
    dest_root = Path(markdown_dir).expanduser().resolve()
    if not src_root.is_dir():
        raise ValueError(f"not a directory: {src_root}")
    skip_dest = None
    if dest_root != src_root and dest_root.is_relative_to(src_root):
        skip_dest = dest_root
    files = iter_source_files(
        src_root, recursive=recursive, skip_under=skip_dest
    )
    if not files:
        raise ValueError(f"no source files under {src_root}")
    dest_root.mkdir(parents=True, exist_ok=True)
    ocr = dict(ocr_config) if ocr_config is not None else default_ocr_config()
    ocr_on, captions = _ocr_flags(ocr)
    plan = plan_workers(
        files,
        requested=workers,
        ocr_enabled=ocr_on,
        captions=captions,
    )
    limiter = AdaptiveLimiter(
        initial=plan.initial,
        maximum=plan.maximum,
        minimum=plan.minimum,
    )
    stats = RunStats(
        label="convert",
        files_total=len(files),
        workers_initial=plan.initial,
        workers_peak=plan.initial,
        workers_adaptive=plan.adaptive,
        cpu_count=plan.cpu_count,
    )
    result = ConvertTreeResult(markdown_dir=dest_root, stats=stats)
    clock = ProgressClock(total=len(files), label="convert")
    pending = len(files)
    pending_lock = threading.Lock()
    LOGGER.info(
        "Converting %d files (%d heavy) with %s threads "
        "(start %d, cap %d, cpu=%d)%s",
        len(files),
        plan.heavy_files,
        "adaptive" if plan.adaptive else "fixed",
        plan.initial,
        plan.maximum,
        plan.cpu_count,
        "" if force else "; skip existing markdown",
    )
    started = time.perf_counter()

    def _run_timed(path: Path) -> FileOutcome:
        limiter.acquire()
        outcome = FileOutcome(rel="?", status="error")
        try:
            try:
                outcome = _convert_one_source(
                    path,
                    src_root=src_root,
                    dest_root=dest_root,
                    ocr=ocr,
                    skip_unknown=skip_unknown,
                    skip_empty=skip_empty,
                    force=force,
                )
            except Exception as exc:  # noqa: BLE001
                rel = path.relative_to(src_root).as_posix()
                outcome = FileOutcome(
                    rel=rel,
                    status="error",
                    error=f"{rel}: {exc}",
                )
            return outcome
        finally:
            with pending_lock:
                nonlocal pending
                pending -= 1
                left = pending
            limiter.release(outcome.seconds, remaining=left)

    with ThreadPoolExecutor(max_workers=plan.pool_size) as pool:
        futures = [pool.submit(_run_timed, path) for path in files]
        for future in as_completed(futures):
            outcome = future.result()
            if outcome.status == "written":
                if outcome.dest is not None:
                    result.written.append(outcome.dest)
                stats.written += 1
                stats.bytes_out += outcome.bytes_out
            elif outcome.status == "cached":
                stats.cached += 1
                result.cached += 1
                stats.bytes_out += outcome.bytes_out
            elif outcome.status == "error":
                stats.errors += 1
                result.errors.append(outcome.error)
                result.skipped += 1
                if len(stats.error_samples) < 8:
                    stats.error_samples.append(outcome.error)
                LOGGER.warning("convert failed %s", outcome.error)
            else:
                stats.skipped += 1
                result.skipped += 1
                if outcome.kind == "icon":
                    LOGGER.info("skip icon-sized raster %s", outcome.rel)
            stats.bytes_in += outcome.bytes_in
            if outcome.status == "written":
                stats.record_kind(outcome.kind)
            stats.workers_peak = limiter.peak
            clock.tick(
                rel=outcome.rel,
                kind=outcome.kind,
                duration=outcome.seconds,
                workers=limiter.current,
                status=outcome.status,
            )
    stats.elapsed_seconds = time.perf_counter() - started
    stats.workers_peak = limiter.peak
    result.written.sort(key=lambda path: path.as_posix().casefold())
    log_run_summary(stats, logger=LOGGER)
    if not result.written and result.cached == 0:
        raise ValueError(
            f"no markdown produced under {src_root}"
            + (f" ({len(result.errors)} errors)" if result.errors else "")
        )
    return result
