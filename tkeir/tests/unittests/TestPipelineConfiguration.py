# -*- coding: utf-8 -*-
"""Tests for pipeline configuration."""

import os

from thot.core.TkeirPaths import configs_dir, resources_dir
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration


class TestPipelineConfiguration:
    def test_load_pipeline_config(self):
        config = PipelineConfiguration()
        with open(
            os.path.join(configs_dir(), "pipeline.json"), encoding="utf-8"
        ) as handle:
            config.load(handle)
        assert config.configuration["default-language"] == "en"
        assert "tokenizer" in config.task_configs
        assert "chunking" in config.task_configs
        assert "ontology" in config.task_configs
        assert "chunk-questions" in config.task_configs

    def test_apply_language_sets_resources(self):
        config = PipelineConfiguration()
        with open(
            os.path.join(configs_dir(), "pipeline.json"), encoding="utf-8"
        ) as handle:
            config.load(handle)
        resource_path = resources_dir("en")
        config.apply_language("en", resource_path)
        assert (
            config.task_configs["tokenizer"].configuration["segmenters"][0][
                "language"
            ]
            == "en"
        )
        assert (
            config.task_configs["tokenizer"].configuration["segmenters"][0][
                "resources-base-path"
            ]
            == resource_path
        )

    def test_apply_language_without_resources(self):
        config = PipelineConfiguration()
        with open(
            os.path.join(configs_dir(), "pipeline.json"), encoding="utf-8"
        ) as handle:
            config.load(handle)
        original = config.task_configs["ner"].configuration["label"][0][
            "resources-base-path"
        ]
        config.apply_language("en", None)
        resolved = config.task_configs["ner"].configuration["label"][0][
            "resources-base-path"
        ]
        assert resolved is not None
        if original:
            assert resolved == original or os.path.isdir(resolved)

    def test_apply_language_uses_spacy_language_for_models(self):
        config = PipelineConfiguration()
        with open(
            os.path.join(configs_dir(), "pipeline.json"), encoding="utf-8"
        ) as handle:
            config.load(handle)
        resource_path = resources_dir("en")
        config.apply_language("en", resource_path, spacy_language="de")
        assert (
            config.task_configs["tokenizer"].configuration["segmenters"][0][
                "language"
            ]
            == "de"
        )
        assert (
            config.task_configs["keywords"].configuration["extractors"][0][
                "language"
            ]
            == "en"
        )

    def test_apply_use_mwe(self):
        config = PipelineConfiguration()
        with open(
            os.path.join(configs_dir(), "pipeline.json"), encoding="utf-8"
        ) as handle:
            config.load(handle)
        config.apply_use_mwe(True)
        for task_name, entry_key in (
            ("tokenizer", "segmenters"),
            ("morphosyntax", "taggers"),
            ("ner", "label"),
            ("syntax", "taggers"),
        ):
            entry = config.task_configs[task_name].configuration[entry_key][0]
            assert entry["use-mwe"] is True
            assert entry["mwe"] == "tkeir_mwe.pkl"
