"""Title: Raw Text Converter

Convert plain text or markdown documents to tkeir format.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from bs4 import BeautifulSoup

from thot.core.ThotLogger import ThotLogger
from thot.tasks.converters.MarkdownSections import (
    looks_like_markdown,
    text_to_content,
)


class RawTextConverter:
    """RawTextConverter container.

    Example:
        >>> from thot.tasks.converters.RawTextConverter import RawTextConverter
        >>> callable(RawTextConverter)
        True
    """

    @staticmethod
    def convert(data: bytes, source_doc_id: str, call_context=None):
        """Decode UTF-8 and split content on paragraphs or markdown sections.

        Markdown (ATX headings, fenced code, or links) is detected
        automatically. HTML markup is stripped only for non-markdown text.

        Args:
            data: Raw document bytes.
            source_doc_id: Source identifier for the document.
            call_context: Optional logger context.

        Returns:
            T-KEIR document with ``content`` as a list of section blocks.

        Example:
            >>> import logging
            >>> logging.disable(logging.CRITICAL)
            >>> from thot.tasks.converters.RawTextConverter import (
            ...     RawTextConverter,
            ... )
            >>> doc = RawTextConverter.convert(
            ...     b"Hello converter", "file://t.txt"
            ... )
            >>> doc["content"]
            ['Hello converter']
        """
        ThotLogger.debug("Call Raw Text Converter", context=call_context)
        text = data.decode("utf-8", errors="replace")
        markdown = looks_like_markdown(text)
        if (not markdown) and "<" in text and ">" in text:
            text = BeautifulSoup(text, "html.parser").get_text()
        title, content, fmt = text_to_content(text, markdown=markdown)
        if not content and text.strip():
            content = [text.strip()]
        return {
            "data_source": "converter-service",
            "source_doc_id": source_doc_id,
            "title": title,
            "content": content,
            "kg": [],
            "error": False,
            "conversion-info": {
                "text-format": fmt,
                "content-blocks": len(content),
            },
        }
