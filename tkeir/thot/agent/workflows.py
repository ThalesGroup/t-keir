"""Title: Workflows

Load workflow YAML specs from ``tkeir/configs/workflows/`` and dataset packs
(``datasets/<pack>/workflows/``).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from thot.agent.models import WorkflowSpec, WorkflowStep
from thot.core.TkeirPaths import configs_dir, repo_root


def workflows_dir() -> Path:
    """Return the core workflows configuration directory.

    Example:
        >>> from thot.agent.workflows import workflows_dir
        >>> workflows_dir().name
        'workflows'
    """
    return Path(configs_dir()) / "workflows"


def workflow_config_dirs() -> list[Path]:
    """Return search roots for workflow YAML (core configs + dataset packs).

    Dataset-specific workflows live under ``datasets/<pack>/workflows/``
    (for example OSINT persona flows under ``datasets/osint/workflows/``).
    Docker images may also ship packs under ``<package>/packs/<pack>/workflows/``.

    Example:
        >>> from thot.agent.workflows import workflow_config_dirs
        >>> any(p.name == "workflows" for p in workflow_config_dirs())
        True
    """
    from thot.core.TkeirPaths import package_root

    roots: list[Path] = [workflows_dir()]
    for base in (
        Path(repo_root()) / "datasets",
        Path(package_root()) / "packs",
    ):
        if not base.is_dir():
            continue
        for pack in sorted(base.iterdir()):
            if not pack.is_dir() or pack.name.startswith("."):
                continue
            candidate = pack / "workflows"
            if candidate.is_dir():
                roots.append(candidate)
    extra = os.getenv("TKEIR_WORKFLOW_CONFIG_DIRS", "").strip()
    if extra:
        for part in extra.split(os.pathsep):
            path = Path(part).expanduser()
            if path.is_dir():
                roots.append(path)
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        key = root.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def resolve_workflow_path(name: str, *, directory: Path | None = None) -> Path:
    """Resolve ``<name>.yaml`` across workflow config roots.

    Args:
        name: Workflow stem (without ``.yaml``).
        directory: Optional single root; raises if missing.

    Returns:
        Path to the workflow YAML file.

    Raises:
        FileNotFoundError: When no matching spec exists.

    Example:
        >>> from thot.agent.workflows import resolve_workflow_path
        >>> resolve_workflow_path("content_brief").name
        'content_brief.yaml'
    """
    if directory is not None:
        path = Path(directory) / f"{name}.yaml"
        if path.is_file():
            return path
        raise FileNotFoundError(f"workflow not found: {path}")
    for root in workflow_config_dirs():
        path = root / f"{name}.yaml"
        if path.is_file():
            return path
    searched = ", ".join(str(p) for p in workflow_config_dirs())
    raise FileNotFoundError(
        f"workflow not found: {name}.yaml (searched: {searched})"
    )


def load_workflow(name: str, *, directory: Path | None = None) -> WorkflowSpec:
    """Load ``<name>.yaml`` into a :class:`WorkflowSpec`.

    Example:
        >>> from thot.agent.workflows import load_workflow
        >>> wf = load_workflow("content_brief")
        >>> wf.name
        'content_brief'
        >>> len(wf.steps) >= 2
        True
    """
    path = resolve_workflow_path(name, directory=directory)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"workflow must be a mapping: {path}")
    raw.setdefault("name", name)
    steps_raw = raw.get("steps") or []
    steps: list[WorkflowStep] = []
    for index, item in enumerate(steps_raw):
        if not isinstance(item, dict):
            raise ValueError(f"workflow step {index} must be a mapping")
        step = dict(item)
        step.setdefault(
            "id",
            step.get("agent") or step.get("builtin") or f"step-{index}",
        )
        if "compose" in step and isinstance(step["compose"], dict):
            compose = dict(step["compose"])
            compose.setdefault("id", step.get("id") or "compose")
            if "template" in step and "template" not in compose:
                compose["template"] = step["template"]
            step["compose"] = compose
            step.setdefault("agent", None)
        steps.append(WorkflowStep.model_validate(step))
    raw["steps"] = [s.model_dump() for s in steps]
    return WorkflowSpec.model_validate(raw)


def list_workflow_names(*, directory: Path | None = None) -> list[str]:
    """List available workflow YAML stems (core + dataset packs).

    Example:
        >>> from thot.agent.workflows import list_workflow_names
        >>> "content_brief" in list_workflow_names()
        True
    """
    if directory is not None:
        root = Path(directory)
        if not root.is_dir():
            return []
        return sorted(p.stem for p in root.glob("*.yaml"))
    names: set[str] = set()
    for root in workflow_config_dirs():
        if not root.is_dir():
            continue
        names.update(p.stem for p in root.glob("*.yaml"))
    return sorted(names)
