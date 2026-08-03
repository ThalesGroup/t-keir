"""Title: Golden Chunker Configuration

Golden chunking configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class GoldenChunkerConfiguration:
    """Load golden chunking configuration.
    
        Example:
            >>> from thot.tasks.golden_chunking.GoldenChunkerConfiguration import GoldenChunkerConfiguration
            >>> callable(GoldenChunkerConfiguration)
            True
    """

    def __init__(self):
        """Initialize the instance.

        Example:
            >>> cfg = GoldenChunkerConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        self.configuration = dict()

    def load(self, config_f=None, path: list = []):
        """load API.

        Example:
            >>> callable(GoldenChunkerConfiguration().load)
            True
        """
        self.loads(load_configuration(config_f))

    def loads(self, configuration: dict | None = None):
        """loads API.

        Example:
            >>> cfg = GoldenChunkerConfiguration()
            >>> cfg.loads({'golden-chunking': {'chunkers': [{}]}})
            >>> 'chunkers' in cfg.configuration
            True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="chunking")
        if "chunkers" in configuration["golden-chunking"]:
            self.configuration["chunkers"] = configuration["golden-chunking"][
                "chunkers"
            ]
        else:
            raise ValueError(
                "chunkers are mandatory in golden-chunking configuration"
            )

    def clear(self):
        """clear API.

        Example:
            >>> cfg = GoldenChunkerConfiguration()
            >>> cfg.loads({'golden-chunking': {'chunkers': [{}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
