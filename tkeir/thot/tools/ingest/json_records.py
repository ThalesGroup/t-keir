"""Title: JSON record corpus helpers for ingest.

Split record-oriented JSON (e.g. OSINT ``{records:[…]}``) into one document
per record, render full attribute trees as Markdown, and derive ontology
concept ids from structured fields (everything except title/text).

Source naming: ``{filename_stem}/{doc_id}``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

# Fields treated as primary narrative — not promoted to ontology concepts.
_NARRATIVE_KEYS = frozenset(
    {
        "title",
        "text",
        "body",
        "content",
        "summary",
        "abstract",
        "description",
    }
)

_ID_KEYS = ("doc_id", "id", "document_id", "uid", "_id")


def corpus_filename_stem(filename: str | None) -> str:
    """Stable stem used in ``{stem}/{doc_id}`` source names."""
    name = (filename or "upload.json").strip() or "upload.json"
    stem = Path(name).name
    if stem.lower().endswith(".json"):
        stem = stem[: -len(".json")]
    cleaned = re.sub(r"[^\w.\-]+", "_", stem).strip("._") or "corpus"
    return cleaned[:120]


def record_doc_id(record: dict[str, Any], *, index: int) -> str:
    """Pick a stable per-record id."""
    for key in _ID_KEYS:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return f"record-{index:05d}"


def source_name(filename: str | None, doc_id: str) -> str:
    """Build ``{filename_stem}/{doc_id}`` source / source_doc_id."""
    return f"{corpus_filename_stem(filename)}/{doc_id}"


def iter_json_records(payload: Any) -> list[dict[str, Any]]:
    """Extract a list of record objects from common JSON corpus shapes."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("records", "documents", "items", "data", "docs"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    # Single-document JSON with a title/text body — treat as one record.
    if any(k in payload for k in ("title", "text", "content", "doc_id")):
        return [payload]
    return []


def is_record_corpus(payload: Any) -> bool:
    """True when payload looks like a multi-record (or single-record) corpus."""
    records = iter_json_records(payload)
    if not records:
        return False
    # Pipeline corpus JSON uses content / content_tokens — leave that path alone.
    if (
        len(records) == 1
        and isinstance(payload, dict)
        and ("content" in payload or "content_tokens" in payload)
        and "records" not in payload
    ):
        return False
    return True


def _scalar_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).strip()


def _markdown_value(value: Any, *, indent: int = 0) -> list[str]:
    """Render nested JSON values as markdown lines."""
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_s = str(key)
            if isinstance(child, (dict, list)):
                lines.append(f"{pad}- **{key_s}:**")
                lines.extend(_markdown_value(child, indent=indent + 1))
            else:
                text = _scalar_to_str(child)
                if text == "":
                    continue
                lines.append(f"{pad}- **{key_s}:** {text}")
        return lines
    if isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_markdown_value(item, indent=indent + 1))
            else:
                text = _scalar_to_str(item)
                if text:
                    lines.append(f"{pad}- {text}")
        return lines
    text = _scalar_to_str(value)
    if text:
        lines.append(f"{pad}{text}")
    return lines


def record_to_markdown(record: dict[str, Any], *, source: str) -> str:
    """Serialize a record as ``# title`` + body text + ``## Information`` attrs.

    Layout::

        # <TITLE>

        <TEXT>

        ## Information

        - **source:** `stem/doc_id`
        - **attr:** value
          - **nested:** value
    """
    title = _scalar_to_str(record.get("title")) or source
    text = _scalar_to_str(
        record.get("text") or record.get("body") or record.get("content") or ""
    )

    lines: list[str] = [f"# {title}", ""]
    if text:
        lines.extend([text, ""])

    # Everything except narrative fields goes under Information as bullets.
    skip = {"title", "text", "body", "content"}
    info: dict[str, Any] = {"source": source}
    doc_id = _scalar_to_str(record.get("doc_id") or record.get("id") or "")
    if doc_id:
        info["doc_id"] = doc_id
    for key, value in record.items():
        if key.casefold() in skip or key in {"doc_id", "id"}:
            continue
        if value is None or value == "" or value == []:
            continue
        info[key] = value

    lines.extend(["## Information", ""])
    lines.extend(_markdown_value(info))
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _concept_token(path: str, value: Any) -> str | None:
    """Build a stable concept id from a field path + scalar value."""
    text = _scalar_to_str(value)
    if not text or len(text) > 120:
        return None
    # Skip pure free-text blobs.
    if len(text) > 64 and " " in text:
        return None
    path_key = re.sub(r"[^\w]+", "_", path).strip("_").upper()
    val_key = re.sub(r"[^\w.\-]+", "_", text).strip("._")
    if not path_key or not val_key:
        return None
    return f"{path_key}:{val_key}"[:180]


def extract_record_concepts(
    record: dict[str, Any],
    *,
    prefix: str = "",
    max_concepts: int = 64,
) -> list[str]:
    """Promote non-narrative attribute values to ontology concept ids."""
    concepts: list[str] = []
    seen: set[str] = set()

    def _walk(node: Any, path: str) -> None:
        if len(concepts) >= max_concepts:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                key_s = str(key)
                leaf = f"{path}.{key_s}" if path else key_s
                if key_s.casefold() in _NARRATIVE_KEYS:
                    continue
                _walk(child, leaf)
            return
        if isinstance(node, list):
            for idx, child in enumerate(node):
                if isinstance(child, (dict, list)):
                    _walk(child, f"{path}[{idx}]")
                else:
                    cid = _concept_token(path, child)
                    if cid and cid.casefold() not in seen:
                        seen.add(cid.casefold())
                        concepts.append(cid)
            return
        cid = _concept_token(path, node)
        if cid and cid.casefold() not in seen:
            seen.add(cid.casefold())
            concepts.append(cid)

    _walk(record, prefix)
    return concepts[:max_concepts]


def split_record_documents(
    payload: Any,
    *,
    filename: str | None,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Split a corpus into markdown documents ready for NLP ingest.

    Each item:
      - ``doc_id``: record id
      - ``source`` / ``source_doc_id``: ``{stem}/{doc_id}``
      - ``title``
      - ``markdown``: full markdown body
      - ``filename``: ``{stem}__{doc_id}.md``
      - ``record_concept_ids``: concepts from structured fields
      - ``metadata``: classification / domain / … for ingest extras
    """
    records = iter_json_records(payload)
    if offset:
        records = records[offset:]
    if limit is not None:
        records = records[: max(0, int(limit))]

    stem = corpus_filename_stem(filename)
    out: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        doc_id = record_doc_id(record, index=offset + index)
        source = source_name(filename, doc_id)
        title = _scalar_to_str(record.get("title")) or doc_id
        markdown = record_to_markdown(record, source=source)
        concepts = extract_record_concepts(record)
        meta: dict[str, Any] = {
            "corpus": stem,
            "title": title,
            "doc_type": _scalar_to_str(
                record.get("domain") or record.get("source_type") or "osint"
            ),
            "language": _scalar_to_str(record.get("language") or "en") or "en",
        }
        for key in (
            "classification",
            "domain",
            "originator",
            "pir_ref",
            "topic_id",
        ):
            value = record.get(key)
            if value is not None and value != "" and value != []:
                meta[key] = value
        safe_id = re.sub(r"[^\w.\-]+", "_", doc_id)
        out.append(
            {
                "doc_id": doc_id,
                "source": source,
                "source_doc_id": source,
                "title": title,
                "markdown": markdown,
                "filename": f"{stem}__{safe_id}.md",
                "record_concept_ids": concepts,
                "metadata": meta,
            }
        )
    return out


def safe_doc_filename(doc_id: str) -> str:
    """Filesystem-safe ``{doc_id}.md`` name for workspace My files."""
    cleaned = re.sub(r"[^\w.\-]+", "_", str(doc_id or "").strip()).strip("._")
    return f"{(cleaned or 'record')[:180]}.md"


def workspace_markdown_files_from_json(
    content: bytes,
    *,
    filename: str | None,
    directory: str = "",
    max_records: int = 5000,
) -> list[dict[str, Any]] | None:
    """If ``content`` is a record corpus, return My-files markdown write specs.

    Each item: ``path`` (relative under workspace files/), ``doc_id``,
    ``markdown`` (str), ``title``. Returns ``None`` when not a record corpus.
    """
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not is_record_corpus(payload):
        return None
    docs = split_record_documents(
        payload, filename=filename, limit=max_records
    )
    if not docs:
        return None
    stem = corpus_filename_stem(filename)
    parent = (directory or "").strip().strip("/")
    base = f"{parent}/{stem}".lstrip("/") if parent else stem
    out: list[dict[str, Any]] = []
    for doc in docs:
        doc_id = str(doc.get("doc_id") or "")
        rel = f"{base}/{safe_doc_filename(doc_id)}"
        out.append(
            {
                "path": rel,
                "doc_id": doc_id,
                "title": doc.get("title") or doc_id,
                "markdown": doc.get("markdown") or "",
                "source_doc_id": doc.get("source_doc_id") or doc.get("source"),
                "record_concept_ids": doc.get("record_concept_ids") or [],
            }
        )
    return out


def load_and_split(
    content: bytes,
    *,
    filename: str | None,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Parse JSON bytes and split into markdown ingest documents."""
    payload = json.loads(content.decode("utf-8"))
    if not is_record_corpus(payload):
        raise ValueError(
            "JSON is not a record corpus (expected {records:[…]} or a list of objects)"
        )
    docs = split_record_documents(
        payload, filename=filename, offset=offset, limit=limit
    )
    if not docs:
        raise ValueError("No records found in JSON corpus")
    return docs


def iter_split(
    content: bytes,
    *,
    filename: str | None,
    offset: int = 0,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Iterator wrapper around :func:`load_and_split`."""
    yield from load_and_split(
        content, filename=filename, offset=offset, limit=limit
    )
