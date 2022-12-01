# -*- coding: utf-8 -*-
"""Test QA configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.qa.QuestionAnsweringConfiguration import QuestionAnsweringConfiguration
import unittest
import json
import traceback


class TestQAConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "qa": {
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
                json.dump(TestQAConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            print(str(e) + " trace:" + str(traceback.format_exc()))
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        qaConfig = QuestionAnsweringConfiguration()
        qaConfig.load(fh)
        fh.close()

        self.assertEqual(qaConfig.logger_config.configuration["logger"], TestQAConfiguration.test_dict["logger"])
        self.assertEqual(qaConfig.net_config.configuration["network"], TestQAConfiguration.test_dict["qa"]["network"])
        self.assertEqual(qaConfig.runtime_config.configuration["runtime"], TestQAConfiguration.test_dict["qa"]["runtime"])

    def test_loads(self):
        qaConfig = QuestionAnsweringConfiguration()
        qaConfig.loads(TestQAConfiguration.test_dict)
        self.assertEqual(qaConfig.logger_config.configuration["logger"], TestQAConfiguration.test_dict["logger"])
        self.assertEqual(qaConfig.net_config.configuration["network"], TestQAConfiguration.test_dict["qa"]["network"])
        self.assertEqual(qaConfig.runtime_config.configuration["runtime"], TestQAConfiguration.test_dict["qa"]["runtime"])

    def test_clear(self):
        qaConfig = QuestionAnsweringConfiguration()
        qaConfig.loads(TestQAConfiguration.test_dict)
        qaConfig.clear()
        self.assertEqual(qaConfig.logger_config.logger_name, "default")
        self.assertEqual(qaConfig.logger_config.configuration, None)
        self.assertEqual(qaConfig.net_config.configuration, None)
        self.assertEqual(qaConfig.runtime_config.configuration, None)
