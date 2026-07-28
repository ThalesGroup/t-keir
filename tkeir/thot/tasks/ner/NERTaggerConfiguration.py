# -*- coding: utf-8 -*-
"""NER Tagger configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class NERTaggerConfiguration:
    """load ner configuration
    A ner configuration is represented by JSON entry:

    Example
    logger": {
            "logging-level": "debug"
             },
    "named-entities": {
        "label":[{
            "language":"en",
            "resources-base-path":"/home/tkeir_svc/tkeir/thot/tests/data",
            "mwe": "tkeir_mwe.pkl",
            "use-pre-label":true
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
        },
        "serialize":{
            "input":{
                "path":"/tmp",
                "keep-service-info":True
            },
            "output":{
                "path":"/tmp",
                "keep-service-info":True
            }
        }
    }


    """

    def __init__(self):
        self.logger_config = LoggerConfiguration()
        self.net_config = NetworkConfiguration()
        self.runtime_config = RuntimeConfiguration()
        # Fill on named entity empty
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
        self.logger_config.loads(configuration, logger_name="named-entities")
        self.net_config.loads(configuration["named-entities"])
        self.runtime_config.loads(configuration["named-entities"])
        if "label" in configuration["named-entities"]:
            self.configuration["label"] = configuration["named-entities"]["label"]
        else:
            raise ValueError("label are mandatory in named entity configuration")

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.configuration = dict()
