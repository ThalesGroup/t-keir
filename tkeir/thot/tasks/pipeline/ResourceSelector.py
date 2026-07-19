"""Select lexical resource directory for a detected language."""

import os

from thot.core.ThotLogger import ThotLogger
from thot.core.TkeirPaths import package_root
from thot.tasks.pipeline import __date_pipeline__, __version_pipeline__
from thot.tasks.TaskInfo import TaskInfo

SUPPORTED_PROCESSING_LANGUAGES = {"en", "fr"}


class ResourceSelector:
    @staticmethod
    def list_available_languages() -> list:
        """List tokenizer resource languages bundled with T-KEIR.

        Returns:
            Sorted language codes with resource directories.

        Example:
            >>> "en" in ResourceSelector.list_available_languages()
            True
        """
        base = os.path.join(
            package_root(), "resources", "modeling", "tokenizer"
        )
        if not os.path.isdir(base):
            return []
        return sorted(
            entry
            for entry in os.listdir(base)
            if os.path.isdir(os.path.join(base, entry))
        )

    @staticmethod
    def select(language: str) -> str | None:
        """Return the tokenizer resource path for a language when present.

        Args:
            language: ISO language code.

        Returns:
            Absolute resources path, or ``None`` when missing.

        Example:
            >>> ResourceSelector.select("en") is None or ResourceSelector.select("en").endswith("en")
            True
        """
        if not language:
            return None
        candidate = os.path.join(
            package_root(), "resources", "modeling", "tokenizer", language
        )
        if os.path.isdir(candidate):
            return candidate
        return None

    @staticmethod
    def processing_language(
        detected_language: str, default_language: str = "en"
    ) -> str:
        """Pick a supported processing language with fallback.

        Args:
            detected_language: Language detected in the document.
            default_language: Fallback when detection is unsupported.

        Returns:
            ``en`` or ``fr`` processing language code.

        Example:
            >>> ResourceSelector.processing_language("de", "en")
            'en'
        """
        if detected_language in SUPPORTED_PROCESSING_LANGUAGES:
            return detected_language
        if default_language in SUPPORTED_PROCESSING_LANGUAGES:
            return default_language
        return "en"

    @staticmethod
    def annotate_document(
        document: dict,
        detected_language: str,
        default_language: str = "en",
        call_context=None,
    ) -> dict:
        """Add resource-selection metadata to a pipeline document.

        Args:
            document: Pipeline JSON document.
            detected_language: Detected language code.
            default_language: Fallback language.
            call_context: Optional logging context.

        Returns:
            Document enriched with ``resource-selection`` and task info.

        Example:
            >>> doc = ResourceSelector.annotate_document({}, "en")
            >>> doc["resource-selection"]["processing-language"]
            'en'
        """
        resource_path = ResourceSelector.select(detected_language)
        processing_language = ResourceSelector.processing_language(
            detected_language, default_language
        )
        if resource_path is None and processing_language != detected_language:
            resource_path = ResourceSelector.select(processing_language)

        document["resource-selection"] = {
            "detected-language": detected_language,
            "processing-language": processing_language,
            "spacy-language": detected_language,
            "resources-base-path": resource_path,
            "available-languages": ResourceSelector.list_available_languages(),
        }
        ThotLogger.debug(
            "Selected resources for language "
            + detected_language
            + " -> "
            + str(resource_path),
            context=call_context,
        )
        task_info = TaskInfo(
            task_name="resource-selection",
            task_version=__version_pipeline__,
            task_date=__date_pipeline__,
        )
        return task_info.addInfo(document)
