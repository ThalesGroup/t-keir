"""Title: Clean HTML/binary pages to well-formatted Markdown.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from bs4 import BeautifulSoup

from thot.tasks.converters.MarkItDownConverter import MarkItDownConverter

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_YAML_BAD = re.compile(r'["\\\n\r]')


def _extension_for(filename: str, content_type: str | None) -> str:
    """Pick a MarkItDown file extension from name or Content-Type.

    Example:
        >>> _extension_for("page.html", "text/html")
        '.html'
        >>> _extension_for("doc", "application/pdf")
        '.pdf'
    """
    name = (filename or "").split("?")[0]
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
        if ext in {
            ".html",
            ".htm",
            ".pdf",
            ".docx",
            ".pptx",
            ".xlsx",
            ".csv",
            ".xml",
        }:
            return ext
    ctype = (content_type or "").split(";")[0].strip().lower()
    mapping = {
        "text/html": ".html",
        "application/xhtml+xml": ".html",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "application/json": ".json",
    }
    return mapping.get(ctype, ".html")


def _strip_noise_html(data: bytes) -> bytes:
    """Remove script/style/chrome noise before MarkItDown when input is HTML.

    Example:
        >>> out = _strip_noise_html(b"<html><script>x</script><p>Hi</p></html>")
        >>> b"script" not in out.lower() or b"Hi" in out
        True
    """
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return data
    if "<" not in text or ">" not in text:
        return data
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "iframe",
            "svg",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
            "button",
        ]
    ):
        tag.decompose()
    for el in soup.find_all(attrs={"role": True}):
        role = str(el.get("role") or "").lower()
        if role in {
            "navigation",
            "banner",
            "contentinfo",
            "complementary",
            "search",
        }:
            el.decompose()
    return str(soup).encode("utf-8", errors="replace")


def clean_markdown(text: str) -> str:
    """Normalize whitespace and drop control characters from markdown.

    Example:
        >>> clean_markdown("Hello\\x00  \\n\\n\\nWorld")
        'Hello\\n\\nWorld'
    """
    cleaned = _CTRL_RE.sub("", text or "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Collapse MarkItDown leftover link-only chrome lines.
    cleaned = re.sub(r"\n{2,}(#{1,6}\s+)", r"\n\n\1", cleaned)
    return cleaned.strip()


def bytes_to_markdown(
    data: bytes,
    *,
    filename: str = "document.html",
    content_type: str | None = None,
) -> str:
    """Convert fetched document bytes to clean Markdown.

    Prefer MarkItDown (HTML/PDF/Office). Fall back to BeautifulSoup text
    extraction when MarkItDown yields nothing useful.

    Example:
        >>> md = bytes_to_markdown(
        ...     b"<html><body><h1>Title</h1><p>Body text</p></body></html>",
        ...     filename="x.html",
        ...     content_type="text/html",
        ... )
        >>> "Title" in md or "Body" in md
        True
    """
    if not data:
        return ""
    ext = _extension_for(filename, content_type)
    payload = _strip_noise_html(data) if ext in {".html", ".htm"} else data
    markdown = ""
    try:
        result = MarkItDownConverter.get_engine().convert_stream(
            BytesIO(payload),
            file_extension=ext,
        )
        markdown = (result.text_content or result.markdown or "").strip()
    except Exception:  # noqa: BLE001
        markdown = ""
    if not markdown and ext in {".html", ".htm", ".txt", ".md"}:
        try:
            text = payload.decode("utf-8", errors="replace")
            if ext in {".html", ".htm"}:
                text = BeautifulSoup(text, "html.parser").get_text("\n")
            markdown = text
        except Exception:  # noqa: BLE001
            markdown = ""
    return clean_markdown(markdown)


def _yaml_scalar(value: Any) -> str:
    """Quote a scalar for a simple YAML front-matter line.

    Example:
        >>> _yaml_scalar(3)
        '3'
        >>> _yaml_scalar('plain')
        'plain'
    """
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value).strip()
    if not text:
        return '""'
    if _YAML_BAD.search(text) or text.startswith(
        ("@", "`", "|", ">", "*", "&", "!")
    ):
        escaped = (
            text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "")
        )
        return f'"{escaped}"'
    return text


def format_collected_markdown(
    body: str,
    *,
    title: str,
    source_url: str,
    query: str | None = None,
    topic: str | None = None,
    engine: str | None = None,
    snippet: str | None = None,
    collected_at: str | None = None,
    content_type: str | None = None,
) -> str:
    """Build a well-formed markdown document with YAML front matter.

    Ensures a single leading ``#`` title, then the cleaned body (without a
    duplicate first heading when it matches ``title``).

    Example:
        >>> md = format_collected_markdown(
        ...     "Body paragraph.",
        ...     title="Hello",
        ...     source_url="https://ex.example/a",
        ...     collected_at="2026-01-01T00:00:00Z",
        ... )
        >>> md.startswith("---\\n")
        True
        >>> "# Hello" in md and "Body paragraph." in md
        True
    """
    title_s = (title or "").strip() or source_url or "Untitled"
    body_s = clean_markdown(body or "")
    # Drop a redundant first ATX heading that repeats the title.
    first_lines = body_s.split("\n", 1)
    if first_lines:
        heading = re.match(r"^#{1,6}\s+(.*)$", first_lines[0].strip())
        if (
            heading
            and heading.group(1).strip().casefold() == title_s.casefold()
        ):
            body_s = (
                first_lines[1].lstrip("\n") if len(first_lines) > 1 else ""
            )
            body_s = clean_markdown(body_s)

    front: list[tuple[str, Any]] = [
        ("title", title_s),
        ("source", source_url),
    ]
    if query:
        front.append(("query", query))
    if topic:
        front.append(("topic", topic))
    if engine:
        front.append(("engine", engine))
    if snippet:
        front.append(("snippet", snippet[:280]))
    if content_type:
        front.append(("content_type", content_type.split(";")[0].strip()))
    if collected_at:
        front.append(("collected_at", collected_at))

    lines = ["---"]
    for key, value in front:
        lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title_s}")
    lines.append("")
    if body_s:
        lines.append(body_s)
        lines.append("")
    return "\n".join(lines)
