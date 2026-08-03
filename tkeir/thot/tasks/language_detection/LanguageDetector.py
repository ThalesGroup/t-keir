"""Title: Language Detector

Detect document language from plain text.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from dataclasses import dataclass

from thot.core.ThotLogger import ThotLogger
from thot.tasks.language_detection import (
    __date_language_detection__,
    __version_language_detection__,
)
from thot.tasks.TaskInfo import TaskInfo


@dataclass
class LanguageDetectionResult:
    """LanguageDetectionResult container.
    
        Example:
            >>> from thot.tasks.language_detection.LanguageDetector import LanguageDetectionResult
            >>> callable(LanguageDetectionResult)
            True
    """
    language: str
    confidence: float

    def to_document_fields(self) -> dict:
        """Serialize detection output for pipeline documents.

        Returns:
            Dict with ``language`` and ``confidence`` keys.

        Example:
            >>> LanguageDetectionResult("fr", 0.91).to_document_fields()["language"]
            'fr'
        """
        return {
            "language": self.language,
            "confidence": self.confidence,
        }


class LanguageDetector:
    """Detect language using langdetect with a safe fallback.
    
        Example:
            >>> from thot.tasks.language_detection.LanguageDetector import LanguageDetector
            >>> callable(LanguageDetector)
            True
    """

    MIN_TEXT_LENGTH = 20
    DEFAULT_LANGUAGE = "en"

    @staticmethod
    def _normalize_language(code: str) -> str:
        """Normalize a language code to a two-letter lowercase tag.

        Args:
            code: Language code such as ``en-US``.

        Returns:
            Lowercase primary language subtag.

        Example:
            >>> LanguageDetector._normalize_language("en-US")
            'en'
        """
        if not code:
            return LanguageDetector.DEFAULT_LANGUAGE
        return code.split("-")[0].lower()

    @staticmethod
    def detect(text: str, call_context=None) -> LanguageDetectionResult:
        """Detect language from plain text.

        Args:
            text: Input text to analyze.
            call_context: Optional logger context.

        Returns:
            Detection result with language and confidence.

        Example:
            >>> result = LanguageDetector.detect(
            ...     "This is an English sentence for language detection."
            ... )
            >>> result.language
            'en'
        """
        cleaned = " ".join((text or "").split())
        if len(cleaned) < LanguageDetector.MIN_TEXT_LENGTH:
            ThotLogger.debug(
                "Text too short for language detection, using default",
                context=call_context,
            )
            return LanguageDetectionResult(
                language=LanguageDetector.DEFAULT_LANGUAGE,
                confidence=0.0,
            )
        try:
            from langdetect import DetectorFactory, detect_langs

            DetectorFactory.seed = 0
            candidates = detect_langs(cleaned)
            if not candidates:
                raise ValueError("no language candidate")
            best = candidates[0]
            return LanguageDetectionResult(
                language=LanguageDetector._normalize_language(best.lang),
                confidence=float(best.prob),
            )
        except Exception as error:
            ThotLogger.warning(
                "Language detection failed, using default: " + str(error),
                context=call_context,
            )
            return LanguageDetectionResult(
                language=LanguageDetector.DEFAULT_LANGUAGE,
                confidence=0.0,
            )

    @staticmethod
    def detect_document(document: dict, call_context=None) -> dict:
        """Detect language from a T-KEIR document and annotate it.

        Args:
            document: Document with optional ``title`` and ``content``.
            call_context: Optional logger context.

        Returns:
            The same document with ``language-detection`` metadata added.

        Example:
            >>> LanguageDetector.detect_document.__name__
            'detect_document'
        """
        parts = []
        if document.get("title"):
            parts.append(str(document["title"]))
        content = document.get("content")
        if isinstance(content, list):
            parts.extend(str(item) for item in content)
        elif content:
            parts.append(str(content))
        result = LanguageDetector.detect(
            " ".join(parts), call_context=call_context
        )
        document["language-detection"] = result.to_document_fields()
        task_info = TaskInfo(
            task_name="language-detection",
            task_version=__version_language_detection__,
            task_date=__date_language_detection__,
        )
        return task_info.addInfo(document)
