"""Title: Convert source document to tkeir indexer document

Document conversion into T-KEIR JSON.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import base64
import json

from thot.core.ThotLogger import ThotLogger
from thot.tasks.converters import __date_converter__, __version_converter__
from thot.tasks.converters.InputFormat import (
    has_extractable_text,
    is_binary_document,
)
from thot.tasks.converters.MarkItDownConverter import MarkItDownConverter
from thot.tasks.converters.RawTextConverter import RawTextConverter
from thot.tasks.TaskInfo import TaskInfo


def _default_image_extraction() -> dict:
    """Return default OCR/image extraction metadata.

    Returns:
        Disabled image extraction stats.

    Example:
        >>> info = _default_image_extraction()
        >>> info["enabled"]
        False
    """
    return {
        "enabled": False,
        "used": False,
        "mode": None,
        "image-regions": 0,
        "scanned-pages": 0,
    }


def _conversion_info(data_type: str, size: int, **extra) -> dict:
    """Build converter ``conversion-info`` metadata.

    Args:
        data_type: Converter datatype string.
        size: Source payload size in bytes.
        **extra: Additional conversion-info fields.

    Returns:
        Conversion metadata dictionary.

    Example:
        >>> info = _conversion_info("raw", 12)
        >>> info["source-size-bytes"]
        12
    """
    info = {
        "datatype": data_type,
        "source-size-bytes": size,
        "image-extraction": _default_image_extraction(),
    }
    info.update(extra)
    return info


class Converter:
    def __init__(self, config=None):
        """Initialize converter with optional configuration.

        Args:
            config: Optional ``ConverterConfiguration`` instance.

        Example:
            >>> "raw" in Converter().listTypes()
            True
        """
        self.config = config
        self._managed_type = set(["tkeir", "raw"]) | set(
            MarkItDownConverter.managed_types()
        )

    def listTypes(self) -> list:
        """Return supported converter datatypes.

        Returns:
            Sorted list of managed datatype names.

        Example:
            >>> "pdf" in Converter().listTypes()
            True
        """
        return sorted(self._managed_type)

    def _convert_tkeir_payload(
        self, data_decode: bytes, data_type: str
    ) -> dict:
        """Load an existing T-KEIR JSON payload into a document dict.

        Args:
            data_decode: Decoded JSON bytes.
            data_type: Converter datatype string.

        Returns:
            Normalized T-KEIR document with conversion metadata.

        Example:
            >>> payload = b'{"content": ["Body"]}'
            >>> doc = Converter()._convert_tkeir_payload(payload, "tkeir")
            >>> doc["content"]
            ['Body']
        """
        loaded_tkeir_doc = json.loads(data_decode.decode())
        for field, default in (
            ("title", ""),
            ("content", []),
            ("data_source", ""),
            ("source_doc_id", ""),
            ("kg", []),
        ):
            loaded_tkeir_doc.setdefault(field, default)
        return {
            "data_source": loaded_tkeir_doc["data_source"],
            "source_doc_id": loaded_tkeir_doc["source_doc_id"],
            "title": loaded_tkeir_doc["title"],
            "content": loaded_tkeir_doc["content"],
            "kg": loaded_tkeir_doc["kg"],
            "error": False,
            "conversion-info": _conversion_info(data_type, len(data_decode)),
        }

    def _ocr_config(self) -> dict | None:
        """Return OCR settings from converter configuration.

        Returns:
            OCR settings dict, or ``None`` when unavailable.

        Example:
            >>> Converter()._ocr_config() is None
            True
        """
        if not self.config or not self.config.configuration:
            return None
        return self.config.configuration.get("settings", {}).get("ocr")

    def _raw_fallback_document(
        self,
        data_decode: bytes,
        source: str,
        data_type: str,
        call_context,
        *,
        image_extraction: dict | None = None,
    ) -> dict:
        """Convert bytes as raw text after a specialized conversion failure.

        Args:
            data_decode: Raw document bytes.
            source: Source identifier.
            data_type: Original requested datatype.
            call_context: Optional logger context.
            image_extraction: Optional OCR stats to preserve.

        Returns:
            Raw T-KEIR document with fallback conversion metadata.

        Example:
            >>> fb = Converter()._raw_fallback_document
            >>> fb.__name__
            '_raw_fallback_document'
        """
        tkeir_doc = RawTextConverter.convert(
            data_decode, source, call_context=call_context
        )
        tkeir_doc["conversion-info"] = _conversion_info(
            "raw",
            len(data_decode),
            **{"fallback-from": data_type},
        )
        if image_extraction is not None:
            tkeir_doc["conversion-info"]["image-extraction"] = image_extraction
        return tkeir_doc

    def _convert_markitdown_type(
        self,
        data_decode: bytes,
        source: str,
        data_type: str,
        call_context,
    ) -> dict:
        """Convert a MarkItDown-managed datatype with raw fallback.

        Args:
            data_decode: Raw document bytes.
            source: Source identifier.
            data_type: MarkItDown datatype name.
            call_context: Optional logger context.

        Returns:
            Converted T-KEIR document, possibly via raw fallback.

        Raises:
            ValueError: When conversion fails and raw fallback is impossible.

        Example:
            >>> isinstance(Converter()._convert_markitdown_type, type(Converter().convert))
            True
        """
        ocr_config = self._ocr_config()
        try:
            tkeir_doc = MarkItDownConverter.convert(
                data_decode,
                source,
                data_type,
                call_context=call_context,
                ocr_config=ocr_config,
            )
        except ValueError as error:
            if not has_extractable_text(data_decode):
                raise
            ThotLogger.warning(
                "Converter could not read '"
                + data_type
                + "' for "
                + source
                + "; falling back to raw text: "
                + str(error),
                context=call_context,
            )
            return self._raw_fallback_document(
                data_decode, source, data_type, call_context
            )

        content = tkeir_doc.get("content") or []
        if (
            not content or not str(content[0]).strip()
        ) and has_extractable_text(data_decode):
            ThotLogger.warning(
                "Converter produced no text for '"
                + data_type
                + "'; falling back to raw for "
                + source,
                context=call_context,
            )
            image_extraction = tkeir_doc.get("conversion-info", {}).get(
                "image-extraction", _default_image_extraction()
            )
            return self._raw_fallback_document(
                data_decode,
                source,
                data_type,
                call_context,
                image_extraction=image_extraction,
            )
        return tkeir_doc

    def convert(
        self,
        data_type: str = "raw",
        data: str | None = None,
        source: str = "empty",
        call_context=None,
        tags=[],
    ):
        """Convert a base64-encoded document to T-KEIR format.

        Args:
            data_type: Converter datatype name.
            data: Base64-encoded document bytes.
            source: Source identifier for the document.
            call_context: Optional logger context.
            tags: Optional keyword tags appended to ``kg``.

        Returns:
            T-KEIR document enriched with task metadata.

        Raises:
            ValueError: When datatype, payload, or content is invalid.

        Example:
            >>> import base64
            >>> payload = base64.b64encode(b"x").decode()
            >>> try:
            ...     Converter().convert("unknown", payload)
            ... except ValueError as exc:
            ...     "not managed" in str(exc)
            ... else:
            ...     False
            True
        """
        if data_type not in self._managed_type:
            raise ValueError("Type '" + data_type + "' is not managed.")
        if data is None:
            raise ValueError("Converter data is mandatory.")
        data_decode = base64.b64decode(data)

        if data_type == "tkeir":
            tkeir_doc = self._convert_tkeir_payload(data_decode, data_type)
        elif data_type == "raw":
            if is_binary_document(data_decode):
                raise ValueError(
                    "Binary documents cannot be converted as raw text; "
                    "use datatype 'auto' or a specific format such as 'pdf'"
                )
            tkeir_doc = RawTextConverter.convert(
                data_decode, source, call_context=call_context
            )
            tkeir_doc["conversion-info"] = _conversion_info(
                data_type, len(data_decode)
            )
        else:
            tkeir_doc = self._convert_markitdown_type(
                data_decode, source, data_type, call_context
            )

        if ("title" not in tkeir_doc) and ("content" not in tkeir_doc):
            raise ValueError("Title and/or Content is mandatory")
        if (not tkeir_doc["content"]) and (not tkeir_doc["title"]):
            raise ValueError("Document is empty")

        for tag in tags:
            tkeir_doc["kg"].append(
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "keywords",
                    "property": {
                        "content": "rel:is_a",
                        "label_content": "",
                        "lemma_content": "rel:is_a",
                        "class": -1,
                        "positions": [-1],
                    },
                    "subject": {
                        "content": tag,
                        "label_content": "",
                        "lemma_content": tag.lower(),
                        "class": -1,
                        "positions": [-1],
                    },
                    "value": {
                        "content": "tag",
                        "label_content": "",
                        "lemma_content": "tag",
                        "class": -1,
                        "positions": [-1],
                    },
                    "weight": 0.0,
                }
            )
        taskInfo = TaskInfo(
            task_name="converter",
            task_version=__version_converter__,
            task_date=__date_converter__,
        )
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        return tkeir_doc

    def run(self, data: dict, call_context=None):
        """Run conversion from a pipeline-style input dict.

        Args:
            data: Dict with ``datatype``, ``data``, and ``source`` keys.
            call_context: Optional logger context.

        Returns:
            Converted T-KEIR document.

        Example:
            >>> import base64
            >>> payload = base64.b64encode(b"x").decode()
            >>> try:
            ...     Converter().run(
            ...         {"datatype": "unknown", "data": payload, "source": "file://x"}
            ...     )
            ... except ValueError as exc:
            ...     "not managed" in str(exc)
            ... else:
            ...     False
            True
        """
        return self.convert(
            data_type=data["datatype"],
            data=data["data"],
            source=data["source"],
            call_context=call_context,
        )
