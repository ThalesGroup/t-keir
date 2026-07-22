"""Title: Chunk Question Generator Configuration

Chunk question generator configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class ChunkQuestionGeneratorConfiguration:
    """Load chunk question generator configuration."""

    def __init__(self):
        """Initialize an empty configuration holder.

        Example:
            >>> from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ...     ChunkQuestionGeneratorConfiguration,
            ... )
            >>> cfg = ChunkQuestionGeneratorConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        self.configuration = dict()

    def load(self, config_f=None, path: list = []):
        """Load configuration from a JSON file path.

        Args:
            config_f: Path to the configuration file.
            path: Unused legacy parameter.

        Example:
            >>> from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ...     ChunkQuestionGeneratorConfiguration,
            ... )
            >>> callable(ChunkQuestionGeneratorConfiguration().load)
            True
        """
        self.loads(load_configuration(config_f))

    def loads(self, configuration: dict | None = None):
        """Load configuration from a parsed dictionary.

        Args:
            configuration: Parsed JSON configuration.

        Raises:
            ValueError: If generators are missing.

        Example:
            >>> from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ...     ChunkQuestionGeneratorConfiguration,
            ... )
            >>> cfg = ChunkQuestionGeneratorConfiguration()
            >>> cfg.loads({'chunk-questions': {'generators': [{}]}})
            >>> 'generators' in cfg.configuration
            True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="chunk-questions")
        if "generators" in configuration["chunk-questions"]:
            self.configuration["generators"] = configuration[
                "chunk-questions"
            ]["generators"]
        else:
            raise ValueError(
                "generators are mandatory in chunk-questions configuration"
            )

    def clear(self):
        """Reset logger and task configuration.

        Example:
            >>> from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ...     ChunkQuestionGeneratorConfiguration,
            ... )
            >>> cfg = ChunkQuestionGeneratorConfiguration()
            >>> cfg.loads({'chunk-questions': {'generators': [{}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
