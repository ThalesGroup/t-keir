# -*- coding: utf-8 -*-
"""Annotation configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json
from thot.core.CommonConfiguration import CommonConfiguration


class AnnotationConfiguration:
    """load annotation item
    An annotation item is a part of annotation configuration file;
    it is represented by JSON entry:
    """

    def __init__(self):
        """initialize class variables"""
        self.configuration = None

    def _check_and_update(self):
        """check and update annotation_item according to environment variables

        Raises:
            ValueError: if not configuration set or "annotation_item" field does not exists

        Returns:
            [bool]: True if annotation_item configuration contains host AND port
        """
        if not self.configuration:
            raise ValueError("Bad annotation configuration")
        if not "data" in self.configuration:
            raise ValueError("'data' field is mandatory")
        if not "resources-base-path" in self.configuration:
            raise ValueError("'resources-base-path' field is mandatory")

    def load(self, config_f, path: list = []):
        """Load annotation_item configuration from file

        Args:
            config_f (file_handler, mandatory): annotation_item configruation file handler.
            path (list,option): access to a part of the configuration
        """
        self.configuration = CommonConfiguration.go_to_configuration_field(json.load(config_f), path)
        self._check_and_update()

    def loads(self, configuration: dict = None):
        """Load annotation_item configuration from dict (json)

        Args:
            configuration (dict, optional): load annotation_item configruation with dict. Defaults to None.
        """
        self.configuration = configuration
        self._check_and_update()

    def clear(self):
        """clear logger configuration"""
        self.configuration = None
