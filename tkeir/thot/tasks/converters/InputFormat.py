# -*- coding: utf-8 -*-
"""Detect and verify converter input formats before conversion."""

from __future__ import annotations

import os

from thot.tasks.converters.MarkItDownConverter import DATATYPE_EXTENSIONS

AUTO_DATATYPE = "auto"

TEXT_EXTENSIONS = {
    ".txt",
    ".text",
    ".md",
    ".markdown",
    ".log",
}

ZIP_BASED_TYPES = frozenset({"csv", "docx", "epub", "ipynb", "pptx", "xlsx"})

OLE_BASED_TYPES = frozenset({"ppt", "xls", "msg"})

BINARY_MAGIC_CHECKS = (
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "zip"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole"),
)

EXTENSION_TO_DATATYPE = {
    extension: datatype for datatype, extension in DATATYPE_EXTENSIONS.items()
}
for extension in TEXT_EXTENSIONS:
    EXTENSION_TO_DATATYPE[extension] = "raw"


def _extension_datatype(path: str) -> str | None:
    """Map a file path extension to a converter datatype.

    Args:
        path: Input file path.

    Returns:
        Datatype name, or ``None`` when the extension is unknown.

    Example:
        >>> _extension_datatype("/tmp/report.pdf")
        'pdf'
    """
    _, extension = os.path.splitext(path)
    if not extension:
        return None
    return EXTENSION_TO_DATATYPE.get(extension.lower())


def is_binary_document(data: bytes) -> bool:
    """Return True when bytes match a known non-text document signature.

    Args:
        data: File content bytes.

    Returns:
        ``True`` for PDF, ZIP-based Office, and OLE compound documents.

    Example:
        >>> is_binary_document(b"%PDF-1.4")
        True
        >>> is_binary_document(b"Plain text.")
        False
    """
    if not data:
        return False
    for prefix, _kind in BINARY_MAGIC_CHECKS:
        if data.startswith(prefix):
            return True
    return False


def _looks_like_text(data: bytes) -> bool:
    """Return True when bytes look like UTF-8 plain text.

    Args:
        data: File content bytes.

    Returns:
        ``True`` for mostly printable UTF-8 samples.

    Example:
        >>> _looks_like_text(b"Plain text document.")
        True
    """
    if not data or b"\x00" in data[:8192]:
        return False
    sample = data[:8192]
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text.strip():
        return True
    printable = sum(
        1 for char in text if char.isprintable() or char in "\n\r\t"
    )
    return printable / len(text) >= 0.85


def has_extractable_text(data: bytes) -> bool:
    """Return True when bytes can be opened as plain text for raw conversion.

    Args:
        data: File content bytes.

    Returns:
        ``True`` when raw text conversion is reasonable.

    Example:
        >>> has_extractable_text(b"hello")
        True
    """
    if not data:
        return False
    if is_binary_document(data):
        return False
    if _looks_like_text(data):
        return True
    text = data[:65536].decode("utf-8", errors="replace").strip()
    if not text:
        return False
    printable = sum(
        1 for char in text if char.isprintable() or char in "\n\r\t"
    )
    return printable / len(text) >= 0.5


def _magic_matches(data_type: str, data: bytes) -> bool:
    """Return True when bytes match the expected magic for a datatype.

    Args:
        data_type: Converter datatype name.
        data: File content bytes.

    Returns:
        ``True`` when content matches the datatype signature.

    Example:
        >>> _magic_matches("pdf", b"%PDF-1.4")
        True
    """
    if not data:
        return data_type == "raw"

    if data_type == "raw":
        return has_extractable_text(data)

    if data_type == "pdf":
        return data.startswith(b"%PDF")

    if data_type == "rtf":
        return data.lstrip().startswith(b"{\\rtf")

    if data_type in ZIP_BASED_TYPES:
        return data.startswith(b"PK\x03\x04")

    if data_type in OLE_BASED_TYPES:
        return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")

    if data_type in {"html", "htm"}:
        head = data[:512].lstrip().lower()
        return head.startswith(b"<!doctype html") or head.startswith(b"<html")

    if data_type in {"xml", "rss"}:
        head = data[:512].lstrip().lower()
        return head.startswith(b"<?xml") or head.startswith(b"<rss")

    if data_type == "email":
        head = data[:4096].lower()
        return (
            head.lstrip().startswith(b"from:")
            or b"mime-version:" in head
            or b"content-type:" in head
        )

    return True


def _compatible_with_magic(data_type: str, data: bytes) -> bool:
    """Return True when content is compatible with the requested datatype.

    Args:
        data_type: Requested converter datatype.
        data: File content bytes.

    Returns:
        ``True`` when magic bytes match or are ambiguously compatible.

    Example:
        >>> _compatible_with_magic("docx", b"PK\x03\x04xxxx")
        True
    """
    if data_type in ZIP_BASED_TYPES and data.startswith(b"PK\x03\x04"):
        return True
    if data_type in OLE_BASED_TYPES and data.startswith(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    ):
        return True
    return _magic_matches(data_type, data)


def _guess_from_content(path: str, data: bytes) -> str:
    """Guess converter datatype from extension and content signatures.

    Args:
        path: Input file path.
        data: File content bytes.

    Returns:
        Best-effort converter datatype name.

    Raises:
        ValueError: When format cannot be detected.

    Example:
        >>> _guess_from_content("/tmp/note.txt", b"Hello world")
        'raw'
    """
    extension_type = _extension_datatype(path)

    checks = (
        ("pdf", lambda: data.startswith(b"%PDF")),
        ("rtf", lambda: data.lstrip().startswith(b"{\\rtf")),
        ("email", lambda: _magic_matches("email", data)),
        ("html", lambda: _magic_matches("html", data)),
        ("xml", lambda: _magic_matches("xml", data)),
    )
    for data_type, matcher in checks:
        if matcher():
            return data_type

    if data.startswith(b"PK\x03\x04") and extension_type in ZIP_BASED_TYPES:
        return extension_type

    if extension_type and extension_type != "raw":
        if _compatible_with_magic(extension_type, data):
            return extension_type

    if has_extractable_text(data):
        return "raw"

    if extension_type and extension_type != "raw":
        return extension_type

    if not data:
        return "raw"
    raise ValueError(
        "Unable to detect input format for "
        + os.path.basename(path)
        + "; file does not look like text or a supported binary format"
    )


def detect_input_format(
    path: str,
    data: bytes,
    requested: str = AUTO_DATATYPE,
) -> str:
    """Resolve the converter datatype for a file, verifying content when possible.

    Args:
        path: Input file path.
        data: File content bytes.
        requested: Explicit datatype or ``auto``.

    Returns:
        Resolved converter datatype name.

    Raises:
        ValueError: When an explicit datatype does not match content.

    Example:
        >>> detect_input_format("/tmp/doc.txt", b"Plain text.", AUTO_DATATYPE)
        'raw'
    """
    requested = (requested or AUTO_DATATYPE).strip().lower()

    if requested not in (AUTO_DATATYPE, ""):
        if not _compatible_with_magic(requested, data):
            if has_extractable_text(data):
                return "raw"
            if requested == "raw" and is_binary_document(data):
                return _guess_from_content(path, data)
            raise ValueError(
                "Input format mismatch for "
                + os.path.basename(path)
                + ": requested datatype '"
                + requested
                + "' does not match file content"
            )
        return requested

    return _guess_from_content(path, data)
