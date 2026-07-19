"""CMorphosyntactic tagger configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class MorphoSyntacticTaggerConfiguration:
    """load morphosyntactic tagger configuration
    A tagger configuration is represented by JSON entry:

    Example
    {
    "logger": {
        "logging-level": "debug"
    },
    "morphosyntax": {
        "taggers":[{
            "language":"en",
            "resources-base-path":"/home/tkeir_svc/tkeir/thot/tests/data",
            "mwe": "tkeir_mwe.pkl",
            "pre-sentencizer": true,
            "pre-tagging":true
        }]
    }
    }
    """

    def __init__(self):
        """Initialize the instance.

        Example:
            >>> cfg = MorphoSyntacticTaggerConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        # Fill on tokenizer empty
        self.configuration = dict()

    def load(self, config_f=None, path: list = []):
        """Load logger configuration from file

        Args:
            config_f (str, optional): load configruation with file handler. Defaults to None.
            path (list,option): access to a part of the configuration

                Example:
                    >>> callable(MorphoSyntacticTaggerConfiguration().load)
                    True
        """
        json_config = load_configuration(config_f)
        self.loads(json_config)

    def loads(self, configuration: dict | None = None):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.

                Example:
                    >>> cfg = MorphoSyntacticTaggerConfiguration()
                    >>> cfg.loads({'logger': {}, 'morphosyntax': {'taggers': [{'language': 'en'}]}})
                    >>> 'taggers' in cfg.configuration
                    True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="morphosyntax")
        if "taggers" in configuration["morphosyntax"]:
            self.configuration["taggers"] = configuration["morphosyntax"][
                "taggers"
            ]
        else:
            raise ValueError(
                "taggers are mandatory in morphosyntactic tagger configuration"
            )

    def clear(self):
        """clear logger configuration

        Example:
            >>> cfg = MorphoSyntacticTaggerConfiguration()
            >>> cfg.loads({'logger': {}, 'morphosyntax': {'taggers': [{'language': 'en'}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
