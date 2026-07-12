# -*- coding: utf-8 -*-
"""Test keywords configuration."""

import json
import os
import unittest

from thot.tasks.keywords.KeywordsConfiguration import KeywordsConfiguration


class TestKeywordsConfiguration(unittest.TestCase):
    test_dict = {
        "logger": {"logging-level": "debug"},
        "keywords": {
            "extractors": [
                {
                    "language": "en",
                    "prunning": 10,
                    "resources-base-path": (
                        "/home/tkeir_svc/tkeir/thot/tests/data"
                    ),
                    "keywords-rules": "tokenizer-rules.json",
                }
            ],
        },
    }

    def test_load(self):
        with open("/tmp/cfg.json", "w", encoding="utf-8") as handle:
            json.dump(self.test_dict, handle)
        with open("/tmp/cfg.json", encoding="utf-8") as handle:
            config = KeywordsConfiguration()
            config.load(handle)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["extractors"],
            self.test_dict["keywords"]["extractors"],
        )
        if os.path.isfile("/tmp/cfg.json"):
            os.remove("/tmp/cfg.json")

    def test_loads(self):
        config = KeywordsConfiguration()
        config.loads(self.test_dict)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["extractors"],
            self.test_dict["keywords"]["extractors"],
        )

    def test_clear(self):
        config = KeywordsConfiguration()
        config.loads(self.test_dict)
        config.clear()
        self.assertEqual(config.logger_config.logger_name, "default")
        self.assertEqual(config.logger_config.configuration, None)
        self.assertEqual(config.configuration, dict())
