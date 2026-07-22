"""Title: Raw Text Converter

Convert plain text documents to tkeir format.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from bs4 import BeautifulSoup

from thot.core.ThotLogger import ThotLogger


class RawTextConverter:
    @staticmethod
    def convert(data: bytes, source_doc_id: str, call_context=None):
        """Decode bytes as UTF-8 text and strip HTML markup when present.

        Args:
            data: Raw document bytes.
            source_doc_id: Source identifier for the document.
            call_context: Optional logger context.

        Returns:
            T-KEIR document dictionary with plain-text content.

        Example:
            >>> from bs4 import BeautifulSoup
            >>> BeautifulSoup("<p>Hi</p>", "html.parser").get_text()
            'Hi'
        """
        ThotLogger.debug("Call Raw Text Converter", context=call_context)
        text = data.decode("utf-8", errors="replace")
        if "<" in text and ">" in text:
            text = BeautifulSoup(text, "html.parser").get_text()
        return {
            "data_source": "converter-service",
            "source_doc_id": source_doc_id,
            "title": "",
            "content": [text],
            "kg": [],
            "error": False,
        }
