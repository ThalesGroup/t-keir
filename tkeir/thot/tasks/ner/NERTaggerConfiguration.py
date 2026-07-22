"""Title: NER Tagger configuration

Named-entity recognition for the T-KEIR NLP pipeline.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class NERTaggerConfiguration:
    """load ner configuration
    A ner configuration is represented by JSON entry:

    Example
    logger": {
            "logging-level": "debug"
             },
    "named-entities": {
        "label":[{
            "language":"en",
            "resources-base-path":"/home/tkeir_svc/tkeir/thot/tests/data",
            "mwe": "tkeir_mwe.pkl",
            "use-pre-label":true
        }]
    }


    """

    def __init__(self):
        """Initialize the instance.

        Example:
            >>> cfg = NERTaggerConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        # Fill on named entity empty
        self.configuration = dict()

    def load(self, config_f=None, path: list = []):
        """Load logger configuration from file

        Args:
            config_f (str, optional): load configruation with file handler. Defaults to None.
            path (list,option): access to a part of the configuration

                Example:
                    >>> callable(NERTaggerConfiguration().load)
                    True
        """
        json_config = load_configuration(config_f)
        self.loads(json_config)

    def loads(self, configuration: dict | None = None):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.

                Example:
                    >>> cfg = NERTaggerConfiguration()
                    >>> cfg.loads({'logger': {}, 'named-entities': {'label': [{'language': 'en'}]}})
                    >>> 'label' in cfg.configuration
                    True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="named-entities")
        if "label" in configuration["named-entities"]:
            self.configuration["label"] = configuration["named-entities"][
                "label"
            ]
        else:
            raise ValueError(
                "label are mandatory in named entity configuration"
            )

    def clear(self):
        """clear logger configuration

        Example:
            >>> cfg = NERTaggerConfiguration()
            >>> cfg.loads({'logger': {}, 'named-entities': {'label': [{'language': 'en'}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
