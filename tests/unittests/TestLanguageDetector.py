"""Title: Language Detector

Tests for language detection.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from unittest.mock import patch

from thot.tasks.language_detection.LanguageDetector import LanguageDetector


class TestLanguageDetector:
    def test_short_text_defaults_to_en(self):
        result = LanguageDetector.detect("hello")
        assert result.language == "en"
        assert result.confidence == 0.0

    @patch("langdetect.detect_langs")
    def test_detect_english(self, mock_detect):
        mock_detect.return_value = [
            type("Lang", (), {"lang": "en", "prob": 0.99})()
        ]
        result = LanguageDetector.detect(
            "This is an English sentence about energy production."
        )
        assert result.language == "en"
        assert result.confidence > 0.9

    @patch("langdetect.detect_langs", side_effect=Exception("boom"))
    def test_detect_failure_fallback(self, _mock_detect):
        result = LanguageDetector.detect(
            "This is an English sentence about energy production."
        )
        assert result.language == "en"
        assert result.confidence == 0.0

    def test_detect_document_adds_task_info(self):
        document = {
            "title": "",
            "content": [
                "This is an English sentence about energy production and trading."
            ],
        }
        result = LanguageDetector.detect_document(document)
        assert "language-detection" in result
        assert "tasks-info" in result
        assert result["language-detection"]["language"] == "en"
