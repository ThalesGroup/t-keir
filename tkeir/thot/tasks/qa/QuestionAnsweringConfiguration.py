# -*- coding: utf-8 -*-
"""Question answering configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class QuestionAnsweringConfiguration:
    """load network configuration
    A question answering configuration is represented by JSON entry:

    Example
    "logger": {
            "logging-level": "info"
        }
    "qa": {
        "settings":{
            "max-document-words":450
        }
        "network": {
            "host":"0.0.0.0",
            "port":"8080",
            "associate-environment": {
                "host":"HOST_ENVNAME",
                "port":"PORT_ENVNAME"
            }
        },
        "runtime":{
            "request-max-size":100000000,
            "request-buffer-queue-size":100,
            "keep-alive":true,
            "keep-alive-timeout":5,
            "graceful-shutown-timeout":15.0,
            "request-timeout":60,
            "response-timeout":60,
            "workers":1,
            "associate-environment": {
                "request-max-size":ENV1,
                "request-buffer-queue-size":ENV2,
                "keep-alive":ENV3,
                "keep-alive-timeout":ENV4,
                "graceful-shutown-timeout":ENV5,
                "request-timout":ENV6,
                "response-timeout":ENV7,
                "workers":ENV8,
            }
        }
    }

    """

    def __init__(self):
        self.logger_config = LoggerConfiguration()
        self.net_config = NetworkConfiguration()
        self.runtime_config = RuntimeConfiguration()
        self.configuration = {}

    def load(self, config_f=None, path: list = []):
        """Load logger configuration from file

        Args:
            config_f (str, optional): load configruation with file handler. Defaults to None.
            path (list,option): access to a part of the configuration
        """
        json_config = json.load(config_f)
        self.loads(json_config)

    def loads(self, configuration: dict = None):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.
        """
        self.logger_config.loads(configuration, logger_name="qa")
        self.net_config.loads(configuration["qa"])
        self.runtime_config.loads(configuration["qa"])
        if "settings" in configuration["qa"]:
            self.configuration["settings"] = configuration["qa"]["settings"]
        else:
            self.configuration = {"settings": {"max-document-words": 450, "language": "en"}}

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
