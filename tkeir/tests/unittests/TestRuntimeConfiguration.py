# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.RuntimeConfiguration import RuntimeConfiguration
import json
import os
import unittest


class TestRuntimeConfiguration(unittest.TestCase):
    def test_load(self):
        """Test load with file function"""
        test_dict = {
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
                "associate-environment": {
                    "request-max-size": "ENV1",
                    "request-buffer-queue-size": "ENV2",
                    "keep-alive": "ENV3",
                    "keep-alive-timeout": "ENV4",
                    "graceful-shutown-timeout": "ENV5",
                    "request-timout": "ENV6",
                    "response-timeout": "ENV7",
                    "workers": "ENV8",
                },
            }
        }
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)

        fh = open("/tmp/cfg.json")
        runtimeconfig = RuntimeConfiguration()
        runtimeconfig.load(fh)
        fh.close()
        self.assertEqual(runtimeconfig.configuration, test_dict)
        runtimeconfig.clear()
        os.environ["ENV1"] = "50000"
        test_dict = {
            "runtime": {
                "request-max-size": 50000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
                "associate-environment": {
                    "request-max-size": "ENV1",
                    "request-buffer-queue-size": "ENV2",
                    "keep-alive": "ENV3",
                    "keep-alive-timeout": "ENV4",
                    "graceful-shutown-timeout": "ENV5",
                    "request-timout": "ENV6",
                    "response-timeout": "ENV7",
                    "workers": "ENV8",
                },
            }
        }
        fh = open("/tmp/cfg.json")
        runtimeconfig.load(fh)
        fh.close()
        self.assertEqual(runtimeconfig.configuration, test_dict)

    def test_loads(self):
        """Test load with dict function"""
        test_dict = {
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
                "associate-environment": {
                    "request-max-size": "ENV1",
                    "request-buffer-queue-size": "ENV2",
                    "keep-alive": "ENV3",
                    "keep-alive-timeout": "ENV4",
                    "graceful-shutown-timeout": "ENV5",
                    "request-timout": "ENV6",
                    "response-timeout": "ENV7",
                    "workers": "ENV8",
                },
            }
        }
        runtimeconfig = RuntimeConfiguration()
        runtimeconfig.loads(test_dict)
        self.assertEqual(runtimeconfig.configuration, test_dict)

        os.environ["ENV1"] = "50000"
        test_dict = {
            "runtime": {
                "request-max-size": 50000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
                "associate-environment": {
                    "request-max-size": "ENV1",
                    "request-buffer-queue-size": "ENV2",
                    "keep-alive": "ENV3",
                    "keep-alive-timeout": "ENV4",
                    "graceful-shutown-timeout": "ENV5",
                    "request-timout": "ENV6",
                    "response-timeout": "ENV7",
                    "workers": "ENV8",
                },
            }
        }
        runtimeconfig.clear()
        runtimeconfig.loads(test_dict)
        self.assertEqual(runtimeconfig.configuration, test_dict)

        runtimeconfig.clear()

    def test_clear(self):
        test_dict = {
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
                "associate-environment": {
                    "request-max-size": "ENV1",
                    "request-buffer-queue-size": "ENV2",
                    "keep-alive": "ENV3",
                    "keep-alive-timeout": "ENV4",
                    "graceful-shutown-timeout": "ENV5",
                    "request-timout": "ENV6",
                    "response-timeout": "ENV7",
                    "workers": "ENV8",
                },
            }
        }
        runtimeconfig = RuntimeConfiguration()
        runtimeconfig.loads(test_dict)
        runtimeconfig.clear()
        self.assertEqual(runtimeconfig.configuration, None)
