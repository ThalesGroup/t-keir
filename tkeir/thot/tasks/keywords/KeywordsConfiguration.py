# -*- coding: utf-8 -*-
"""Keyword configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

import json

from thot.core.LoggerConfiguration import LoggerConfiguration


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
        """Initialize the instance.

        Example:
            >>> cfg = KeywordsConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        self.configuration = dict()

    def load(self, config_f=None, path: list = []):
        """Load logger configuration from file

        Args:
            config_f (str, optional): load configruation with file handler. Defaults to None.
            path (list,option): access to a part of the configuration

                Example:
                    >>> callable(KeywordsConfiguration().load)
                    True
        """
        json_config = json.load(config_f)
        self.loads(json_config)

    def loads(self, configuration: dict | None = None):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.

                Example:
                    >>> cfg = KeywordsConfiguration()
                    >>> cfg.loads({'logger': {}, 'keywords': {'extractors': [{'language': 'en'}]}})
                    >>> 'extractors' in cfg.configuration
                    True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="keywords")
        if "extractors" in configuration["keywords"]:
            self.configuration["extractors"] = configuration["keywords"][
                "extractors"
            ]
        else:
            raise ValueError(
                "extractors are mandatory in keywords configuration"
            )

    def clear(self):
        """clear logger configuration

        Example:
            >>> cfg = KeywordsConfiguration()
            >>> cfg.loads({'logger': {}, 'keywords': {'extractors': [{'language': 'en'}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
