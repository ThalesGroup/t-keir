"""Title: Mark It Down Converter

Convert documents to tkeir format using Microsoft MarkItDown.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import os
import traceback
from io import BytesIO

from thot.core.Constants import exception_error_and_trace
from thot.core.ThotLogger import ThotLogger
from thot.tasks.converters.MarkdownSections import text_to_content
from thot.tasks.converters.PdfImageOcr import build_pdf_content_with_ocr

DATATYPE_EXTENSIONS = {
    "email": ".eml",
    "pdf": ".pdf",
    "docx": ".docx",
    "rtf": ".rtf",
    "html": ".html",
    "htm": ".htm",
    "pptx": ".pptx",
    "ppt": ".ppt",
    "xlsx": ".xlsx",
    "xls": ".xls",
    "csv": ".csv",
    "epub": ".epub",
    "ipynb": ".ipynb",
    "msg": ".msg",
    "rss": ".rss",
    "xml": ".xml",
}


def _pdf_title(data: bytes, fallback: str = "") -> str:
    """Read PDF metadata title, or ``fallback``.

    Example:
        >>> callable(_pdf_title)
        True
    """
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as document:
            meta = document.metadata or {}
            return meta.get("title") or fallback
    except Exception:
        return fallback


def _pdf_inline_markdown(data: bytes, ocr_config) -> tuple[str | None, str]:
    """Extract PDF markdown via UniversalConverter when possible.

    Example:
        >>> callable(_pdf_inline_markdown)
        True
    """
    from thot.tasks.converters.UniversalConverter import _extract_pdf

    try:
        inline = _extract_pdf(data, ocr_config)
    except Exception:
        inline = ""
    if not inline.strip():
        return None, ""
    return inline, _pdf_title(data)


def _pdf_ocr_markdown(data: bytes, ocr_config, call_context):
    """Run PDF OCR fallback; return content, ocr_info, title.

    Example:
        >>> callable(_pdf_ocr_markdown)
        True
    """
    content, ocr_info = build_pdf_content_with_ocr(
        data, ocr_config=ocr_config, call_context=call_context
    )
    if content:
        return content, ocr_info, _pdf_title(data)
    ThotLogger.warning(
        "PDF OCR produced no text; falling back to MarkItDown",
        context=call_context,
    )
    return None, ocr_info, _pdf_title(data, "")


def _markitdown_stream(data: bytes, extension: str, title: str, call_context):
    """Convert bytes with MarkItDown.

    Example:
        >>> callable(_markitdown_stream)
        True
    """
    try:
        result = MarkItDownConverter.get_engine().convert_stream(
            BytesIO(data),
            file_extension=extension,
        )
    except Exception as error:
        ThotLogger.error(
            "MarkItDown conversion failed",
            context=call_context,
            trace=exception_error_and_trace(
                str(error), traceback.format_exc()
            ),
        )
        raise ValueError(
            "MarkItDown conversion failed: " + str(error)
        ) from error
    content = result.text_content or result.markdown or ""
    return content, result.title or title


class MarkItDownConverter:
    """MarkItDownConverter container.

    Example:
        >>> from thot.tasks.converters.MarkItDownConverter import MarkItDownConverter
        >>> callable(MarkItDownConverter)
        True
    """

    _engine = None

    @classmethod
    def get_engine(cls):
        """Return the shared MarkItDown engine instance.

        Returns:
            Lazily initialized ``MarkItDown`` converter.

        Example:
            >>> engine = MarkItDownConverter.get_engine()
            >>> engine is not None
            True
        """
        if cls._engine is None:
            from markitdown import MarkItDown

            cls._engine = MarkItDown(enable_plugins=False)
        return cls._engine

    @staticmethod
    def managed_types():
        """Return supported MarkItDown converter datatypes.

        Returns:
            Sorted list of managed datatype names.

        Example:
            >>> "pdf" in MarkItDownConverter.managed_types()
            True
        """
        return sorted(set(DATATYPE_EXTENSIONS.keys()))

    @staticmethod
    def extension_for(data_type: str, source_doc_id: str) -> str:
        """Resolve the file extension used for MarkItDown conversion.

        Args:
            data_type: Requested converter datatype.
            source_doc_id: Source path or URI used as fallback.

        Returns:
            Lowercase extension including the leading dot.

        Example:
            >>> MarkItDownConverter.extension_for("pdf", "file://doc.pdf")
            '.pdf'
        """
        if data_type in DATATYPE_EXTENSIONS:
            return DATATYPE_EXTENSIONS[data_type]
        if source_doc_id:
            _, extension = os.path.splitext(source_doc_id.split("?")[0])
            if extension:
                return extension.lower()
        return ".bin"

    @staticmethod
    def convert(
        data: bytes,
        source_doc_id: str,
        data_type: str,
        call_context=None,
        ocr_config=None,
    ):
        """Convert binary document bytes to a T-KEIR document.

        Args:
            data: Raw document bytes.
            source_doc_id: Source identifier for the document.
            data_type: Converter datatype name.
            call_context: Optional logger context.
            ocr_config: Optional PDF OCR settings.

        Returns:
            T-KEIR document dictionary produced by MarkItDown or PDF OCR.

        Raises:
            ValueError: When MarkItDown conversion fails.

        Example:
            >>> isinstance(MarkItDownConverter.convert, type(MarkItDownConverter.managed_types))
            True
        """
        ThotLogger.debug("Call MarkItDown Converter", context=call_context)
        extension = MarkItDownConverter.extension_for(data_type, source_doc_id)
        content: str | None = None
        title = ""
        ocr_info = {
            "enabled": bool(ocr_config and ocr_config.get("enabled")),
            "used": False,
            "mode": (ocr_config or {}).get("mode"),
            "image-regions": 0,
            "scanned-pages": 0,
        }
        if extension == ".pdf":
            content, title = _pdf_inline_markdown(data, ocr_config)
        if (
            content is None
            and extension == ".pdf"
            and ocr_config
            and ocr_config.get("enabled")
        ):
            content, ocr_info, title = _pdf_ocr_markdown(
                data, ocr_config, call_context
            )
        if content is None:
            content, title = _markitdown_stream(
                data, extension, title, call_context
            )
        extracted_title, blocks, text_fmt = text_to_content(
            content or "", document_title=title or None
        )
        title = title or extracted_title
        if not blocks and (content or "").strip():
            blocks = [content.strip()]
        return {
            "data_source": "converter-service",
            "source_doc_id": source_doc_id,
            "title": title,
            "content": blocks,
            "kg": [],
            "error": False,
            "conversion-info": {
                "datatype": data_type,
                "source-size-bytes": len(data),
                "image-extraction": ocr_info,
                "text-format": text_fmt,
                "content-blocks": len(blocks),
            },
        }
