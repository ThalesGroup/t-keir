"""Annotation configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

from thot.core.CommonConfiguration import CommonConfiguration
from thot.core.ConfigurationUtils import load_configuration


class AnnotationConfiguration:
    """load annotation item
    An annotation item is a part of annotation configuration file;
    it is represented by JSON entry:
    """

    def __init__(self):
        """Initialize an empty annotation configuration holder.

        Example:
            >>> from thot.tools.annotation.AnnotationConfiguration import AnnotationConfiguration
            >>> AnnotationConfiguration().configuration is None
            True
        """
        self.configuration = None

    def _check_and_update(self):
        """Validate that required annotation configuration fields are present.

        Raises:
            ValueError: When configuration is missing or incomplete.

        Returns:
            ``True`` when ``data`` and ``resources-base-path`` are defined.

        Example:
            >>> from thot.tools.annotation.AnnotationConfiguration import AnnotationConfiguration
            >>> cfg = AnnotationConfiguration()
            >>> try:
            ...     cfg._check_and_update()
            ... except ValueError as err:
            ...     "Bad annotation configuration" in str(err)
            ... else:
            ...     False
            True
        """
        if not self.configuration:
            raise ValueError("Bad annotation configuration")
        if "data" not in self.configuration:
            raise ValueError("'data' field is mandatory")
        if "resources-base-path" not in self.configuration:
            raise ValueError("'resources-base-path' field is mandatory")

    def load(self, config_f, path: list = []):
        """Load annotation configuration from an open JSON file handle.

        Args:
            config_f: Open file handle containing JSON configuration.
            path: Optional nested path into the configuration document.

        Example:
            >>> import io, json
            >>> from thot.tools.annotation.AnnotationConfiguration import AnnotationConfiguration
            >>> payload = {"data": [], "resources-base-path": "/tmp"}
            >>> cfg = AnnotationConfiguration()
            >>> cfg.load(io.StringIO(json.dumps(payload)))
            >>> cfg.configuration["resources-base-path"]
            '/tmp'
        """
        self.configuration = CommonConfiguration.go_to_configuration_field(
            load_configuration(config_f), path
        )
        self._check_and_update()

    def loads(self, configuration: dict | None = None):
        """Load annotation configuration from an in-memory dict.

        Args:
            configuration: Parsed annotation JSON configuration.

        Example:
            >>> from thot.tools.annotation.AnnotationConfiguration import AnnotationConfiguration
            >>> cfg = AnnotationConfiguration()
            >>> cfg.loads({"data": [], "resources-base-path": "/tmp"})
            >>> cfg.configuration["resources-base-path"]
            '/tmp'
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.configuration = configuration
        self._check_and_update()

    def clear(self):
        """Reset the loaded configuration to ``None``.

        Example:
            >>> from thot.tools.annotation.AnnotationConfiguration import AnnotationConfiguration
            >>> cfg = AnnotationConfiguration()
            >>> cfg.loads({"data": [], "resources-base-path": "/tmp"})
            >>> cfg.clear()
            >>> cfg.configuration is None
            True
        """
        self.configuration = None
