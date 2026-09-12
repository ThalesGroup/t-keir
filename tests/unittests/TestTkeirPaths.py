"""Title: Tkeir Paths

Automated tests for T-KEIR (unit / functional).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import os

from thot.core.ConfigurationUtils import load_json_configuration
from thot.core.TkeirPaths import (
    blip_model_dir,
    configs_dir,
    effective_resources_path,
    package_root,
    rag_prompts_path,
    repo_root,
    resolve_mwe_path,
    resolve_path,
    resolve_tkeir_paths,
    resources_dir,
    shared_resources_dir,
    spacy_models_dir,
    tessdata_dir,
    vespa_dir,
)


class TestTkeirPaths:
    def test_package_paths(self):
        root = package_root()
        assert os.path.isdir(root)
        assert os.path.isdir(configs_dir())
        assert os.path.isdir(resources_dir())
        assert os.path.isdir(shared_resources_dir())
        assert os.path.isfile(
            os.path.join(shared_resources_dir(), "rivers.txt")
        )
        assert os.path.isfile(
            os.path.join(shared_resources_dir(), "lakes.txt")
        )
        assert os.path.isfile(
            os.path.join(shared_resources_dir(), "mountains.txt")
        )
        assert os.path.isfile(
            os.path.join(shared_resources_dir(), "regions.txt")
        )
        found = resolve_mwe_path(resources_dir("en"))
        assert found is None or found.endswith("tkeir_mwe.pkl")

    def test_resolve_path(self):
        root = package_root()
        absolute = os.path.join(
            root, "resources", "modeling", "tokenizer", "en"
        )
        assert resolve_path("resources/modeling/tokenizer/en") == absolute
        assert resolve_path(absolute) == absolute

    def test_resolve_tkeir_paths(self):
        configuration = {
            "segmenters": [
                {"resources-base-path": "resources/modeling/tokenizer/en"}
            ]
        }
        resolve_tkeir_paths(configuration)
        assert configuration["segmenters"][0]["resources-base-path"].endswith(
            "resources/modeling/tokenizer/en"
        )

    def test_load_json_configuration(self):
        config_path = os.path.join(configs_dir(), "converter.yaml")
        with open(config_path, encoding="utf-8") as config_f:
            configuration = load_json_configuration(config_f)
        assert "converter" in configuration

    def test_effective_resources_path_falls_back_to_language(self):
        assert effective_resources_path(None, "en") == resources_dir("en")
        assert effective_resources_path(
            resources_dir("en"), "en"
        ) == resources_dir("en")

    def test_tool_paths(self):
        assert os.path.isdir(vespa_dir())
        assert os.path.isfile(rag_prompts_path())
        assert rag_prompts_path().startswith(configs_dir())
        assert vespa_dir().startswith(repo_root())
        assert spacy_models_dir().endswith("resources/modeling/spacy")
        assert tessdata_dir().endswith("resources/modeling/tesseract")
        assert blip_model_dir().endswith(
            "resources/modeling/net/blip-image-captioning-base"
        )
