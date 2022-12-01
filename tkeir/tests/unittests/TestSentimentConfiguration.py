# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.sentiment.SentimentAnalysisConfiguration import SentimentAnalysisConfiguration
import unittest
import json
import traceback


class TestSentimentConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "sentiment": {
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
                json.dump(TestSentimentConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            print(str(e) + " trace:" + str(traceback.format_exc()))
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        qaConfig = SentimentAnalysisConfiguration()
        qaConfig.load(fh)
        fh.close()

        self.assertEqual(qaConfig.logger_config.configuration["logger"], TestSentimentConfiguration.test_dict["logger"])
        self.assertEqual(
            qaConfig.net_config.configuration["network"], TestSentimentConfiguration.test_dict["sentiment"]["network"]
        )
        TestSentimentConfiguration.test_dict["sentiment"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            qaConfig.runtime_config.configuration["runtime"], TestSentimentConfiguration.test_dict["sentiment"]["runtime"]
        )

    def test_loads(self):
        qaConfig = SentimentAnalysisConfiguration()
        qaConfig.loads(TestSentimentConfiguration.test_dict)
        self.assertEqual(qaConfig.logger_config.configuration["logger"], TestSentimentConfiguration.test_dict["logger"])
        self.assertEqual(
            qaConfig.net_config.configuration["network"], TestSentimentConfiguration.test_dict["sentiment"]["network"]
        )
        TestSentimentConfiguration.test_dict["sentiment"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            qaConfig.runtime_config.configuration["runtime"], TestSentimentConfiguration.test_dict["sentiment"]["runtime"]
        )

    def test_clear(self):
        qaConfig = SentimentAnalysisConfiguration()
        qaConfig.loads(TestSentimentConfiguration.test_dict)
        qaConfig.clear()
        self.assertEqual(qaConfig.logger_config.logger_name, "default")
        self.assertEqual(qaConfig.logger_config.configuration, None)
        self.assertEqual(qaConfig.net_config.configuration, None)
        self.assertEqual(qaConfig.runtime_config.configuration, None)
