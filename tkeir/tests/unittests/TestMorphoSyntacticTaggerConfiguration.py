# -*- coding: utf-8 -*-
"""Test morphosyntactic tagger configuration."""

import json
import os
import unittest

from thot.tasks.morphosyntax.MorphoSyntacticTaggerConfiguration import (
    MorphoSyntacticTaggerConfiguration,
)


class TestMorphoSyntacticTaggerConfiguration(unittest.TestCase):
    test_dict = {
        "logger": {"logging-level": "debug"},
        "morphosyntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": (
                        "/home/tkeir_svc/tkeir/thot/tests/data"
                    ),
                    "mwe": "tkeir_mwe.pkl",
                    "pre-sentencizer": True,
                    "pre-tagging-with-concept": True,
                    "add-concept-in-knowledge-graph": True,
                }
            ],
        },
    }

    def test_load(self):
        with open("/tmp/cfg.json", "w", encoding="utf-8") as handle:
            json.dump(self.test_dict, handle)
        with open("/tmp/cfg.json", encoding="utf-8") as handle:
            config = MorphoSyntacticTaggerConfiguration()
            config.load(handle)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["taggers"],
            self.test_dict["morphosyntax"]["taggers"],
        )
        if os.path.isfile("/tmp/cfg.json"):
            os.remove("/tmp/cfg.json")

    def test_loads(self):
        config = MorphoSyntacticTaggerConfiguration()
        config.loads(self.test_dict)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["taggers"],
            self.test_dict["morphosyntax"]["taggers"],
        )

    def test_clear(self):
        config = MorphoSyntacticTaggerConfiguration()
        config.loads(self.test_dict)
        config.clear()
        self.assertEqual(config.logger_config.logger_name, "default")
        self.assertEqual(config.logger_config.configuration, None)
        self.assertEqual(config.configuration, dict())
