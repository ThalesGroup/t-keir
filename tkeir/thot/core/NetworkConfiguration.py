# -*- coding: utf-8 -*-
"""Network configuration

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json
from thot.core.CommonConfiguration import CommonConfiguration


class NetworkConfiguration:
    """load network configuration
    A network configuration is represented by JSON entry:

    "network": {
        "host":"0.0.0.0",
        "port":"8080",
        "associate-environment": {
            "host":"HOST_ENVNAME",
            "port":"PORT_ENVNAME"
        },
        "ssl":{
            "cert":"/home/tkeir_svc/tkeir/app/ssl/certificate.crt",
            "key":"/home/tkeir_svc/tkeir/app/ssl/privateKey.key"
        }
    }

    """

    def __init__(self):
        """initialize class variables"""
        self.configuration = None

    def _check_and_update(self):
        """check and update network according to environment variables

        Raises:
            ValueError: if not configuration set or "network" field does not exists

        Returns:
            [bool]: True if network configuration contains host AND port
        """
        if self.configuration and ("network" in self.configuration):
            CommonConfiguration.affect_associated_environment(self.configuration["network"])
            return ("host" in self.configuration["network"]) and ("port" in self.configuration["network"])
        raise ValueError("Bad network configuration")

    def load(self, config_f, path: list = []):
        """Load network configuration from file

        Args:
            config_f (file_handler, mandatory): network configruation file handler.
            path (list,option): access to a part of the configuration
        """
        self.configuration = CommonConfiguration.go_to_configuration_field(json.load(config_f), path)
        self._check_and_update()

    def loads(self, configuration: dict = None):
        """Load network configuration from dict (json)

        Args:
            configuration (dict, optional): load network configruation with dict. Defaults to None.
        """
        self.configuration = configuration
        self._check_and_update()

    def clear(self):
        """clear logger configuration"""
        self.configuration = None
