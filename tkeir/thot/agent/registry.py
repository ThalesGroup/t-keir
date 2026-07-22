"""Title: Registry

Load and validate agent YAML specs from ``tkeir/configs/agents/``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from thot.agent.models import AgentSpec
from thot.core.TkeirPaths import configs_dir

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), match.group(0))

    return _ENV_PATTERN.sub(repl, value)


def agents_dir() -> Path:
    """Return the agents configuration directory.

    Example:
        >>> from thot.agent.registry import agents_dir
        >>> agents_dir().name
        'agents'
    """
    return Path(configs_dir()) / "agents"


def load_agent_spec(name: str, *, directory: Path | None = None) -> AgentSpec:
    """Load ``<name>.yaml`` into an :class:`AgentSpec`.

    Example:
        >>> from thot.agent.registry import load_agent_spec
        >>> spec = load_agent_spec("researcher")
        >>> spec.name
        'researcher'
        >>> "search" in spec.tools
        True
    """
    root = directory or agents_dir()
    path = root / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"agent spec not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"agent spec must be a mapping: {path}")
    if isinstance(raw.get("system_prompt"), str):
        raw["system_prompt"] = _expand_env(raw["system_prompt"])
    if isinstance(raw.get("model"), str):
        raw["model"] = _expand_env(raw["model"])
    raw.setdefault("name", name)
    return AgentSpec.model_validate(raw)


def list_agent_names(*, directory: Path | None = None) -> list[str]:
    """List available agent YAML stems.

    Example:
        >>> from thot.agent.registry import list_agent_names
        >>> "researcher" in list_agent_names()
        True
    """
    root = directory or agents_dir()
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.yaml"))
