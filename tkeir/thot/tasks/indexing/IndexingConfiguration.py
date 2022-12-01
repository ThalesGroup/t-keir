# -*- coding: utf-8 -*-
"""Indexing configuration

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.CommonConfiguration import CommonConfiguration
from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class IndexingConfiguration:
    """load tokenizer configuration
    A tokenizer configuration is represented by JSON entry:

    Example
    "logger": {
            "logging-level": "debug"
        },
    "indexing": {
        "elasticsearch":{
            "network": {
                "host": "localhost",
                "port": 9200,
                "use_ssl": false,
                "verify_certs": false,
                "associate-environment": {
                    "host":"HOST_ENVNAME",
                    "port":"PORT_ENVNAME"
                }
            },
            "nms-index":{
                "index-name":"nms-index",
                "mapping-file":/home/tkeir_svc/tkeir/configs/axeleria/resources/indices/indices_mapping/nms_cache_index.json"
            },
            "text-index:{
                "index-name":"text-index,
                "mapping-file":/home/tkeir_svc/tkeir/configs/axeleria/resources/indices/indices_mapping/cache_index.json"
            },
            "relation-index:{
                "index-name":"relation-index,
                "mapping-file":/home/tkeir_svc/tkeir/configs/axeleria/resources/indices/indices_mapping/relation_index.json"
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
        self.logger_config.loads(configuration, logger_name="indexing")
        self.net_config.loads(configuration["indexing"])
        self.runtime_config.loads(configuration["indexing"])
        if "elasticsearch" in configuration["indexing"]:
            self.configuration["elasticsearch"] = configuration["indexing"]["elasticsearch"]
            CommonConfiguration.affect_associated_environment(self.configuration["elasticsearch"]["network"])
            if "auth" in self.configuration["elasticsearch"]["network"]:
                CommonConfiguration.affect_associated_environment(self.configuration["elasticsearch"]["network"]["auth"])
        else:
            raise ValueError("elasticsearch is mandatory in indexing configuration")
        if "document" in configuration["indexing"]:
            self.configuration["document"] = configuration["indexing"]["document"]

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.configuration = dict()
