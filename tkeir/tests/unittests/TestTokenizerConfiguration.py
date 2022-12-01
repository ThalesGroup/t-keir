# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration
import unittest
import json


class TestTokenizerConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "tokenizers": {
            "segmenters": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/thot/tests/data",
                    "mwe": "tkeir_mwe.pkl",
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            },
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    def test_load(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestTokenizerConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        tokenizerConfig = TokenizerConfiguration()
        tokenizerConfig.load(fh)
        fh.close()

        self.assertEqual(tokenizerConfig.logger_config.configuration["logger"], TestTokenizerConfiguration.test_dict["logger"])
        self.assertEqual(
            tokenizerConfig.net_config.configuration["network"], TestTokenizerConfiguration.test_dict["tokenizers"]["network"]
        )
        TestTokenizerConfiguration.test_dict["tokenizers"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            tokenizerConfig.runtime_config.configuration["runtime"],
            TestTokenizerConfiguration.test_dict["tokenizers"]["runtime"],
        )
        self.assertEqual(
            tokenizerConfig.configuration["segmenters"], TestTokenizerConfiguration.test_dict["tokenizers"]["segmenters"]
        )

    def test_loads(self):
        tokenizerConfig = TokenizerConfiguration()
        tokenizerConfig.loads(TestTokenizerConfiguration.test_dict)
        self.assertEqual(tokenizerConfig.logger_config.configuration["logger"], TestTokenizerConfiguration.test_dict["logger"])
        self.assertEqual(
            tokenizerConfig.net_config.configuration["network"], TestTokenizerConfiguration.test_dict["tokenizers"]["network"]
        )
        TestTokenizerConfiguration.test_dict["tokenizers"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            tokenizerConfig.runtime_config.configuration["runtime"],
            TestTokenizerConfiguration.test_dict["tokenizers"]["runtime"],
        )
        self.assertEqual(
            tokenizerConfig.configuration["segmenters"], TestTokenizerConfiguration.test_dict["tokenizers"]["segmenters"]
        )

    def test_clear(self):
        tokenizerConfig = TokenizerConfiguration()
        tokenizerConfig.loads(TestTokenizerConfiguration.test_dict)
        tokenizerConfig.clear()
        self.assertEqual(tokenizerConfig.logger_config.logger_name, "default")
        self.assertEqual(tokenizerConfig.logger_config.configuration, None)
        self.assertEqual(tokenizerConfig.net_config.configuration, None)
        self.assertEqual(tokenizerConfig.runtime_config.configuration, None)
        self.assertEqual(tokenizerConfig.configuration, dict())
