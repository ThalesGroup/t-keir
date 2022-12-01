# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.syntax.SyntacticTaggerConfiguration import SyntacticTaggerConfiguration
import unittest
import json


class TestSyntacticTaggerConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "syntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/thot/tests/data",
                    "syntactic-rules": "syntactic-rules.json",
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
                json.dump(TestSyntacticTaggerConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        syntaxConfig = SyntacticTaggerConfiguration()
        syntaxConfig.load(fh)
        fh.close()

        self.assertEqual(
            syntaxConfig.logger_config.configuration["logger"], TestSyntacticTaggerConfiguration.test_dict["logger"]
        )
        self.assertEqual(
            syntaxConfig.net_config.configuration["network"], TestSyntacticTaggerConfiguration.test_dict["syntax"]["network"]
        )
        TestSyntacticTaggerConfiguration.test_dict["syntax"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            syntaxConfig.runtime_config.configuration["runtime"],
            TestSyntacticTaggerConfiguration.test_dict["syntax"]["runtime"],
        )
        self.assertEqual(syntaxConfig.configuration["taggers"], TestSyntacticTaggerConfiguration.test_dict["syntax"]["taggers"])

    def test_loads(self):
        syntaxConfig = SyntacticTaggerConfiguration()
        syntaxConfig.loads(TestSyntacticTaggerConfiguration.test_dict)
        self.assertEqual(
            syntaxConfig.logger_config.configuration["logger"], TestSyntacticTaggerConfiguration.test_dict["logger"]
        )
        self.assertEqual(
            syntaxConfig.net_config.configuration["network"], TestSyntacticTaggerConfiguration.test_dict["syntax"]["network"]
        )
        TestSyntacticTaggerConfiguration.test_dict["syntax"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            syntaxConfig.runtime_config.configuration["runtime"],
            TestSyntacticTaggerConfiguration.test_dict["syntax"]["runtime"],
        )
        self.assertEqual(syntaxConfig.configuration["taggers"], TestSyntacticTaggerConfiguration.test_dict["syntax"]["taggers"])

    def test_clear(self):
        syntaxConfig = SyntacticTaggerConfiguration()
        syntaxConfig.loads(TestSyntacticTaggerConfiguration.test_dict)
        syntaxConfig.clear()
        self.assertEqual(syntaxConfig.logger_config.logger_name, "default")
        self.assertEqual(syntaxConfig.logger_config.configuration, None)
        self.assertEqual(syntaxConfig.net_config.configuration, None)
        self.assertEqual(syntaxConfig.runtime_config.configuration, None)
        self.assertEqual(syntaxConfig.configuration, dict())
