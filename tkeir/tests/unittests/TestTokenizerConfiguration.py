"""Title: Tokenizer Configuration

Test tokenizer configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import json
import os
import unittest

from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration


class TestTokenizerConfiguration(unittest.TestCase):
    test_dict = {
        "logger": {"logging-level": "debug"},
        "tokenizers": {
            "segmenters": [
                {
                    "language": "en",
                    "resources-base-path": (
                        "/home/tkeir_svc/tkeir/thot/tests/data"
                    ),
                    "mwe": "tkeir_mwe.pkl",
                }
            ],
        },
    }

    def test_load(self):
        with open("/tmp/cfg.json", "w", encoding="utf-8") as handle:
            json.dump(self.test_dict, handle)
        with open("/tmp/cfg.json", encoding="utf-8") as handle:
            config = TokenizerConfiguration()
            config.load(handle)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["segmenters"],
            self.test_dict["tokenizers"]["segmenters"],
        )
        if os.path.isfile("/tmp/cfg.json"):
            os.remove("/tmp/cfg.json")

    def test_loads(self):
        config = TokenizerConfiguration()
        config.loads(self.test_dict)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertEqual(
            config.configuration["segmenters"],
            self.test_dict["tokenizers"]["segmenters"],
        )

    def test_clear(self):
        config = TokenizerConfiguration()
        config.loads(self.test_dict)
        config.clear()
        self.assertEqual(config.logger_config.logger_name, "default")
        self.assertEqual(config.logger_config.configuration, None)
        self.assertEqual(config.configuration, dict())
