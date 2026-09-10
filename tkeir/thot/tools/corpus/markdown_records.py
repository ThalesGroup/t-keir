"""Title: Markdown → record helpers

Read a directory of ``.md`` / ``.markdown`` files into record dicts
compatible with ``thot.tools.ingest.json_records``.

Each file becomes one record:

- ``doc_id`` — YAML frontmatter ``doc_id``, else relative path stem
- ``title`` — frontmatter ``title``, else first ``#`` heading, else stem
- ``text`` — body after the title heading (``## Information`` stripped)

Optional YAML frontmatter and ``## Information`` bullets become extra
fields (C2-style ``classification``, ``location``, …).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER = re.compile(
    r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?",
    re.DOTALL,
)
_H1 = re.compile(r"\A[ \t]*#[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_INFO_HEADING = re.compile(
    r"^##[ \t]+Information[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_BULLET = re.compile(r"^([ \t]*)-\s+\*\*([^*]+):\*\*[ \t]*(.*)$")
_MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
_SKIP_INFO_KEYS = frozenset({"source", "title", "text"})


def iter_markdown_files(root: Path, *, recursive: bool = True) -> list[Path]:
    """Return sorted markdown files under ``root``.

    Args:
        root: Directory to walk.
        recursive: When False, only the top level is scanned.

    Returns:
        Paths sorted by relative POSIX path (casefold).

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.corpus.markdown_records import (
        ...     iter_markdown_files,
        ... )
        >>> isinstance(iter_markdown_files, object)
        True
    """
    if recursive:
        found = [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in _MARKDOWN_SUFFIXES
        ]
    else:
        found = [
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in _MARKDOWN_SUFFIXES
        ]
    kept: list[Path] = []
    for path in found:
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        kept.append(path)

    def _sort_key(path: Path) -> str:
        return path.relative_to(root).as_posix().casefold()

    return sorted(kept, key=_sort_key)


def default_doc_id(root: Path, path: Path) -> str:
    """Relative path without suffix, POSIX separators.

    Args:
        root: Corpus root directory.
        path: Markdown file under ``root``.

    Returns:
        Relative stem used as a default ``doc_id``.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.corpus.markdown_records import default_doc_id
        >>> default_doc_id(Path("/c"), Path("/c/reports/a.md"))
        'reports/a'
    """
    rel = path.relative_to(root)
    return rel.with_suffix("").as_posix()


def _coerce_scalar(raw: str) -> Any:
    """Parse a markdown Information value.

    Args:
        raw: Bullet remainder after ``**key:**``.

    Returns:
        Bool, int, float, or stripped string (backticks removed).

    Example:
        >>> _coerce_scalar("true")
        True
        >>> _coerce_scalar("`stem/id`")
        'stem/id'
    """
    text = raw.strip()
    if text.startswith("`") and text.endswith("`") and len(text) >= 2:
        text = text[1:-1].strip()
    if text.casefold() == "true":
        return True
    if text.casefold() == "false":
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def parse_information_section(body: str) -> tuple[str, dict[str, Any]]:
    """Split narrative text from an optional ``## Information`` block.

    Args:
        body: Markdown after the H1 title.

    Returns:
        ``(narrative_text, extra_fields)``. Nested bullets become dicts.

    Example:
        >>> text, extra = parse_information_section(
        ...     "Body.\\n\\n## Information\\n\\n- **domain:** OSINT\\n"
        ... )
        >>> text
        'Body.'
        >>> extra["domain"]
        'OSINT'
    """
    match = _INFO_HEADING.search(body)
    if match is None:
        return body.strip(), {}
    text = body[: match.start()].strip()
    extras: dict[str, Any] = {}
    current: str | None = None
    for line in body[match.end() :].splitlines():
        bullet = _BULLET.match(line)
        if bullet is None:
            continue
        indent, key, rest = bullet.groups()
        key = key.strip()
        if key.casefold() in _SKIP_INFO_KEYS:
            current = None
            continue
        if indent == "":
            if rest.strip():
                extras[key] = _coerce_scalar(rest)
                current = None
            else:
                extras[key] = {}
                current = key
            continue
        if current and isinstance(extras.get(current), dict) and rest.strip():
            extras[current][key] = _coerce_scalar(rest)
    extras.pop("source", None)
    return text, extras


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Pull YAML frontmatter off a markdown document.

    Args:
        raw: Full file contents.

    Returns:
        ``(frontmatter_mapping, remainder)``. Empty mapping when absent.

    Example:
        >>> meta, body = split_frontmatter("---\\ndoc_id: r1\\n---\\n# T\\n")
        >>> meta["doc_id"]
        'r1'
        >>> body.startswith("# T")
        True
    """
    match = _FRONTMATTER.match(raw)
    if match is None:
        return {}, raw
    loaded = yaml.safe_load(match.group(1)) or {}
    if not isinstance(loaded, dict):
        raise ValueError("YAML frontmatter must be a mapping")
    return loaded, raw[match.end() :]


def parse_markdown_record(
    raw: str,
    *,
    default_id: str,
) -> dict[str, Any]:
    """Build one ingest record dict from markdown text.

    Args:
        raw: Markdown document (optional YAML frontmatter).
        default_id: Fallback ``doc_id`` (usually the relative stem).

    Returns:
        Record with at least ``doc_id``, ``title``, and ``text``.

    Example:
        >>> parse_markdown_record("# Hello\\n\\nWorld.\\n", default_id="n1")
        {'doc_id': 'n1', 'title': 'Hello', 'text': 'World.'}
    """
    front, rest = split_frontmatter(raw)
    heading = _H1.search(rest.lstrip("\n"))
    title_from_h1 = ""
    body = rest
    if heading is not None and rest.lstrip("\n").startswith("#"):
        title_from_h1 = heading.group(1).strip()
        # Drop the first H1 line only.
        stripped = rest.lstrip("\n")
        first_nl = stripped.find("\n")
        body = stripped[first_nl + 1 :] if first_nl >= 0 else ""
    text, info = parse_information_section(body)
    record: dict[str, Any] = {}
    record.update(info)
    for key, value in front.items():
        if key in {"title", "text", "doc_id"}:
            continue
        record[key] = value
    doc_id = (
        str(front.get("doc_id") or "").strip()
        or str(record.get("doc_id") or "").strip()
        or default_id
    )
    title = (
        str(front.get("title") or "").strip()
        or title_from_h1
        or Path(default_id).name
    )
    if front.get("text") is not None and str(front.get("text")).strip():
        text = str(front["text"]).strip()
    record["doc_id"] = doc_id
    record["title"] = title
    record["text"] = text
    return record


def markdown_file_to_record(root: Path, path: Path) -> dict[str, Any]:
    """Read ``path`` and return a record dict.

    Args:
        root: Corpus root (for the default ``doc_id``).
        path: Markdown file to parse.

    Returns:
        Record mapping ready for ``validate_record``.

    Example:
        >>> from pathlib import Path
        >>> callable(markdown_file_to_record)
        True
    """
    raw = path.read_text(encoding="utf-8")
    return parse_markdown_record(raw, default_id=default_doc_id(root, path))
