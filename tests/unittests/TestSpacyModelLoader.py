"""Title: Spacy Model Loader

Tests for spaCy model selection.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from pathlib import Path
from unittest.mock import patch

from thot.core.SpacyModelLoader import (
    MULTILINGUAL_MODEL,
    blank_model_name,
    clear_spacy_model_cache,
    load_spacy_model,
    model_name_candidates,
    resolve_spacy_load_name,
)


class TestSpacyModelLoader:
    def setup_method(self):
        clear_spacy_model_cache()

    def teardown_method(self):
        clear_spacy_model_cache()

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
        assert "en_core_web_sm" in str(mock_load.call_args[0][0])

    @patch("thot.core.SpacyModelLoader.spacy.load")
    def test_reuses_cached_model(self, mock_load):
        mock_load.return_value = object()
        first, _ = load_spacy_model("en", size="sm")
        second, _ = load_spacy_model("en", size="sm")
        assert first is second
        assert mock_load.call_count == 1
        assert "en_core_web_sm" in str(mock_load.call_args[0][0])

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

    @patch("thot.tools.install_spacy_models.install_one_model")
    @patch("thot.core.SpacyModelLoader.spacy.load")
    def test_downloads_primary_model_when_missing(
        self, mock_load, mock_install
    ):
        mock_load.side_effect = [OSError("missing"), object()]
        _, model_name = load_spacy_model(
            "en", size="md", download_if_missing=True, task_name="morphosyntax"
        )
        assert model_name == "en_core_web_md"
        mock_install.assert_called_once()
        assert mock_load.call_count == 2

    def test_resolve_prefers_resources_directory(self, tmp_path):
        from thot.core.SpacyModelLoader import resolve_spacy_load_name

        model = "en_core_web_sm"
        versioned = tmp_path / model / f"{model}-3.6.0"
        versioned.mkdir(parents=True)
        (versioned / "config.cfg").write_text("[nlp]\n", encoding="utf-8")
        resolved = resolve_spacy_load_name(model, models_dir=str(tmp_path))
        assert resolved == str(versioned)

    def test_extract_wheel_into_resources(self, tmp_path):
        import zipfile

        from thot.tools.install_spacy_models import extract_spacy_wheel

        model = "xx_ent_wiki_sm"
        staging = tmp_path / "src"
        inner = staging / model / f"{model}-3.6.0"
        inner.mkdir(parents=True)
        (inner / "config.cfg").write_text("[nlp]\n", encoding="utf-8")
        wheel = tmp_path / "model.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            for path in inner.rglob("*"):
                archive.write(path, path.relative_to(staging).as_posix())
        dest = tmp_path / "spacy"
        extract_spacy_wheel(wheel, dest, model)
        resolved = resolve_spacy_load_name(model, models_dir=str(dest))
        assert Path(resolved).name.startswith(model)
        assert (Path(resolved) / "config.cfg").is_file()

    def test_arabic_uses_blank_pipeline(self):
        nlp, model_name = load_spacy_model("ar", size="sm")
        assert model_name == blank_model_name("ar")
        assert nlp.lang == "ar"
        tokens = [token.text for token in nlp("الجيش اللبناني في بيروت")]
        assert "الجيش" in tokens
        assert "اللبناني" in tokens

    def test_arabic_does_not_call_missing_ar_core(self):
        from unittest.mock import patch

        with patch("thot.core.SpacyModelLoader.spacy.load") as mock_load:
            _, model_name = load_spacy_model("ar")
        assert model_name == "blank:ar"
        mock_load.assert_not_called()
