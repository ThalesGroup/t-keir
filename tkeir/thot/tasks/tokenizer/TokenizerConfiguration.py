"""Title: Tokenizer configuration

Tokenization and MWE handling for T-KEIR documents.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class TokenizerConfiguration:
    """load tokenizer configuration
    A tokenizer configuration is represented by JSON entry:

    Example
    logger": {
            "logging-level": "debug"
        },
        "tokenizers": {
            "segmenters":[{
                "language":"en",
                "resources-base-path":"/home/tkeir_svc/tkeir/thot/tests/data",
                "mwe": "tkeir_mwe.pkl"
            }]
        }
    }

        Example:
            >>> from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration
            >>> callable(TokenizerConfiguration)
            True
    """

    def __init__(self):
        """Initialize the instance.

        Example:
            >>> cfg = TokenizerConfiguration()
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
                    >>> callable(TokenizerConfiguration().load)
                    True
        """
        json_config = load_configuration(config_f)
        self.loads(json_config)

    def loads(self, configuration: dict | None = None):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.

                Example:
                    >>> cfg = TokenizerConfiguration()
                    >>> cfg.loads({'logger': {}, 'tokenizers': {'segmenters': [{'language': 'en'}]}})
                    >>> 'segmenters' in cfg.configuration
                    True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="tokenizers")
        if "segmenters" in configuration["tokenizers"]:
            self.configuration["segmenters"] = configuration["tokenizers"][
                "segmenters"
            ]
        else:
            raise ValueError(
                "segmenters are mandatory in tokenizer configuration"
            )

    def clear(self):
        """clear logger configuration

        Example:
            >>> cfg = TokenizerConfiguration()
            >>> cfg.loads({'logger': {}, 'tokenizers': {'segmenters': [{'language': 'en'}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
