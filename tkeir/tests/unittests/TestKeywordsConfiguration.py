# -*- coding: utf-8 -*-
"""Test Keywords configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.keywords.KeywordsConfiguration import KeywordsConfiguration
import unittest
import json


class TestKeywordsConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "keywords": {
            "extractors": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/thot/tests/data",
                    "stopwords": "en.stopwords.lst",
                    "use-lemma": True,
                    "use-pos": True,
                    "use-form": False,
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
                json.dump(TestKeywordsConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        kwConfig = KeywordsConfiguration()
        kwConfig.load(fh)
        fh.close()

        self.assertEqual(kwConfig.logger_config.configuration["logger"], TestKeywordsConfiguration.test_dict["logger"])
        self.assertEqual(
            kwConfig.net_config.configuration["network"], TestKeywordsConfiguration.test_dict["keywords"]["network"]
        )
        TestKeywordsConfiguration.test_dict["keywords"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            kwConfig.runtime_config.configuration["runtime"], TestKeywordsConfiguration.test_dict["keywords"]["runtime"]
        )
        self.assertEqual(kwConfig.configuration["extractors"], TestKeywordsConfiguration.test_dict["keywords"]["extractors"])

    def test_loads(self):
        kwConfig = KeywordsConfiguration()
        kwConfig.loads(TestKeywordsConfiguration.test_dict)
        self.assertEqual(kwConfig.logger_config.configuration["logger"], TestKeywordsConfiguration.test_dict["logger"])
        self.assertEqual(
            kwConfig.net_config.configuration["network"], TestKeywordsConfiguration.test_dict["keywords"]["network"]
        )
        TestKeywordsConfiguration.test_dict["keywords"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            kwConfig.runtime_config.configuration["runtime"], TestKeywordsConfiguration.test_dict["keywords"]["runtime"]
        )
        self.assertEqual(kwConfig.configuration["extractors"], TestKeywordsConfiguration.test_dict["keywords"]["extractors"])

    def test_clear(self):
        kwConfig = KeywordsConfiguration()
        kwConfig.loads(TestKeywordsConfiguration.test_dict)
        kwConfig.clear()
        self.assertEqual(kwConfig.logger_config.logger_name, "default")
        self.assertEqual(kwConfig.logger_config.configuration, None)
        self.assertEqual(kwConfig.net_config.configuration, None)
        self.assertEqual(kwConfig.runtime_config.configuration, None)
        self.assertEqual(kwConfig.configuration, dict())
