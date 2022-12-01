# -*- coding: utf-8 -*-
"""Logger configuration
define logger configuration

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import logging
import traceback
import json
import os
import errno
from thot.core.CommonConfiguration import CommonConfiguration


class LoggerConfiguration:
    """load logger configuration
    Example of logger entry
    "logger": {
        "logging-level": "debug"
    }
    Logger should be at top level
    """

    def __init__(self):
        """Initialize class variables"""
        self.logger_name = "default"
        self.configuration = None

    def _default_load(self):
        """create logger"""
        if (not self.configuration) or ("logger" not in self.configuration):
            logging.warning("Create default logger")
            self.configuration = {"logger": dict()}

        if "logging-level" not in self.configuration["logger"]:
            self.configuration["logger"]["logging-level"] = "debug"

    def load(self, config_f , logger_name: str = "default", path: list = []):
        """Load logger configuration from file

        Args:
            config_f (mandatory): configruation with file handler.
            logger_name (str,optional) : name of the logger (display in log line). Defaults to default
            path (list,option): access to a part of the configuration
        """
        self.configuration = CommonConfiguration.go_to_configuration_field(json.load(config_f), path)
        self.logger_name = logger_name
        self._default_load()

    def loads(self, configuration: dict = None, logger_name: str = "default"):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.
            logger_name (str,optional) : name of the logger (display in log line). Defaults to default
        """
        self.logger_name = logger_name
        self.configuration = configuration
        self._default_load()

    def clear(self):
        """clear logger configuration"""
        self.logger_name = "default"
        self.configuration = None
