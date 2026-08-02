"""Title: Resource Selector

Tests for resource selection.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.TkeirPaths import resources_dir
from thot.tasks.pipeline.ResourceSelector import ResourceSelector


class TestResourceSelector:
    def test_list_available_languages_contains_en(self):
        assert "en" in ResourceSelector.list_available_languages()

    def test_select_existing_language(self):
        assert ResourceSelector.select("en") == resources_dir("en")

    def test_select_missing_language(self):
        assert ResourceSelector.select("zz") is None

    def test_processing_language_fallback(self):
        assert ResourceSelector.processing_language("de") == "en"
        assert ResourceSelector.processing_language("fr") == "fr"

    def test_processing_language_invalid_default(self):
        assert ResourceSelector.processing_language("de", "de") == "en"

    def test_select_empty_language(self):
        assert ResourceSelector.select("") is None

    def test_annotate_document(self):
        document = {"content": ["sample"]}
        result = ResourceSelector.annotate_document(document, "en")
        assert result["resource-selection"]["detected-language"] == "en"
        assert result["resource-selection"][
            "resources-base-path"
        ] == resources_dir("en")

    def test_annotate_document_missing_language_falls_back(self):
        document = {"content": ["sample"]}
        result = ResourceSelector.annotate_document(document, "zz")
        assert result["resource-selection"]["detected-language"] == "zz"
        assert result["resource-selection"]["processing-language"] == "en"
        assert result["resource-selection"][
            "resources-base-path"
        ] == resources_dir("en")
