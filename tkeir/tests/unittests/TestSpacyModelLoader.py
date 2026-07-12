# -*- coding: utf-8 -*-
"""Tests for spaCy model selection."""

from unittest.mock import patch

from thot.core.SpacyModelLoader import (
    MULTILINGUAL_MODEL,
    load_spacy_model,
    model_name_candidates,
)


class TestSpacyModelLoader:
    def test_model_candidates_for_english(self):
        assert model_name_candidates("en", size="sm")[0] == "en_core_web_sm"

    def test_model_candidates_for_french(self):
        assert model_name_candidates("fr", size="md")[0] == "fr_core_news_md"

    def test_model_candidates_include_multilingual_fallback(self):
        assert MULTILINGUAL_MODEL in model_name_candidates("de", size="sm")

    @patch("thot.core.SpacyModelLoader.spacy.load")
    def test_loads_language_specific_model(self, mock_load):
        mock_load.return_value = object()
        _, model_name = load_spacy_model("en", size="sm")
        assert model_name == "en_core_web_sm"
        mock_load.assert_called_once_with("en_core_web_sm")

    @patch("thot.core.SpacyModelLoader.spacy.load")
    def test_falls_back_to_multilingual_model(self, mock_load):
        mock_load.side_effect = [
            OSError("missing"),
            OSError("missing"),
            object(),
        ]
        _, model_name = load_spacy_model("de", size="sm")
        assert model_name == MULTILINGUAL_MODEL
        assert mock_load.call_count == 3

    @patch("thot.core.SpacyModelLoader.subprocess.run")
    @patch("thot.core.SpacyModelLoader.spacy.load")
    def test_downloads_primary_model_when_missing(self, mock_load, mock_run):
        mock_load.side_effect = [OSError("missing"), object()]
        _, model_name = load_spacy_model(
            "en", size="md", download_if_missing=True, task_name="morphosyntax"
        )
        assert model_name == "en_core_web_md"
        mock_run.assert_called_once()
        assert mock_load.call_count == 2
