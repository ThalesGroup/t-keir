"""Title: Synatctic tagger configuration

Syntactic tagging and SVO triple extraction.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class SyntacticTaggerConfiguration:
    """load morphosyntactic tagger configuration
    A tagger configuration is represented by JSON entry:

    Example
    {
    "logger": {
        "logging-level": "debug"
    },
    "syntax": {
        "taggers":[{
            "language":"en",
            "resources-base-path":"/home/tkeir_svc/tkeir/thot/tests/data",
            "syntactic-rules": "syntactic-rules.json"
        }]

    }
    }

        Example:
            >>> from thot.tasks.syntax.SyntacticTaggerConfiguration import SyntacticTaggerConfiguration
            >>> callable(SyntacticTaggerConfiguration)
            True
    """

    def __init__(self):
        """Initialize the instance.

        Example:
            >>> cfg = SyntacticTaggerConfiguration()
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
                    >>> callable(SyntacticTaggerConfiguration().load)
                    True
        """
        json_config = load_configuration(config_f)
        self.loads(json_config)

    def loads(self, configuration: dict | None = None):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.

                Example:
                    >>> cfg = SyntacticTaggerConfiguration()
                    >>> cfg.loads({'logger': {}, 'syntax': {'taggers': [{'language': 'en'}]}})
                    >>> 'taggers' in cfg.configuration
                    True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="syntax")
        if "taggers" in configuration["syntax"]:
            self.configuration["taggers"] = configuration["syntax"]["taggers"]
        else:
            raise ValueError(
                "taggers are mandatory in morphosyntactic tagger configuration"
            )

    def clear(self):
        """clear logger configuration

        Example:
            >>> cfg = SyntacticTaggerConfiguration()
            >>> cfg.loads({'logger': {}, 'syntax': {'taggers': [{'language': 'en'}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
