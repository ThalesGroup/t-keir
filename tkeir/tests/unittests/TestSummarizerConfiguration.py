# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.summarizer.SummarizerConfiguration import SummarizerConfiguration
import unittest
import json
import traceback


class TestSummarizerConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "summarizer": {
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
                json.dump(TestSummarizerConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            print(str(e) + " trace:" + str(traceback.format_exc()))
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        summarizeConfig = SummarizerConfiguration()
        summarizeConfig.load(fh)
        fh.close()

        self.assertEqual(summarizeConfig.logger_config.configuration["logger"], TestSummarizerConfiguration.test_dict["logger"])
        self.assertEqual(
            summarizeConfig.net_config.configuration["network"], TestSummarizerConfiguration.test_dict["summarizer"]["network"]
        )
        TestSummarizerConfiguration.test_dict["summarizer"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            summarizeConfig.runtime_config.configuration["runtime"],
            TestSummarizerConfiguration.test_dict["summarizer"]["runtime"],
        )

    def test_loads(self):
        summarizeConfig = SummarizerConfiguration()
        summarizeConfig.loads(TestSummarizerConfiguration.test_dict)
        self.assertEqual(summarizeConfig.logger_config.configuration["logger"], TestSummarizerConfiguration.test_dict["logger"])
        self.assertEqual(
            summarizeConfig.net_config.configuration["network"], TestSummarizerConfiguration.test_dict["summarizer"]["network"]
        )
        TestSummarizerConfiguration.test_dict["summarizer"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            summarizeConfig.runtime_config.configuration["runtime"],
            TestSummarizerConfiguration.test_dict["summarizer"]["runtime"],
        )

    def test_clear(self):
        summarizeConfig = SummarizerConfiguration()
        summarizeConfig.loads(TestSummarizerConfiguration.test_dict)
        summarizeConfig.clear()
        self.assertEqual(summarizeConfig.logger_config.logger_name, "default")
        self.assertEqual(summarizeConfig.logger_config.configuration, None)
        self.assertEqual(summarizeConfig.net_config.configuration, None)
        self.assertEqual(summarizeConfig.runtime_config.configuration, None)
