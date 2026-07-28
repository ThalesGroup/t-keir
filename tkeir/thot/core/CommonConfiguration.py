# -*- coding: utf-8 -*-
"""Common configuration

Common configuration function

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import os
from copy import deepcopy
from thot.core.Utils import is_numeric


class CommonConfiguration:
    @staticmethod
    def _replace_string_by_type(configuration: dict, assoc_field: str)->dict:
        """Replace a string by a typed value
        e.g string '10' will be replaced by interger 10
        Args:
          configuration (dict): a configuration file
          assco_field : field that should be changed"""
        if isinstance(configuration[assoc_field], str):
            if is_numeric(configuration[assoc_field]) :
                if "." in configuration[assoc_field]:
                    configuration[assoc_field] = float(configuration[assoc_field])
                else:
                    configuration[assoc_field] = int(configuration[assoc_field])
            elif configuration[assoc_field].lower() == "false":
                configuration[assoc_field] = False
            elif configuration[assoc_field].lower() == "true":
                configuration[assoc_field] = True
        
            
        return configuration

    @staticmethod
    def affect_associated_environment(configuration: dict):
        """affect environement variable to dedicated fields
        E.G: the following part configuration, "host" and "port"
        have default values (resp. 0.0.0.0 and 8000)
        "network": {
        "host":"0.0.0.0",
        "port":8080,
        "associate-environment": {
            "host":"HOST_ENVNAME",
            "port":"PORT_ENVNAME"
        }
        the new values of "host" and "port" if environement variables
        HOST_ENVNAME and PORT_ENVNAME will be affectted (if they exists)

        Args:
            configuration (dict): configuration file containing field "associated-environment"
        """

        if "associate-environment" in configuration:
            for assoc_field in configuration["associate-environment"]:
                if assoc_field in configuration:
                    configuration[assoc_field] = os.getenv(
                        configuration["associate-environment"][assoc_field], configuration[assoc_field]
                    )
                    configuration = CommonConfiguration._replace_string_by_type(configuration, assoc_field)

    @staticmethod
    def go_to_configuration_field(configuration: dict = dict(), path: list = [], keep_last_field: bool = True):
        """get only part of configuration according to a configuration tree path

        Args:
            configuration (dict, optional): the initial configuration. Defaults to dict()).
            path (list, optional): path to extract. Defaults to [].
            keep_last_field (bool, optional) keep the last field entry on the returned stucture. Default to True

        Raises:
            ValueError: if path does not exist raise exception

        Returns:
            dict: return the target configuration
        """
        decay_configuration = deepcopy(configuration)
        for field in path:
            if field in decay_configuration:
                decay_configuration = decay_configuration[field]
            else:
                raise ValueError("Bad path in " + str(path) + " ' stop at '" + field + "'.")
        if keep_last_field and (len(path) > 0):
            decay_configuration = {path[-1]: decay_configuration}

        return decay_configuration
