# -*- coding: utf-8 -*-
"""Shared helpers for loading service configuration files."""

import json

from thot.core.TkeirPaths import resolve_tkeir_paths


def load_json_configuration(config_f):
    """Load JSON configuration and resolve bundled resource paths.

    Args:
        config_f: File-like object containing JSON configuration.

    Returns:
        Parsed configuration with ``resources-base-path`` entries resolved.

    Example:
        >>> from io import StringIO
        >>> import json
        >>> load_json_configuration(StringIO(json.dumps({"logger": {}})))
        {'logger': {}}
    """
    configuration = json.load(config_f)
    return resolve_tkeir_paths(configuration)
