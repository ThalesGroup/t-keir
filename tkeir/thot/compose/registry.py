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
from thot.core.TkeirPaths import configs_dir, package_root, repo_root


def extra_template_dirs() -> list[Path]:
    """Return pack ``templates/`` dirs for the active usecase.

    Searches ``datasets/<usecase>/templates/`` then
    ``packs/<usecase>/templates/`` (container images).

    Example:
        >>> from thot.compose.registry import extra_template_dirs
        >>> isinstance(extra_template_dirs(), list)
        True
    """
    from thot.agent.orchestrator_config import resolve_usecase

    selected = resolve_usecase()
    if not selected:
        return []
    out: list[Path] = []
    for base in (
        Path(repo_root()) / "datasets",
        Path(package_root()) / "packs",
    ):
        pack = base / selected / "templates"
        if pack.is_dir():
            out.append(pack)
    return out


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

    Searches ``datasets/<usecase>/templates/`` then
    ``packs/<usecase>/templates/``, then ``tkeir/configs/templates/``.

    Example:
        >>> from thot.compose.registry import load_template
        >>> spec = load_template("synthesis_note")
        >>> spec.name
        'synthesis_note'
        >>> any(s.name == "executive_summary" for s in spec.slots)
        True
    """
    roots = (
        [directory]
        if directory is not None
        else extra_template_dirs() + [templates_dir()]
    )
    path: Path | None = None
    for root in roots:
        candidate = root / f"{name}.yaml"
        if candidate.is_file():
            path = candidate
            break
    if path is None:
        searched = ", ".join(str(root) for root in roots) or "(none)"
        raise FileNotFoundError(
            f"template not found: {name}.yaml (searched {searched})"
        )
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
    roots = (
        [directory]
        if directory is not None
        else extra_template_dirs() + [templates_dir()]
    )
    names: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        names.update(p.stem for p in root.glob("*.yaml"))
    return sorted(names)
