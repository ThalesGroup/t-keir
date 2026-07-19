"""Test converter configuration."""

import json
import os
import unittest

from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration


class TestConverterConfiguration(unittest.TestCase):
    test_dict = {
        "logger": {"logging-level": "debug"},
        "converter": {
            "settings": {
                "output": {"zip": True},
                "ocr": {"enabled": True, "mode": "tesseract"},
            },
        },
    }

    def test_load(self):
        with open("/tmp/cfg.json", "w", encoding="utf-8") as handle:
            json.dump(self.test_dict, handle)
        with open("/tmp/cfg.json", encoding="utf-8") as handle:
            config = ConverterConfiguration()
            config.load(handle)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertTrue(config.configuration["settings"]["output"]["zip"])
        if os.path.isfile("/tmp/cfg.json"):
            os.remove("/tmp/cfg.json")

    def test_loads(self):
        config = ConverterConfiguration()
        config.loads(self.test_dict)
        self.assertEqual(
            config.logger_config.configuration["logger"],
            self.test_dict["logger"],
        )
        self.assertTrue(config.configuration["settings"]["output"]["zip"])
        self.assertTrue(config.configuration["settings"]["ocr"]["enabled"])

    def test_clear(self):
        config = ConverterConfiguration()
        config.loads(self.test_dict)
        config.clear()
        self.assertEqual(config.logger_config.logger_name, "default")
        self.assertEqual(config.logger_config.configuration, None)
        self.assertEqual(config.configuration, {})
