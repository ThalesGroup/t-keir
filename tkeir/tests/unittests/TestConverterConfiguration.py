# -*- coding: utf-8 -*-
"""Test converter configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration
import json
import os
import unittest


class TestConverterConfiguration(unittest.TestCase):
    def test_load(self):
        """Test load with file function"""
        test_dict = {
            "logger": {"logging-level": "debug"},
            "converter": {
                "network": {
                    "host": "0.0.0.0",
                    "port": 8080,
                    "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
                },
                "settings": {
                    "tika": {
                        "host": "localhost",
                        "port": 9998,
                        "associate-environment": {"host": "TIKA_HOST", "port": "TIKA_PORT"},
                    },
                    "output": {"zip": True},
                },
                "serialize": {
                    "input": {"path": "/tmp", "keep-service-info": True},
                    "output": {"path": "/tmp", "keep-service-info": True},
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
                },
            },
        }
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        if "HOST_ENVNAME" in os.environ:
            del os.environ["HOST_ENVNAME"]
        if "PORT_ENVNAME" in os.environ:
            del os.environ["PORT_ENVNAME"]
        converterConfig = ConverterConfiguration()
        converterConfig.load(fh)
        fh.close()

        self.assertEqual(converterConfig.logger_config.configuration["logger"], test_dict["logger"])
        self.assertEqual(converterConfig.net_config.configuration["network"], test_dict["converter"]["network"])
        test_dict["converter"]["serialize"]["do-serialization"] = True
        self.assertEqual(converterConfig.runtime_config.configuration["runtime"], test_dict["converter"]["runtime"])

    def test_loads(self):
        """Test load with dict function"""
        test_dict = {
            "logger": {"logging-level": "debug"},
            "converter": {
                "network": {
                    "host": "0.0.0.0",
                    "port": 8080,
                    "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
                },
                "settings": {
                    "tika": {
                        "host": "localhost",
                        "port": 9998,
                        "associate-environment": {"host": "TIKA_HOST", "port": "TIKA_PORT"},
                    },
                    "output": {"zip": True},
                },
                "serialize": {
                    "input": {"path": "/tmp", "keep-service-info": True},
                    "output": {"path": "/tmp", "keep-service-info": True},
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
                },
            },
        }
        if "HOST_ENVNAME" in os.environ:
            del os.environ["HOST_ENVNAME"]
        if "PORT_ENVNAME" in os.environ:
            del os.environ["PORT_ENVNAME"]
        converterConfig = ConverterConfiguration()
        converterConfig.loads(test_dict)

        self.assertEqual(converterConfig.logger_config.configuration["logger"], test_dict["logger"])
        self.assertEqual(converterConfig.net_config.configuration["network"], test_dict["converter"]["network"])
        test_dict["converter"]["serialize"]["do-serialization"] = True
        self.assertEqual(converterConfig.runtime_config.configuration["runtime"], test_dict["converter"]["runtime"])

    def test_clear(self):
        """Test clear function"""
        test_dict = {
            "logger": {"logging-level": "debug"},
            "converter": {
                "network": {
                    "host": "0.0.0.0",
                    "port": 8080,
                    "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
                },
                "settings": {
                    "tika": {
                        "host": "localhost",
                        "port": 9998,
                        "associate-environment": {"host": "TIKA_HOST", "port": "TIKA_PORT"},
                    },
                    "output": {"zip": True},
                },
                "serialize": {
                    "input": {"path": "/tmp", "keep-service-info": True},
                    "output": {"path": "/tmp", "keep-service-info": True},
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
                },
            },
        }
        converterConfig = ConverterConfiguration()
        converterConfig.loads(test_dict)
        converterConfig.clear()
        self.assertEqual(converterConfig.logger_config.logger_name, "default")
        self.assertEqual(converterConfig.logger_config.configuration, None)
        self.assertEqual(converterConfig.net_config.configuration, None)
        self.assertEqual(converterConfig.runtime_config.configuration, None)
