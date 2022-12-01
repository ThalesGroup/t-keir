# -*- coding: utf-8 -*-
"""Keyword configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class KeywordsConfiguration:
    """load ner configuration
     A ner configuration is represented by JSON entry:

     Example
     logger": {
             "logging-level": "debug"
              },
     "keywords": {
         "extractors":[{
             "language":"en"
             "resources-base-path":"/home/tkeir_svc/tkeir/thot/tests/data",
             "stopwords:"en.stopwords.lst",
             "use-lemma":True,
             "use-pos":True,
             "use-form": False
         }]
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


    """

    def __init__(self):
        self.logger_config = LoggerConfiguration()
        self.net_config = NetworkConfiguration()
        self.runtime_config = RuntimeConfiguration()
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
        self.logger_config.loads(configuration, logger_name="keywords")
        self.net_config.loads(configuration["keywords"])
        self.runtime_config.loads(configuration["keywords"])
        if "extractors" in configuration["keywords"]:
            self.configuration["extractors"] = configuration["keywords"]["extractors"]
        else:
            raise ValueError("extractors are mandatory in keywords configuration")

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.configuration = dict()
