# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.LoggerConfiguration import LoggerConfiguration
import json
import os
import unittest


class TestLoggerConfiguration(unittest.TestCase):
    def test_load(self):
        """Test load with file function"""
        test_dict = {"logger": {"logging-level": "debug"}}
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        logger_config = LoggerConfiguration()
        logger_config.load(fh, logger_name="test")
        fh.close()

        self.assertEqual(logger_config.configuration, test_dict)

    def test_loads(self):
        """Test load with dict function"""
        logger_config = LoggerConfiguration()
        logger_config.loads({"logger": {"logging-level": "info"}}, logger_name="test")

        test_dict = {"logger": {"logging-level": "info"}}
        self.assertEqual(logger_config.configuration, test_dict)

        logger_config.clear()
        logger_config.loads({"logger": {"logging-level": "debug"}}, logger_name="test")
        test_dict = {"logger": {"logging-level": "debug"}}
        self.assertEqual(logger_config.configuration, test_dict)

    def test_clear(self):
        logger_config = LoggerConfiguration()
        logger_config.loads({"logging-level": "info"})
        logger_config.clear()
        self.assertEqual(logger_config.logger_name, "default")
        self.assertEqual(logger_config.configuration, None)
