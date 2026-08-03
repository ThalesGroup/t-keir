"""Title: Ontology upload staging

Stage client-uploaded ontology bytes under the ingest root. The server never
reads client-local filesystem paths — only staged content from the request.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_ontology_filename(name: str | None, *, index: int = 0) -> str:
    """Sanitize an ontology upload filename for staging on disk.

    Example:
        >>> from thot.tools.ingest.ontology_upload import safe_ontology_filename
        >>> safe_ontology_filename("My Ontology.owl")
        'My_Ontology.owl'
    """
    raw = Path(name or f"ontology_{index}.ttl").name
    cleaned = _SAFE_NAME.sub("_", raw).strip("._") or f"ontology_{index}.ttl"
    if Path(cleaned).suffix.lower() not in {
        ".ttl",
        ".owl",
        ".rdf",
        ".xml",
        ".n3",
        ".nt",
        ".jsonld",
        ".json",
    }:
        cleaned = f"{cleaned}.ttl"
    return cleaned


def stage_ontology_bytes(
    staging_dir: Path,
    items: list[tuple[str, bytes]],
) -> list[str]:
    """Write ontology payloads to ``staging_dir`` and return absolute paths.

    Args:
        staging_dir: Directory under ``INGEST_ROOT`` (server-local only).
        items: ``(filename, content)`` pairs from the client request.

    Returns:
        Absolute paths to staged files (safe for pipeline derive-from).
    

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tools.ingest.ontology_upload import stage_ontology_bytes
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     paths = stage_ontology_bytes(Path(temp_dir), [("test.ttl", b"@prefix ex: <http://ex/> .")])
        ...     len(paths)
        1
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    seen: set[str] = set()
    for index, (name, content) in enumerate(items):
        if not content:
            continue
        dest_name = safe_ontology_filename(name, index=index)
        base = dest_name
        n = 1
        while dest_name in seen:
            stem = Path(base).stem
            suffix = Path(base).suffix
            dest_name = f"{stem}_{n}{suffix}"
            n += 1
        seen.add(dest_name)
        dest = staging_dir / dest_name
        dest.write_bytes(content)
        paths.append(str(dest.resolve()))
        LOGGER.info(
            "Staged uploaded ontology %s (%s bytes)", dest.name, len(content)
        )
    return paths


def decode_ontology_uploads(raw: Any) -> list[tuple[str, bytes]]:
    """Decode JSON ontology uploads: ``[{filename, content_base64}, ...]``.

    Raises:
        ValueError: When the payload shape is invalid.
    

    Example:
        >>> import base64
        >>> from thot.tools.ingest.ontology_upload import decode_ontology_uploads
        >>> b64 = base64.b64encode(b"ttl").decode()
        >>> decode_ontology_uploads([{"filename": "x.ttl", "content_base64": b64}])
        [('x.ttl', b'ttl')]
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            "ontologies must be a list of "
            "{filename, content_base64} objects (upload content, not paths)"
        )
    out: list[tuple[str, bytes]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            raise ValueError(
                "ontology path strings are not accepted: the ingest server "
                "cannot read client files. Upload ontology content via "
                "multipart ontology_file or JSON content_base64."
            )
        if not isinstance(item, dict):
            raise ValueError(f"ontologies[{index}] must be an object")
        filename = str(
            item.get("filename") or item.get("name") or f"ontology_{index}.ttl"
        )
        b64 = (
            item.get("content_base64")
            or item.get("content")
            or item.get("data")
        )
        if not isinstance(b64, str) or not b64.strip():
            raise ValueError(
                f"ontologies[{index}] requires content_base64 (file bytes)"
            )
        try:
            content = base64.b64decode(b64, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"ontologies[{index}] content_base64 is invalid: {exc}"
            ) from exc
        if not content:
            raise ValueError(f"ontologies[{index}] content is empty")
        out.append((filename, content))
    return out


def strip_client_ontology_paths(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Remove path-based ontology keys from metadata (server cannot use them).

    Example:
        >>> from thot.tools.ingest.ontology_upload import strip_client_ontology_paths
        >>> strip_client_ontology_paths({"ontologies": ["/local/path.ttl"], "title": "x"})
        {'title': 'x'}
    """
    if not metadata:
        return metadata
    cleaned = dict(metadata)
    for key in (
        "ontologies",
        "derive_from_ontologies",
        "ontology_sources",
    ):
        cleaned.pop(key, None)
    return cleaned
