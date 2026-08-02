"""Title: Convert source document to tkeir indexer document

Automated tests for T-KEIR (unit / functional).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import io
import json
import os
import sys
import unittest

from thot.core.ThotLogger import LogUserContext, ThotLogger


class TestThotLogger(unittest.TestCase):
    def test_shutdown(self):
        """Test shutdown function"""
        test_dict = {"logger": {"logging-level": "info"}}
        ThotLogger.loads(test_dict)
        self.assertEqual(ThotLogger.logger_config.configuration, test_dict)
        ThotLogger.shutdown()
        self.assertEqual(ThotLogger.logger, None)
        self.assertEqual(ThotLogger.logger_config.logger_name, "default")
        self.assertEqual(ThotLogger.logger_config.configuration, None)

    def test_load(self):
        """Test load with file function"""
        test_dict = {"logger": {"logging-level": "debug"}}
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(test_dict, f)
                f.close()
        except Exception:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        ThotLogger.load(fh, logger_name="test")
        fh.close()

        self.assertEqual(ThotLogger.logger_config.configuration, test_dict)
        if os.path.isfile("/tmp/f0.log"):
            os.remove("/tmp/f0.log")
        if os.path.isfile("/tmp/cfg.json"):
            os.remove("/tmp/cfg.json")

    def test_loads(self):
        """Test load with dict function"""
        ThotLogger.loads({"logger": {"logging-level": "info"}})

        test_dict = {"logger": {"logging-level": "info"}}

        self.assertEqual(ThotLogger.logger_config.configuration, test_dict)

        ThotLogger.shutdown()
        ThotLogger.loads(
            {"logger": {"logging-level": "info"}}, logger_name="test"
        )
        self.assertEqual(ThotLogger.logger_config.configuration, test_dict)

    def test_logging(self):
        old_stdout = sys.stdout
        new_stdout = io.StringIO()
        sys.stdout = new_stdout
        log_context = LogUserContext("my-cor-id")
        ThotLogger.loads(
            {"logging-level": "info"}, logger_name="** My test Logger **"
        )
        log_context["status"] = 500
        ThotLogger.error("test error", context=log_context, trace="mytrace")
        log_context["status"] = 200
        ThotLogger.warning("test warn", context=log_context, trace="mytrace")
        ThotLogger.info("test info", context=log_context, trace="mytrace")
        output = new_stdout.getvalue()
        self.assertTrue(
            "[context-log-chunk:3][status:200][context-info:][trace:mytrace] test info"
            in output
        )
        sys.stdout = old_stdout

    def test__aggregate_context(self):
        log_context = LogUserContext("my-cor-id")
        ThotLogger.loads(
            {"logging-level": "info"}, logger_name="** My test Logger **"
        )
        log_str = ThotLogger._aggregate_context(
            "my tracte", {**log_context, **{"ctx1": "1", "ctx2": "2"}}
        )
        self.assertTrue("ctx1" in log_str)
        self.assertTrue("ctx2" in log_str)
