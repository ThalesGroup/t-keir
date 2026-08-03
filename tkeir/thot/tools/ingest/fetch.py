"""Title: Fetch

Fetch document bytes from URLs or local paths.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx

from thot.action.models import sha256_hex


class FetchError(RuntimeError):
    """Raised when source bytes cannot be retrieved."""


def doc_id_from_content(content: bytes) -> str:
    """Return ``sha256(content)`` used as the canonical document id.

    Example:
        >>> from thot.tools.ingest.fetch import doc_id_from_content
        >>> doc_id_from_content(b"hello") == sha256_hex(b"hello")
        True
    """
    return sha256_hex(content)


def _filename_from_url(url: str, fallback: str | None) -> str:
    """Derive a filename from a URL or explicit fallback.

    Example:
        >>> _filename_from_url("file:///tmp/report.pdf", None)
        'report.pdf'
    """
    if fallback:
        return fallback
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(parsed.path).name or "document.bin"
    path_name = Path(parsed.path).name
    return path_name or "document.bin"


async def fetch_bytes(
    url: str,
    *,
    filename: str | None = None,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = 100 * 1024 * 1024,
) -> tuple[bytes, str, str | None]:
    """Download or read bytes for ``url``.

    Supports ``file://`` paths and HTTP(S) URLs.

    Returns:
        Tuple of ``(content, resolved_filename, content_type)``.

    Example:
        >>> import asyncio
        >>> from thot.tools.ingest.fetch import fetch_bytes
        >>> asyncio.run(fetch_bytes("file:///etc/hosts"))  # doctest: +SKIP
    """
    parsed = urlparse(url)
    resolved_name = _filename_from_url(url, filename)

    if parsed.scheme in {"", "file"}:
        path = Path(parsed.path if parsed.scheme == "file" else url)
        if not path.is_file():
            raise FetchError(f"Local file not found: {path}")
        content = path.read_bytes()
        if len(content) > max_bytes:
            raise FetchError(
                f"File exceeds max size ({max_bytes} bytes): {path}"
            )
        return content, resolved_name, None

    if parsed.scheme not in {"http", "https"}:
        raise FetchError(f"Unsupported URL scheme: {parsed.scheme}")

    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
    )
    try:
        response = await http.get(url)
        response.raise_for_status()
        content = response.content
        if len(content) > max_bytes:
            raise FetchError(
                f"Download exceeds max size ({max_bytes} bytes): {url}"
            )
        content_type = response.headers.get("content-type")
        return content, resolved_name, content_type
    except httpx.HTTPError as exc:
        raise FetchError(str(exc)) from exc
    finally:
        if owns_client:
            await http.aclose()


def write_upload(content: bytes, *, dest: Path) -> None:
    """Persist uploaded bytes atomically.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tools.ingest.fetch import write_upload
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     dest = Path(temp_dir) / "x.bin"
        ...     write_upload(b"data", dest=dest)
        ...     dest.read_bytes()
        b'data'
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, dest)
