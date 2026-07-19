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
    """Helpers for loading and normalizing service configuration."""

    @staticmethod
    def _replace_string_by_type(configuration: dict, assoc_field: str) -> dict:
        """Replace a string field with a typed value when possible.

        Args:
            configuration: Configuration dictionary updated in place.
            assoc_field: Field name to coerce.

        Returns:
            Updated configuration dictionary.

        Example:
            >>> from thot.core.CommonConfiguration import CommonConfiguration
            >>> cfg = {"port": "8080"}
            >>> CommonConfiguration._replace_string_by_type(cfg, "port")
            {'port': 8080}
        """
        if isinstance(configuration[assoc_field], str):
            if is_numeric(configuration[assoc_field]):
                if "." in configuration[assoc_field]:
                    configuration[assoc_field] = float(
                        configuration[assoc_field]
                    )
                else:
                    configuration[assoc_field] = int(
                        configuration[assoc_field]
                    )
            elif configuration[assoc_field].lower() == "false":
                configuration[assoc_field] = False
            elif configuration[assoc_field].lower() == "true":
                configuration[assoc_field] = True

        return configuration

    @staticmethod
    def affect_associated_environment(configuration: dict):
        """Override configuration fields from associated environment variables.

        Args:
            configuration: Configuration containing an
                ``associate-environment`` mapping.

        Example:
            >>> import os
            >>> from thot.core.CommonConfiguration import CommonConfiguration
            >>> os.environ["TEST_HOST"] = "127.0.0.1"
            >>> cfg = {
            ...     "host": "0.0.0.0",
            ...     "associate-environment": {"host": "TEST_HOST"},
            ... }
            >>> CommonConfiguration.affect_associated_environment(cfg)
            >>> cfg["host"]
            '127.0.0.1'
        """
        if "associate-environment" in configuration:
            for assoc_field in configuration["associate-environment"]:
                if assoc_field in configuration:
                    configuration[assoc_field] = os.getenv(
                        configuration["associate-environment"][assoc_field],
                        configuration[assoc_field],
                    )
                    configuration = (
                        CommonConfiguration._replace_string_by_type(
                            configuration, assoc_field
                        )
                    )

    @staticmethod
    def go_to_configuration_field(
        configuration: dict = dict(),
        path: list = [],
        keep_last_field: bool = True,
    ):
        """Extract a nested configuration subtree by path.

        Args:
            configuration: Initial configuration dictionary.
            path: Sequence of keys describing the target subtree.
            keep_last_field: When ``True``, wrap the result with the final key.

        Raises:
            ValueError: If any path segment is missing.

        Returns:
            Target configuration subtree.

        Example:
            >>> from thot.core.CommonConfiguration import CommonConfiguration
            >>> cfg = {"network": {"host": "localhost"}}
            >>> CommonConfiguration.go_to_configuration_field(
            ...     cfg, ["network", "host"]
            ... )
            {'host': 'localhost'}
        """
        decay_configuration = deepcopy(configuration)
        for field in path:
            if field in decay_configuration:
                decay_configuration = decay_configuration[field]
            else:
                raise ValueError(
                    "Bad path in " + str(path) + " ' stop at '" + field + "'."
                )
        if keep_last_field and (len(path) > 0):
            decay_configuration = {path[-1]: decay_configuration}

        return decay_configuration
