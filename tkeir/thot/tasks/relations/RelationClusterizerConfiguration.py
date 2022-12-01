# -*- coding: utf-8 -*-
"""Relation clustering configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.CommonConfiguration import CommonConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class RelationClusterizerConfiguration:
    """load relation clusterizer configuration
    A ner configuration is represented by JSON entry:

    Example
    logger": {
            "logging-file": "test.log",
            "logging-path": "/tmp",
            "logging-level": {"file": "info", "screen": "debug"}
             },
    "relations": {
        "cluster":{
            "number-of-classes":100,
            "number-of-iterations":100,
            "seed":123456,
            "batch-size":1024
        },
        "embeddings-":{
            "host":"0.0.0.0",
            "port":10006
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
        self.logger_config.loads(configuration, logger_name="relations")
        self.net_config.loads(configuration["relations"])
        self.runtime_config.loads(configuration["relations"])
        self.configuration["cluster"] = {
            "number-of-classes": 100,
            "number-of-iterations": 100,
            "batch-size": 1024,
            "seed": 123456,
        }

        if "cluster" in configuration["relations"]:
            self.configuration["cluster"].update(configuration["relations"]["cluster"])
            if "embeddings" in self.configuration["cluster"]:
                CommonConfiguration.affect_associated_environment(self.configuration["cluster"]["embeddings"]["server"])

        if "clustering-model" in configuration["relations"]:
            self.configuration["clustering-model"] = configuration["relations"]["clustering-model"]

        if "graph" in configuration["relations"]:
            self.configuration["graph"] = configuration["relations"]["graph"]

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.configuration = dict()
