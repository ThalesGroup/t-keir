"""Title: Markdown vs raw text → T-KEIR content blocks

Detect whether a string is markdown or plain prose, then split it into
``content`` list items that follow section / subsection boundaries.

Tokenizer treats each ``content`` item as a paragraph, so heading-aware
splits keep NER and golden-chunking aligned with the document outline.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from typing import Iterator

_ATX = re.compile(r"^(#{1,6})[ \t]+(\S.*?)\s*$")
_SETEXT_H1 = re.compile(r"^=+\s*$")
_SETEXT_H2 = re.compile(r"^-+\s*$")
_FENCE = re.compile(r"^(`{3,}|~{3,})")
_FRONTMATTER = re.compile(
    r"\A---[ \t]*\n.*?\n---[ \t]*\n?",
    re.DOTALL,
)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_BULLET = re.compile(r"^(\s*)[-*+]\s+", re.MULTILINE)
_STRONG_HEADING = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)
_STRONG_FENCE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)
_STRONG_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")
_WEAK_LIST = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\S", re.MULTILINE)
_WEAK_BOLD = re.compile(r"\*\*[^*]+\*\*|__[^_]+__")
_WEAK_QUOTE = re.compile(r"^\s*>\s+\S", re.MULTILINE)


def looks_like_markdown(text: str) -> bool:
    """Return True when ``text`` looks like markdown rather than prose.

    Strong signals (one is enough): ATX headings, fenced code, markdown
    links, YAML frontmatter. Weak signals need at least two hits.

    Args:
        text: Candidate document or record body.

    Returns:
        ``True`` when markdown structure is detected.

    Example:
        >>> looks_like_markdown("# Title\\n\\nHello.\\n")
        True
        >>> looks_like_markdown("Cautious calm around Suez.")
        False
        >>> looks_like_markdown("See #Suez in the channel.")
        False
    """
    sample = (text or "").strip()
    if not sample:
        return False
    if sample.startswith("---") and _FRONTMATTER.match(sample):
        return True
    if _STRONG_HEADING.search(sample):
        return True
    if _STRONG_FENCE.search(sample):
        return True
    if _STRONG_LINK.search(sample):
        return True
    weak = 0
    if _WEAK_LIST.search(sample):
        weak += 1
    if _WEAK_BOLD.search(sample):
        weak += 1
    if _WEAK_QUOTE.search(sample):
        weak += 1
    if _SETEXT_H1.search(sample) or _SETEXT_H2.search(sample):
        weak += 1
    return weak >= 2


def unwrap_inline_markdown(text: str) -> str:
    """Strip common inline markdown markers, keep readable words.

    Skips unwrapping when the block contains a fenced code region.

    Args:
        text: One content block.

    Returns:
        Plain-text-ish block.

    Example:
        >>> unwrap_inline_markdown("- **domain:** OSINT")
        'domain: OSINT'
        >>> unwrap_inline_markdown("[Suez](https://ex.example)")
        'Suez'
    """
    if not text:
        return ""
    if _FENCE.search(text) or "```" in text:
        return text
    out = _MD_IMAGE.sub(r"\1", text)
    out = _MD_LINK.sub(r"\1", out)
    out = _MD_BOLD.sub(
        lambda match: match.group(1) or match.group(2) or "", out
    )
    out = _MD_CODE.sub(r"\1", out)
    out = _MD_ITALIC.sub(
        lambda match: match.group(1) or match.group(2) or "", out
    )
    out = _MD_BULLET.sub(r"\1", out)
    return out


def split_paragraphs(text: str) -> list[str]:
    """Split prose on blank lines (markdown / raw paragraph boundaries).

    Args:
        text: Raw or markdown body without heading splits.

    Returns:
        Non-empty paragraph strings.

    Example:
        >>> split_paragraphs("One.\\n\\nTwo.\\n")
        ['One.', 'Two.']
    """
    parts = re.split(r"\n\s*\n+", (text or "").strip())
    return [part.strip() for part in parts if part.strip()]


def _strip_heading_marks(title: str) -> str:
    """Remove trailing ATX hashes from a heading title.

    Example:
        >>> _strip_heading_marks("Background ##")
        'Background'
    """
    return re.sub(r"\s+#+\s*$", "", (title or "").strip()).strip()


def _iter_section_raw(
    text: str,
) -> Iterator[tuple[int, str, str]]:
    """Yield ``(level, heading, body)`` from markdown source.

    Level ``0`` is the preamble before the first heading. Fenced code
    is kept inside the current section.

    Example:
        >>> levels = [item[0] for item in _iter_section_raw("# T\\n\\nHi.\\n")]
        >>> 1 in levels
        True
    """
    body = _FRONTMATTER.sub("", text or "", count=1)
    lines = body.splitlines()
    level = 0
    heading = ""
    buf: list[str] = []
    fence: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if fence is not None:
            buf.append(line)
            if stripped.startswith(fence):
                fence = None
            index += 1
            continue
        fence_match = _FENCE.match(stripped)
        if fence_match is not None:
            fence = fence_match.group(1)[0] * len(fence_match.group(1))
            buf.append(line)
            index += 1
            continue
        atx = _ATX.match(line)
        if atx is not None:
            yield level, heading, "\n".join(buf)
            level = len(atx.group(1))
            heading = _strip_heading_marks(atx.group(2))
            buf = []
            index += 1
            continue
        if (
            index + 1 < len(lines)
            and stripped
            and not stripped.startswith("#")
        ):
            nxt = lines[index + 1].strip()
            if _SETEXT_H1.match(nxt):
                yield level, heading, "\n".join(buf)
                level = 1
                heading = _strip_heading_marks(stripped)
                buf = []
                index += 2
                continue
        buf.append(line)
        index += 1
    yield level, heading, "\n".join(buf)


def _push_heading(
    stack: list[tuple[int, str]], level: int, title: str
) -> list[str]:
    """Update the heading stack and return the breadcrumb titles.

    Example:
        >>> _push_heading([(1, "A")], 2, "B")
        ['A', 'B']
    """
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, title))
    return [item[1] for item in stack]


def markdown_to_content(
    text: str,
    *,
    document_title: str | None = None,
) -> tuple[str, list[str]]:
    """Split markdown into a document title plus section content blocks.

    Each heading starts a new ``content`` item. Subsection items are
    prefixed with a ``Parent / Child`` breadcrumb so NLP still sees the
    outline. The first H1 becomes ``title`` when ``document_title`` is
    empty; a duplicate H1 matching the title is not repeated in content.

    Args:
        text: Markdown source (record body or converted file).
        document_title: Optional title already known (ingest extras).

    Returns:
        ``(title, content_blocks)``.

    Example:
        >>> title, blocks = markdown_to_content(
        ...     "# Report\\n\\nIntro.\\n\\n## Ports\\n\\nSuez is busy.\\n"
        ... )
        >>> title
        'Report'
        >>> blocks[0]
        'Intro.'
        >>> "Ports" in blocks[1] and "Suez is busy." in blocks[1]
        True
    """
    known = (document_title or "").strip()
    title = known
    stack: list[tuple[int, str]] = []
    blocks: list[str] = []
    title_from_h1 = False

    for level, heading, raw_body in _iter_section_raw(text):
        body = raw_body.strip()
        if level == 0:
            blocks.extend(
                unwrap_inline_markdown(part)
                for part in split_paragraphs(body)
            )
            continue
        heading_cf = heading.casefold()
        if level == 1 and not title:
            title = heading
            title_from_h1 = True
            stack = [(1, heading)]
            blocks.extend(
                unwrap_inline_markdown(part)
                for part in split_paragraphs(body)
            )
            continue
        if (
            level == 1
            and title
            and heading_cf == title.casefold()
            and (title_from_h1 or known)
        ):
            stack = [(1, heading)]
            blocks.extend(
                unwrap_inline_markdown(part)
                for part in split_paragraphs(body)
            )
            continue
        crumb_titles = _push_heading(stack, level, heading)
        if (
            known
            and crumb_titles
            and crumb_titles[0].casefold() == known.casefold()
        ):
            crumb_titles = crumb_titles[1:]
        if (
            title_from_h1
            and crumb_titles
            and crumb_titles[0].casefold() == title.casefold()
        ):
            crumb_titles = crumb_titles[1:]
        breadcrumb = " / ".join(crumb_titles)
        if not body and not breadcrumb:
            continue
        if body:
            piece = f"{breadcrumb}\n\n{body}" if breadcrumb else body
        else:
            piece = breadcrumb
        cleaned = unwrap_inline_markdown(piece).strip()
        if cleaned:
            blocks.append(cleaned)
    return title, [item for item in blocks if item]


def text_to_content(
    text: str,
    *,
    document_title: str | None = None,
    markdown: bool | None = None,
) -> tuple[str, list[str], str]:
    """Detect format (unless given) and split into T-KEIR content blocks.

    Args:
        text: Document or record narrative.
        document_title: Optional known title.
        markdown: Force markdown (True) or raw (False); ``None`` detects.

    Returns:
        ``(title, content_blocks, text_format)`` where format is
        ``markdown`` or ``raw``.

    Example:
        >>> title, blocks, fmt = text_to_content("Hello.\\n\\nWorld.\\n")
        >>> fmt, blocks
        ('raw', ['Hello.', 'World.'])
        >>> text_to_content("# A\\n\\nB.\\n")[2]
        'markdown'
    """
    sample = text or ""
    is_md = looks_like_markdown(sample) if markdown is None else bool(markdown)
    if is_md:
        title, blocks = markdown_to_content(
            sample, document_title=document_title
        )
        return title, blocks, "markdown"
    known = (document_title or "").strip()
    blocks = split_paragraphs(sample)
    return known, blocks, "raw"
