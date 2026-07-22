"""Title: Registry

Load versioned templates from ``tkeir/configs/templates/``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from thot.compose.template_models import TemplateSpec
from thot.core.TkeirPaths import configs_dir


def templates_dir() -> Path:
    """Return the templates configuration directory.

    Example:
        >>> from thot.compose.registry import templates_dir
        >>> templates_dir().name
        'templates'
    """
    return Path(configs_dir()) / "templates"


def load_template(name: str, *, directory: Path | None = None) -> TemplateSpec:
    """Load ``<name>.yaml`` into a :class:`TemplateSpec`.

    Example:
        >>> from thot.compose.registry import load_template
        >>> spec = load_template("synthesis_note")
        >>> spec.name
        'synthesis_note'
        >>> any(s.name == "executive_summary" for s in spec.slots)
        True
    """
    root = directory or templates_dir()
    path = root / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"template not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"template must be a mapping: {path}")
    raw.setdefault("name", name)
    return TemplateSpec.model_validate(raw)


def list_template_names(*, directory: Path | None = None) -> list[str]:
    """List available template YAML stems.

    Example:
        >>> from thot.compose.registry import list_template_names
        >>> "entity_profile" in list_template_names()
        True
    """
    root = directory or templates_dir()
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.yaml"))
