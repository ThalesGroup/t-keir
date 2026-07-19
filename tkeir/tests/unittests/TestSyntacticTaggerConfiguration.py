"""Test syntactic tagger configuration."""

import json
import os
import unittest

from thot.tasks.syntax.SyntacticTaggerConfiguration import (
    SyntacticTaggerConfiguration,
)


class TestSyntacticTaggerConfiguration(unittest.TestCase):
    test_dict = {
        "logger": {"logging-level": "debug"},
        "syntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": (
                        "/home/tkeir_svc/tkeir/thot/tests/data"
                    ),
                    "syntactic-rules": "syntactic-rules.json",
                }
            ],
        },
    }

    def test_load(self):
        with open("/tmp/cfg.json", "w", encoding="utf-8") as handle:
            json.dump(self.test_dict, handle)
        with open("/tmp/cfg.json", encoding="utf-8") as handle:
            config = SyntacticTaggerConfiguration()
            config.load(handle)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["taggers"],
            self.test_dict["syntax"]["taggers"],
        )
        if os.path.isfile("/tmp/cfg.json"):
            os.remove("/tmp/cfg.json")

    def test_loads(self):
        config = SyntacticTaggerConfiguration()
        config.loads(self.test_dict)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["taggers"],
            self.test_dict["syntax"]["taggers"],
        )

    def test_clear(self):
        config = SyntacticTaggerConfiguration()
        config.loads(self.test_dict)
        config.clear()
        self.assertEqual(config.logger_config.logger_name, "default")
        self.assertEqual(config.logger_config.configuration, None)
        self.assertEqual(config.configuration, dict())
