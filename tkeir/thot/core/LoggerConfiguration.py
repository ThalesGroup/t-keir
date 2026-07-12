# -*- coding: utf-8 -*-
"""Logger configuration
define logger configuration

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

import json
import logging

from thot.core.CommonConfiguration import CommonConfiguration


class LoggerConfiguration:
    """Load and store logger configuration from JSON sources.

    Example of logger entry:

    "logger": {
        "logging-level": "debug"
    }

    Logger should be at top level.
    """

    def __init__(self):
        """Initialize class variables.

        Example:
            >>> from thot.core.LoggerConfiguration import LoggerConfiguration
            >>> config = LoggerConfiguration()
            >>> config.logger_name
            'default'
            >>> config.configuration is None
            True
        """
        self.logger_name = "default"
        self.configuration = None

    def _default_load(self):
        """Create default logger settings when configuration is incomplete.

        Example:
            >>> from thot.core.LoggerConfiguration import LoggerConfiguration
            >>> config = LoggerConfiguration()
            >>> config._default_load()
            >>> config.configuration["logger"]["logging-level"]
            'debug'
        """
        if (not self.configuration) or ("logger" not in self.configuration):
            logging.warning("Create default logger")
            self.configuration = {"logger": dict()}

        if "logging-level" not in self.configuration["logger"]:
            self.configuration["logger"]["logging-level"] = "debug"

    def load(self, config_f, logger_name: str = "default", path: list = []):
        """Load logger configuration from a JSON file.

        Args:
            config_f: File-like object containing configuration JSON.
            logger_name: Logger name displayed in log lines.
            path: Optional configuration path prefix.

        Example:
            >>> from io import StringIO
            >>> import json
            >>> from thot.core.LoggerConfiguration import LoggerConfiguration
            >>> config = LoggerConfiguration()
            >>> config.load(
            ...     StringIO(json.dumps({"logger": {"logging-level": "info"}}))
            ... )
            >>> config.configuration["logger"]["logging-level"]
            'info'
        """
        self.configuration = CommonConfiguration.go_to_configuration_field(
            json.load(config_f), path
        )
        self.logger_name = logger_name
        self._default_load()

    def loads(self, configuration: dict = None, logger_name: str = "default"):
        """Load logger configuration from a dictionary.

        Args:
            configuration: Logger configuration dictionary.
            logger_name: Logger name displayed in log lines.

        Example:
            >>> from thot.core.LoggerConfiguration import LoggerConfiguration
            >>> config = LoggerConfiguration()
            >>> config.loads({"logger": {"logging-level": "warning"}})
            >>> config.configuration["logger"]["logging-level"]
            'warning'
        """
        self.logger_name = logger_name
        self.configuration = configuration
        self._default_load()

    def clear(self):
        """Clear logger configuration and reset the logger name.

        Example:
            >>> from thot.core.LoggerConfiguration import LoggerConfiguration
            >>> config = LoggerConfiguration()
            >>> config.loads({"logger": {"logging-level": "debug"}})
            >>> config.clear()
            >>> config.logger_name
            'default'
            >>> config.configuration is None
            True
        """
        self.logger_name = "default"
        self.configuration = None
