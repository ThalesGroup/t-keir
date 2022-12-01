# -*- coding: utf-8 -*-
"""Tokenizer configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class TokenizerConfiguration:
    """load tokenizer configuration
    A tokenizer configuration is represented by JSON entry:

    Example
    logger": {
            "logging-level": "debug"
        },
        "tokenizers": {
            "segmenters":[{
                "language":"en",
                "resources-base-path":"/home/tkeir_svc/tkeir/thot/tests/data",
                "mwe": "tkeir_mwe.pkl"
            }],
            "network": {
                "host":"0.0.0.0",
                "port":8080,
                "associate-environment": {
                    "host":"HOST_ENVNAME",
                    "port":"PORT_ENVNAME"
                }
            },
            "runtime":{
                "request-max-size":100000000,
                "request-buffer-queue-size":100,
                "keep-alive":True,
                "keep-alive-timeout":5,
                "graceful-shutown-timeout":15.0,
                "request-timeout":60,
                "response-timeout":60,
                "workers":1
            }

        }
    }

    """

    def __init__(self):
        self.logger_config = LoggerConfiguration()
        self.net_config = NetworkConfiguration()
        self.runtime_config = RuntimeConfiguration()
        # Fill on tokenizer empty
        self.configuration = dict()

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
        self.logger_config.loads(configuration, logger_name="tokenizers")
        self.net_config.loads(configuration["tokenizers"])
        self.runtime_config.loads(configuration["tokenizers"])
        if "segmenters" in configuration["tokenizers"]:
            self.configuration["segmenters"] = configuration["tokenizers"]["segmenters"]
        else:
            raise ValueError("segmenters are mandatory in tokenizer configuration")

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.configuration = dict()
