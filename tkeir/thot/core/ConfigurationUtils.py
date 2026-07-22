"""Title: Configuration Utils

Shared helpers for loading service configuration files.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import os
from typing import Any, TextIO

import yaml

from thot.core.TkeirPaths import resolve_tkeir_paths


def _parse_configuration_text(text: str, *, source_name: str = "") -> dict:
    """Parse configuration text as YAML or JSON.

    YAML is preferred. JSON is accepted for backward compatibility
    (``*.json`` files and JSON-compatible documents).

    Args:
        text: Raw configuration contents.
        source_name: Optional path/name used for format hints and errors.

    Returns:
        Parsed configuration dictionary.

    Raises:
        ValueError: When the content is not a mapping.

    Example:
        >>> _parse_configuration_text("logger:\\n  logging-level: info")
        {'logger': {'logging-level': 'info'}}
    """
    name = (source_name or "").lower()
    data: Any
    if name.endswith(".json"):
        data = json.loads(text)
    else:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            data = json.loads(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Configuration root must be a mapping (got {type(data).__name__})"
            + (f" in {source_name}" if source_name else "")
        )
    return data


def load_configuration(config_f: TextIO) -> dict:
    """Load YAML/JSON configuration and resolve bundled resource paths.

    Args:
        config_f: File-like object containing YAML or JSON configuration.

    Returns:
        Parsed configuration with ``resources-base-path`` entries resolved.

    Example:
        >>> from io import StringIO
        >>> load_configuration(StringIO("logger: {}\\n"))
        {'logger': {}}
    """
    text = config_f.read()
    source_name = getattr(config_f, "name", "") or ""
    configuration = _parse_configuration_text(text, source_name=source_name)
    return resolve_tkeir_paths(configuration)


def load_json_configuration(config_f: TextIO) -> dict:
    """Backward-compatible alias for :func:`load_configuration`.

    Example:
        >>> from io import StringIO
        >>> load_json_configuration(StringIO('{"logger": {}}'))
        {'logger': {}}
    """
    return load_configuration(config_f)


def resolve_config_path(path: str, *, search_dir: str | None = None) -> str:
    """Resolve a config path, preferring ``.yaml`` / ``.yml`` over ``.json``.

    Args:
        path: Absolute or relative configuration path / basename.
        search_dir: Directory used when ``path`` is not absolute.

    Returns:
        Existing filesystem path.

    Raises:
        FileNotFoundError: When no matching config file exists.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import configs_dir
        >>> resolve_config_path("pipeline.yaml", search_dir=configs_dir()).endswith(
        ...     "pipeline.yaml"
        ... )
        True
    """
    candidates: list[str] = []
    if os.path.isabs(path):
        candidates.append(path)
    elif search_dir:
        candidates.append(os.path.join(search_dir, path))
        candidates.append(os.path.join(search_dir, os.path.basename(path)))
    else:
        candidates.append(path)

    expanded: list[str] = []
    for candidate in candidates:
        expanded.append(candidate)
        root, ext = os.path.splitext(candidate)
        if ext.lower() in {".yaml", ".yml", ".json"}:
            for alt in (".yaml", ".yml", ".json"):
                if alt.lower() == ext.lower():
                    continue
                expanded.append(root + alt)
        else:
            expanded.extend(
                [candidate + ".yaml", candidate + ".yml", candidate + ".json"]
            )

    seen: set[str] = set()
    for candidate in expanded:
        if candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(f"Configuration file not found: {path}")
