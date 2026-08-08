"""Title: Agent workflows package.

YAML workflow loader (:mod:`thot.agent.workflows.loader`) plus domain
pipelines such as LLM-Wiki (:class:`WikiGeneratorWorkflow`).

``WikiGeneratorWorkflow`` is loaded lazily so importing the loader does not
pull OKF/exporter and create circular imports with ``thot.compose``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any

from thot.agent.workflows.loader import (
    list_workflow_names,
    load_workflow,
    resolve_workflow_path,
    workflow_config_dirs,
    workflows_dir,
)

__all__ = [
    "WikiGeneratorWorkflow",
    "list_workflow_names",
    "load_workflow",
    "resolve_workflow_path",
    "workflow_config_dirs",
    "workflows_dir",
]


def __getattr__(name: str) -> Any:
    """Lazy-export domain workflow classes (avoid OKF import cycles).

    Example:
        >>> from thot.agent import workflows
        >>> workflows.WikiGeneratorWorkflow.__name__
        'WikiGeneratorWorkflow'
    """
    if name == "WikiGeneratorWorkflow":
        from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow

        return WikiGeneratorWorkflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
