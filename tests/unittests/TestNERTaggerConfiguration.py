"""Title: NERTagger Configuration

Test NER tagger configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import json
import os
import unittest

from thot.tasks.ner.NERTaggerConfiguration import NERTaggerConfiguration


class TestNERTaggerConfiguration(unittest.TestCase):
    test_dict = {
        "logger": {"logging-level": "debug"},
        "named-entities": {
            "label": [
                {
                    "language": "en",
                    "resources-base-path": (
                        "/home/tkeir_svc/tkeir/thot/tests/data"
                    ),
                    "mwe": "tkeir_mwe.pkl",
                    "use-pre-label": True,
                }
            ],
        },
    }

    def test_load(self):
        with open("/tmp/cfg.json", "w", encoding="utf-8") as handle:
            json.dump(self.test_dict, handle)
        with open("/tmp/cfg.json", encoding="utf-8") as handle:
            config = NERTaggerConfiguration()
            config.load(handle)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["label"],
            self.test_dict["named-entities"]["label"],
        )
        if os.path.isfile("/tmp/cfg.json"):
            os.remove("/tmp/cfg.json")

    def test_loads(self):
        config = NERTaggerConfiguration()
        config.loads(self.test_dict)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["label"],
            self.test_dict["named-entities"]["label"],
        )

    def test_clear(self):
        config = NERTaggerConfiguration()
        config.loads(self.test_dict)
        config.clear()
        self.assertEqual(config.logger_config.logger_name, "default")
        self.assertEqual(config.logger_config.configuration, None)
        self.assertEqual(config.configuration, dict())
