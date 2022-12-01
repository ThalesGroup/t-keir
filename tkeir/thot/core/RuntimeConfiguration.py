# -*- coding: utf-8 -*-
"""Runtime configuration

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json
from thot.core.CommonConfiguration import CommonConfiguration
from thot.core.Utils import set_if_not_exists


class RuntimeConfiguration:
    """load runtime configuration
    A runtime configuration is represented by JSON entry:

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

    """

    def __init__(self):
        """initialize class variables"""
        self.configuration = None

    def _check_and_update(self):
        """check and update runtime according to environment variables

        Raises:
            ValueError: if not configuration set or "runtime" field does not exists

        Returns:
            [bool]: True if runtime configuration contains host AND port
        """
        if self.configuration:
            if "runtime" in self.configuration:
                CommonConfiguration.affect_associated_environment(self.configuration["runtime"])
                set_if_not_exists(self.configuration["runtime"], "request-max-size", 100000000)
                set_if_not_exists(self.configuration["runtime"], "request-buffer-queue-size", 100)
                set_if_not_exists(self.configuration["runtime"], "keep-alive", True)
                set_if_not_exists(self.configuration["runtime"], "keep-alive-timeout", 5)
                set_if_not_exists(self.configuration["runtime"], "graceful-shutown-timeout", 15)
                set_if_not_exists(self.configuration["runtime"], "request-timeout", 60)
                set_if_not_exists(self.configuration["runtime"], "response-timeout", 60)
                set_if_not_exists(self.configuration["runtime"], "workers", 1)
            else:
                self.configuration["runtime"] = {
                    "request-max-size": 100000000,
                    "request-buffer-queue-size": 100,
                    "keep-alive": True,
                    "keep-alive-timeout": 5,
                    "graceful-shutown-timeout": 15.0,
                    "request-timeout": 60,
                    "response-timeout": 60,
                    "workers": 1,
                }
            return True
        raise ValueError("Bad runtime configuration")

    def load(self, config_f, path: list = []):
        """Load runtime configuration from file

        Args:
            config_f (file_handler, mandatory): runtime configruation file handler.
            path (list,option): access to a part of the configuration
        """
        self.configuration = CommonConfiguration.go_to_configuration_field(json.load(config_f), path)
        self._check_and_update()

    def loads(self, configuration: dict = None):
        """Load runtime configuration from dict (json)

        Args:
            configuration (dict, optional): load runtime configruation with dict. Defaults to None.
        """
        self.configuration = configuration
        self._check_and_update()

    def clear(self):
        """clear logger configuration"""
        self.configuration = None
