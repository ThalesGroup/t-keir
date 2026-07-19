"""Load workflow YAML specs from ``tkeir/configs/workflows/``."""

from __future__ import annotations

from pathlib import Path

import yaml

from thot.agent.models import WorkflowSpec, WorkflowStep
from thot.core.TkeirPaths import configs_dir


def workflows_dir() -> Path:
    """Return the workflows configuration directory.

    Example:
        >>> from thot.agent.workflows import workflows_dir
        >>> workflows_dir().name
        'workflows'
    """
    return Path(configs_dir()) / "workflows"


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
    root = directory or workflows_dir()
    path = root / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"workflow not found: {path}")
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
        step.setdefault("id", step.get("agent") or f"step-{index}")
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
    """List available workflow YAML stems.

    Example:
        >>> from thot.agent.workflows import list_workflow_names
        >>> "content_brief" in list_workflow_names()
        True
    """
    root = directory or workflows_dir()
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.yaml"))
