"""Title: Tkeir Paths

Resolve bundled T-KEIR configuration and resource paths.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os

_PATH_KEYS = ("resources-base-path",)


def package_root() -> str:
    """Return the absolute path to the ``tkeir`` package root.

    Returns:
        Absolute directory containing ``thot/``, ``configs/``, and ``resources/``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import package_root
        >>> root = package_root()
        >>> os.path.isdir(os.path.join(root, "thot"))
        True
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def configs_dir() -> str:
    """Return the bundled configuration directory.

    Returns:
        Absolute path to ``tkeir/configs``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import configs_dir
        >>> os.path.isfile(os.path.join(configs_dir(), "pipeline.yaml"))
        True
    """
    return os.path.join(package_root(), "configs")


def resources_dir(language: str = "en") -> str:
    """Return tokenizer resources for a language.

    Args:
        language: ISO language code (for example ``"en"`` or ``"fr"``).

    Returns:
        Absolute path to ``resources/modeling/tokenizer/<language>``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import resources_dir
        >>> os.path.isdir(resources_dir("en"))
        True
    """
    return os.path.join(
        package_root(), "resources", "modeling", "tokenizer", language
    )


def ontologies_dir() -> str:
    """Return the bundled generic ontologies directory.

    Application / corpus ontologies must not live here — upload them at
    ingest time. Only product-neutral reference graphs belong under
    ``resources/ontologies/``.

    Returns:
        Absolute path to ``resources/ontologies``.

    Example:
        >>> from thot.core.TkeirPaths import ontologies_dir
        >>> ontologies_dir().endswith("resources/ontologies")
        True
    """
    return os.path.join(package_root(), "resources", "ontologies")


def repo_root() -> str:
    """Return the repository root (parent of the ``tkeir`` package).

    Returns:
        Absolute path to the git repository root.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import repo_root, vespa_dir
        >>> os.path.isdir(vespa_dir())
        True
        >>> vespa_dir().startswith(repo_root())
        True
    """
    return os.path.abspath(os.path.join(package_root(), ".."))


def vespa_dir() -> str:
    """Return the Vespa deployment directory.

    Returns:
        Absolute path to ``vespa/`` at the repository root.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import vespa_dir
        >>> os.path.isdir(vespa_dir())
        True
        >>> os.path.isfile(os.path.join(vespa_dir(), "start_vespa.sh"))
        True
    """
    return os.path.join(repo_root(), "vespa")


def rag_prompts_path() -> str:
    """Return the RAG prompt template file used by the search API.

    Returns:
        Absolute path to ``configs/rag-prompts.yaml``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import rag_prompts_path
        >>> os.path.isfile(rag_prompts_path())
        True
    """
    return os.path.join(configs_dir(), "rag-prompts.yaml")


def rag_config_path() -> str:
    """Return the RAG runtime configuration file.

    Returns:
        Absolute path to ``configs/rag.yaml``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import rag_config_path
        >>> os.path.isfile(rag_config_path())
        True
    """
    return os.path.join(configs_dir(), "rag.yaml")


def docs_dir() -> str:
    """Return the MkDocs documentation directory.

    Returns:
        Absolute path to ``tkeir/docs``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import docs_dir
        >>> os.path.isdir(docs_dir())
        True
    """
    return os.path.join(package_root(), "docs")


def evaluation_report_path() -> str:
    """Return the BEIR evaluation report path under documentation.

    Returns:
        Absolute path to ``docs/evaluation_report.md``.

    Example:
        >>> from thot.core.TkeirPaths import evaluation_report_path
        >>> evaluation_report_path().endswith("docs/evaluation_report.md")
        True
    """
    return os.path.join(docs_dir(), "evaluation_report.md")


def resolve_path(path: str) -> str:
    """Expand a path relative to the ``tkeir`` package root.

    Args:
        path: Relative or absolute filesystem path.

    Returns:
        Absolute path when ``path`` is relative; unchanged when already absolute.

    Example:
        >>> from thot.core.TkeirPaths import resolve_path
        >>> resolve_path("configs/pipeline.yaml").endswith("configs/pipeline.yaml")
        True
    """
    if not path or os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(package_root(), path))


def resolve_tkeir_paths(configuration):
    """Recursively resolve known path fields in a loaded configuration dict.

    Args:
        configuration: Nested dict or list loaded from a JSON config file.

    Returns:
        The same object with ``resources-base-path`` entries expanded in place.

    Example:
        >>> from thot.core.TkeirPaths import resolve_tkeir_paths
        >>> cfg = {"segmenters": [{"resources-base-path": "resources/modeling/tokenizer/en"}]}
        >>> resolved = resolve_tkeir_paths(cfg)
        >>> resolved["segmenters"][0]["resources-base-path"].endswith("tokenizer/en")
        True
    """
    if isinstance(configuration, dict):
        for key, value in configuration.items():
            if key in _PATH_KEYS and isinstance(value, str):
                configuration[key] = resolve_path(value)
            else:
                resolve_tkeir_paths(value)
    elif isinstance(configuration, list):
        for item in configuration:
            resolve_tkeir_paths(item)
    return configuration


def effective_resources_path(
    resource_path: str | None, language: str = "en"
) -> str | None:
    """Return a usable resources directory, falling back to bundled defaults.

    Args:
        resource_path: Configured resources path, or ``None``.
        language: Fallback language when the configured path is missing.

    Returns:
        Existing directory path, bundled default when available, or ``resource_path``.

    Example:
        >>> from thot.core.TkeirPaths import effective_resources_path, resources_dir
        >>> effective_resources_path(None, "en") == resources_dir("en")
        True
    """
    if resource_path and os.path.isdir(resource_path):
        return resource_path
    candidate = resources_dir(language)
    if os.path.isdir(candidate):
        return candidate
    return resource_path
